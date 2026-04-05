import sqlite3
import pandas as pd

def check_database():
    db_path = "data/finance_system.db"
    
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(db_path)
        
        # SQL Query to grab the most important columns
        query = """
            SELECT 
                invoice_id, 
                vendor_name, 
                subtotal, 
                tax_amount, 
                grand_total, 
                validation_passed 
            FROM processed_invoices 
            LIMIT 10
        """
        
        # Read the SQL query directly into a Pandas DataFrame
        df = pd.read_sql_query(query, conn)
        
        print("\n" + "="*80)
        print("📊 FIRST 10 INVOICES LOADED INTO DATABASE")
        print("="*80)
        print(df.to_string(index=False))
        
        # Calculate the grand total using pure SQL
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(grand_total) FROM processed_invoices")
        total_sum = cursor.fetchone()[0]
        
        print("-" * 80)
        print(f"💰 TOTAL EXPENDITURE PROCESSED: Rs. {total_sum:,.2f}")
        print("="*80 + "\n")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_database()