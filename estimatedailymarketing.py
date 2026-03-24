import pandas as pd
from datetime import date, timedelta
import calendar
import sys
import os  # Used to find your desktop path

# --- Configuration ---

# List of vendors to filter for (Google Ads added)
TARGET_VENDORS = [
    'Spektra Insurance Solutions',
    'Roku Inc.',
    'Quote.com',
    'Quantum Digital Media Inc',
    'Peak Media LLC',
    'Optimize to Convert Digital, LLC',
    'Lucent Media, LLC',
    'Little Brook Media',
    'Channel Edge Media LLC',
    'BrokerCalls LLC',
    'Barrington Media Group LLC',
    'Google LLC',
    'Google Ads'  # <-- Added Google Ads as a synonym
]

# Set of holiday dates. 
# WARNING: This list is for 2024. It will be used for all calculations,
# including dates in 2025, which may slightly skew 2025 numbers.
HOLIDAYS_SET = {
    date(2024, 1, 1),
    date(2024, 4, 18),
    date(2024, 5, 26),
    date(2024, 7, 4),
    date(2024, 9, 1),
    date(2024, 11, 27),
    date(2024, 11, 28),
    date(2024, 12, 24),
    date(2024, 12, 25)
}

# --- File Paths ---
# Find the user's home directory (e.g., C:\Users\HFreeman)
USER_HOME_DIR = os.path.expanduser("~")

# Construct the full path to the input file on the desktop
INPUT_FILE = os.path.join(USER_HOME_DIR, 'Desktop', 'ALLBILLS.csv')

# --- MODIFIED: Construct the path to the DORADO folder and the output file ---
DORADO_FOLDER = os.path.join(USER_HOME_DIR, 'Desktop', 'DORADO')
OUTPUT_FILE = os.path.join(DORADO_FOLDER, 'dorado_marketing.csv')
# ----------------------------------------------------------------------------

# --- Report Start Date ---
REPORT_START_DATE = pd.to_datetime('2024-01-01')

# --- Helper Function ---

def is_workday(d, holidays_set):
    """
    Checks if a given date is a weekday (Mon-Fri) and not a holiday.
    """
    # weekday() returns 0 for Monday and 6 for Sunday
    is_weekday = d.weekday() < 5
    is_not_holiday = d not in holidays_set
    return is_weekday and is_not_holiday

# --- Main Processing Function ---

