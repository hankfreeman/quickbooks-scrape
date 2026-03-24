import pdfplumber
import pandas as pd
import os
import re 
import numpy as np

# 1. Configuration
username = 'HFreeman' 
filename = 'employeesummary.pdf' 

# Define new output structure
OUTPUT_DIR = fr'C:\Users\{username}\Desktop\DORADO' # ⭐ Folder path to create/use
OUTPUT_FILENAME = 'dorado_payroll.csv' # ⭐ Final CSV name
input_file = fr'C:\Users\{username}\Desktop\{filename}'
output_file = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME) # Combined path

# Create the output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True) # ⭐ Logic to create the DORADO folder

print(f"Attempting to read file from: {input_file}")
print(f"Output will be saved to: {output_file}")
print("-" * 40)

# List of Position IDs to exclude
EXCLUDE_POSITION_IDS = [
    'XAJ05994N', 'XAJ68493N', 'XAJ71769N', 'XCY000070', 
    'XCY000074', 'XCY000075', 'XCY000139', 'XCY000263', 
    'XCY000463', 'XCY000492', 'XCY000564', 'XCY000565', 
    'XCY000566', 'XCY000567', 'XCY000568'
]

# Define the old field names extracted from the PDF (to be renamed later)
ORIGINAL_FIELD_NAMES = [
    'Name', 
    'Position ID', 
    'Job Acronym', 
    'Job Title', 
    'Position Start Date', 
    'Status', 
    'Regular Pay Rate', 
    'comm_tier',
]

# Define the new column names for the final output CSV
NEW_COLUMN_NAMES = [
    'name', 
    'id', 
    'acronym', 
    'title', 
    'hiredate', 
    'status', 
    'payrate', 
    'commtier'
]

# Create a mapping dictionary for renaming the columns
COLUMN_MAPPING = dict(zip(ORIGINAL_FIELD_NAMES, NEW_COLUMN_NAMES))

# All fields we need to EXTRACT, including temporary ones (Rate 2)
EXTRACTED_FIELDS = [
    'Name', 'Position ID', 'Job Acronym', 'Job Title', 
    'Position Start Date', 'Status', 'Regular Pay Rate', 
    'Pay Frequency', 'Standard Hours', 'Rate 2'
]

# Regex to capture Name and Position ID from the top line:
TOP_LINE_PATTERN = re.compile(r'Name: (.+?) Position ID: (\S+)')

# Headers that are followed by simple rate data
SIMPLE_HEADERS = [
    'Regular Pay Rate', 
    'Pay Frequency', 
    'Standard Hours', 
    'Rate 2'
]

# 2. Iterative Dynamic Extraction Logic
all_employee_data = []

