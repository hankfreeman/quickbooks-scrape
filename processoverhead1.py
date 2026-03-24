import pandas as pd
import os
from pathlib import Path
from datetime import date, timedelta
import numpy as np 

# Define the mapping from 'Account' to 'group'
ACCOUNT_TO_GROUP = {
    '1099 Contractor': 'overhead_pure',
    'Accounts Payable (A/P)': 'overhead_pure',
    'Advertising': 'marketing',
    'Advertising & Marketing:Advertising': 'marketing',
    'Advertising & Marketing:Marketing': 'marketing',
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
    'Website & Software': 'overhead_pure'
}

# Define which groups are expenses vs income
EXPENSE_GROUPS = ['overhead_pure', 'overhead_salary', 'marketing']
INCOME_GROUPS = ['income']


def generate_daily_report(input_filename='alltransactions.csv', output_folder_name='DORADO', output_filename='dorado_daily_buckets.csv'):
    """
    Reads transactions, categorizes them into buckets (income, marketing, overhead_pure, overhead_salary),
    sums by date, and saves daily totals to a CSV.
    """
    desktop_path = Path.home() / 'Desktop'
    output_directory = desktop_path / output_folder_name
    output_file_path = output_directory / output_filename
    input_file_path = desktop_path / input_filename
    
    print(f"Target output path: {output_file_path}")
    
    try:
        output_directory.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Error creating directory {output_directory}: {e}")
        return

    try:
        # Read and prepare data
        df = pd.read_csv(input_file_path)
        df = df.rename(columns={'TransactionDate': 'date', 'txn_Type': 'type', 'LineAmount': 'amount'})
        
        # Create 'account' column based on transaction type
        df['account'] = np.select(
            [
                df['type'] == 'Deposit',
                df['type'].isin(['Purchase', 'Bill', 'Check'])
            ],
            [
                df['DepositLineDetail_AccountRef_name'],
                df['ExpenseAccount']
            ],
            default=None
        )
        
        df.dropna(subset=['account'], inplace=True)
        
        # Map accounts to groups
        df['group'] = df['account'].apply(lambda x: ACCOUNT_TO_GROUP.get(x, 'other'))
        
        # Prepare date column
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        # Filter for relevant transaction types
        # Expenses: Purchase, Bill, Check
        # Income: Deposit
        df_expenses = df[
            (df['group'].isin(EXPENSE_GROUPS)) & 
            (df['type'].isin(['Purchase', 'Bill', 'Check']))
        ].copy()
        
        df_income = df[
            (df['group'].isin(INCOME_GROUPS)) & 
            (df['type'] == 'Deposit')
        ].copy()
        
        # Combine for pivoting
        df_combined = pd.concat([df_expenses, df_income])
        
        # Pivot to get daily sums by group
        daily_pivot = df_combined.pivot_table(
            index='date',
            columns='group',
            values='amount',
            aggfunc='sum',
            fill_value=0
        ).reset_index()
        
        # Create complete date range
        start_date = date(2024, 1, 1)
        end_date = date.today()
        all_dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        full_date_range_df = pd.DataFrame({'date': all_dates})
        
        # Merge with full date range
        final_df = full_date_range_df.merge(daily_pivot, on='date', how='left').fillna(0.0)
        
        # Ensure all bucket columns exist (in case some have no data)
        for bucket in ['income', 'marketing', 'overhead_pure', 'overhead_salary']:
            if bucket not in final_df.columns:
                final_df[bucket] = 0.0
        
        # Reorder columns
        final_df = final_df[['date', 'income', 'marketing', 'overhead_pure', 'overhead_salary']]
        
        # Format date
        final_df['date'] = final_df['date'].astype(str)

        # Save
        final_df.to_csv(output_file_path, index=False)

        print(f"\nReport Generation Complete! 🎉")
        print(f"Daily bucket data saved to: **{output_file_path}**")
        print(f"The output CSV contains {len(final_df)} rows and columns: {final_df.columns.tolist()}")
        print(f"\nSample of totals:")
        print(f"  Total Income: ${final_df['income'].sum():,.2f}")
        print(f"  Total Marketing: ${final_df['marketing'].sum():,.2f}")
        print(f"  Total Overhead (Pure): ${final_df['overhead_pure'].sum():,.2f}")
        print(f"  Total Overhead (Salary): ${final_df['overhead_salary'].sum():,.2f}")

    except FileNotFoundError:
        print(f"\nError: The input file '{input_filename}' was **not found** at the expected location.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during processing: {e}")


if __name__ == '__main__':
    generate_daily_report()