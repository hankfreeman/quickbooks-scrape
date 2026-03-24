import pandas as pd
import os
from pathlib import Path
from datetime import date, timedelta
import numpy as np 

# Define the mapping from 'Account' to 'group'
ACCOUNT_TO_GROUP = {
    '1099 Contractor': 'overhead',
    'Accounts Payable (A/P)': 'overhead',
    'Advertising': 'marketing',
    'Advertising & Marketing:Advertising': 'marketing',
    'Advertising & Marketing:Marketing': 'marketing',
    'Airfare': 'overhead',
    'Bank Service Charges': 'overhead',
    'Brex Credit Card': 'overhead',
    'Business Licenses & Permits': 'overhead',
    'Business Tax & Registration Fees': 'overhead',
    'Charitable Donations': 'overhead',
    'Commission Income': 'income_special', 
    'Computer Equipment': 'overhead',
    'Consulting & Accounting': 'overhead',
    'Contract Labor:1099 Contractor': 'overhead',
    'Credit Card Rewards': 'overhead',
    'Discounts/Refunds': 'overhead',
    'Dues & Subscriptions': 'overhead',
    'Education & Training': 'overhead',
    'Employee Advances': 'payroll',
    'Employer Taxes': 'overhead',
    'Franchise Tax': 'overhead',
    'Guaranteed Payments - Nic West': 'overhead',
    'Guaranteed Payments - Rootfin LLC': 'overhead',
    'Hotels': 'overhead',
    'Insurance': 'overhead',
    'Insurance CRM': 'income_special', 
    'Intangible Asset - NoExam.com': 'overhead',
    'Interest Expense - Home Bank Loan': 'overhead',
    'Leads Income': 'income_special', 
    'Leasehold Improvements': 'overhead',
    'Legal & Professional Fees:Professional Fees': 'overhead',
    'Legal Fees': 'overhead',
    'Loan Payable - First Home Bank': 'overhead',
    'Loan Payable - WHL Advisors Inc': 'income_special',
    'Marketing': 'marketing',
    'Mastermind Events': 'overhead',
    'Meals & Entertainment': 'overhead',
    'Meals with Clients': 'overhead',
    'Merchant Cash Advance - Stripe': 'overhead',
    'Merchant Fees': 'overhead',
    'Office Deposits': 'overhead',
    'Office Equipment': 'overhead',
    'Office Expenses': 'overhead',
    'Office Furniture': 'overhead',
    'Office/General Admin. Expenses:Business Tax & Registration Fees': 'overhead',
    'Office/General Admin. Expenses:Office Expenses': 'overhead',
    'Office/General Admin. Expenses:Office Expenses:IT Support': 'overhead',
    'Office/General Admin. Expenses:Office Expenses:Office supplies': 'overhead',
    'Opening Balance Equity': 'other',
    'Other Business Expenses:Bank Service Charges': 'overhead',
    'Other Business Expenses:Insurance': 'overhead',
    'Other Business Expenses:Meals & Entertainment': 'overhead',
    'Other Business Expenses:Merchant Fees': 'overhead',
    'Other Business Expenses:Recruitment': 'overhead',
    'Other Business Expenses:Repairs & Maintenance': 'overhead',
    'Overseas Contractors': 'overhead',
    'Parking': 'overhead',
    'Payroll Benefits': 'payroll',
    'Payroll Expenses': 'payroll',
    'Payroll Expenses:Employer Taxes': 'payroll',
    'Payroll Expenses:Payroll Benefits': 'payroll',
    'Payroll Expenses:Payroll Wage Expense': 'payroll',
    'Payroll Wage Expense': 'payroll',
    'Postage & Delivery': 'overhead',
    'Printing & Stationery': 'overhead',
    'Professional Fees': 'overhead',
    'Recruitment': 'overhead',
    'Rent Expense': 'overhead',
    'Rental Vehicle Gasoline': 'overhead',
    'Repairs & Maintenance': 'overhead',
    'Software Development': 'overhead',
    'SPIFF Incentives': 'overhead',
    'Stripe Bank': 'overhead',
    'Stripe CRM (deleted)': 'overhead',
    'Taxis or shared rides': 'overhead',
    'Telephone & Internet': 'overhead',
    'Travel': 'overhead',
    'Travel Meals': 'overhead',
    'Travel:Airfare': 'overhead',
    'Uncategorized Expense': 'overhead',
    'Uniforms': 'overhead',
    'Vehicle Rental': 'overhead',
    'Website & Software': 'overhead'
}


