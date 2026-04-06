import pytest
from scripts.extract_ocr_data import _safe_float, validate_record, _extract_vendor, PATTERNS, _match

def test_safe_float():
    assert _safe_float("1,18,000.50") == 118000.50
    assert _safe_float("500") == 500.0
    assert _safe_float(None) is None

def test_validate_record_success():
    record = {"subtotal": 1000.0, "tax_amount": 180.0, "grand_total": 1180.0}
    passed, note = validate_record(record)
    assert passed is True
    assert note == ""

def test_validate_record_tolerance():
    record = {"subtotal": 1000.0, "tax_amount": 180.0, "grand_total": 1180.50}
    passed, note = validate_record(record)
    assert passed is True

def test_validate_record_failure():
    record = {"subtotal": 1000.0, "tax_amount": 180.0, "grand_total": 1500.0}
    passed, note = validate_record(record)
    assert passed is False
    assert "Total mismatch" in note

def test_validate_record_missing_fields():
    record = {"subtotal": 1000.0, "tax_amount": None, "grand_total": 1180.0}
    passed, note = validate_record(record)
    assert passed is True 
    assert "Validation skipped" in note

def test_extract_vendor():
    text = "\n\n   Acme Corp   \n123 Street\n"
    assert _extract_vendor(text) == "Acme Corp"

def test_regex_invoice_id():
    text = "Tax Invoice\nInvoice No: INV-12345\nDate: 12-10-2023"
    assert _match(PATTERNS["invoice_id"], text) == "INV-12345"

def test_regex_grand_total():
    text = "Subtotal: Rs. 500\nGST (18%): Rs. 90\nGrand Total: Rs. 590.00"
    assert _match(PATTERNS["grand_total"], text) == "590.00"