"""
extract_ocr_data.py  —  Step 2 of the invoice-ocr-pipeline
===========================================================
Real-world extraction engine that handles:
  • Text-layer PDFs (pdfplumber — fast, no dependencies)
  • Scanned / image PDFs (pytesseract OCR — fallback when text layer is empty)
  • Indian GST split: CGST + SGST (intra-state) and IGST (inter-state)
  • Multiple invoice number, date, total, and vendor label formats
  • Per-field confidence scoring: HIGH / LOW / MISSING
  • Total validation: grand_total ≈ subtotal + tax_amount

Outputs:
  • data/extracted_invoices.csv  — all records (flagged anomalies included)
  • data/failed_invoices.csv     — PDFs that could not be parsed at all
"""

import csv
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd
import pdfplumber
from dotenv import load_dotenv

# Optional: pytesseract for scanned PDFs. Gracefully skipped if not installed.
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

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
RAW_INVOICES_DIR  = Path(os.getenv("RAW_INVOICES_DIR",  "raw_invoices"))
EXTRACTED_CSV     = Path(os.getenv("EXTRACTED_CSV",     "data/extracted_invoices.csv"))
FAILED_CSV        = Path(os.getenv("FAILED_CSV",        "data/failed_invoices.csv"))
VALIDATION_TOLERANCE = 1.00   # Rs. tolerance for float comparison

# ---------------------------------------------------------------------------
# Regex pattern banks
# Each list is tried IN ORDER. First match wins.
# Supports: Tally, Zoho Books, Vyapar, Busy, and manually-typed formats.
# ---------------------------------------------------------------------------

# Invoice ID patterns
_INVOICE_ID_PATTERNS = [
    re.compile(r"Invoice\s+No\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]+)", re.I),
    re.compile(r"Tax\s+Invoice\s+No\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]+)", re.I),
    re.compile(r"Invoice\s*#\s*([A-Z0-9][A-Z0-9\-/]+)", re.I),
    re.compile(r"Bill\s+No\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]+)", re.I),
    re.compile(r"Ref\.?\s+No\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]+)", re.I),
]

# Date patterns — ordered from most to least specific
_DATE_PATTERNS = [
    re.compile(r"(?:Invoice\s+)?Date\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", re.I),
    re.compile(r"(?:Invoice\s+)?Date\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})", re.I),  # "12 March 2024"
    re.compile(r"Dated?\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", re.I),
    re.compile(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})\b"),                          # bare DD/MM/YYYY
]

