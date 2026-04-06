# Invoice OCR & Analytics Pipeline

> Automated GST invoice ingestion for Indian SMEs — extract, validate, and analyse PDF invoices at scale.

---

## Quick Start

```bash
# 1. Clone & enter the project
git clone https://github.com/your-org/invoice-ocr-pipeline.git
cd invoice-ocr-pipeline

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Configure the environment
cp .env.example .env
# Edit .env — set DB_PATH, PDF_INPUT_DIR, etc.

# 5. Initialise the database
sqlite3 data/finance_system.db < schema.sql

# 6. Drop your PDF invoices into the input directory
cp /path/to/invoices/*.pdf data/invoices/

# 7. Run the pipeline
python run_pipeline.py
```

Logs are written to `logs/pipeline.log`.  
Failed invoices are recorded in `data/failed_invoices.csv`.

---

## Running Tests

```bash
pytest tests/ -v
```

All tests live in `tests/test_extraction.py` and exercise the regex extraction functions with  
standard, edge-case, and malformed invoice text.

---

## Project Structure

```
invoice-ocr-pipeline/
│
├── run_pipeline.py          # Orchestrator — runs the full ETL
│
├── scripts/
│   ├── __init__.py
│   ├── extract.py           # PDF parsing + field extraction
│   └── load_to_database.py  # Validation + idempotent SQLite loader
│
├── tests/
│   ├── __init__.py
│   └── test_extraction.py   # pytest suite
│
├── data/
│   ├── invoices/            # Input PDFs (gitignored)
│   └── failed_invoices.csv  # Auto-generated; invoices that failed validation
│
├── logs/
│   └── pipeline.log         # Run logs (gitignored)
│
├── schema.sql               # Authoritative DB schema (DDL)
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Configuration template
├── .gitignore
├── README.md
└── PROJECT_DOCUMENTATION.md # Architecture, data dictionary, limitations
```

---

## Configuration

All runtime configuration is driven by environment variables. Copy `.env.example` to `.env`  
and edit the values. **Never commit `.env` to version control.**

Key variables:

| Variable | Purpose |
|---|---|
| `DB_PATH` | Path to the SQLite database |
| `PDF_INPUT_DIR` | Directory containing input PDFs |
| `FAILED_INVOICES_CSV` | Path for the failure log CSV |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` |
| `VALIDATION_TOLERANCE_PCT` | Allowed % difference between extracted and computed totals |

See `.env.example` for the full list with descriptions.

---

## How It Works

1. **Extract** — `pdfplumber` reads raw text from each PDF; regex patterns pull out invoice ID,  
   date, vendor name, subtotal, tax components, and grand total.
2. **Validate** — checks that `subtotal + tax ≈ grand_total` (within `VALIDATION_TOLERANCE_PCT`).  
   Invalid records are written to `failed_invoices.csv`.
3. **Load** — valid records are inserted with `INSERT OR IGNORE`; re-running the pipeline on  
   the same PDFs is safe (idempotent).

For a full architecture walkthrough, data dictionary, and future roadmap see  
[`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md).

---

## Known Limitations

- Regex extraction is brittle for non-standard or scanned invoices.
- Tested on synthetic data only; real-world accuracy varies.
- SQLite is single-writer; not suitable for concurrent multi-process deployments.

See the **Limitations** section in `PROJECT_DOCUMENTATION.md` for details.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Add or update tests in `tests/` for any changed extraction logic.
3. Ensure `pytest tests/ -v` passes before opening a PR.
4. Do not commit `data/`, `logs/`, or `.env`.