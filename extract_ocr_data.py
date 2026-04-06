"""
extract_ocr_data.py  —  Step 2 of the invoice-ocr-pipeline
===========================================================
Reads each PDF in raw_invoices/, extracts financial fields via pdfplumber
+ regex, validates totals, and writes:
  • data/extracted_invoices.csv  — all records (including flagged anomalies)
  • data/failed_invoices.csv     — PDFs that could not be parsed at all

Phase 1: error handling, logging, failed_invoices.csv, env-var config.
Phase 2:
  - Data validation step: checks that grand_total ≈ subtotal + tax_amount
    (within a Rs. 1.00 floating-point tolerance).
  - Each record gains two new fields: validation_passed (bool) and
    validation_note (human-readable anomaly detail or empty string).
  - Validation summary logged at the end of extraction.
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
# Configuration
# ---------------------------------------------------------------------------
RAW_INVOICES_DIR = Path(os.getenv("RAW_INVOICES_DIR", "raw_invoices"))
EXTRACTED_CSV    = Path(os.getenv("EXTRACTED_CSV",    "data/extracted_invoices.csv"))
FAILED_CSV       = Path(os.getenv("FAILED_CSV",       "data/failed_invoices.csv"))

# Tolerance for floating-point comparison of extracted monetary values (INR).
# Regex may strip paise, so we allow up to Rs. 1.00 discrepancy.
VALIDATION_TOLERANCE = 1.00

# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module level for performance)
# ---------------------------------------------------------------------------
PATTERNS = {
    "invoice_id": re.compile(
        r"Invoice\s+No[.:\s]+([A-Z0-9\-]+)", re.IGNORECASE
    ),
    "invoice_date": re.compile(
        r"Date[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", re.IGNORECASE
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
    """Convert a comma-formatted INR string to float, or return None."""
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _match(pattern: re.Pattern, text: str) -> str | None:
    """Return the first capture group of a regex match, or None — never raises."""
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _extract_vendor(text: str) -> str | None:
    """Return the first non-empty line of extracted text (vendor name)."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_record(record: dict) -> tuple[bool, str]:
    """
    Check that grand_total ≈ subtotal + tax_amount within VALIDATION_TOLERANCE.

    Returns:
        (passed: bool, note: str)
        note is empty when passed=True; contains the discrepancy detail otherwise.
    """
    subtotal    = record.get("subtotal")
    tax_amount  = record.get("tax_amount")
    grand_total = record.get("grand_total")

    # If any field is missing we can't validate — flag as a warning, not a fail.
    if subtotal is None or tax_amount is None or grand_total is None:
        missing = [
            f for f, v in [("subtotal", subtotal),
                            ("tax_amount", tax_amount),
                            ("grand_total", grand_total)]
            if v is None
        ]
        note = f"Validation skipped — missing fields: {', '.join(missing)}"
        logger.warning("  [WARN] %s — %s", record.get("source_file", "?"), note)
        # Skipped validation is treated as passed=True to avoid false positives.
        return True, note

    expected = round(subtotal + tax_amount, 2)
    diff     = abs(grand_total - expected)

    if diff <= VALIDATION_TOLERANCE:
        return True, ""

    note = (
        f"Total mismatch: grand_total={grand_total:.2f} but "
        f"subtotal({subtotal:.2f}) + tax({tax_amount:.2f}) = {expected:.2f} "
        f"(diff={diff:.2f})"
    )
    return False, note


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: Path) -> dict:
    """
    Open one PDF, extract all text, run regex patterns, and validate totals.

    Returns a dict with keys:
        invoice_id, invoice_date, vendor_name,
        subtotal, tax_amount, grand_total,
        validation_passed, validation_note, source_file

    Raises:
        ValueError  — PDF contains no extractable text.
        Any pdfplumber / IO exception propagates to caller.
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

    # ── Phase 2: Validate totals ───────────────────────────────────────────
    passed, note = validate_record(record)
    record["validation_passed"] = int(passed)   # SQLite stores as INTEGER
    record["validation_note"]   = note

    if not passed:
        logger.warning(
            "  [ANOMALY] %s — %s", pdf_path.name, note
        )

    return record


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> list[dict]:
    """
    Process all PDFs in RAW_INVOICES_DIR.
    Writes extracted_invoices.csv and failed_invoices.csv.
    Returns the list of successfully extracted record dicts.
    """
    if not RAW_INVOICES_DIR.exists():
        logger.error(
            "Raw invoices directory not found: '%s'. "
            "Run generate_invoices.py first.",
            RAW_INVOICES_DIR,
        )
        return []

    pdf_files = sorted(RAW_INVOICES_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s.", RAW_INVOICES_DIR)
        return []

    logger.info("Found %d PDF(s) in %s — starting extraction...",
                len(pdf_files), RAW_INVOICES_DIR)

    EXTRACTED_CSV.parent.mkdir(parents=True, exist_ok=True)
    FAILED_CSV.parent.mkdir(parents=True, exist_ok=True)

    extracted_records: list[dict] = []
    failed_records:    list[dict] = []

    for pdf_path in pdf_files:
        try:
            record = extract_from_pdf(pdf_path)
            extracted_records.append(record)
            status = "OK " if record["validation_passed"] else "WARN"
            logger.info(
                "  [%s] %s → invoice_id=%-12s  total=%s",
                status,
                pdf_path.name,
                record.get("invoice_id") or "?",
                f"Rs. {record['grand_total']:,.2f}"
                if record.get("grand_total") is not None else "?",
            )
        except Exception as exc:               # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            logger.error("  [FAIL] %s — %s", pdf_path.name, reason)
            failed_records.append({"filename": pdf_path.name, "reason": reason})

    # ── Write CSVs ────────────────────────────────────────────────────────
    if extracted_records:
        df = pd.DataFrame(extracted_records)
        df.to_csv(EXTRACTED_CSV, index=False)
        logger.info("Extracted CSV written → %s  (%d rows)",
                    EXTRACTED_CSV, len(df))

        # ── Phase 2: Validation summary ───────────────────────────────────
        n_passed  = df["validation_passed"].sum()
        n_flagged = len(df) - n_passed
        logger.info(
            "Validation summary — passed: %d | flagged: %d",
            n_passed, n_flagged,
        )
        if n_flagged:
            flagged_ids = df.loc[
                df["validation_passed"] == 0, "invoice_id"
            ].tolist()
            logger.warning(
                "Flagged invoice IDs (review recommended): %s",
                ", ".join(str(i) for i in flagged_ids),
            )
    else:
        logger.warning("No records were successfully extracted.")

    if failed_records:
        with open(FAILED_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "reason"])
            writer.writeheader()
            writer.writerows(failed_records)
        logger.warning("%d PDF(s) failed — details in %s",
                       len(failed_records), FAILED_CSV)

    logger.info("Extraction complete — %d extracted, %d failed.",
                len(extracted_records), len(failed_records))
    return extracted_records


if __name__ == "__main__":
    main()