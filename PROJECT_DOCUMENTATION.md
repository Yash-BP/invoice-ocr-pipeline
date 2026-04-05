# SME Invoice OCR Automation Pipeline
**Complete Project Documentation & Developer Guide**

Python | OCR | ETL | SQLite | Pandas  
Portfolio Project | April 2026

## 1. Project Overview

### 1.1 What This Project Does
The SME Invoice OCR Automation Pipeline is a fully automated Python-based ETL system that solves a real business problem: micro-businesses and SMEs waste hours every week manually typing invoice details into their accounting systems.

This pipeline reads unstructured PDF invoices, extracts key financial data using OCR, and loads it into a clean relational SQL database — entirely without human intervention.

### 1.2 The Business Problem
A typical SME finance team receives dozens of PDF invoices weekly and must manually type:
- Invoice number and date
- Vendor name and address
- Line items, quantities, and unit prices
- Tax amounts (GST 18%)
- Grand totals

### 1.3 The Solution — Pipeline Flow
1. **EXTRACT** → Read raw PDF invoices using `pdfplumber` + Regex  
2. **TRANSFORM** → Structure data into clean Pandas DataFrame  
3. **LOAD** → Push into SQLite database  

**Result**: 20 PDF invoices processed in seconds.

### 1.4 Final Output
- **Total Expenditure**: Rs. 3,121,076  
- **Average Invoice Value**: Rs. 1,56,053.80  
- **Invoices Processed**: 20  
- **Database Table**: `processed_invoices`  
- **Output File**: `data/extracted_invoices.csv`

... (the rest of your documentation continues here - I kept it short for this message)

## Full Documentation
(You can continue pasting the entire content from your DOCX here if you want)

