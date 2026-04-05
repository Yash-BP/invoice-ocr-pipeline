import sqlite3
import pandas as pd
import os

def load_data_to_sql():
    print("Connecting to the Finance Database...")
    
    # Define file paths
    csv_path = 'data/extracted_invoices.csv'
    db_path = 'data/finance_system.db'
    
    # Check if the extracted data exists
    if not os.path.exists(csv_path):
        print("Error: Could not find extracted_invoices.csv. Run extraction script first.")
        return

    # Read the clean data
    df = pd.read_csv(csv_path)
    
    # Connect to SQLite database (this will create it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create a secure table schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_invoices (
            Invoice_ID TEXT PRIMARY KEY,
            Date TEXT,
            Vendor_Name TEXT,
            Tax_Amount_INR INTEGER,
            Total_Amount_INR INTEGER,
            Processed_Status TEXT DEFAULT 'Automated_OCR'
        )
    ''')
    
    # Insert the Pandas DataFrame into the SQL table
    # We use 'replace' to avoid duplicates if we run the script twice
    df.to_sql('processed_invoices', conn, if_exists='replace', index=False)
    
    # Verify the insertion using a quick SQL query
    cursor.execute("SELECT COUNT(*) FROM processed_invoices")
    record_count = cursor.fetchone()[0]
    
    print(f"✅ Successfully loaded {record_count} invoices into 'finance_system.db'")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    load_data_to_sql()