"""
tests/test_extraction.py
========================
Unit tests for the regex extraction functions in extract_ocr_data.py.
Run with: pytest tests/ -v

Tests are pure (text-in → value-out) — no PDFs, DB, or filesystem needed.
"""

import pytest

# ---------------------------------------------------------------------------
# Import the functions under test directly from the scripts package.
# ---------------------------------------------------------------------------
from scripts.extract_ocr_data import (
    _match,
    _safe_float,
    _extract_vendor,
    PATTERNS,
    validate_record,
)


# ---------------------------------------------------------------------------
# Fixtures — representative OCR text blocks
# ---------------------------------------------------------------------------

FULL_INVOICE = """
Acme Technologies Pvt. Ltd.
123 Business Park, Mumbai, MH 400001
GSTIN: 27AABCU9603R1ZX

TAX INVOICE                         Invoice No: INV-00042
                                    Date: 15-08-2024

Bill To: XYZ Traders

Description        Qty   Rate       Amount
Cloud Storage       10   500.00    5000.00
IT Consulting        5   300.00    1500.00

Subtotal: Rs. 6,500.00
GST (18%): Rs. 1,170.00
Grand Total: Rs. 7,670.00

Thank you for your business. Payment due within 30 days.
"""

MINIMAL_INVOICE = """
Vendor Ltd
Invoice No: INV-00001
Date: 01-01-2024
Subtotal: Rs. 1,000.00
GST (18%): Rs. 180.00
Grand Total: Rs. 1,180.00
"""

MALFORMED_AMOUNTS = """
Quick Supply Co
Invoice No: INV-99999
Date: 10-05-2024
Subtotal: Rs. 1,00,000.00
GST (18%): Rs. 18,000.00
Grand Total: Rs. 1,18,000.00
"""

MISSING_ALL_FIELDS = """
This document has no recognisable invoice fields.
Please contact accounts@example.com for clarification.
"""

MISSING_GRAND_TOTAL = """
Partial Invoice Corp
Invoice No: INV-PARTIAL
Date: 20-03-2024
Subtotal: Rs. 5,000.00
GST (18%): Rs. 900.00
"""

MISMATCH_INVOICE = """
Bad Math Ltd
Invoice No: INV-BAD
Date: 01-06-2024
Subtotal: Rs. 1,000.00
GST (18%): Rs. 180.00
Grand Total: Rs. 2,000.00
"""


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_plain_number(self):
        assert _safe_float("1234.56") == pytest.approx(1234.56)

    def test_comma_formatted(self):
        assert _safe_float("1,234.56") == pytest.approx(1234.56)

    def test_indian_lakh_notation(self):
        assert _safe_float("1,18,000.00") == pytest.approx(118000.0)

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_non_numeric_returns_none(self):
        assert _safe_float("N/A") is None

    def test_empty_string_returns_none(self):
        assert _safe_float("") is None


# ---------------------------------------------------------------------------
# _match (invoice_id)
# ---------------------------------------------------------------------------

class TestMatchInvoiceId:
    def test_standard_format(self):
        result = _match(PATTERNS["invoice_id"], FULL_INVOICE)
        assert result == "INV-00042"

    def test_minimal_invoice(self):
        result = _match(PATTERNS["invoice_id"], MINIMAL_INVOICE)
        assert result == "INV-00001"

    def test_missing_returns_none(self):
        result = _match(PATTERNS["invoice_id"], MISSING_ALL_FIELDS)
        assert result is None

    def test_partial_invoice(self):
        result = _match(PATTERNS["invoice_id"], MISSING_GRAND_TOTAL)
        assert result == "INV-PARTIAL"


# ---------------------------------------------------------------------------
# _match (invoice_date)
# ---------------------------------------------------------------------------

class TestMatchInvoiceDate:
    def test_dd_mm_yyyy_hyphen(self):
        result = _match(PATTERNS["invoice_date"], FULL_INVOICE)
        assert result == "15-08-2024"

    def test_minimal_date(self):
        result = _match(PATTERNS["invoice_date"], MINIMAL_INVOICE)
        assert result == "01-01-2024"

    def test_missing_returns_none(self):
        result = _match(PATTERNS["invoice_date"], MISSING_ALL_FIELDS)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_vendor
# ---------------------------------------------------------------------------

class TestExtractVendor:
    def test_first_line_is_vendor(self):
        result = _extract_vendor(FULL_INVOICE)
        assert result == "Acme Technologies Pvt. Ltd."

    def test_minimal_vendor(self):
        result = _extract_vendor(MINIMAL_INVOICE)
        assert result == "Vendor Ltd"

    def test_empty_document_returns_none(self):
        result = _extract_vendor("   \n   \n   ")
        assert result is None


# ---------------------------------------------------------------------------
# _match (subtotal)
# ---------------------------------------------------------------------------

class TestMatchSubtotal:
    def test_standard(self):
        raw = _match(PATTERNS["subtotal"], FULL_INVOICE)
        assert _safe_float(raw) == pytest.approx(6500.00)

    def test_indian_lakh_format(self):
        raw = _match(PATTERNS["subtotal"], MALFORMED_AMOUNTS)
        assert _safe_float(raw) == pytest.approx(100000.00)

    def test_missing_returns_none(self):
        assert _match(PATTERNS["subtotal"], MISSING_ALL_FIELDS) is None


# ---------------------------------------------------------------------------
# _match (grand_total)
# ---------------------------------------------------------------------------

class TestMatchGrandTotal:
    def test_standard(self):
        raw = _match(PATTERNS["grand_total"], FULL_INVOICE)
        assert _safe_float(raw) == pytest.approx(7670.00)

    def test_missing_returns_none(self):
        assert _match(PATTERNS["grand_total"], MISSING_GRAND_TOTAL) is None

    def test_indian_lakh_format(self):
        raw = _match(PATTERNS["grand_total"], MALFORMED_AMOUNTS)
        assert _safe_float(raw) == pytest.approx(118000.00)


# ---------------------------------------------------------------------------
# validate_record
# ---------------------------------------------------------------------------

class TestValidateRecord:
    def _make_record(self, subtotal, tax, grand):
        return {
            "subtotal": subtotal,
            "tax_amount": tax,
            "grand_total": grand,
            "source_file": "test.pdf",
        }

    def test_valid_totals_pass(self):
        record = self._make_record(6500.00, 1170.00, 7670.00)
        passed, note = validate_record(record)
        assert passed is True
        assert note == ""

    def test_mismatch_fails(self):
        record = self._make_record(1000.00, 180.00, 2000.00)
        passed, note = validate_record(record)
        assert passed is False
        assert "mismatch" in note.lower()

    def test_within_tolerance_passes(self):
        # Rs. 0.50 rounding difference — within the Rs. 1.00 tolerance
        record = self._make_record(1000.00, 180.00, 1180.50)
        passed, _ = validate_record(record)
        assert passed is True

    def test_missing_subtotal_skips_not_fails(self):
        record = self._make_record(None, 180.00, 1180.00)
        passed, note = validate_record(record)
        # Missing field → validation skipped, treated as passed=True
        assert passed is True
        assert "missing" in note.lower()

    def test_all_missing_skips(self):
        record = self._make_record(None, None, None)
        passed, note = validate_record(record)
        assert passed is True
        assert "missing" in note.lower()