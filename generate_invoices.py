"""
generate_invoices.py  —  Step 1 of the invoice-ocr-pipeline
============================================================
Generates a configurable number of realistic Indian GST invoices as PDFs
using Faker (en_IN locale) and ReportLab.

Phase 1 changes:
  - Replaced all print() calls with logging.
  - Wrapped the entire generation loop in try/except so a single bad invoice
    never kills the whole batch.
  - Output directory is created automatically if it does not exist.
  - Invoice count and output directory read from environment variables
    (with sensible defaults) — groundwork for Phase 3 config management.
"""

import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from faker import Faker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_invoices")

fake = Faker("en_IN")

# ---------------------------------------------------------------------------
# Configuration  (overridable via .env)
# ---------------------------------------------------------------------------
OUTPUT_DIR     = Path(os.getenv("RAW_INVOICES_DIR", "raw_invoices"))
INVOICE_COUNT  = int(os.getenv("INVOICE_COUNT", "20"))
GST_RATE       = 0.18

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_date(start_year: int = 2023, end_year: int = 2024) -> str:
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    delta = end - start
    random_day = start + timedelta(days=random.randint(0, delta.days))
    return random_day.strftime("%d-%m-%Y")


def _random_line_items(n: int = 3) -> list[dict]:
    products = [
        "Cloud Storage Services", "Software Licensing", "IT Consulting",
        "Network Equipment", "Cyber Security Audit", "Data Backup Solution",
        "Hardware Maintenance", "Training Services", "Domain Registration",
        "Technical Support",
    ]
    items = []
    for _ in range(n):
        qty        = random.randint(1, 20)
        unit_price = round(random.uniform(500, 15000), 2)
        items.append({
            "description": random.choice(products),
            "quantity":    qty,
            "unit_price":  unit_price,
            "amount":      round(qty * unit_price, 2),
        })
    return items


def _format_inr(value: float) -> str:
    return f"Rs. {value:,.2f}"


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

def generate_invoice(invoice_number: int, output_dir: Path) -> Path:
    """
    Generate a single PDF invoice and write it to output_dir.
    Returns the Path of the created file.
    Raises on any ReportLab or I/O error so the caller can handle it.
    """
    invoice_id  = f"INV-{invoice_number:05d}"
    vendor_name = fake.company()
    vendor_addr = fake.address().replace("\n", ", ")
    buyer_name  = fake.company()
    buyer_addr  = fake.address().replace("\n", ", ")
    invoice_date = _random_date()
    gstin        = fake.bothify(text="##?????#####???#", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    line_items   = _random_line_items(n=random.randint(2, 5))
    subtotal     = round(sum(item["amount"] for item in line_items), 2)
    tax_amount   = round(subtotal * GST_RATE, 2)
    grand_total  = round(subtotal + tax_amount, 2)

    # ---- Build the PDF ----
    filename    = output_dir / f"{invoice_id}.pdf"
    doc         = SimpleDocTemplate(str(filename), pagesize=A4,
                                    rightMargin=1.5*cm, leftMargin=1.5*cm,
                                    topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles      = getSampleStyleSheet()
    bold_style  = ParagraphStyle("Bold", parent=styles["Normal"],
                                 fontName="Helvetica-Bold", fontSize=10)
    normal_style = styles["Normal"]
    normal_style.fontSize = 9

    story = []

    # Header
    story.append(Paragraph(vendor_name, ParagraphStyle(
        "Header", parent=styles["Title"], fontSize=16, spaceAfter=4)))
    story.append(Paragraph(vendor_addr, normal_style))
    story.append(Paragraph(f"GSTIN: {gstin}", normal_style))
    story.append(Spacer(1, 0.4*cm))

    # Invoice meta
    meta_data = [
        ["TAX INVOICE", "", f"Invoice No: {invoice_id}"],
        ["",            "", f"Date: {invoice_date}"],
    ]
    meta_table = Table(meta_data, colWidths=[5*cm, 6*cm, 6*cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 10),
        ("ALIGN",     (2, 0), (2, -1), "RIGHT"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.3*cm))

    # Bill To
    story.append(Paragraph("Bill To:", bold_style))
    story.append(Paragraph(buyer_name, normal_style))
    story.append(Paragraph(buyer_addr, normal_style))
    story.append(Spacer(1, 0.4*cm))

    # Line items table
    table_data = [["Description", "Qty", "Unit Price (Rs.)", "Amount (Rs.)"]]
    for item in line_items:
        table_data.append([
            item["description"],
            str(item["quantity"]),
            f"{item['unit_price']:,.2f}",
            f"{item['amount']:,.2f}",
        ])

    items_table = Table(table_data,
                        colWidths=[9*cm, 2*cm, 4*cm, 4*cm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("ALIGN",        (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f3f4")]),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#bdc3c7")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.3*cm))

    # Totals
    totals_data = [
        ["", "Subtotal:",           _format_inr(subtotal)],
        ["", f"GST ({int(GST_RATE*100)}%):", _format_inr(tax_amount)],
        ["", "Grand Total:",        _format_inr(grand_total)],
    ]
    totals_table = Table(totals_data, colWidths=[9*cm, 4*cm, 4*cm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME",  (1, 2), (2, 2), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("ALIGN",     (2, 0), (2, -1), "RIGHT"),
        ("LINEABOVE", (1, 2), (2, 2), 0.5, colors.black),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 0.6*cm))

    # Footer
    story.append(Paragraph(
        "Thank you for your business. Payment due within 30 days.",
        ParagraphStyle("Footer", parent=normal_style,
                       textColor=colors.HexColor("#7f8c8d"), fontSize=8)
    ))

    doc.build(story)
    return filename


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting invoice generation — target: %d invoices → %s",
                INVOICE_COUNT, OUTPUT_DIR)

    success_count = 0
    failure_count = 0

    for i in range(1, INVOICE_COUNT + 1):
        try:
            path = generate_invoice(i, OUTPUT_DIR)
            logger.info("  [OK] Generated %s", path.name)
            success_count += 1
        except Exception as exc:                          # noqa: BLE001
            logger.error("  [FAIL] Invoice %05d — %s: %s",
                         i, type(exc).__name__, exc)
            failure_count += 1

    logger.info(
        "Generation complete — %d succeeded, %d failed.",
        success_count, failure_count,
    )


if __name__ == "__main__":
    main()