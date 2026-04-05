"""
load_to_database.py  —  Step 3 of the invoice-ocr-pipeline
===========================================================
Reads data/extracted_invoices.csv and loads it into the SQLite database,
initialising the schema from schema.sql if the table doesn't exist yet.

Phase 1 changes:
  - Replaced all print() calls with logging.
  - Schema is initialised from schema.sql at startup (idempotent DROP/CREATE).
    No more committing a binary .db file to git.
  - Every DB write is wrapped in try/except; row-level failures are logged
    without stopping the rest of the batch.
  - Uses a context manager (with sqlite3.connect()) so the connection is
    always cleanly closed, even on error.
  - Paths read from environment variables with sensible defaults.

Phase 2 preview:
  - INSERT OR IGNORE (idempotency) and validation_passed flag will be added
    in Phase 2 when the schema gets its UNIQUE constraint.
"""

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("load_to_database")

# ---------------------------------------------------------------------------
# Configuration  (overridable via .env)
# ---------------------------------------------------------------------------
EXTRACTED_CSV = Path(os.getenv("EXTRACTED_CSV", "data/extracted_invoices.csv"))
DB_PATH       = Path(os.getenv("DB_PATH",       "data/finance_system.db"))
SCHEMA_PATH   = Path(os.getenv("SCHEMA_PATH",   "schema.sql"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_schema(conn: sqlite3.Connection) -> None:
    """
    Execute schema.sql against the open connection.
    This is safe to call on every run — the DDL uses IF NOT EXISTS guards
    (and DROP IF EXISTS for a clean slate when schema.sql is re-applied).
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"schema.sql not found at '{SCHEMA_PATH}'. "
            "Make sure it is present in the project root."
        )
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    logger.info("Schema initialised from %s.", SCHEMA_PATH)


def _load_csv(csv_path: Path) -> pd.DataFrame:
    """Load and lightly validate the extracted CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Extracted CSV not found at '{csv_path}'. "
            "Run extract_ocr_data.py first."
        )
    df = pd.read_csv(csv_path)
    required_cols = {
        "invoice_id", "invoice_date", "vendor_name",
        "subtotal", "tax_amount", "grand_total", "source_file",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing expected columns: {', '.join(sorted(missing))}"
        )
    return df


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def load_records(conn: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    """
    Insert each row from the DataFrame into processed_invoices.

    Returns (inserted_count, failed_count).

    Note: Phase 2 will upgrade this to INSERT OR IGNORE for full idempotency
    once the UNIQUE constraint on invoice_id is active.
    """
    cursor = conn.cursor()
    inserted = 0
    failed   = 0

    for _, row in df.iterrows():
        try:
            cursor.execute(
                """
                INSERT INTO processed_invoices
                    (invoice_id, invoice_date, vendor_name,
                     subtotal, tax_amount, grand_total, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("invoice_id"),
                    row.get("invoice_date"),
                    row.get("vendor_name"),
                    row.get("subtotal"),
                    row.get("tax_amount"),
                    row.get("grand_total"),
                    row.get("source_file"),
                ),
            )
            inserted += 1

        except sqlite3.IntegrityError as exc:
            # UNIQUE violation — already loaded, safe to skip.
            logger.warning(
                "  [SKIP] invoice_id=%s — already in DB. (%s)",
                row.get("invoice_id", "?"), exc,
            )
            failed += 1

        except sqlite3.Error as exc:
            logger.error(
                "  [FAIL] invoice_id=%s — DB error: %s",
                row.get("invoice_id", "?"), exc,
            )
            failed += 1

    conn.commit()
    return inserted, failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Starting database load — source: %s → %s",
                EXTRACTED_CSV, DB_PATH)

    # Ensure the data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load CSV first (fail fast before touching the DB)
    try:
        df = _load_csv(EXTRACTED_CSV)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Cannot load CSV: %s", exc)
        return

    logger.info("Loaded %d record(s) from CSV.", len(df))

    try:
        with sqlite3.connect(DB_PATH) as conn:
            _init_schema(conn)
            inserted, failed = load_records(conn, df)

    except FileNotFoundError as exc:
        logger.error("Schema error: %s", exc)
        return
    except sqlite3.Error as exc:
        logger.error("Unrecoverable database error: %s", exc)
        return

    # ---- Summary ----
    logger.info(
        "Load complete — %d inserted, %d skipped/failed.",
        inserted, failed,
    )

    # Quick summary query
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT COUNT(*), SUM(grand_total), AVG(grand_total) "
                "FROM processed_invoices"
            )
            count, total, avg = cur.fetchone()
            logger.info(
                "DB summary — rows: %d | total expenditure: Rs. %s | avg: Rs. %s",
                count or 0,
                f"{total:,.2f}" if total else "0.00",
                f"{avg:,.2f}"   if avg   else "0.00",
            )
    except sqlite3.Error as exc:
        logger.warning("Could not run summary query: %s", exc)


if __name__ == "__main__":
    main()