try:
    with pdfplumber.open(input_file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            employee_record = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # --- RULE 1: Top Line Extraction (Name and Position ID) ---
                if 'Name:' in line and 'Position ID:' in line and 'Name' not in employee_record:
                    try:
                        match = TOP_LINE_PATTERN.search(line)
                        if match:
                            employee_record['Name'] = match.group(1).strip()
                            employee_record['Position ID'] = match.group(2).strip()
                    except Exception as e:
                        print(f"⚠️ Warning on Page {page_num + 1}: Error parsing Name/ID line: {e}")
                    continue

                # --- RULE 2: Job Acronym and Job Title ---
                if line.startswith('Job Title'):
                    try:
                        data_part = line.split('Job Title', 1)[-1].strip()
                        parts = data_part.split(None, 1) 
                        
                        employee_record['Job Acronym'] = parts[0].strip() if len(parts) >= 1 else np.nan
                        employee_record['Job Title'] = parts[1].strip() if len(parts) >= 2 else np.nan
                    except Exception as e:
                        print(f"⚠️ Warning on Page {page_num + 1}: Error parsing Job Title line: {e}")
                    continue

                # --- RULE 3: Position Start Date and Status ---
                if line.startswith('Position Start Date'):
                    try:
                        data_part = line.split('Position Start Date', 1)[-1].strip()
                        parts = data_part.split(None, 2) 
                        
                        employee_record['Position Start Date'] = parts[0].strip() if len(parts) >= 1 else np.nan
                        employee_record['Status'] = parts[1].strip() if len(parts) >= 2 else np.nan
                    except Exception as e:
                        print(f"⚠️ Warning on Page {page_num + 1}: Error parsing Start Date/Status line: {e}")
                    continue

                # --- RULE 4: Simple Pay Fields (Regular Pay Rate, Pay Frequency, Standard Hours, Rate 2) ---
                for field in SIMPLE_HEADERS:
                    if line.startswith(field):
                        try:
                            data = line.split(field, 1)[-1].strip()
                            
                            if field in ['Regular Pay Rate', 'Rate 2']:
                                # Use regex to find the currency amount reliably
                                match = re.match(r'[\$£€]?([\d\.\,]+)', data.strip())
                                value = match.group(1).replace(',', '') if match else data.split(None, 1)[0]
                                employee_record[field] = value
                            else:
                                employee_record[field] = data.split(None, 1)[0]
                        except Exception as e:
                            print(f"⚠️ Warning on Page {page_num + 1}: Error parsing {field} line: {e}")
                        break
                        
            # --- POST-EXTRACTION CLEANUP AND CONDITIONAL LOGIC (Performed for each record) ---
            
            # 1. Truncate 'Attendance Supervisor' from Job Title
            job_title = employee_record.get('Job Title')
            if isinstance(job_title, str):
                suffix = 'Attendance Supervisor'
                if job_title.endswith(suffix):
                    employee_record['Job Title'] = job_title[:-len(suffix)].strip()
            
            # 2. Overwrite Regular Pay Rate with Rate 2 if Rate 2 exists
            rate_2 = employee_record.get('Rate 2')
            if rate_2 is not None and not pd.isna(rate_2):
                employee_record['Regular Pay Rate'] = rate_2
            
            # Add the record if the name was found
            if employee_record.get('Name'):
                for field in EXTRACTED_FIELDS:
                    if field not in employee_record:
                        employee_record[field] = np.nan
                all_employee_data.append(employee_record)
            
except FileNotFoundError:
    print(f"❌ Error: The file was not found at **{input_file}**. Please verify the path and filename.")
    exit()
except Exception as e:
    print(f"❌ Critical Error during PDF processing: {e}")
    exit()


# 3. Create the final output DataFrame and write to CSV
if not all_employee_data:
    print("⚠️ No employee records found. Check the PDF file.")
    exit()
    
df_output = pd.DataFrame(all_employee_data)

# --- Filter out excluded Position IDs ---
initial_count = len(df_output)
df_output = df_output[~df_output['Position ID'].isin(EXCLUDE_POSITION_IDS)]
excluded_count = initial_count - len(df_output)
print(f"ℹ️ Excluded {excluded_count} record(s) based on the provided Position IDs.")

# --- Conditional Logic for comm_tier column ---
# Ensure 'Regular Pay Rate' is numeric for comparisons, coercing errors to NaN
df_output['payrate_numeric'] = pd.to_numeric(df_output['Regular Pay Rate'], errors='coerce')

# Define the conditions and values for comm_tier
conditions = [
    (df_output['Job Title'] == 'Agent') & (df_output['payrate_numeric'] == 28.85),
    (df_output['Job Title'] == 'Agent') & (df_output['payrate_numeric'] == 14.42),
    (df_output['Job Title'] == 'Call Center Agent - Team Lead') & (df_output['payrate_numeric'] == 20.00)
]
choices = ['Training', 'Performing', 'Performing']

df_output['comm_tier'] = np.select(conditions, choices, default=None)

# Remove the temporary numeric column and the temporary pay rate columns
df_output = df_output.drop(columns=['payrate_numeric', 'Pay Frequency', 'Standard Hours', 'Rate 2'], errors='ignore')

# Filter down and reorder to the list of columns needed for output
df_output = df_output.reindex(columns=ORIGINAL_FIELD_NAMES)

# Rename columns to the final, requested names
df_output = df_output.rename(columns=COLUMN_MAPPING)

# ⭐ Save the final CSV to the DORADO folder
df_output.to_csv(output_file, index=False) 

print(f"✅ Success! Found **{len(df_output)}** final employee records. Data extracted, cleaned, and saved to **{output_file}**")
print("\nExtracted Data (First 5 Rows with new column names):")
print("------------------------------")
print(df_output.head().to_markdown(index=False))