"""
tests/test_extraction.py
========================
Unit tests for the extraction logic in scripts/extract_ocr_data.py.

Tests use hardcoded invoice text strings that mirror real Indian invoice
formats from Tally, Zoho Books, Vyapar, and manually-typed invoices.
No PDFs are required — tests run in milliseconds.

Run:
    pytest tests/ -v
"""

import sys
from pathlib import Path

# Add project root to path so imports work without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.extract_ocr_data import (
    _first_match,
    _extract_all_tax_components,
    _extract_vendor,
    _safe_float,
    _validate,
    InvoiceRecord,
    _INVOICE_ID_PATTERNS,
    _DATE_PATTERNS,
    _GRAND_TOTAL_PATTERNS,
    _SUBTOTAL_PATTERNS,
)


# =============================================================================
# _safe_float
# =============================================================================

class TestSafeFloat:
    def test_plain_number(self):
        assert _safe_float("1234.56") == 1234.56

    def test_comma_formatted_western(self):
        assert _safe_float("1,234.56") == 1234.56

    def test_comma_formatted_lakh(self):
        # Indian lakh format: 1,23,456.78
        assert _safe_float("1,23,456.78") == 123456.78

    def test_none_input(self):
        assert _safe_float(None) is None

    def test_empty_string(self):
        assert _safe_float("") is None

    def test_non_numeric(self):
        assert _safe_float("N/A") is None

    def test_integer_string(self):
        assert _safe_float("50000") == 50000.0


# =============================================================================
# Invoice ID extraction
# =============================================================================

class TestInvoiceIdExtraction:
    def test_standard_format(self):
        text = "Invoice No: INV-00042\nDate: 12-03-2024"
        val, conf = _first_match(_INVOICE_ID_PATTERNS, text)
        assert val == "INV-00042"
        assert conf == "HIGH"

    def test_tally_format(self):
        text = "Tax Invoice No.: 2024-25/GST/0042"
        val, conf = _first_match(_INVOICE_ID_PATTERNS, text)
        assert val is not None
        assert "2024" in val or "0042" in val

    def test_hash_format(self):
        text = "Invoice # TXN/2024/00199"
        val, conf = _first_match(_INVOICE_ID_PATTERNS, text)
        assert val is not None

    def test_bill_number_format(self):
        text = "Bill No.: BL-2024-001"
        val, conf = _first_match(_INVOICE_ID_PATTERNS, text)
        assert val is not None
        assert conf == "LOW"   # not first pattern → LOW confidence

    def test_no_invoice_id(self):
        text = "This document has no invoice number at all."
        val, conf = _first_match(_INVOICE_ID_PATTERNS, text)
        assert val is None
        assert conf == "MISSING"


# =============================================================================
# Date extraction
# =============================================================================

class TestDateExtraction:
    def test_dd_mm_yyyy_dash(self):
        text = "Invoice Date: 12-03-2024"
        val, conf = _first_match(_DATE_PATTERNS, text)
        assert val == "12-03-2024"
        assert conf == "HIGH"

    def test_dd_mm_yyyy_slash(self):
        text = "Date: 05/11/2023"
        val, conf = _first_match(_DATE_PATTERNS, text)
        assert "05" in val and "11" in val

    def test_written_date(self):
        text = "Invoice Date: 12 March 2024"
        val, conf = _first_match(_DATE_PATTERNS, text)
        assert val is not None
        assert "March" in val or "12" in val

    def test_no_date(self):
        text = "Invoice No: INV-001\nVendor: ABC Ltd"
        val, conf = _first_match(_DATE_PATTERNS, text)
        # Bare date pattern may or may not match — just confirm no crash
        assert conf in ("HIGH", "LOW", "MISSING")


# =============================================================================
# GST extraction — the most important set of tests
# =============================================================================

