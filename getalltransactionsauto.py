import os
import json
import urllib.parse
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

APP_ENV = os.getenv("ENVIRONMENT", "development").strip()

if APP_ENV == "production":
    API_BASE = "https://quickbooks.api.intuit.com/v3/company"
else:
    API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"

# --- Configuration ---
CLIENT_ID = os.getenv("INTUIT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("INTUIT_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl").strip()
TOKENS_PATH = "tokens.json"

AUTH_BASE = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPE = "com.intuit.quickbooks.accounting"

# --- Token Management ---
def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return None
    with open(TOKENS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tokens(tokens):
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 60
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

def is_access_token_expired(tokens):
    return time.time() > tokens.get("expires_at", 0)

def refresh_tokens(refresh_token, realm_id):
    auth = (CLIENT_ID, CLIENT_SECRET)
    headers = {"Accept": "application/json"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    print("🔄 Refreshing access token...")
    r = requests.post(TOKEN_URL, auth=auth, data=data, headers=headers, timeout=30)
    
    if r.status_code != 200:
        print(f"❌ Refresh failed (HTTP {r.status_code}): {r.text}")
        return None
    
    new_tokens = r.json()
    new_tokens["realmId"] = realm_id
    save_tokens(new_tokens)
    print("✅ Access token refreshed successfully.")
    return new_tokens

def get_valid_tokens():
    """
    Returns a valid access token, refreshing automatically if needed.
    Only prompts for manual auth if no tokens.json exists at all.
    """
    tokens = load_tokens()

    # No tokens at all — first-time setup
    if not tokens:
        print("⚠️  No tokens found. One-time manual authentication required.")
        tokens = get_tokens_from_user_input()
        if not tokens:
            return None

    # Access token expired — refresh silently using the refresh token
    elif is_access_token_expired(tokens):
        tokens = refresh_tokens(tokens["refresh_token"], tokens["realmId"])
        if not tokens:
            print("\n⚠️  Refresh token has expired (this happens every ~100 days).")
            print("Re-authenticating...")
            tokens = get_tokens_from_user_input()
            if not tokens:
                return None

    return tokens


# --- QuickBooks API ---
def get_all_transactions(access_token, realm_id):
    print("⏳ Fetching all transactions from QuickBooks...")
    base_url = f"{API_BASE}/{realm_id}/query"

    transaction_types = [
        "Invoice", "Payment", "Deposit", "CreditMemo", "JournalEntry",
        "Bill", "VendorCredit", "Purchase"
    ]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    all_transactions = []

    for transaction_type in transaction_types:
        print(f"  -> Fetching all {transaction_type} records...")
        start_position = 1
        max_results = 1000

        while True:
            query = f"SELECT * FROM {transaction_type} STARTPOSITION {start_position} MAXRESULTS {max_results}"

            try:
                params = {"query": query, "minorversion": "70"}
                r = requests.get(base_url, headers=headers, params=params, timeout=120)

                if r.status_code in [401, 403]:
                    raise requests.exceptions.HTTPError("Token expired or invalid.", response=r)

                r.raise_for_status()

                data = r.json()
                query_response = data.get("QueryResponse", {})
                transactions = query_response.get(transaction_type, [])

                for txn in transactions:
                    txn['Type'] = transaction_type

                all_transactions.extend(transactions)
                print(f"     -> Retrieved {len(transactions)} {transaction_type} records.")

                if len(transactions) < max_results:
                    break
                else:
                    start_position += max_results

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400 and "Entity" in e.response.text:
                    print(f"     -> No data found for {transaction_type}, skipping.")
                    break
                else:
                    print(f"❌ Error fetching {transaction_type}: {e}")
                    print(f"Response: {e.response.text}")
                    raise
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                return None

    print(f"\n✅ Total records retrieved: {len(all_transactions)}")
    return all_transactions


def process_and_save_transactions(transactions):
    if not transactions:
        print("No transactions to save.")
        return

    for txn in transactions:
        if not txn.get('Line'):
            txn['Line'] = [{}]

    normalized_data = pd.json_normalize(
        transactions,
        record_path=['Line'],
        meta=[
            'Id', 'SyncToken', ['MetaData', 'CreateTime'], ['MetaData', 'LastUpdatedTime'],
            'DocNumber', 'TxnDate', 'TotalAmt', ['CurrencyRef', 'value'], ['CurrencyRef', 'name'],
            ['CustomerRef', 'value'], ['CustomerRef', 'name'], 'PaymentRefNum', 'PrivateNote',
            ['DepositToAccountRef', 'name'], ['DepositToAccountRef', 'value'], 'Type'
        ],
        sep='_',
        errors='ignore',
        meta_prefix='txn_'
    )

    normalized_data.rename(columns={
        'txn_Id': 'TransactionId',
        'txn_SyncToken': 'SyncToken',
        'txn_MetaData_CreateTime': 'CreateTime',
        'txn_MetaData_LastUpdatedTime': 'LastUpdatedTime',
        'txn_TotalAmt': 'TotalAmount',
        'txn_CurrencyRef_value': 'Currency',
        'txn_CustomerRef_value': 'CustomerId',
        'txn_CustomerRef_name': 'CustomerName',
        'txn_PrivateNote': 'Notes',
        'txn_DepositToAccountRef_name': 'DepositToAccount',
        'txn_TxnDate': 'TransactionDate',
        'LineNum': 'LineNumber',
        'Description': 'LineDescription',
        'Amount': 'LineAmount',
        'SalesItemLineDetail_UnitPrice': 'UnitPrice',
        'SalesItemLineDetail_Qty': 'Quantity',
        'SalesItemLineDetail_ItemRef_name': 'ItemName',
        'SalesItemLineDetail_ItemRef_value': 'ItemId',
        'Line_DetailType': 'DetailType',
        'AccountBasedExpenseLineDetail_AccountRef_name': 'ExpenseAccount',
        'AccountBasedExpenseLineDetail_AccountRef_value': 'ExpenseAccountId'
    }, inplace=True)

    desktop_path = Path.home() / "Desktop" / "AllTransactions.csv"
    normalized_data.to_csv(desktop_path, index=False)
    print(f"✅ Saved to: {desktop_path}  ({len(normalized_data)} rows)")


# --- Manual Auth (first-time only) ---
def get_tokens_from_user_input():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": "xyz123",
    }
    auth_url = f"{AUTH_BASE}?{urllib.parse.urlencode(params)}"

    print("-" * 50)
    print("📋 One-Time Authentication Required")
    print("This only needs to be done once every ~100 days.\n")
    print("1. Open this URL in your browser:")
    print(auth_url)
    print("\n2. Authorize the app.")
    print("3. Copy the full redirect URL from your browser's address bar.")
    print("-" * 50)

    redirect_url = input("Paste the full callback URL here and press Enter: ")

    try:
        parsed_url = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        code = query_params.get("code", [None])[0]
        realm_id = query_params.get("realmId", [None])[0]
        state = query_params.get("state", [None])[0]
        error = query_params.get("error", [None])[0]

        if error:
            print(f"❌ Authorization error: {error}")
            return None
        if state != "xyz123":
            print("❌ Invalid state parameter.")
            return None
        if not code or not realm_id:
            print("❌ 'code' or 'realmId' not found. Please copy the full URL.")
            return None
    except Exception as e:
        print(f"❌ Failed to parse URL: {e}")
        return None

    print("\n✅ Exchanging code for tokens...")
    auth = (CLIENT_ID, CLIENT_SECRET)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    try:
        r = requests.post(TOKEN_URL, auth=auth, data=data, timeout=30)
        r.raise_for_status()
        tokens = r.json()
        tokens["realmId"] = realm_id
        save_tokens(tokens)
        print("✅ Tokens saved to tokens.json.")
        return tokens
    except requests.exceptions.RequestException as e:
        print(f"❌ Token exchange failed: {e}")
        return None


# --- Main ---
if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("⚠️  Missing INTUIT_CLIENT_ID or INTUIT_CLIENT_SECRET in .env")
        exit()

    # This handles everything: first-time auth, silent refresh, expired refresh token
    tokens = get_valid_tokens()
    if not tokens:
        print("❌ Authentication failed. Exiting.")
        exit()

    all_transactions = get_all_transactions(tokens["access_token"], tokens["realmId"])
    if all_transactions:
        process_and_save_transactions(all_transactions)
    else:
        print("❌ No transactions retrieved.")