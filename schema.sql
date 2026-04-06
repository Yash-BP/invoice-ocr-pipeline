-- =============================================================================
-- invoice-ocr-pipeline : schema.sql
-- =============================================================================
-- Source of truth for the database structure.
-- Usage   : sqlite3 data/finance_system.db < schema.sql
--           (also executed automatically by load_to_database.py on startup)
-- Re-runnable: DROP IF EXISTS guards make this safe to apply repeatedly.
--
-- Phase 2 changes:
--   • UNIQUE constraint added to invoice_id  → enables INSERT OR IGNORE
--     idempotency in the load step.
--   • validation_passed column added          → flags total-mismatch anomalies.
--   • pipeline_run_log table added            → written by run_pipeline.py.
-- =============================================================================

DROP TABLE IF EXISTS processed_invoices;
DROP TABLE IF EXISTS pipeline_run_log;

-- ---------------------------------------------------------------------------
-- Table: processed_invoices
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_invoices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core invoice identifiers
    invoice_id          TEXT    NOT NULL UNIQUE,   -- e.g. "INV-00042"
    invoice_date        TEXT,                      -- "DD-MM-YYYY" as extracted
    vendor_name         TEXT,                      -- First line of PDF text

    -- Financials (INR, stored as REAL for arithmetic queries)
    subtotal            REAL,                      -- Pre-tax amount
    tax_amount          REAL,                      -- GST 18%
    grand_total         REAL,                      -- Billed total

    -- Data quality
    -- 1 = grand_total ≈ subtotal + tax_amount (within Rs. 1 tolerance)
    -- 0 = mismatch detected; row is flagged for manual review
    validation_passed   INTEGER NOT NULL DEFAULT 1,
    validation_note     TEXT,                      -- Human-readable anomaly detail

    source_file         TEXT,                      -- Original PDF filename

    -- Audit
    loaded_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Table: pipeline_run_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_run_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    invoices_found   INTEGER,
    invoices_loaded  INTEGER,
    invoices_failed  INTEGER,
    duration_seconds REAL,
    notes            TEXT
);

-- ---------------------------------------------------------------------------
-- Indexes — improves BI tool query performance on common filter columns
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_invoice_date   ON processed_invoices (invoice_date);
CREATE INDEX IF NOT EXISTS idx_vendor_name    ON processed_invoices (vendor_name);
CREATE INDEX IF NOT EXISTS idx_validation     ON processed_invoices (validation_passed);