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

# Add this line near the top of your script
APP_ENV = os.getenv("ENVIRONMENT", "development").strip()

# Change the API_BASE URL definition
if APP_ENV == "production":
    API_BASE = "https://quickbooks.api.intuit.com/v3/company"
else:
    API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"

# --- Configuration ---
CLIENT_ID = os.getenv("INTUIT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("INTUIT_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl").strip()
TOKENS_PATH = "tokens.json"

# Intuit OAuth endpoints
AUTH_BASE = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPE = "com.intuit.quickbooks.accounting"

# --- Helper Functions ---
def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return None
    with open(TOKENS_PATH, "r", encoding="utf-8") as f:
        tokens = json.load(f)
        # Check if the access token is expired based on the saved expiration time
        if "expires_at" in tokens and time.time() > tokens["expires_at"]:
            print("Access token expired based on timestamp.")
            return None
        return tokens
        
def save_tokens(tokens):
    # Quickbooks access tokens are valid for 1 hour (3600 seconds)
    tokens["expires_at"] = time.time() + tokens["expires_in"] - 60  # Subtract 60s buffer
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

def refresh_tokens(refresh_token, realm_id):
    auth = (CLIENT_ID, CLIENT_SECRET)
    headers = {"Accept": "application/json"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    print("🔄 Refreshing access token...")
    r = requests.post(TOKEN_URL, auth=auth, data=data, headers=headers, timeout=30)
    r.raise_for_status()
    new_tokens = r.json()
    new_tokens["realmId"] = realm_id # Preserve realmId
    save_tokens(new_tokens)
    return new_tokens

def get_all_transactions(access_token, realm_id):
    """
    Fetches all transactions from QuickBooks by querying individual transaction types.
    Handles pagination to get all records for each type.
    """
    print("⏳ Fetching all transactions from QuickBooks by type...")
    base_url = f"{API_BASE}/{realm_id}/query"
    
    # List of transaction types to query
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
                params = {
                    "query": query,
                    "minorversion": "70"
                }
                r = requests.get(base_url, headers=headers, params=params, timeout=120)

                if r.status_code in [401, 403]:
                    raise requests.exceptions.HTTPError("Token expired or invalid.", response=r)
                
                # Check for other errors before attempting to process JSON
                r.raise_for_status()
                
                data = r.json()
                query_response = data.get("QueryResponse", {})
                
                # Get transactions for the current type
                transactions = query_response.get(transaction_type, [])
                
                # Add a 'Type' key to each transaction dictionary for later identification
                for txn in transactions:
                    txn['Type'] = transaction_type
                
                all_transactions.extend(transactions)
                
                print(f"     -> Retrieved {len(transactions)} {transaction_type} records.")

                if len(transactions) < max_results:
                    break
                else:
                    start_position += max_results
                    
            except requests.exceptions.HTTPError as e:
                # Some entities might not exist or the user might not have access
                if e.response.status_code == 400 and "Entity" in e.response.text:
                    print(f"     -> No data found for {transaction_type}, skipping.")
                    break
                else:
                    print(f"❌ An error occurred while fetching {transaction_type}: {e}")
                    print(f"Response Text: {e.response.text}")
                    raise
            except Exception as e:
                print(f"❌ An unexpected error occurred: {e}")
                return None
    
    print(f"\n✅ Finished fetching all transactions. Total records retrieved: {len(all_transactions)}")
    return all_transactions



def process_and_save_transactions(transactions):
    """
    Processes the raw transaction data and saves it to a CSV file on the desktop.
    This function flattens the nested JSON structure.
    """
    if not transactions:
        print("No transactions to save.")
        return
    
    # Check for empty Line lists and insert a dummy value
    # This ensures json_normalize doesn't fail on empty line items
    for txn in transactions:
        if not txn.get('Line'):
            txn['Line'] = [{}]

    # Flatten the nested JSON data, correcting for missing keys and conflicting names
    normalized_data = pd.json_normalize(transactions, 
                                        record_path=['Line'], 
                                        meta=[
                                            'Id', 'SyncToken', ['MetaData', 'CreateTime'], ['MetaData', 'LastUpdatedTime'], 
                                            'DocNumber', 'TxnDate', 'TotalAmt', ['CurrencyRef', 'value'], ['CurrencyRef', 'name'], 
                                            ['CustomerRef', 'value'], ['CustomerRef', 'name'], 'PaymentRefNum', 'PrivateNote',
                                            ['DepositToAccountRef', 'name'], ['DepositToAccountRef', 'value'], 'Type'
                                        ], 
                                        sep='_', 
                                        errors='ignore',
                                        meta_prefix='txn_')
                                        
    # Clean up column names and rename for clarity
    normalized_data.rename(columns={
        'txn_Id': 'TransactionId',  # This key now has a prefix
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
    
    # Save to CSV
    desktop_path = Path.home() / "Desktop" / "AllTransactions.csv"
    normalized_data.to_csv(desktop_path, index=False)
    print(f"✅ All transaction data saved to: {desktop_path}")
    print(f"Total rows in CSV: {len(normalized_data)}")

# The rest of your script (the main execution block) remains the same.


def get_tokens_from_user_input():
    # 1. Construct the authorization URL
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": "xyz123",
    }
    auth_url = f"{AUTH_BASE}?{urllib.parse.urlencode(params)}"
    
    # 2. Instruct the user to open the URL and paste the callback result
    print("-" * 50)
    print("📋 Manual Authentication Required")
    print("1. Open this URL in your browser:")
    print(auth_url)
    print("\n2. Authorize the app.")
    print("3. You will be redirected to a blank page or an error page.")
    print("4. Copy the entire URL from your browser's address bar and paste it here.")
    print("-" * 50)
    
    redirect_url = input("Paste the full callback URL here and press Enter: ")
    
    # 3. Parse the URL to get the code and realmId
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
            print("❌ 'code' or 'realmId' not found in the URL. Please ensure you copied the full URL.")
            return None
    except Exception as e:
        print(f"❌ Failed to parse URL: {e}")
        return None
    
    # 4. Exchange the code for tokens
    print("\n✅ URL parsed successfully. Exchanging code for tokens...")
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

# --- Main Logic ---
if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("⚠️ Missing INTUIT_CLIENT_ID or INTUIT_CLIENT_SECRET in .env")
        exit()

    tokens = load_tokens()

    if not tokens:
        print("Tokens not found or expired. Starting manual OAuth flow...")
        tokens = get_tokens_from_user_input()
        if not tokens:
            print("❌ Authentication failed. Exiting.")
            exit()
    
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    realm_id = tokens["realmId"]

    try:
        # Step 1: Get all transactions
        all_transactions = get_all_transactions(access_token, realm_id)
        if all_transactions is not None:
            # Step 2: Process and save them to a CSV
            process_and_save_transactions(all_transactions)
        else:
            print("❌ No transactions were retrieved.")

    except requests.exceptions.HTTPError as e:
        if "Token expired" in str(e):
            print("Token expired. Attempting to refresh...")
            try:
                new_tokens = refresh_tokens(refresh_token, realm_id)
                access_token = new_tokens["access_token"]
                
                # Retry the main logic with the new token
                all_transactions = get_all_transactions(access_token, realm_id)
                if all_transactions is not None:
                    process_and_save_transactions(all_transactions)
                else:
                    print("❌ No transactions were retrieved on retry.")
            except requests.exceptions.RequestException as refresh_e:
                print(f"❌ Failed to refresh tokens: {refresh_e}")
                print("Your refresh token may have expired. Please re-run the script to re-authenticate.")
                exit()
        else:
            print(f"❌ An error occurred: {e}")
            print(f"Response Text: {e.response.text}")
            exit()
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        exit()