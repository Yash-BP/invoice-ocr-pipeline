-- =============================================================================
-- invoice-ocr-pipeline : schema.sql  (final version)
-- =============================================================================
-- Source of truth for database structure.
-- Re-runnable: DROP IF EXISTS guards make this safe to apply any time.
--
-- Key additions vs Phase 2:
--   • Per-field confidence columns (HIGH / LOW / MISSING)
--   • CGST, SGST, IGST breakdown columns
--   • extraction_method column (text_layer | ocr)
--   • overall_confidence column for quick BI filtering
-- =============================================================================

DROP TABLE IF EXISTS processed_invoices;
DROP TABLE IF EXISTS pipeline_run_log;

-- ---------------------------------------------------------------------------
-- Table: processed_invoices
-- ---------------------------------------------------------------------------
CREATE TABLE processed_invoices (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core identifiers
    invoice_id               TEXT    UNIQUE,          -- "INV-00042", "2024-25/GST/042"
    invoice_id_confidence    TEXT    DEFAULT 'MISSING', -- HIGH / LOW / MISSING
    invoice_date             TEXT,                    -- as extracted from PDF
    invoice_date_confidence  TEXT    DEFAULT 'MISSING',
    vendor_name              TEXT,
    vendor_name_confidence   TEXT    DEFAULT 'MISSING',

    -- Financials (INR)
    subtotal                 REAL,
    subtotal_confidence      TEXT    DEFAULT 'MISSING',
    tax_amount               REAL,                    -- sum of all GST components
    tax_amount_confidence    TEXT    DEFAULT 'MISSING',

    -- GST breakdown (Indian-specific)
    cgst                     REAL,                    -- Central GST component
    sgst                     REAL,                    -- State GST component
    igst                     REAL,                    -- Integrated GST (inter-state)

    grand_total              REAL,
    grand_total_confidence   TEXT    DEFAULT 'MISSING',

    -- Extraction metadata
    extraction_method        TEXT    DEFAULT 'text_layer', -- text_layer | ocr
    overall_confidence       TEXT    DEFAULT 'MISSING',    -- HIGH / LOW / MISSING

    -- Data quality
    -- 1 = totals balance within Rs. 1 tolerance
    -- 0 = mismatch flagged for review
    validation_passed        INTEGER NOT NULL DEFAULT 1,
    validation_note          TEXT,

    source_file              TEXT,
    loaded_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Table: pipeline_run_log — one row per run_pipeline.py execution
-- ---------------------------------------------------------------------------
CREATE TABLE pipeline_run_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    invoices_found   INTEGER,
    invoices_loaded  INTEGER,
    invoices_failed  INTEGER,
    n_high_conf      INTEGER,   -- how many HIGH confidence records this run
    n_low_conf       INTEGER,
    n_missing_conf   INTEGER,
    duration_seconds REAL,
    notes            TEXT
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX idx_invoice_date        ON processed_invoices (invoice_date);
CREATE INDEX idx_vendor_name         ON processed_invoices (vendor_name);
CREATE INDEX idx_validation          ON processed_invoices (validation_passed);
CREATE INDEX idx_overall_confidence  ON processed_invoices (overall_confidence);
CREATE INDEX idx_extraction_method   ON processed_invoices (extraction_method);