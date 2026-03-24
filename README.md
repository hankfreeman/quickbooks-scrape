# DORADO

**DORADO** is a small analytics pipeline that pulls transaction data from **QuickBooks Online**, classifies line items into business buckets (income, marketing, overhead), and loads daily aggregates into **Snowflake**.

## What `qb2sf.py` does

1. **Authenticates** to QuickBooks using OAuth2 (tokens are stored locally in `tokens.json`; see [Setup](#setup)).
2. **Downloads** transactions across common types: invoices, payments, deposits, credit memos, journal entries, bills, vendor credits, and purchases.
3. **Normalizes** line-level detail into a flat table (including expense account names on purchase-type transactions).
4. **Maps** each QuickBooks account name to a bucket using `ACCOUNT_TO_GROUP` — for example advertising-style accounts roll into **marketing**, payroll-related lines into **overhead_salary**, and other operating expenses into **overhead_pure**.
5. **Builds** a daily time series from 2024-01-01 through today with columns: `income`, `marketing`, `overhead_pure`, `overhead_salary`.
6. **Writes** a raw CSV backup to your Desktop (`AllTransactions.csv`) and **replaces** the Snowflake table `DORADO_BUCKETS` with the daily aggregates.

Use `ENVIRONMENT=production` in `.env` to hit the live QuickBooks API; omit it or use `development` for the sandbox.

## Other scripts in this repo

| Script | Role |
|--------|------|
| `getalltransactions.py` / `getalltransactionsauto.py` | Fetch all QuickBooks transactions (CSV-oriented helpers). |
| `processoverhead.py`, `processoverhead1.py` | Overhead processing on exported transaction data. |
| `estimatedailymarketing.py` | Marketing estimates from daily data. |
| `convertemployeesummary.py` | ADP employee summary PDF → usable input for payroll flows. |

Legacy notes for manual exports (bills.com, ADP) live in `README.txt`.

## Setup

1. Copy `.env.example` to `.env` and fill in **Intuit** and **Snowflake** variables. Do not commit `.env`.
2. Install dependencies (Python 3):

   ```bash
   pip install requests pandas numpy snowflake-connector-python python-dotenv
   ```

3. First run: complete the browser OAuth flow when prompted so `tokens.json` is created (keep this file out of version control).

4. Run the main pipeline:

   ```bash
   python qb2sf.py
   ```

## Security

- Never commit **`.env`**, **`tokens.json`**, or real account passwords.
- Rotate Intuit and Snowflake credentials if they were ever exposed in code or a public repository.

## License

Add a license file if you plan to share this repository publicly.
