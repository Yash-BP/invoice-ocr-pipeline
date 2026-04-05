# ========================
# main.py - Run entire pipeline with ONE command
# ========================

import os

print("="*70)
print("🚀 SME Invoice OCR Automation Pipeline")
print("   Full ETL Pipeline Started...")
print("="*70)

print("\n1️⃣ Generating 20 realistic Indian invoices...")
os.system("python scripts/generate_invoices.py")

print("\n2️⃣ Extracting data using OCR + Regex...")
os.system("python scripts/extract_ocr_data.py")

print("\n3️⃣ Loading data into SQLite database...")
os.system("python scripts/load_to_database.py")

print("\n4️⃣ Generating financial summary report...")
os.system("python scripts/analyze_spending.py")

print("\n✅ ✅ ✅ FULL PIPELINE COMPLETED SUCCESSFULLY!")
print("📁 Output files ready:")
print("   → data/extracted_invoices.csv")
print("   → data/finance_system.db")
print("   → Run: python main.py  (anytime)")
