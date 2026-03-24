import os
import json
import urllib.parse
import requests
import pandas as pd
import numpy as np
import snowflake.connector as sf
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
import time

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

APP_ENV = os.getenv("ENVIRONMENT", "development").strip()
API_BASE = (
    "https://quickbooks.api.intuit.com/v3/company" if APP_ENV == "production"
    else "https://sandbox-quickbooks.api.intuit.com/v3/company"
)

CLIENT_ID     = os.getenv("INTUIT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("INTUIT_CLIENT_SECRET", "").strip()
REDIRECT_URI  = os.getenv("REDIRECT_URI", "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl").strip()
TOKENS_PATH   = "tokens.json"

AUTH_BASE = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPE     = "com.intuit.quickbooks.accounting"

# ============================================================
# SNOWFLAKE CONFIG — set via environment or .env (never commit secrets)
# ============================================================

SF_USER      = os.getenv("SF_USER", "").strip()
SF_PASSWORD  = os.getenv("SF_PASSWORD", "").strip()
SF_ACCOUNT   = os.getenv("SF_ACCOUNT", "").strip()
SF_WAREHOUSE = os.getenv("SF_WAREHOUSE", "").strip()
SF_DATABASE  = os.getenv("SF_DATABASE", "").strip()
SF_SCHEMA    = os.getenv("SF_SCHEMA", "").strip()


def get_snowflake_conn():
    missing = [
        name
        for name, val in (
            ("SF_USER", SF_USER),
            ("SF_PASSWORD", SF_PASSWORD),
            ("SF_ACCOUNT", SF_ACCOUNT),
            ("SF_WAREHOUSE", SF_WAREHOUSE),
            ("SF_DATABASE", SF_DATABASE),
            ("SF_SCHEMA", SF_SCHEMA),
        )
        if not val
    ]
    if missing:
        raise ValueError(
            "Missing Snowflake configuration: " + ", ".join(missing) + ". "
            "Set these in your environment or a local .env file (see .env.example)."
        )
    return sf.connect(
        user=SF_USER, password=SF_PASSWORD, account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE, database=SF_DATABASE, schema=SF_SCHEMA
    )

# ============================================================
# ACCOUNT → BUCKET MAPPING
# ============================================================

ACCOUNT_TO_GROUP = {
    '1099 Contractor': 'overhead_pure',
    'Accounts Payable (A/P)': 'overhead_pure',
    'Advertising': 'marketing',
    'Advertising & Marketing': 'marketing',
    'Advertising & Marketing:Advertising (deleted)': 'marketing',
    'Advertising & Marketing:Marketing (deleted)': 'marketing',
    'Airfare': 'overhead_pure',
    'Bank Service Charges': 'overhead_pure',
    'Brex Credit Card': 'overhead_pure',
    'Business Licenses & Permits': 'overhead_pure',
    'Business Tax & Registration Fees': 'overhead_pure',
    'Charitable Donations': 'overhead_pure',
    'Commission Income': 'income',
    'Computer Equipment': 'overhead_pure',
    'Consulting & Accounting': 'overhead_pure',
    'Contract Labor:1099 Contractor': 'overhead_pure',
    'Cost of Goods Sold:Lead Acquisition (3rd Party)': 'marketing',
    'Cost of Goods Sold:Lead Acquisition (Internal)': 'marketing',
    'Credit Card Rewards': 'overhead_pure',
    'Discounts/Refunds': 'overhead_pure',
    'Dues & Subscriptions': 'overhead_pure',
    'Education & Training': 'overhead_pure',
    'Employee Advances': 'overhead_salary',
    'Employer Taxes': 'overhead_salary',
    'Franchise Tax': 'overhead_pure',
    'Guaranteed Payments - Nic West': 'overhead_salary',
    'Guaranteed Payments - Rootfin LLC': 'overhead_salary',
    'Hotels': 'overhead_pure',
    'Insurance': 'overhead_pure',
    'Insurance CRM': 'income',
    'Intangible Asset - NoExam.com': 'overhead_pure',
    'Interest Expense - Home Bank Loan': 'overhead_pure',
    'Leads Income': 'income',
    'Leasehold Improvements': 'overhead_pure',
    'Legal & Professional Fees:Professional Fees': 'overhead_pure',
    'Legal Fees': 'overhead_pure',
    'Loan Payable - First Home Bank': 'overhead_pure',
    'Loan Payable - WHL Advisors Inc': 'income',
    'Marketing': 'marketing',
    'Mastermind Events': 'overhead_pure',
    'Meals & Entertainment': 'overhead_pure',
    'Meals with Clients': 'overhead_pure',
    'Merchant Cash Advance - Stripe': 'overhead_pure',
    'Merchant Fees': 'overhead_pure',
    'Office Deposits': 'overhead_pure',
    'Office Equipment': 'overhead_pure',
    'Office Expenses': 'overhead_pure',
    'Office Furniture': 'overhead_pure',
    'Office/General Admin. Expenses:Business Tax & Registration Fees': 'overhead_pure',
    'Office/General Admin. Expenses:Office Expenses': 'overhead_pure',
    'Office/General Admin. Expenses:Office Expenses:IT Support': 'overhead_pure',
    'Office/General Admin. Expenses:Office Expenses:Office supplies': 'overhead_pure',
    'Opening Balance Equity': 'other',
    'Other Business Expenses:Bank Service Charges': 'overhead_pure',
    'Other Business Expenses:Insurance': 'overhead_pure',
    'Other Business Expenses:Meals & Entertainment': 'overhead_pure',
    'Other Business Expenses:Merchant Fees': 'overhead_pure',
    'Other Business Expenses:Recruitment': 'overhead_pure',
    'Other Business Expenses:Repairs & Maintenance': 'overhead_pure',
    'Overseas Contractors': 'overhead_pure',
    'Parking': 'overhead_pure',
    'Payroll Benefits': 'overhead_salary',
    'Payroll Expenses': 'overhead_salary',
    'Payroll Expenses:Employer Taxes': 'overhead_salary',
    'Payroll Expenses:Payroll Benefits': 'overhead_salary',
    'Payroll Expenses:Payroll Wage Expense': 'overhead_salary',
    'Payroll Wage Expense': 'overhead_salary',
    'Postage & Delivery': 'overhead_pure',
    'Printing & Stationery': 'overhead_pure',
    'Professional Fees': 'overhead_pure',
    'Recruitment': 'overhead_pure',
    'Rent Expense': 'overhead_pure',
    'Rental Vehicle Gasoline': 'overhead_pure',
    'Repairs & Maintenance': 'overhead_pure',
    'Software Development': 'overhead_pure',
    'SPIFF Incentives': 'overhead_pure',
    'Stripe Bank': 'overhead_pure',
    'Stripe CRM (deleted)': 'overhead_pure',
    'Taxis or shared rides': 'overhead_pure',
    'Telephone & Internet': 'overhead_pure',
    'Travel': 'overhead_pure',
    'Travel Meals': 'overhead_pure',
    'Travel:Airfare': 'overhead_pure',
    'Uncategorized Expense': 'overhead_pure',
    'Uniforms': 'overhead_pure',
    'Vehicle Rental': 'overhead_pure',
    'Website & Software': 'overhead_pure',
}

EXPENSE_GROUPS = ['overhead_pure', 'overhead_salary', 'marketing']
INCOME_GROUPS  = ['income']

# ============================================================
# TOKEN MANAGEMENT
# ============================================================

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
    print("🔄 Refreshing access token...")
    r = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Accept": "application/json"},
        timeout=30
    )
    if r.status_code != 200:
        print(f"❌ Refresh failed (HTTP {r.status_code}): {r.text}")
        return None
    new_tokens = r.json()
    new_tokens["realmId"] = realm_id
    save_tokens(new_tokens)
    print("✅ Access token refreshed.")
    return new_tokens

