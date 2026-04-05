# ========================
# main.py - One-command pipeline
# ========================

import os

print("="*60)
print("🚀 SME Invoice OCR Automation Pipeline")
print("="*60)

print("\n📌 Step 1: Generating 20 fake invoices...")
os.system("python scripts/generate_invoices.py")

print("\n📌 Step 2: Extracting data using OCR + Regex...")
os.system("python scripts/extract_ocr_data.py")

print("\n📌 Step 3: Loading data into SQLite database...")
os.system("python scripts/load_to_database.py")

print("\n📌 Step 4: Generating financial summary...")
os.system("python scripts/analyze_spending.py")

print("\n✅ Full pipeline completed successfully!")
print("📁 Check: data/extracted_invoices.csv and data/finance_system.db")
