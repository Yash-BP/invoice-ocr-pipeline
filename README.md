Here is the finalized, high-impact **README.md** content. You can copy the block below and paste it directly into your `README.md` file in VS Code. [cite: 2026-03-01]

-----

# 📑 SME Invoice OCR Automation Pipeline

> **End-to-end Python ETL pipeline that eliminates manual data entry by extracting financial data from raw PDF invoices and loading it into a validated SQL database.**

-----

## 💡 The Business Problem

Small businesses across India spend 10+ hours per week manually entering invoice data—vendor names, dates, GST amounts, and totals—into spreadsheets. [cite: 2026-03-01] This pipeline eliminates that bottleneck entirely by automating the extraction, validation, and storage of financial data from raw PDFs into a queryable SQL database. [cite: 2026-03-01]

-----

## ⚙️ ETL Pipeline Flow

```text
Raw PDF invoices → pdfplumber OCR → Regex extraction → Data Validation → SQLite DB → Streamlit Dashboard
```

-----

## 📂 Project Structure

```text
invoice-ocr-pipeline/
├── scripts/
│   ├── generate_invoices.py   # Step 1 — PDF generation with Faker
│   ├── extract_ocr_data.py    # Step 2 — OCR + Regex logic
│   └── load_to_database.py    # Step 3 — SQL ingestion & Math validation
├── data/
│   ├── finance_system.db      # SQLite relational database
│   ├── extracted_invoices.csv # Intermediate structured data
│   └── pipeline.log           # Automated audit trail
├── raw_invoices/              # Folder for input PDF files
├── run_pipeline.py            # Master Orchestrator (Single-command run)
├── dashboard.py               # Streamlit analytics frontend
├── schema.sql                 # Database DDL
└── requirements.txt           # Pinned dependencies
```

-----

## 🚀 Pipeline Scripts & Automation

| Step | Script | Responsibility |
| :--- | :--- | :--- |
| **1** | `generate_invoices.py` | Creates 20 realistic Indian tax invoices (PDF) using Faker (en\_IN) with 18% GST. [cite: 2026-03-01] |
| **2** | `extract_ocr_data.py` | Uses `pdfplumber` to pull Invoice ID, Date, Vendor, and Totals via optimized Regex. [cite: 2026-03-01] |
| **3** | `load_to_database.py` | Performs math validation (`Subtotal + Tax == Total`) and loads data into SQLite. [cite: 2026-03-01] |
| **Auto**| `run_pipeline.py` | **Orchestrator:** Runs all steps in sequence and logs performance/errors. [cite: 2026-03-01] |

-----

## 📊 Analytics Dashboard

**Executive Summary & Spend Trends:**

**Structured SQL Records (Validated):**

-----

## 🛠️ Tech Stack

  * **Language:** Python 3.13 [cite: 2026-03-01]
  * **OCR & Extraction:** `pdfplumber`, `re` (Regex) [cite: 2026-03-01]
  * **Data Science:** `pandas`, `numpy` [cite: 2026-03-01]
  * **Database:** `SQLite3` (Relational) [cite: 2026-03-01]
  * **Visualization:** `Streamlit`, `Plotly Express` [cite: 2026-03-01]
  * **Generation:** `ReportLab`, `Faker` [cite: 2026-03-01]

-----

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Yash-BP/invoice-ocr-pipeline.git
cd invoice-ocr-pipeline

# 2. Set up virtual environment
python -m venv venv
.\venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the full automated pipeline
python run_pipeline.py

# 5. View the dashboard
streamlit run dashboard.py
```

-----

## 🌟 Why This Project Stands Out

  * **Handles Unstructured Data:** 80% of business data lives in PDFs. This pipeline proves the ability to clean and structure "messy" data. [cite: 2026-03-01]
  * **Production-Ready Logic:** Features idempotency (no duplicate entries) and error handling for corrupt files. [cite: 2026-03-01]
  * **Full ETL Ownership:** Demonstrates mastery of the entire data lifecycle from raw source to visual insight. [cite: 2026-03-01]