def get_valid_tokens():
    tokens = load_tokens()
    if not tokens:
        print("⚠️  No tokens found. One-time manual authentication required.")
        return get_tokens_from_user_input()
    if is_access_token_expired(tokens):
        tokens = refresh_tokens(tokens["refresh_token"], tokens["realmId"])
        if not tokens:
            print("\n⚠️  Refresh token expired (~100 day limit). Re-authenticating...")
            return get_tokens_from_user_input()
    return tokens

def get_tokens_from_user_input():
    params = {
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": SCOPE, "state": "xyz123",
    }
    auth_url = f"{AUTH_BASE}?{urllib.parse.urlencode(params)}"
    print("-" * 50)
    print("📋 One-Time Authentication (required every ~100 days)\n")
    print("1. Open this URL in your browser:")
    print(auth_url)
    print("\n2. Authorize the app.")
    print("3. Copy the full redirect URL from your browser's address bar.")
    print("-" * 50)
    redirect_url = input("Paste the full callback URL and press Enter: ")
    try:
        query_params = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
        code     = query_params.get("code",    [None])[0]
        realm_id = query_params.get("realmId", [None])[0]
        state    = query_params.get("state",   [None])[0]
        error    = query_params.get("error",   [None])[0]
        if error:          print(f"❌ Auth error: {error}");           return None
        if state != "xyz123": print("❌ Invalid state.");              return None
        if not code or not realm_id: print("❌ Missing code/realmId."); return None
    except Exception as e:
        print(f"❌ Failed to parse URL: {e}"); return None
    print("\n✅ Exchanging code for tokens...")
    try:
        r = requests.post(TOKEN_URL, auth=(CLIENT_ID, CLIENT_SECRET),
                          data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
                          timeout=30)
        r.raise_for_status()
        tokens = r.json()
        tokens["realmId"] = realm_id
        save_tokens(tokens)
        print("✅ Tokens saved.")
        return tokens
    except requests.exceptions.RequestException as e:
        print(f"❌ Token exchange failed: {e}"); return None

