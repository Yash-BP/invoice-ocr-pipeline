import sqlite3
import pandas as pd
import os

def run_analysis():
    db_path = 'data/finance_system.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    
    table_name_query = "SELECT name FROM sqlite_master WHERE type='table';"
    tables = pd.read_sql_query(table_name_query, conn)
    
    if tables.empty:
        print("❌ Error: The database exists but it is empty (no tables found).")
        return
        
    target_table = tables.iloc[0]['name']
    print(f"📊 Analyzing table: {target_table}")

    df = pd.read_sql_query(f"SELECT * FROM {target_table}", conn)
    
    print("\n--- Financial Summary ---")
    print(f"Total Expenditure: ₹{df['Total_Amount_INR'].sum():,}")
    print(f"Average Invoice:   ₹{df['Total_Amount_INR'].mean():,.2f}")
    
    conn.close()

if __name__ == "__main__":
    run_analysis()