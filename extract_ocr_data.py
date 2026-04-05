"""
extract_ocr_data.py  —  Step 2 of the invoice-ocr-pipeline
===========================================================
Reads each PDF in raw_invoices/, extracts key financial fields using
pdfplumber + regex, and writes a clean CSV to data/extracted_invoices.csv.

Phase 1 changes:
  - Replaced all print() calls with logging.
  - Each PDF is processed in an isolated try/except block.
    A failed PDF is recorded in data/failed_invoices.csv (filename + reason)
    rather than crashing the whole run.
  - Regex matches are guarded: a missing field returns None instead of
    raising AttributeError.
  - Output directories are created automatically.
  - Paths read from environment variables with sensible defaults.
"""

import csv
import logging
import os
import re
from pathlib import Path

import pandas as pd
import pdfplumber
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("extract_ocr_data")

# ---------------------------------------------------------------------------
# Configuration  (overridable via .env)
# ---------------------------------------------------------------------------
RAW_INVOICES_DIR  = Path(os.getenv("RAW_INVOICES_DIR",  "raw_invoices"))
EXTRACTED_CSV     = Path(os.getenv("EXTRACTED_CSV",     "data/extracted_invoices.csv"))
FAILED_CSV        = Path(os.getenv("FAILED_CSV",        "data/failed_invoices.csv"))

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
# All patterns use re.IGNORECASE and are anchored as tightly as possible
# to reduce false positives on varied invoice layouts.

PATTERNS = {
    "invoice_id": re.compile(
        r"Invoice\s+No[.:\s]+([A-Z0-9\-]+)", re.IGNORECASE
    ),
    "invoice_date": re.compile(
        r"Date[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", re.IGNORECASE
    ),
    "vendor_name": re.compile(
        # First non-empty line of the document is typically the vendor.
        # Extracted separately in _extract_vendor(); pattern kept for reference.
        r"^(.+)$",
        re.MULTILINE,
    ),
    "subtotal": re.compile(
        r"Subtotal[:\s]+Rs\.?\s*([\d,]+\.?\d*)", re.IGNORECASE
    ),
    "tax_amount": re.compile(
        r"GST\s*\(?\d+%?\)?[:\s]+Rs\.?\s*([\d,]+\.?\d*)", re.IGNORECASE
    ),
    "grand_total": re.compile(
        r"Grand\s+Total[:\s]+Rs\.?\s*([\d,]+\.?\d*)", re.IGNORECASE
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: str | None) -> float | None:
    """Convert a comma-formatted string like '1,23,456.78' to float, or None."""
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _extract_vendor(text: str) -> str | None:
    """
    Return the first non-empty line of the extracted text, which in our
    ReportLab-generated invoices is always the vendor company name.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _match(pattern: re.Pattern, text: str) -> str | None:
    """Return group(1) of the first match, or None — never raises."""
    m = pattern.search(text)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: Path) -> dict:
    """
    Open a single PDF, extract all text, and run regex patterns against it.

    Returns a dict with keys:
        invoice_id, invoice_date, vendor_name,
        subtotal, tax_amount, grand_total, source_file

    Raises:
        ValueError  — if the PDF contains no extractable text.
        Any pdfplumber / IO exception propagates to the caller.
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]

    full_text = "\n".join(pages_text).strip()
    if not full_text:
        raise ValueError("No extractable text found in PDF.")

    record = {
        "invoice_id":   _match(PATTERNS["invoice_id"],   full_text),
        "invoice_date": _match(PATTERNS["invoice_date"],  full_text),
        "vendor_name":  _extract_vendor(full_text),
        "subtotal":     _safe_float(_match(PATTERNS["subtotal"],    full_text)),
        "tax_amount":   _safe_float(_match(PATTERNS["tax_amount"],  full_text)),
        "grand_total":  _safe_float(_match(PATTERNS["grand_total"], full_text)),
        "source_file":  pdf_path.name,
    }

    return record


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> list[dict]:
    """
    Process all PDFs in RAW_INVOICES_DIR.
    Writes extracted_invoices.csv and failed_invoices.csv.
    Returns the list of successfully extracted records.
    """
    if not RAW_INVOICES_DIR.exists():
        logger.error(
            "Raw invoices directory not found: %s  "
            "(Run generate_invoices.py first.)",
            RAW_INVOICES_DIR,
        )
        return []

    pdf_files = sorted(RAW_INVOICES_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s.", RAW_INVOICES_DIR)
        return []

    logger.info("Found %d PDF(s) in %s. Starting extraction...",
                len(pdf_files), RAW_INVOICES_DIR)

    # Ensure output directories exist
    EXTRACTED_CSV.parent.mkdir(parents=True, exist_ok=True)
    FAILED_CSV.parent.mkdir(parents=True, exist_ok=True)

    extracted_records: list[dict] = []
    failed_records:    list[dict] = []

    for pdf_path in pdf_files:
        try:
            record = extract_from_pdf(pdf_path)
            extracted_records.append(record)
            logger.info("  [OK]   %s → invoice_id=%s  total=%s",
                        pdf_path.name,
                        record.get("invoice_id", "?"),
                        record.get("grand_total", "?"))

        except Exception as exc:                           # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            logger.error("  [FAIL] %s — %s", pdf_path.name, reason)
            failed_records.append({"filename": pdf_path.name, "reason": reason})

    # ---- Write extracted CSV ----
    if extracted_records:
        df = pd.DataFrame(extracted_records)
        df.to_csv(EXTRACTED_CSV, index=False)
        logger.info(
            "Extraction complete — %d succeeded, %d failed.",
            len(extracted_records), len(failed_records),
        )
        logger.info("Extracted CSV written to: %s", EXTRACTED_CSV)
    else:
        logger.warning("No records were successfully extracted.")

    # ---- Write failed CSV ----
    if failed_records:
        with open(FAILED_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "reason"])
            writer.writeheader()
            writer.writerows(failed_records)
        logger.warning(
            "%d invoice(s) failed — see %s for details.",
            len(failed_records), FAILED_CSV,
        )

    return extracted_records


if __name__ == "__main__":
    main()