# Subtotal / pre-tax amount patterns
_SUBTOTAL_PATTERNS = [
    re.compile(r"Sub[\s\-]?Total\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Total\s+Before\s+Tax\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Taxable\s+(?:Value|Amount)\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Amount\s+Before\s+(?:Tax|GST)\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Subtotal\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
]

# Grand total patterns
_GRAND_TOTAL_PATTERNS = [
    re.compile(r"Grand\s+Total\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Total\s+Amount\s+(?:Due|Payable)\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Net\s+(?:Amount\s+)?(?:Payable|Due)\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Amount\s+Payable\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Total\s+(?:Bill|Invoice)\s+Amount\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"(?:^|\n)\s*Total\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)\s*$", re.I | re.M),
]

# GST component patterns — handles CGST+SGST split AND single IGST/GST line
_TAX_COMPONENT_PATTERNS = [
    # IGST (inter-state) — single line
    re.compile(r"IGST\s*@?\s*\d+\.?\d*\s*%?\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    # CGST (intra-state, half of total GST)
    re.compile(r"CGST\s*@?\s*\d+\.?\d*\s*%?\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    # SGST / UTGST (intra-state, other half)
    re.compile(r"[SU]TGST\s*@?\s*\d+\.?\d*\s*%?\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"SGST\s*@?\s*\d+\.?\d*\s*%?\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    # Generic GST/Tax line (fallback)
    re.compile(r"GST\s*\(?\d+\.?\d*\s*%?\)?\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Tax\s+Amount\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Output\s+Tax\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", re.I),
]

# Vendor name: lines to skip when scanning for the company name
_SKIP_VENDOR_TOKENS = {
    "tax invoice", "invoice", "gstin", "bill", "receipt",
    "original", "duplicate", "triplicate", "copy", "page",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class InvoiceRecord:
    """One extracted invoice. Confidence: HIGH / LOW / MISSING per field."""
    invoice_id:              str | None = None
    invoice_id_confidence:   str = "MISSING"
    invoice_date:            str | None = None
    invoice_date_confidence: str = "MISSING"
    vendor_name:             str | None = None
    vendor_name_confidence:  str = "MISSING"
    subtotal:                float | None = None
    subtotal_confidence:     str = "MISSING"
    tax_amount:              float | None = None
    tax_amount_confidence:   str = "MISSING"
    cgst:                    float | None = None
    sgst:                    float | None = None
    igst:                    float | None = None
    grand_total:             float | None = None
    grand_total_confidence:  str = "MISSING"
    extraction_method:       str = "text_layer"   # text_layer | ocr
    validation_passed:       int = 1
    validation_note:         str = ""
    source_file:             str = ""

    def overall_confidence(self) -> str:
        """Aggregate confidence across core financial fields."""
        scores = {
            "HIGH": 2, "LOW": 1, "MISSING": 0
        }
        core = [
            self.invoice_id_confidence,
            self.grand_total_confidence,
            self.tax_amount_confidence,
        ]
        total = sum(scores.get(c, 0) for c in core)
        if total >= 5:   return "HIGH"
        if total >= 3:   return "LOW"
        return "MISSING"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: str | None) -> float | None:
    """Convert comma-formatted INR string ('1,23,456.78') to float."""
    if value is None:
        return None
    try:
        cleaned = value.replace(",", "").strip()
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _first_match(patterns: list[re.Pattern], text: str) -> tuple[str | None, str]:
    """
    Try each pattern in order. Return (matched_string, confidence).
    First pattern that matches → HIGH confidence.
    Any subsequent pattern that matches → LOW confidence.
    No match → (None, MISSING).
    """
    for i, pat in enumerate(patterns):
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            confidence = "HIGH" if i == 0 else "LOW"
            return val, confidence
    return None, "MISSING"


def _extract_all_tax_components(text: str) -> tuple[float | None, float | None, float | None, float, str]:
    """
    Find every CGST, SGST, IGST, and generic GST/Tax line in the text.
    Sum all components to get total_tax.

    Returns: (cgst, sgst, igst, total_tax, confidence)
    """
    cgst = sgst = igst = None
    generic_tax = 0.0
    components_found = 0

    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # CGST
        m = _TAX_COMPONENT_PATTERNS[1].search(line_stripped)
        if m:
            val = _safe_float(m.group(1))
            if val is not None:
                cgst = (cgst or 0) + val
                components_found += 1
            continue

        # SGST / UTGST
        m = _TAX_COMPONENT_PATTERNS[2].search(line_stripped) or \
            _TAX_COMPONENT_PATTERNS[3].search(line_stripped)
        if m:
            val = _safe_float(m.group(1))
            if val is not None:
                sgst = (sgst or 0) + val
                components_found += 1
            continue

        # IGST
        m = _TAX_COMPONENT_PATTERNS[0].search(line_stripped)
        if m:
            val = _safe_float(m.group(1))
            if val is not None:
                igst = (igst or 0) + val
                components_found += 1
            continue

    # Generic fallback — only use if no components found above
    if components_found == 0:
        for pat in _TAX_COMPONENT_PATTERNS[4:]:
            m = pat.search(text)
            if m:
                val = _safe_float(m.group(1))
                if val is not None:
                    generic_tax = val
                    components_found += 1
                    break

    # Sum all found components
    total = 0.0
    if cgst      is not None: total += cgst
    if sgst      is not None: total += sgst
    if igst      is not None: total += igst
    if not (cgst or sgst or igst): total += generic_tax

    if components_found == 0:
        return None, None, None, 0.0, "MISSING"

    confidence = "HIGH" if components_found >= 2 else "LOW"
    return cgst, sgst, igst, round(total, 2), confidence


def _extract_vendor(text: str) -> tuple[str | None, str]:
    """
    Find the vendor name: first non-empty line that is not a known
    invoice keyword, is not all digits, and is at least 3 characters.
    """
    for line in text.splitlines()[:15]:   # vendor is always near the top
        stripped = line.strip()
        if not stripped or len(stripped) < 3:
            continue
        lower = stripped.lower()
        if any(token in lower for token in _SKIP_VENDOR_TOKENS):
            continue
        if stripped.replace(" ", "").isdigit():
            continue
        # Heuristic: company names often contain letters
        if re.search(r"[A-Za-z]", stripped):
            confidence = "HIGH" if len(stripped) > 5 else "LOW"
            return stripped, confidence
    return None, "MISSING"

# ---------------------------------------------------------------------------
# Text extraction (two strategies)
# ---------------------------------------------------------------------------

def _extract_text_via_pdfplumber(pdf_path: Path) -> str:
    """Extract text from the PDF's text layer. Fast. Returns "" if image-only."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def _extract_text_via_ocr(pdf_path: Path) -> str:
    """
    Rasterise each PDF page and run Tesseract OCR.
    Only called when pdfplumber returns empty text (scanned invoice).
    Requires: pip install pdf2image pytesseract  +  Tesseract system binary.
    """
    if not OCR_AVAILABLE:
        raise RuntimeError(
            "OCR fallback requires pdf2image and pytesseract. "
            "Install with: pip install pdf2image pytesseract\n"
            "Then install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
        )
    images = convert_from_path(str(pdf_path), dpi=300)
    pages  = [pytesseract.image_to_string(img, lang="eng") for img in images]
    return "\n".join(pages).strip()

# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: Path) -> InvoiceRecord:
    """
    Extract all fields from one PDF using a two-strategy approach:
      1. pdfplumber (text layer) — fast, accurate when text is embedded
      2. pytesseract OCR          — fallback for scanned/image PDFs

    Returns a populated InvoiceRecord. Never raises — caller handles exceptions.
    """
    record = InvoiceRecord(source_file=pdf_path.name)

    # ── Strategy 1: text layer ─────────────────────────────────────────────
    text = _extract_text_via_pdfplumber(pdf_path)

    if not text:
        # ── Strategy 2: OCR fallback ───────────────────────────────────────
        logger.info("  [OCR]  %s — text layer empty, trying OCR...", pdf_path.name)
        try:
            text = _extract_text_via_ocr(pdf_path)
            record.extraction_method = "ocr"
        except RuntimeError as exc:
            logger.warning("  [OCR]  %s — %s", pdf_path.name, exc)
            raise ValueError(
                "No extractable text and OCR is not installed. "
                "See logs for setup instructions."
            ) from exc

    if not text:
        raise ValueError("PDF produced no text even after OCR attempt.")

    # ── Invoice ID ─────────────────────────────────────────────────────────
    raw, conf = _first_match(_INVOICE_ID_PATTERNS, text)
    record.invoice_id            = raw
    record.invoice_id_confidence = conf

    # ── Date ───────────────────────────────────────────────────────────────
    raw, conf = _first_match(_DATE_PATTERNS, text)
    record.invoice_date            = raw
    record.invoice_date_confidence = conf

    # ── Vendor name ────────────────────────────────────────────────────────
    name, conf = _extract_vendor(text)
    record.vendor_name            = name
    record.vendor_name_confidence = conf

    # ── Subtotal ───────────────────────────────────────────────────────────
    raw, conf = _first_match(_SUBTOTAL_PATTERNS, text)
    record.subtotal            = _safe_float(raw)
    record.subtotal_confidence = conf if record.subtotal is not None else "MISSING"

    # ── Tax — CGST/SGST/IGST aware ─────────────────────────────────────────
    cgst, sgst, igst, total_tax, conf = _extract_all_tax_components(text)
    record.cgst               = cgst
    record.sgst               = sgst
    record.igst               = igst
    record.tax_amount         = total_tax if total_tax else None
    record.tax_amount_confidence = conf

    # ── Grand total ────────────────────────────────────────────────────────
    raw, conf = _first_match(_GRAND_TOTAL_PATTERNS, text)
    record.grand_total            = _safe_float(raw)
    record.grand_total_confidence = conf if record.grand_total is not None else "MISSING"

    # ── Validation ─────────────────────────────────────────────────────────
    record.validation_passed, record.validation_note = _validate(record)

    return record


def _validate(record: InvoiceRecord) -> tuple[int, str]:
    """
    Check grand_total ≈ subtotal + tax_amount.
    Returns (1, "") on pass, (0, reason) on fail.
    """
    sub = record.subtotal
    tax = record.tax_amount
    tot = record.grand_total

    if sub is None or tax is None or tot is None:
        missing = [
            name for name, val in
            [("subtotal", sub), ("tax_amount", tax), ("grand_total", tot)]
            if val is None
        ]
        return 1, f"Validation skipped — missing: {', '.join(missing)}"

    expected = round(sub + tax, 2)
    diff     = abs(tot - expected)
    if diff <= VALIDATION_TOLERANCE:
        return 1, ""

    return 0, (
        f"Total mismatch: grand_total={tot:.2f}, "
        f"subtotal({sub:.2f}) + tax({tax:.2f}) = {expected:.2f}, "
        f"diff={diff:.2f}"
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> list[dict]:
    """
    Process all PDFs in RAW_INVOICES_DIR.
    Returns list of extracted record dicts (used by run_pipeline.py).
    """
    if not RAW_INVOICES_DIR.exists():
        logger.error(
            "Directory not found: '%s'. Run generate_invoices.py first.",
            RAW_INVOICES_DIR,
        )
        return []

    pdf_files = sorted(RAW_INVOICES_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s.", RAW_INVOICES_DIR)
        return []

    logger.info("Found %d PDF(s) → starting extraction", len(pdf_files))
    EXTRACTED_CSV.parent.mkdir(parents=True, exist_ok=True)

    extracted: list[InvoiceRecord] = []
    failed:    list[dict]          = []

    for pdf_path in pdf_files:
        try:
            record = extract_from_pdf(pdf_path)
            extracted.append(record)

            conf   = record.overall_confidence()
            status = "OK  " if record.validation_passed else "WARN"
            logger.info(
                "  [%s] %-20s  id=%-14s  total=%-12s  tax=%-10s  conf=%s  via=%s",
                status,
                pdf_path.name,
                record.invoice_id or "?",
                f"Rs.{record.grand_total:,.2f}" if record.grand_total else "?",
                f"Rs.{record.tax_amount:,.2f}"  if record.tax_amount  else "?",
                conf,
                record.extraction_method,
            )
            if not record.validation_passed:
                logger.warning("  [ANOMALY] %s — %s",
                               pdf_path.name, record.validation_note)

        except Exception as exc:               # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"
            logger.error("  [FAIL] %s — %s", pdf_path.name, reason)
            failed.append({"filename": pdf_path.name, "reason": reason})

    # ── Write CSV ─────────────────────────────────────────────────────────
    extracted_dicts = [asdict(r) for r in extracted]
    if extracted_dicts:
        df = pd.DataFrame(extracted_dicts)
        df.to_csv(EXTRACTED_CSV, index=False)

        # Observability summary
        n_high    = sum(1 for r in extracted if r.overall_confidence() == "HIGH")
        n_low     = sum(1 for r in extracted if r.overall_confidence() == "LOW")
        n_missing = sum(1 for r in extracted if r.overall_confidence() == "MISSING")
        n_flagged = sum(1 for r in extracted if not r.validation_passed)
        n_ocr     = sum(1 for r in extracted if r.extraction_method == "ocr")

        logger.info("─" * 62)
        logger.info("Extraction summary")
        logger.info("  Total processed : %d", len(extracted))
        logger.info("  Confidence HIGH : %d", n_high)
        logger.info("  Confidence LOW  : %d", n_low)
        logger.info("  Confidence MISS : %d", n_missing)
        logger.info("  Flagged (total mismatch): %d", n_flagged)
        logger.info("  Used OCR fallback        : %d", n_ocr)
        logger.info("  Failed (unreadable)      : %d", len(failed))
        logger.info("  Output → %s", EXTRACTED_CSV)
        logger.info("─" * 62)
    else:
        logger.warning("No records extracted.")

    # ── Write failed CSV ──────────────────────────────────────────────────
    if failed:
        with open(FAILED_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "reason"])
            writer.writeheader()
            writer.writerows(failed)
        logger.warning("%d PDF(s) failed — see %s", len(failed), FAILED_CSV)

    return extracted_dicts


if __name__ == "__main__":
    main()