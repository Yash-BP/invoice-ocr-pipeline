# SME Invoice OCR Automation Pipeline

> End-to-end Python ETL pipeline that extracts financial data from Indian GST
> invoices (PDF) and loads it into a queryable SQLite database.

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![SQLite](https://img.shields.io/badge/Database-SQLite-green)](https://sqlite.org)
[![CI](https://github.com/Yash-BP/invoice-ocr-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Yash-BP/invoice-ocr-pipeline/actions)

---

## The Business Problem

Indian SMEs receive invoices from dozens of vendors — all in different formats,
all requiring manual data entry. This pipeline automates extraction of structured
financial data from PDF invoices and loads it into a database ready for
accounting, BI tools, or GST reconciliation.

---

## Pipeline Flow

```
PDF invoices
    │
    ▼
pdfplumber (text-layer extraction)
    │  if empty ↓
pytesseract OCR (scanned PDF fallback)
    │
    ▼
Multi-pattern regex engine
  • Invoice ID, Date, Vendor
  • CGST + SGST (intra-state) or IGST (inter-state)
  • Subtotal, Grand Total
  • Per-field confidence: HIGH / LOW / MISSING
    │
    ▼
Validation (grand_total ≈ subtotal + tax, within Rs. 1)
    │
    ▼
SQLite (INSERT OR IGNORE — idempotent)
    │
    ▼
data/finance_system.db  +  data/pipeline.log
```

---

## Project Structure

```
invoice-ocr-pipeline/
├── scripts/
│   ├── __init__.py
│   ├── generate_invoices.py   # Step 1 — generate sample PDFs
│   ├── extract_ocr_data.py    # Step 2 — extract + validate
│   └── load_to_database.py    # Step 3 — load to SQLite
├── tests/
│   └── test_extraction.py     # pytest unit tests (no PDFs needed)
├── data/
│   └── .gitkeep               # directory tracked; outputs are gitignored
├── .github/
│   └── workflows/ci.yml       # runs pytest on every push
├── run_pipeline.py            # orchestrator — runs all 3 steps
├── schema.sql                 # database DDL (source of truth)
├── requirements.txt           # pinned dependencies
├── .env.example               # configuration template
└── .gitignore
```

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| PDF text extraction | pdfplumber | Fast, no binary deps, handles text-layer PDFs |
| OCR fallback | pytesseract + pdf2image | Handles scanned/image PDFs (optional) |
| Data processing | pandas | DataFrame transforms, CSV I/O |
| Database | SQLite3 | Zero-config, BI-tool compatible (Power BI, Tableau) |
| PDF generation | ReportLab + Faker | Generates realistic Indian GST test invoices |
| Config | python-dotenv | Env-var based, no secrets in code |
| Testing | pytest | 20+ unit tests on extraction logic |
| CI | GitHub Actions | Runs tests on every push |

---

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/Yash-BP/invoice-ocr-pipeline.git
cd invoice-ocr-pipeline
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure (optional — defaults work out of the box)
cp .env.example .env

# 3. Run the full pipeline
python run_pipeline.py

# 4. Skip PDF generation if you already have raw_invoices/
python run_pipeline.py --skip-gen

# 5. Run tests
pytest tests/ -v
```

---

## GST Handling

The extractor supports all three Indian GST invoice formats:

| Invoice type | Tax lines | Handled? |
|---|---|---|
| Intra-state B2B | CGST @ 9% + SGST @ 9% | Yes — summed automatically |
| Inter-state B2B | IGST @ 18% | Yes |
| Single-line GST | GST (18%) | Yes |
| Multi-slab (5% + 18%) | Multiple CGST/SGST pairs | Yes — all components summed |

---

## Observability

Every pipeline run logs:

```
DB summary (all-time)
  Total invoices  : 20
  Total spend     : Rs. 31,21,076.00
  Avg invoice     : Rs. 1,56,053.80
  Confidence HIGH : 18
  Confidence LOW  : 2
  Confidence MISS : 0
  Via OCR         : 0
  Flagged (review): 0
```

Flagged rows (validation failed) can be queried directly:
```sql
SELECT * FROM processed_invoices WHERE validation_passed = 0;
SELECT * FROM processed_invoices WHERE overall_confidence = 'MISSING';
```

---

## Honest Limitations

- **Extraction accuracy on real invoices**: The regex patterns cover common
  formats (Tally, Zoho Books, Vyapar, Busy). Unusual or highly customised
  invoice templates may return `MISSING` confidence on some fields — those rows
  are flagged in the DB for manual review.

- **pdfplumber is not OCR**: It reads the embedded text layer of a PDF. For
  scanned invoices (image-only PDFs), the OCR fallback via pytesseract is
  required. Install it separately — see `requirements.txt`.

- **SQLite for single-process use only**: SQLite file-locking prevents
  concurrent writes. For parallel processing at scale, migrate to PostgreSQL
  by swapping the connection string (schema is compatible).

- **No LLM fallback yet**: A planned future improvement is to call a vision
  model (Claude/GPT-4o) for invoices where confidence is MISSING, rather than
  sending them to failed_invoices.csv.

---

## Why This Project Stands Out

- Handles real Indian GST complexity (CGST/SGST/IGST split)
- Per-field confidence scoring — you know which data to trust
- Fully idempotent — re-running never creates duplicates
- Honest about what it can and cannot do (scanned PDFs, unusual formats)
- CI badge that actually means the tests pass