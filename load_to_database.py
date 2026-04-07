"""
load_to_database.py  —  Step 3 of the invoice-ocr-pipeline
===========================================================
Loads data/extracted_invoices.csv into SQLite.

Key behaviours:
  • Applies schema.sql on startup (idempotent)
  • INSERT OR IGNORE — re-running never creates duplicates
  • Handles all new columns: confidence, CGST/SGST/IGST, extraction_method
  • Prints a rich post-load observability summary
"""

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("load_to_database")

EXTRACTED_CSV = Path(os.getenv("EXTRACTED_CSV", "data/extracted_invoices.csv"))
DB_PATH       = Path(os.getenv("DB_PATH",       "data/finance_system.db"))
SCHEMA_PATH   = Path(os.getenv("SCHEMA_PATH",   "schema.sql"))

# All columns in the INSERT, in order. Must match schema.sql exactly.
_INSERT_COLUMNS = [
    "invoice_id", "invoice_id_confidence",
    "invoice_date", "invoice_date_confidence",
    "vendor_name", "vendor_name_confidence",
    "subtotal", "subtotal_confidence",
    "tax_amount", "tax_amount_confidence",
    "cgst", "sgst", "igst",
    "grand_total", "grand_total_confidence",
    "extraction_method", "overall_confidence",
    "validation_passed", "validation_note",
    "source_file",
]


def _init_schema(conn: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at '{SCHEMA_PATH}'.")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    logger.info("Schema applied from %s.", SCHEMA_PATH)


def _load_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Extracted CSV not found: '{csv_path}'.")
    df = pd.read_csv(csv_path)

    # Back-fill columns that may be absent in older CSV versions
    defaults = {
        "invoice_id_confidence":   "MISSING",
        "invoice_date_confidence": "MISSING",
        "vendor_name_confidence":  "MISSING",
        "subtotal_confidence":     "MISSING",
        "tax_amount_confidence":   "MISSING",
        "grand_total_confidence":  "MISSING",
        "extraction_method":       "text_layer",
        "overall_confidence":      "MISSING",
        "cgst":                    None,
        "sgst":                    None,
        "igst":                    None,
        "validation_passed":       1,
        "validation_note":         "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    return df


def _row_value(row: pd.Series, col: str):
    """Return None for NaN/NaT, otherwise the raw value."""
    val = row.get(col)
    if pd.isna(val):
        return None
    return val


def load_records(conn: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    cursor   = conn.cursor()
    inserted = skipped = 0

    placeholders = ", ".join("?" * len(_INSERT_COLUMNS))
    sql = (
        f"INSERT OR IGNORE INTO processed_invoices "
        f"({', '.join(_INSERT_COLUMNS)}) VALUES ({placeholders})"
    )

    for _, row in df.iterrows():
        values = tuple(_row_value(row, col) for col in _INSERT_COLUMNS)
        try:
            cursor.execute(sql, values)
            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
                logger.debug("  [SKIP] %s — already in DB", row.get("invoice_id"))
        except sqlite3.Error as exc:
            logger.error("  [FAIL] %s — %s", row.get("invoice_id"), exc)

    conn.commit()
    return inserted, skipped


def main() -> None:
    logger.info("Database load: %s → %s", EXTRACTED_CSV, DB_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = _load_csv(EXTRACTED_CSV)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return

    logger.info("Read %d row(s) from CSV.", len(df))

    try:
        with sqlite3.connect(DB_PATH) as conn:
            _init_schema(conn)
            inserted, skipped = load_records(conn, df)
    except (FileNotFoundError, sqlite3.Error) as exc:
        logger.error("Database error: %s", exc)
        return

    logger.info("Load complete — %d inserted, %d skipped.", inserted, skipped)

    # ── Observability summary ──────────────────────────────────────────────
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                          AS total,
                    SUM(grand_total)                                  AS spend,
                    AVG(grand_total)                                  AS avg_inv,
                    SUM(CASE WHEN validation_passed=0  THEN 1 ELSE 0 END) AS flagged,
                    SUM(CASE WHEN overall_confidence='HIGH'    THEN 1 ELSE 0 END) AS high,
                    SUM(CASE WHEN overall_confidence='LOW'     THEN 1 ELSE 0 END) AS low,
                    SUM(CASE WHEN overall_confidence='MISSING' THEN 1 ELSE 0 END) AS missing,
                    SUM(CASE WHEN extraction_method='ocr'      THEN 1 ELSE 0 END) AS ocr
                FROM processed_invoices
            """).fetchone()

            total, spend, avg, flagged, high, low, miss, ocr = row
            logger.info("─" * 56)
            logger.info("DB summary (all-time)")
            logger.info("  Total invoices  : %d", total or 0)
            logger.info("  Total spend     : Rs. %s",
                        f"{spend:,.2f}" if spend else "0.00")
            logger.info("  Avg invoice     : Rs. %s",
                        f"{avg:,.2f}"   if avg   else "0.00")
            logger.info("  Confidence HIGH : %d", high    or 0)
            logger.info("  Confidence LOW  : %d", low     or 0)
            logger.info("  Confidence MISS : %d", miss    or 0)
            logger.info("  Via OCR         : %d", ocr     or 0)
            logger.info("  Flagged (review): %d", flagged or 0)
            logger.info("─" * 56)

            if flagged:
                logger.warning(
                    "%d row(s) need review → "
                    "SELECT * FROM processed_invoices WHERE validation_passed=0;",
                    flagged,
                )
            if miss and miss > (total or 1) * 0.3:
                logger.warning(
                    "%.0f%% of records have MISSING confidence — "
                    "check regex patterns against your invoice formats.",
                    100 * miss / total,
                )
    except sqlite3.Error as exc:
        logger.warning("Summary query failed: %s", exc)


if __name__ == "__main__":
    main()