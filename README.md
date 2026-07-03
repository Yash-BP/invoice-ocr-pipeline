# Invoice OCR & Analytics Pipeline

> End-to-end Python ETL pipeline that eliminates manual invoice data entry for Indian SMEs —  
> extracting structured financial data from raw PDF invoices, validating it, and loading it into  
> a queryable SQL database with a live analytics dashboard.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![Pandas](https://img.shields.io/badge/Pandas-2.x-orange)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B)
![Status](https://img.shields.io/badge/Status-Production_Ready-brightgreen)

---

## Dashboard Preview

![GST Invoice Analytics Dashboard](dashboard_charts.png)

*Live dashboard showing total spend, GST paid, vendor breakdown, and expenditure timeline — generated from 20 OCR-processed PDF invoices.*

---

## The Business Problem

Indian SMEs receive dozens of PDF invoices weekly and manually re-type every field — invoice number, vendor name, GST amount, grand total — into spreadsheets or accounting tools. This pipeline **automates that entirely** by parsing text layers or running optical character recognition (OCR), running deterministic validation checks, and outputting to clean analytics engines.

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Yash-BP/invoice-ocr-pipeline.git
cd invoice-ocr-pipeline

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the full pipeline (one command)
python run_pipeline.py

# 5. Run accuracy validation report
python scripts/validate_accuracy.py

# 6. Launch the analytics dashboard
streamlit run dashboard.py
```

> Re-runs are fully safe — the pipeline is designed to be idempotent.

---

## Architecture

```
┌─────────────────────────── run_pipeline.py ───────────────────────────┐
│              Orchestrator + step timing + SQLite audit log            │
└──────┬─────────────────────┬───────────────────────┬──────────────────┘
       ▼                     ▼                       ▼
 scripts/generate_invoices  scripts/extract_ocr_data  scripts/load_to_database
       │                     │                       │
 20 realistic PDFs     Text layer/OCR fallback +     INSERT OR IGNORE
 (Faker + ReportLab)   Confidence scoring + Regex      into SQLite DB
```

---

## Project Structure

```
invoice-ocr-pipeline/
├── run_pipeline.py              # Orchestrator & timing execution script
├── dashboard.py                 # Streamlit interactive dashboard
├── schema.sql                   # Database initialization script
├── requirements.txt             # Project dependencies
├── .env                         # Environment variables configuration
├── README.md                    # Project documentation
├── scripts/
│   ├── generate_invoices.py     # Step 1: Synthesizes Indian GST invoices
│   ├── extract_ocr_data.py      # Step 2: Extracts fields & scores confidence
│   ├── load_to_database.py      # Step 3: Loads extracted data to SQLite
│   ├── validate_accuracy.py     # Validation: Compares OCR output with Ground Truth
│   └── analyze_spending.py      # Analytics: Simple console spending summary
├── tests/                       # Unit tests suite
│   └── test_extraction.py
└── data/                        # Output directory (CSV, logs, DB)
    ├── extracted_invoices.csv   # Data extracted from invoices
    ├── failed_invoices.csv      # List of files that could not be parsed
    ├── ground_truth_invoices.csv# Expected ground truth (synthetic manifest)
    ├── finance_system.db        # SQLite relational database
    └── pipeline.log             # Consolidated execution logs
```

---

## Pipeline Steps

| Step | Script | Input | Output | What it does |
| :--- | :--- | :--- | :--- | :--- |
| **1** | [generate_invoices.py](file:///c:/invoice-ocr-pipeline/scripts/generate_invoices.py) | Config (`.env`) | `raw_invoices/*.pdf`<br>`data/ground_truth_invoices.csv` | Generates 20 realistic Indian GST invoices using `Faker` (en_IN) and `ReportLab`. |
| **2** | [extract_ocr_data.py](file:///c:/invoice-ocr-pipeline/scripts/extract_ocr_data.py) | `raw_invoices/*.pdf` | `data/extracted_invoices.csv`<br>`data/failed_invoices.csv` | Extracts text layer (`pdfplumber`) or falls back to OCR (`pytesseract`). Scores confidence per field and validates mathematical totals. |
| **3** | [load_to_database.py](file:///c:/invoice-ocr-pipeline/scripts/load_to_database.py) | `data/extracted_invoices.csv` | `data/finance_system.db` | Runs `schema.sql` (if table does not exist) and performs database insertion using idempotent logic. |

---

## Database Schema

The pipeline database (`data/finance_system.db`) structured on [schema.sql](file:///c:/invoice-ocr-pipeline/schema.sql) contains two main tables:

### 1. `processed_invoices`
Stores extracted and validated invoice records with audit columns:
```sql
CREATE TABLE processed_invoices (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id               TEXT UNIQUE,
    invoice_id_confidence    TEXT DEFAULT 'MISSING',
    invoice_date             TEXT,
    invoice_date_confidence  TEXT DEFAULT 'MISSING',
    vendor_name              TEXT,
    vendor_name_confidence   TEXT DEFAULT 'MISSING',
    subtotal                 REAL,
    subtotal_confidence      TEXT DEFAULT 'MISSING',
    tax_amount               REAL,
    tax_amount_confidence    TEXT DEFAULT 'MISSING',
    cgst                     REAL, -- Central GST (intra-state split)
    sgst                     REAL, -- State GST (intra-state split)
    igst                     REAL, -- Integrated GST (inter-state)
    grand_total              REAL,
    grand_total_confidence   TEXT DEFAULT 'MISSING',
    extraction_method        TEXT DEFAULT 'text_layer',
    overall_confidence       TEXT DEFAULT 'MISSING',
    validation_passed        INTEGER NOT NULL DEFAULT 1,
    validation_note          TEXT,
    source_file              TEXT,
    loaded_at                TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2. `pipeline_run_log`
Tracks every execution of [run_pipeline.py](file:///c:/invoice-ocr-pipeline/run_pipeline.py):
```sql
CREATE TABLE pipeline_run_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT NOT NULL DEFAULT (datetime('now')),
    invoices_found   INTEGER,
    invoices_loaded  INTEGER,
    invoices_failed  INTEGER,
    n_high_conf      INTEGER,
    n_low_conf       INTEGER,
    n_missing_conf   INTEGER,
    duration_seconds REAL,
    notes            TEXT
);
```

---

## Accuracy Validation Report

Since [generate_invoices.py](file:///c:/invoice-ocr-pipeline/scripts/generate_invoices.py) generates the PDFs with known properties, it records the expected values in a ground-truth CSV. The validation script [validate_accuracy.py](file:///c:/invoice-ocr-pipeline/scripts/validate_accuracy.py) joins the database records with this CSV to measure extraction precision:

```bash
python scripts/validate_accuracy.py
```

*Output Example:*
```text
=================================================================
  OCR ACCURACY VALIDATION REPORT
=================================================================
  Ground truth invoices : 20
  Found in DB           : 20
  Invoice match rate    : 100.0%
-----------------------------------------------------------------
  Field                Correct    Total   Accuracy
-----------------------------------------------------------------
  invoice_date              20       20     100.0%  [====================]
  vendor_name               20       20     100.0%  [====================]
  subtotal                  20       20     100.0%  [====================]
  tax_amount                20       20     100.0%  [====================]
  grand_total               20       20     100.0%  [====================]
=================================================================
  OVERALL                  100      100     100.0%
=================================================================
```

---

## Running Tests

Automated unit tests assert the reliability of Regex extractions, text cleanups, parsing, and arithmetic checks:

```bash
pytest tests/ -v
```

---

## Tech Stack

- **Language:** Python 3.13
- **PDF Extraction:** `pdfplumber` (text layer parser) & `pytesseract` + `pdf2image` (fallback OCR)
- **Data Wrangling:** `pandas`
- **Database:** `SQLite3` (relational storage with index optimizations)
- **BI Visualizations:** `Streamlit`, `Plotly Express`
- **Testing Framework:** `pytest`
- **Synthetic Data Generation:** `ReportLab` + `Faker` (en_IN locale)

---

## Key Features

- **Automated Fallback to OCR:** Parses modern clean PDFs using high-speed text layers. If no text layer is detected (scanned documents), automatically activates OCR processing.
- **GST Breakdown-Aware:** Automatically splits and sums CGST, SGST, and IGST lines typical of Indian tax rules.
- **Observable Execution Log:** All runs record processing speeds, extraction success rates, and errors. Writes history to the database and detailed execution steps to `data/pipeline.log`.
- **Confidence Scoring:** Validates fields individually. Computes flags (`HIGH`/`LOW`/`MISSING`) for fields to aid audit reviews.
- **Mathematical Integrity Validation:** Evaluates if `grand_total ≈ subtotal + tax_amount` within ₹1 rounding tolerance, alerting the user about anomalies via the database `validation_passed` flag.