# ============================================================
# QUICKBOOKS FETCH
# ============================================================

def get_all_transactions(access_token, realm_id):
    print("\n⏳ Fetching transactions from QuickBooks...")
    base_url = f"{API_BASE}/{realm_id}/query"
    headers  = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    types    = ["Invoice", "Payment", "Deposit", "CreditMemo", "JournalEntry",
                "Bill", "VendorCredit", "Purchase"]
    all_txns = []

    for txn_type in types:
        print(f"  -> {txn_type}...")
        pos = 1
        while True:
            query = f"SELECT * FROM {txn_type} STARTPOSITION {pos} MAXRESULTS 1000"
            try:
                r = requests.get(base_url, headers=headers,
                                 params={"query": query, "minorversion": "70"}, timeout=120)
                if r.status_code in [401, 403]:
                    raise requests.exceptions.HTTPError("Token expired.", response=r)
                r.raise_for_status()
                txns = r.json().get("QueryResponse", {}).get(txn_type, [])
                for t in txns:
                    t['Type'] = txn_type
                all_txns.extend(txns)
                print(f"     {len(txns)} records")
                if len(txns) < 1000:
                    break
                pos += 1000
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400 and "Entity" in e.response.text:
                    print(f"     No data, skipping.")
                    break
                raise
    print(f"\n✅ Total QB records: {len(all_txns)}")
    return all_txns

# ============================================================
# NORMALIZE TRANSACTIONS → DATAFRAME
# ============================================================

def normalize_transactions(transactions):
    for txn in transactions:
        if not txn.get('Line'):
            txn['Line'] = [{}]

    df = pd.json_normalize(
        transactions,
        record_path=['Line'],
        meta=[
            'Id', 'SyncToken', ['MetaData', 'CreateTime'], ['MetaData', 'LastUpdatedTime'],
            'DocNumber', 'TxnDate', 'TotalAmt', ['CurrencyRef', 'value'], ['CurrencyRef', 'name'],
            ['CustomerRef', 'value'], ['CustomerRef', 'name'], 'PaymentRefNum', 'PrivateNote',
            ['DepositToAccountRef', 'name'], ['DepositToAccountRef', 'value'], 'Type'
        ],
        sep='_', errors='ignore', meta_prefix='txn_'
    )

    df.rename(columns={
        'txn_Id': 'TransactionId', 'txn_SyncToken': 'SyncToken',
        'txn_MetaData_CreateTime': 'CreateTime', 'txn_MetaData_LastUpdatedTime': 'LastUpdatedTime',
        'txn_TotalAmt': 'TotalAmount', 'txn_CurrencyRef_value': 'Currency',
        'txn_CustomerRef_value': 'CustomerId', 'txn_CustomerRef_name': 'CustomerName',
        'txn_PrivateNote': 'Notes', 'txn_DepositToAccountRef_name': 'DepositToAccount',
        'txn_TxnDate': 'TransactionDate', 'txn_Type': 'Type',
        'LineNum': 'LineNumber', 'Description': 'LineDescription', 'Amount': 'LineAmount',
        'SalesItemLineDetail_UnitPrice': 'UnitPrice', 'SalesItemLineDetail_Qty': 'Quantity',
        'SalesItemLineDetail_ItemRef_name': 'ItemName', 'SalesItemLineDetail_ItemRef_value': 'ItemId',
        'Line_DetailType': 'DetailType',
        'AccountBasedExpenseLineDetail_AccountRef_name': 'ExpenseAccount',
        'AccountBasedExpenseLineDetail_AccountRef_value': 'ExpenseAccountId',
    }, inplace=True)

    return df

# ============================================================
# BUILD DAILY BUCKETS
# ============================================================

