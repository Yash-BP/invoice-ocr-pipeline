import os
import random
from faker import Faker
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Use Indian locale for realistic local business names and addresses
fake = Faker('en_IN')

def create_fake_invoice(filename, invoice_id):
    c = canvas.Canvas(filename, pagesize=letter)
    
    # --- HEADER ---
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 750, "TAX INVOICE")

    c.setFont("Helvetica", 12)
    c.drawString(50, 710, f"Invoice No: {invoice_id}")
    c.drawString(50, 690, f"Date: {fake.date_this_year()}")
    c.drawString(50, 670, f"Vendor: {fake.company()}")
    c.drawString(50, 650, f"Address: {fake.city()}, {fake.state()}")

    # --- TABLE HEADERS ---
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 600, "Description")
    c.drawString(300, 600, "Qty")
    c.drawString(380, 600, "Unit Price")
    c.drawString(460, 600, "Total")

    # --- LINE ITEMS ---
    c.setFont("Helvetica", 12)
    y_pos = 570
    total_amount = 0
    
    # Standard IT & Office Supplies for SMEs
    services = ["Cloud Server Hosting", "Software License Renewal", "IT Consultation", "SEO Optimization", "Office Wi-Fi Setup", "Hardware Maintenance"]

    for _ in range(random.randint(2, 5)):
        item = random.choice(services)
        qty = random.randint(1, 10)
        price = random.randint(1500, 15000)
        line_total = qty * price
        total_amount += line_total

        c.drawString(50, y_pos, item)
        c.drawString(300, y_pos, str(qty))
        c.drawString(380, y_pos, f"INR {price}")
        c.drawString(460, y_pos, f"INR {line_total}")
        y_pos -= 30

    # --- TOTALS (Adding 18% GST) ---
    tax = total_amount * 0.18
    grand_total = total_amount + tax

    c.setFont("Helvetica-Bold", 12)
    c.drawString(350, y_pos - 30, "Subtotal:")
    c.drawString(460, y_pos - 30, f"INR {total_amount}")
    
    c.drawString(350, y_pos - 50, "GST (18%):")
    c.drawString(460, y_pos - 50, f"INR {int(tax)}")
    
    c.drawString(350, y_pos - 70, "GRAND TOTAL:")
    c.drawString(460, y_pos - 70, f"INR {int(grand_total)}")

    c.save()

def main():
    # Ensure the folder exists
    os.makedirs('raw_invoices', exist_ok=True)
    
    print("Generating 20 localized PDF invoices...")
    for i in range(1, 21):
        inv_id = f"INV-2026-{1000+i}"
        filename = f"raw_invoices/{inv_id}.pdf"
        create_fake_invoice(filename, inv_id)
        
    print("✅ Success! 20 raw PDFs generated in the 'raw_invoices' directory.")

if __name__ == "__main__":
    main()