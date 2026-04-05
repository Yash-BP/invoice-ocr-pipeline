# SME Invoice OCR Automation Pipeline

> End-to-end Python ETL pipeline that eliminates manual data entry by extracting 
> financial data from raw PDF invoices and loading it into a SQL database.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![Status](https://img.shields.io/badge/Status-Complete-brightgreen)

---

## The Business Problem

Small businesses across India spend 10+ hours per week manually entering invoice 
data — vendor names, dates, GST amounts, and totals — into spreadsheets. This 
pipeline eliminates that bottleneck entirely by automating extraction and storage 
of financial data from raw PDFs into a queryable SQL database.

---

## ETL Pipeline Flow
```
Raw PDF invoices → pdfplumber OCR → Regex extraction → pandas DataFrame → SQLite DB
```

---

## Pipeline Scripts

| Step | Script | What it does |
|------|--------|-------------|
| 1 | `generate_invoices.py` | Creates 20 realistic Indian tax invoices as PDFs using Faker and ReportLab with 18% GST and INR formatting |
| 2 | `extract_ocr_data.py` | Reads each PDF with pdfplumber, runs regex to pull Invoice ID, Date, Vendor, Tax, and Grand Total into a clean CSV |
| 3 | `load_to_database.py` | Loads the CSV via pandas into a SQLite `processed_invoices` table ready for SQL queries or BI tools |

---

## Project Structure
```
invoice-ocr-pipeline/
├── scripts/
│   ├── generate_invoices.py   # Step 1 — PDF generation
│   ├── extract_ocr_data.py    # Step 2 — OCR + regex
│   └── load_to_database.py    # Step 3 — SQL ingestion
├── data/
│   ├── extracted_invoices.csv # Clean structured output
│   └── finance_system.db      # SQLite database
├── raw_invoices/              # Generated PDF files
├── .env
├── .gitignore
└── README.md
```

---

## Tech Stack

- **Language:** Python 3.13
- **OCR Engine:** pdfplumber, re (regex)
- **Data Processing:** pandas
- **PDF Generation:** ReportLab, Faker (en_IN locale)
- **Database:** SQLite3
- **Environment:** venv, python-dotenv

---

## Quick Start
```bash
# 1. Clone the repo
git clone https://github.com/Yash-BP/invoice-ocr-pipeline.git
cd invoice-ocr-pipeline

# 2. Set up virtual environment
python -m venv venv
.\venv\Scripts\activate       # Windows
source venv/bin/activate      # Mac/Linux

# 3. Install dependencies
pip install pandas pdfplumber faker reportlab python-dotenv

# 4. Run the full pipeline
python scripts/generate_invoices.py
python scripts/extract_ocr_data.py
python scripts/load_to_database.py
```

---

## Why This Project Stands Out

- **Unstructured data** — 80% of real business data lives in PDFs, not clean CSVs. This proves you can handle it.
- **Full ETL ownership** — Built all three stages (Extract, Transform, Load) independently.
- **Industry-agnostic** — Every company processes invoices. FinTech, logistics, SaaS — all immediately understand the value.
- **BI-ready output** — The SQLite database plugs directly into Power BI or Tableau for live dashboards.