def build_daily_buckets(df):
    df = df.copy()
    df = df.rename(columns={'TransactionDate': 'date', 'LineAmount': 'amount'})

    # Determine account name based on transaction type
    df['account'] = np.select(
        [
            df['Type'] == 'Deposit',
            df['Type'].isin(['Purchase', 'Bill', 'Check'])
        ],
        [
            df.get('DepositLineDetail_AccountRef_name', pd.Series(dtype=str)),
            df.get('ExpenseAccount', pd.Series(dtype=str))
        ],
        default=None
    )

    df.dropna(subset=['account'], inplace=True)
    df['group'] = df['account'].apply(lambda x: ACCOUNT_TO_GROUP.get(x, 'other'))
    df['date']  = pd.to_datetime(df['date']).dt.date

    df_expenses = df[df['group'].isin(EXPENSE_GROUPS) & df['Type'].isin(['Purchase', 'Bill', 'Check'])]
    df_income   = df[df['group'].isin(INCOME_GROUPS)  & (df['Type'] == 'Deposit')]
    df_combined = pd.concat([df_expenses, df_income])

    daily_pivot = df_combined.pivot_table(
        index='date', columns='group', values='amount',
        aggfunc='sum', fill_value=0
    ).reset_index()

    # Fill complete date range from 2024-01-01 to today
    all_dates = [date(2024, 1, 1) + timedelta(days=x)
                 for x in range((date.today() - date(2024, 1, 1)).days + 1)]
    final_df = pd.DataFrame({'date': all_dates}).merge(daily_pivot, on='date', how='left').fillna(0.0)

    for col in ['income', 'marketing', 'overhead_pure', 'overhead_salary']:
        if col not in final_df.columns:
            final_df[col] = 0.0

    return final_df[['date', 'income', 'marketing', 'overhead_pure', 'overhead_salary']]

# ============================================================
# SNOWFLAKE UPLOAD
# ============================================================

def upload_to_snowflake(final_df):
    print("\n🔌 Connecting to Snowflake...")
    conn   = get_snowflake_conn()
    cursor = conn.cursor()
    try:
        print("📤 Creating/replacing DORADO_BUCKETS table...")
        cursor.execute("""
            CREATE OR REPLACE TABLE DORADO_BUCKETS (
                DATE DATE, INCOME FLOAT, MARKETING FLOAT,
                OVERHEAD_PURE FLOAT, OVERHEAD_SALARY FLOAT
            )
        """)
        print(f"   Inserting {len(final_df)} rows...")
        cursor.executemany(
            "INSERT INTO DORADO_BUCKETS VALUES (%s, %s, %s, %s, %s)",
            [(r['date'], r['income'], r['marketing'], r['overhead_pure'], r['overhead_salary'])
             for _, r in final_df.iterrows()]
        )
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM DORADO_BUCKETS")
        print(f"✅ Snowflake upload complete — {cursor.fetchone()[0]} rows in DORADO_BUCKETS")
    finally:
        cursor.close()
        conn.close()

# ============================================================
# MAIN PIPELINE
# ============================================================

if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("⚠️  Missing INTUIT_CLIENT_ID or INTUIT_CLIENT_SECRET in .env")
        exit()

    # Step 1: Auth
    tokens = get_valid_tokens()
    if not tokens:
        print("❌ Authentication failed."); exit()

    # Step 2: Fetch from QuickBooks
    raw_transactions = get_all_transactions(tokens["access_token"], tokens["realmId"])
    if not raw_transactions:
        print("❌ No transactions retrieved."); exit()

    # Step 3: Normalize into flat DataFrame
    print("\n🔧 Normalizing transaction data...")
    df = normalize_transactions(raw_transactions)

    # Step 4: Save raw CSV backup to Desktop
    csv_path = Path.home() / "Desktop" / "AllTransactions.csv"
    df.to_csv(csv_path, index=False)
    print(f"💾 Raw CSV backup saved to: {csv_path}")

    # Step 5: Build daily buckets
    print("\n📊 Building daily buckets...")
    daily_df = build_daily_buckets(df)

    # Step 6: Upload to Snowflake
    upload_to_snowflake(daily_df)

    # Step 7: Summary
    print(f"\n{'='*50}")
    print("🎉 Pipeline complete!")
    print(f"   Income:           ${daily_df['income'].sum():>12,.2f}")
    print(f"   Marketing:        ${daily_df['marketing'].sum():>12,.2f}")
    print(f"   Overhead (pure):  ${daily_df['overhead_pure'].sum():>12,.2f}")
    print(f"   Overhead (salary):${daily_df['overhead_salary'].sum():>12,.2f}")
    print(f"{'='*50}")