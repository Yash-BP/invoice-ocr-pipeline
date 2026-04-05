import os
from pathlib import Path
import pdfplumber
import pandas as pd
import re

def extract_data_from_invoice(pdf_path: str) -> dict:
    """Extract data from one PDF with better error handling"""
    pdf_path = Path(pdf_path)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        # Improved regex patterns (more flexible)
        invoice_no = re.search(r"Invoice No:\s*(INV-\d{4}-\d+)", text)
        date       = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", text)
        vendor     = re.search(r"Vendor:\s*(.+?)(?:\n|$)", text)
        gst        = re.search(r"GST \(18%\):\s*INR\s*(\d+)", text)
        grand_total= re.search(r"GRAND TOTAL:\s*INR\s*(\d+)", text)

        data = {
            "Invoice_ID": invoice_no.group(1) if invoice_no else None,
            "Date": date.group(1) if date else None,
            "Vendor_Name": vendor.group(1).strip() if vendor else None,
            "Tax_Amount_INR": int(gst.group(1)) if gst else 0,
            "Total_Amount_INR": int(grand_total.group(1)) if grand_total else 0,
        }

        # Count how many fields were successfully extracted
        success_count = sum(1 for v in data.values() if v is not None and v != 0)
        data["Extraction_Success"] = round(success_count / 5 * 100, 1)

        return data

    except Exception as e:
        print(f"❌ Error reading {pdf_path.name}: {e}")
        return None


def main():
    print("🔍 Starting OCR Extraction Pipeline (Improved Version)...\n")
    
    invoice_folder = Path("raw_invoices")
    all_data = []

    pdf_files = list(invoice_folder.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF invoices to process.\n")

    for pdf_file in pdf_files:
        print(f"📄 Scanning → {pdf_file.name}")
        result = extract_data_from_invoice(pdf_file)
        if result:
            all_data.append(result)

    if not all_data:
        print("❌ No data extracted!")
        return

    # Create DataFrame and sort
    df = pd.DataFrame(all_data)
    df = df.sort_values(by="Invoice_ID")

    # Save clean CSV
    output_path = Path("data/extracted_invoices.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # Final Accuracy Report
    success_rate = df["Extraction_Success"].mean()
    print("\n" + "="*60)
    print("✅ Pipeline Complete!")
    print("="*60)
    print(f"📊 Total Invoices Processed : {len(df)}")
    print(f"📈 Average Extraction Accuracy: {success_rate:.1f}%")
    print(f"💾 Saved to: {output_path}")
    print("="*60)
    print(df[["Invoice_ID", "Vendor_Name", "Total_Amount_INR"]].head())

if __name__ == "__main__":
    main()
