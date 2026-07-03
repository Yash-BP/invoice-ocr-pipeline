import sqlite3
import pandas as pd
import os

def run_analysis():
    db_path = 'data/finance_system.db'
    
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    
    # Check if table exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_invoices';")
    if not cursor.fetchone():
        print("[ERROR] processed_invoices table not found in the database.")
        conn.close()
        return

    df = pd.read_sql_query("SELECT * FROM processed_invoices", conn)
    
    if df.empty:
        print("[ERROR] The processed_invoices table is empty.")
        conn.close()
        return
        
    print("[INFO] Analyzing table: processed_invoices")
    print("\n--- Financial Summary ---")
    print(f"Total Expenditure: Rs. {df['grand_total'].sum():,.2f}")
    print(f"Average Invoice:   Rs. {df['grand_total'].mean():,.2f}")
    
    print("\n--- Top Vendors by Spend ---")
    vendor_sums = df.groupby('vendor_name')['grand_total'].sum().sort_values(ascending=False).head(5)
    for vendor, spend in vendor_sums.items():
        print(f"  - {vendor}: Rs. {spend:,.2f}")
        
    conn.close()

if __name__ == "__main__":
    run_analysis()