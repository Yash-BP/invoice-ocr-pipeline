-- =============================================================================
-- invoice-ocr-pipeline : schema.sql
-- =============================================================================
-- Purpose : Recreate the SQLite database and all tables from scratch.
-- Usage   : sqlite3 finance_system.db < schema.sql
--           (Or executed programmatically via load_to_database.py)
-- Notes   : finance_system.db is .gitignored. Use this file as the source
--           of truth for the database structure instead.
-- =============================================================================

-- Drop tables if they exist so this script is safely re-runnable.
DROP TABLE IF EXISTS processed_invoices;
DROP TABLE IF EXISTS pipeline_run_log;

-- ---------------------------------------------------------------------------
-- Table: processed_invoices
-- ---------------------------------------------------------------------------
-- Stores one row per successfully extracted and validated invoice.
-- The UNIQUE constraint on invoice_id makes the load step idempotent:
-- re-running the pipeline will not insert duplicate records.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_invoices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core invoice identifiers
    invoice_id          TEXT    NOT NULL UNIQUE,   -- e.g. "INV-00042"
    invoice_date        TEXT,                      -- ISO-8601: "YYYY-MM-DD"
    vendor_name         TEXT,                      -- Extracted vendor / company name

    -- Financial fields (all stored in INR, as plain numeric strings)
    subtotal            REAL,                      -- Pre-tax amount
    tax_amount          REAL,                      -- GST amount (18%)
    grand_total         REAL,                      -- Final payable amount

    -- Data quality flags
    validation_passed   INTEGER NOT NULL DEFAULT 1, -- 1 = totals balance, 0 = anomaly
    source_file         TEXT,                       -- Original PDF filename

    -- Audit columns
    loaded_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Table: pipeline_run_log
-- ---------------------------------------------------------------------------
-- Tracks each pipeline execution for auditing and debugging.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT NOT NULL DEFAULT (datetime('now')),
    invoices_found  INTEGER,
    invoices_loaded INTEGER,
    invoices_failed INTEGER,
    duration_seconds REAL,
    notes           TEXT
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_invoice_date   ON processed_invoices (invoice_date);
CREATE INDEX IF NOT EXISTS idx_vendor_name    ON processed_invoices (vendor_name);
CREATE INDEX IF NOT EXISTS idx_validation     ON processed_invoices (validation_passed);