def generate_daily_overhead_report(input_filename='alltransactions.csv', output_folder_name='DORADO', output_filename='dorado_overhead.csv'):
    """
    Reads the transactions, dynamically determines the 'account' based on txn_Type 
    (Deposit: DepositLineDetail_AccountRef_name, Expense: ExpenseAccount), 
    filters for 'overhead' group and 'Purchase'/'Bill' types,
    sums the 'LineAmount' by date, and saves the daily totals to a CSV.
    """
    # Define paths
    desktop_path = Path.home() / 'Desktop'
    output_directory = desktop_path / output_folder_name
    output_file_path = output_directory / output_filename
    input_file_path = desktop_path / input_filename
    
    print(f"Target output path: {output_file_path}")
    
    # 1. Ensure the DORADO output directory exists
    try:
        output_directory.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Error creating directory {output_directory}: {e}")
        return

    try:
        # 2. Read the CSV file
        df = pd.read_csv(input_file_path)

        # 3. Rename columns for consistency
        df = df.rename(columns={'TransactionDate': 'date', 'txn_Type': 'type', 'LineAmount': 'amount'})
        
        # 4. Create the 'account' column using conditional logic (The key modification 🔑)
        # Check if it's a Deposit, then use Deposit account name.
        # Otherwise (assuming it's an expense like Purchase/Bill), use ExpenseAccount.
        df['account'] = np.select(
            [
                df['type'] == 'Deposit',
                df['type'].isin(['Purchase', 'Bill', 'Check']) # Common expense types
            ],
            [
                df['DepositLineDetail_AccountRef_name'],
                df['ExpenseAccount']
            ],
            default=None # Default to None for unhandled transaction types
        )
        
        # Drop rows where 'account' couldn't be mapped (None/NaN)
        df.dropna(subset=['account'], inplace=True) 

        # 5. Create the 'group' column by mapping 'account' values
        df['group'] = df['account'].apply(lambda x: ACCOUNT_TO_GROUP.get(x, 'other'))
        
        # Apply the special group logic from the original code (mostly for income types)
        def get_final_group(row):
            if row['group'] == 'income_special':
                if row['account'] == 'Commission Income':
                    return 'income - commission'
                elif row['account'] == 'Insurance CRM':
                    return 'income - leads'
                elif row['account'] == 'Loan Payable - WHL Advisors Inc':
                    return 'income - loan payable'
                else:
                    return 'income - other'
            return row['group']

        df['group'] = df.apply(get_final_group, axis=1)

        
        # 6. Filter the data based on your specific criteria
        # Filter for 'overhead' group and expense-related transaction types
        df_filtered = df[
            (df['group'] == 'overhead') & 
            (df['type'].isin(['Purchase', 'Bill', 'Check'])) # Filtering for expense transactions
        ].copy() # Use .copy() to avoid SettingWithCopyWarning
        
        # 7. Prepare date column and calculate daily sums
        df_filtered['date'] = pd.to_datetime(df_filtered['date']).dt.date
        
        # Sum the amounts for each day and reset the index to turn 'date' back into a column
        daily_overhead = df_filtered.groupby('date')['amount'].sum().reset_index()
        daily_overhead.rename(columns={'amount': 'dailyoverhead'}, inplace=True)
        
        # 8. Create a complete date range from January 1, 2024, to today
        start_date = date(2024, 1, 1)
        end_date = date.today()
        all_dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        full_date_range_df = pd.DataFrame({'date': all_dates})
        
        # 9. Merge the daily sums with the full date range
        final_df = full_date_range_df.merge(daily_overhead, on='date', how='left').fillna(0.0)
        
        # 10. Ensure the date column is in the correct format for the final output
        final_df['date'] = final_df['date'].astype(str)

        # 11. Save the final DataFrame to the specified path
        final_df.to_csv(output_file_path, index=False)

        print(f"\nReport Generation Complete! 🎉")
        print(f"Daily overhead data saved to: **{output_file_path}**")
        print(f"The output CSV contains {len(final_df)} rows (one for each day) and the columns: {final_df.columns.tolist()}")


    except FileNotFoundError:
        print(f"\nError: The input file '{input_filename}' was **not found** at the expected location.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during processing: {e}")

# The main execution block
if __name__ == '__main__':
    generate_daily_overhead_report()