class TestGSTExtraction:
    def test_single_gst_line(self):
        """Standard generated invoice format."""
        text = "Subtotal: Rs. 50,000.00\nGST (18%): Rs. 9,000.00\nGrand Total: Rs. 59,000.00"
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert total == 9000.0
        assert conf in ("HIGH", "LOW")

    def test_cgst_plus_sgst_split(self):
        """Tally / Zoho Books intra-state invoice: GST split into CGST 9% + SGST 9%."""
        text = (
            "Taxable Value: Rs. 50,000.00\n"
            "CGST @ 9%: Rs. 4,500.00\n"
            "SGST @ 9%: Rs. 4,500.00\n"
            "Total Amount Due: Rs. 59,000.00"
        )
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert cgst == 4500.0
        assert sgst == 4500.0
        assert igst is None
        assert total == 9000.0
        assert conf == "HIGH"   # 2 components found → HIGH

    def test_igst_inter_state(self):
        """Inter-state invoice: single IGST line instead of CGST+SGST."""
        text = (
            "Taxable Value: Rs. 1,00,000.00\n"
            "IGST @ 18%: Rs. 18,000.00\n"
            "Grand Total: Rs. 1,18,000.00"
        )
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert igst == 18000.0
        assert cgst is None
        assert sgst is None
        assert total == 18000.0

    def test_multiple_tax_slabs(self):
        """Invoice with items at different GST rates (5% and 18%)."""
        text = (
            "CGST @ 2.5%: Rs. 500.00\n"
            "SGST @ 2.5%: Rs. 500.00\n"
            "CGST @ 9%: Rs. 2,700.00\n"
            "SGST @ 9%: Rs. 2,700.00\n"
            "Grand Total: Rs. 36,400.00"
        )
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert cgst == 3200.0   # 500 + 2700
        assert sgst == 3200.0   # 500 + 2700
        assert total == 6400.0

    def test_no_tax_lines(self):
        """Invoice text with no recognisable tax lines."""
        text = "Invoice No: 001\nAmount: Rs. 5,000\nDate: 01-01-2024"
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert total == 0.0
        assert conf == "MISSING"

    def test_tax_amount_label(self):
        """Vyapar format: 'Tax Amount' instead of CGST/SGST."""
        text = "Sub Total: 25000.00\nTax Amount: 4500.00\nTotal: 29500.00"
        cgst, sgst, igst, total, conf = _extract_all_tax_components(text)
        assert total == 4500.0


# =============================================================================
# Grand total extraction
# =============================================================================

class TestGrandTotalExtraction:
    def test_standard_grand_total(self):
        text = "Grand Total: Rs. 59,000.00"
        val, conf = _first_match(_GRAND_TOTAL_PATTERNS, text)
        assert _safe_float(val) == 59000.0
        assert conf == "HIGH"

    def test_amount_due_format(self):
        text = "Total Amount Due: Rs. 1,18,000.00"
        val, conf = _first_match(_GRAND_TOTAL_PATTERNS, text)
        assert _safe_float(val) == 118000.0

    def test_net_payable_format(self):
        text = "Net Payable: Rs. 29,500.00"
        val, conf = _first_match(_GRAND_TOTAL_PATTERNS, text)
        assert _safe_float(val) == 29500.0

    def test_rupee_symbol(self):
        text = "Grand Total: ₹59,000.00"
        val, conf = _first_match(_GRAND_TOTAL_PATTERNS, text)
        assert _safe_float(val) == 59000.0


# =============================================================================
# Vendor name extraction
# =============================================================================

class TestVendorExtraction:
    def test_company_name_first_line(self):
        text = "Reliance Industries Ltd\nGSTIN: 27AAACR5055K1Z5\nInvoice No: 001"
        name, conf = _extract_vendor(text)
        assert name == "Reliance Industries Ltd"
        assert conf == "HIGH"

    def test_skips_invoice_keyword(self):
        text = "TAX INVOICE\nABC Private Limited\nGSTIN: 29AABCU9603R1ZP"
        name, conf = _extract_vendor(text)
        # Should skip "TAX INVOICE" and return the company name
        assert name == "ABC Private Limited"

    def test_skips_numeric_lines(self):
        text = "12345\nABC Traders\nGSTIN: ..."
        name, conf = _extract_vendor(text)
        assert name == "ABC Traders"


# =============================================================================
# Validation
# =============================================================================

class TestValidation:
    def _make_record(self, sub, tax, total) -> InvoiceRecord:
        r = InvoiceRecord()
        r.subtotal    = sub
        r.tax_amount  = tax
        r.grand_total = total
        return r

    def test_valid_totals(self):
        r = self._make_record(50000.0, 9000.0, 59000.0)
        passed, note = _validate(r)
        assert passed == 1
        assert note == ""

    def test_valid_with_float_rounding(self):
        # 0.1 + 0.2 float issue — tolerance should absorb this
        r = self._make_record(10000.01, 1800.00, 11800.00)
        passed, note = _validate(r)
        assert passed == 1

    def test_mismatch_flagged(self):
        r = self._make_record(50000.0, 9000.0, 60000.0)   # off by Rs. 1000
        passed, note = _validate(r)
        assert passed == 0
        assert "mismatch" in note.lower()

    def test_missing_field_skips_validation(self):
        r = self._make_record(50000.0, None, 59000.0)
        passed, note = _validate(r)
        assert passed == 1   # skipped, not failed
        assert "skipped" in note.lower()