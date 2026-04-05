import os
import pdfplumber
import pandas as pd
import re

def extract_data_from_invoice(pdf_path):
    # Open the PDF and extract the raw text from the first page
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        
    # Use Regex patterns to hunt for the specific data fields
    invoice_no = re.search(r"Invoice No:\s*(INV-\d{4}-\d+)", text)
    date = re.search(r"Date:\s*(.*)", text)
    vendor = re.search(r"Vendor:\s*(.*)", text)
    gst = re.search(r"GST \(18%\):\s*INR\s*(\d+)", text)
    grand_total = re.search(r"GRAND TOTAL:\s*INR\s*(\d+)", text)

    # Return a structured dictionary
    return {
        "Invoice_ID": invoice_no.group(1) if invoice_no else None,
        "Date": date.group(1).strip() if date else None,
        "Vendor_Name": vendor.group(1).strip() if vendor else None,
        "Tax_Amount_INR": int(gst.group(1)) if gst else 0,
        "Total_Amount_INR": int(grand_total.group(1)) if grand_total else 0
    }

def main():
    print("Starting OCR Extraction Pipeline...")
    invoice_folder = 'raw_invoices'
    all_extracted_data = []

    # Loop through every PDF in our raw data folder
    for filename in os.listdir(invoice_folder):
        if filename.endswith('.pdf'):
            filepath = os.path.join(invoice_folder, filename)
            print(f"Scanning {filename}...")
            
            try:
                extracted_info = extract_data_from_invoice(filepath)
                all_extracted_data.append(extracted_info)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    # Convert our extracted data into a clean Pandas DataFrame
    df = pd.DataFrame(all_extracted_data)
    
    # Save the structured data to a CSV in our data folder
    output_path = 'data/extracted_invoices.csv'
    df.to_csv(output_path, index=False)
    
    print(f"\n✅ Pipeline Complete! Extracted data saved to {output_path}")
    print("\n--- Data Preview ---")
    print(df.head())

if __name__ == "__main__":
    main()