def process_bills():
    """
    Reads the input CSV, processes the data, and writes the output CSV.
    """
    print(f"Starting to process {INPUT_FILE}...")
    print(f"Warning: Using the provided 2024 holiday list for all calculations.")
    print(f"Report will start on {REPORT_START_DATE.date()}.")

    # --- 1. Read and Prepare Data ---
    try:
        # Note: If your CSV is tab-separated (TSV) instead of comma-separated,
        # use: df = pd.read_csv(INPUT_FILE, sep='\t')
        df = pd.read_csv(INPUT_FILE)
    except FileNotFoundError:
        print(f"ERROR: Input file not found at '{INPUT_FILE}'.")
        print("Please make sure the file is on your desktop.")
        return
    except Exception as e:
        print(f"ERROR: Could not read file. {e}")
        print("Please check if the file is a valid CSV.")
        return

    # Clean column names (remove leading/trailing whitespace)
    df.columns = df.columns.str.strip()

    # Ensure required columns exist
    required_cols = ['Invoice no.', 'Vendor', 'Invoice date', 'Invoice amount']
    if not all(col in df.columns for col in required_cols):
        print(f"ERROR: Input CSV is missing one or more required columns.")
        print(f"Required: {required_cols}")
        print(f"Found: {list(df.columns)}")
        return

    # 1a. Condense based on unique Invoice no.
    df.drop_duplicates(subset=['Invoice no.'], keep='first', inplace=True)

    # 1b. Filter for target vendors
    df_filtered = df[df['Vendor'].isin(TARGET_VENDORS)].copy()

    # *** NEW: Normalize 'Google Ads' to 'Google LLC' ***
    df_filtered['Vendor'] = df_filtered['Vendor'].replace('Google Ads', 'Google LLC')
    
    if df_filtered.empty:
        print(f"No records found for the target vendors. Exiting.")
        return

    # 1c. Clean and convert data types
    df_filtered['Invoice date'] = pd.to_datetime(
        df_filtered['Invoice date'], errors='coerce'
    )
    # Remove '$' or ',' from amount before converting to numeric
    df_filtered['Invoice amount'] = (
        df_filtered['Invoice amount']
        .replace(r'[$,]', '', regex=True)
        .pipe(pd.to_numeric, errors='coerce')
    )

    # Drop rows where essential data is missing after conversion
    df_filtered.dropna(
        subset=['Invoice date', 'Invoice amount'], inplace=True
    )
    
    print(f"Found {len(df_filtered)} valid invoices from target vendors.")

    # --- 2. Calculate Daily Spend Allocations ---
    
    output_rows = []
    
    for _, row in df_filtered.iterrows():
        vendor = row['Vendor']
        amount = row['Invoice amount']
        # Convert pandas timestamp to standard date object
        inv_date = row['Invoice date'].date()

        workdays_for_this_invoice = []

        # This logic now handles 'Google LLC' and 'Google Ads' (as it was renamed)
        if vendor in ('Roku Inc.', 'Google LLC'):
            # Monthly logic
            
            # Determine the correct year and month for the spend
            spend_year = inv_date.year
            spend_month = inv_date.month

            if vendor == 'Google LLC' and inv_date.day == 1:
                # Invoice on 1st = for previous month
                # Go back one day from the invoice date to get into the previous month
                prev_month_date = inv_date - timedelta(days=1)
                spend_year = prev_month_date.year
                spend_month = prev_month_date.month
            
            # --- Now, find all workdays in that (spend_year, spend_month) ---
            num_days_in_month = calendar.monthrange(
                spend_year, spend_month
            )[1]
            
            for day_num in range(1, num_days_in_month + 1):
                current_date = date(spend_year, spend_month, day_num)
                if is_workday(current_date, HOLIDAYS_SET):
                    workdays_for_this_invoice.append(current_date)
        
        else:
            # Weekly logic (for all other target vendors)
            # Find the Monday of the invoice's week
            days_since_monday = inv_date.weekday()
            start_of_week_monday = inv_date - timedelta(days=days_since_monday)
            
            # Find all workdays in that Mon-Sun week
            for i in range(7):
                current_date = start_of_week_monday + timedelta(days=i)
                if is_workday(current_date, HOLIDAYS_SET):
                    workdays_for_this_invoice.append(current_date)

        # Distribute the amount over the found workdays
        num_workdays = len(workdays_for_this_invoice)
        if num_workdays > 0:
            daily_spend = amount / num_workdays
            
            for d in workdays_for_this_invoice:
                output_rows.append({
                    'date': d,
                    'vendor': vendor,
                    'est_daily_spend': daily_spend
                })
        else:
            print(f"Warning: No workdays found for invoice {row['Invoice no.']} "
                  f"(Amount: {amount}, Date: {inv_date}). Spend not allocated.")

    if not output_rows:
        print("No spend data was allocated. Output file will be empty.")
        return

    # Create DataFrame from all calculated spend days
    spend_df = pd.DataFrame(output_rows)
    
    # Sum up spend for any days that had overlapping invoices
    daily_spend_total = spend_df.groupby(
        ['date', 'vendor']
    )['est_daily_spend'].sum().reset_index()

    # --- 3. Create Full Calendar Report ---

    print("Generating full daily report...")

    # 3a. Find the dynamic end date based on the latest invoice data
    # Convert 'date' column to datetime objects for comparison
    daily_spend_total['date'] = pd.to_datetime(daily_spend_total['date'])
    
    report_end_date = daily_spend_total['date'].max()

    # Handle case where no data is found, or all data is before the start date
    if pd.isna(report_end_date):
        print("No valid invoice data found to process. Creating empty 2024 report.")
        report_end_date = pd.to_datetime('2024-1T23:59:59')
    
    # Ensure the report's end date is at least the start date
    report_end_date = max(REPORT_START_DATE, report_end_date)
    
    print(f"Report will end on {report_end_date.date()}.")

    # 3b. Create a base calendar from the start date to the dynamic end date
    all_dates = pd.date_range(start=REPORT_START_DATE, end=report_end_date, freq='D')
    
    # 3c. Create the Cartesian product of all dates and all target vendors
    # We must get a unique list of vendors *after* the renaming
    final_vendor_list = df_filtered['Vendor'].unique()
    
    calendar_df = pd.DataFrame(
        index=pd.MultiIndex.from_product(
            [all_dates, final_vendor_list], 
            names=['date', 'vendor']
        )
    ).reset_index()

    # 3d. Merge the calculated spend data into the full calendar
    final_df = pd.merge(
        calendar_df, 
        daily_spend_total, 
        on=['date', 'vendor'], 
        how='left'
    )

    # 3e. Fill in 0 for days with no calculated spend
    final_df['est_daily_spend'].fillna(0, inplace=True)

    # 3f. Add the 'holiday' column
    # We use .dt.date to compare date objects (ignoring time)
    final_df['holiday'] = final_df['date'].dt.date.isin(HOLIDAYS_SET)
    final_df['holiday'] = final_df['holiday'].map({True: 'TRUE', False: 'FALSE'})

    # --- 4. Format and Save Output ---

    # Format date column to YYYY-MM-DD
    final_df['date'] = final_df['date'].dt.strftime('%Y-%m-%d')
    
    # Ensure final columns are in the correct order
    final_df = final_df[['date', 'vendor', 'est_daily_spend', 'holiday']]

    # Sort by date, then vendor
    final_df.sort_values(by=['date', 'vendor'], inplace=True)

    # --- MODIFIED: Create the DORADO folder if it doesn't exist ---
    try:
        os.makedirs(DORADO_FOLDER, exist_ok=True)
    except Exception as e:
        print(f"\nERROR: Could not create output directory {DORADO_FOLDER}. {e}")
        return
    # ---------------------------------------------------------------
    
    # Save to CSV
    try:
        final_df.to_csv(OUTPUT_FILE, index=False, float_format='%.2f')
        print(f"\nSuccess! Report saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"\nERROR: Could not save output file. {e}")


# --- Run the Script ---
if __name__ == "__main__":
    process_bills()