"""
load_to_database.py  —  Step 3 of the invoice-ocr-pipeline
===========================================================
Reads data/extracted_invoices.csv (written by extract_ocr_data.py) and
idempotently loads every row into the processed_invoices SQLite table.

Phase 3 improvements over the previous version:
  • Correct table name: processed_invoices (was wrongly targeting 'invoices')
  • INSERT now includes validation_passed + validation_note columns
  • schema.sql is auto-applied on startup so the DB is always initialised
  • main() function restored — required by run_pipeline.py orchestrator
  • All paths sourced from .env (DB_PATH, EXTRACTED_CSV, FAILED_CSV, SCHEMA_PATH)
  • Per-row WAL-mode transactions; one bad row never blocks the rest
  • LoadResult dataclass returned from load_invoices() for programmatic callers
  • Graceful KeyError if DB_PATH missing from env (clear error, not a traceback)
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all values from .env, matching .env.example exactly
# ---------------------------------------------------------------------------

def _require_env(key: str) -> Path:
    """Raise a clear error if a required env variable is missing."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example → .env and fill in the value."
        )
    return Path(val)


DB_PATH        = _require_env("DB_PATH")           # data/finance_system.db
EXTRACTED_CSV  = _require_env("EXTRACTED_CSV")     # data/extracted_invoices.csv
FAILED_CSV     = _require_env("FAILED_CSV")        # data/failed_invoices.csv
SCHEMA_PATH    = Path(os.getenv("SCHEMA_PATH", "schema.sql"))


# ---------------------------------------------------------------------------
# Result type — returned to run_pipeline.py orchestrator
# ---------------------------------------------------------------------------

@dataclass
class LoadResult:
    loaded:  int = 0
    skipped: int = 0   # duplicate invoice_id — INSERT OR IGNORE silently skips
    failed:  int = 0
    errors:  list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Apply schema.sql if it exists.
    Uses CREATE TABLE IF NOT EXISTS so this is safe to call on every run —
    it will never overwrite existing data.
    """
    if not SCHEMA_PATH.exists():
        logger.warning(
            "schema.sql not found at '%s' — skipping schema init. "
            "If the table doesn't exist, inserts will fail.",
            SCHEMA_PATH,
        )
        return

    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # Strip the DROP TABLE lines so re-runs never wipe existing data
    safe_sql = "\n".join(
        line for line in sql.splitlines()
        if not line.strip().upper().startswith("DROP TABLE")
    )
    conn.executescript(safe_sql)
    logger.debug("Schema applied from %s", SCHEMA_PATH)


# ---------------------------------------------------------------------------
# CSV failure sink
# ---------------------------------------------------------------------------

def _write_failed(invoice: dict[str, Any], reason: str) -> None:
    """Append one failure row to FAILED_CSV (creates the file + header if needed)."""
    FAILED_CSV.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not FAILED_CSV.exists()

    with FAILED_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["timestamp", "invoice_id", "vendor_name", "reason"],
            extrasaction="ignore",
        )
        if needs_header:
            writer.writeheader()

        writer.writerow({
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "invoice_id":  invoice.get("invoice_id", "UNKNOWN"),
            "vendor_name": invoice.get("vendor_name", ""),
            "reason":      reason,
        })


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

# SQL matches processed_invoices schema exactly (see schema.sql)
_INSERT_SQL = """
    INSERT OR IGNORE INTO processed_invoices (
        invoice_id,
        invoice_date,
        vendor_name,
        subtotal,
        tax_amount,
        grand_total,
        validation_passed,
        validation_note,
        source_file,
        loaded_at
    ) VALUES (
        :invoice_id,
        :invoice_date,
        :vendor_name,
        :subtotal,
        :tax_amount,
        :grand_total,
        :validation_passed,
        :validation_note,
        :source_file,
        :loaded_at
    )
"""


def load_invoices(invoices: list[dict[str, Any]]) -> LoadResult:
    """
    Idempotently insert a list of invoice dicts into processed_invoices.

    Records that already exist (matched by UNIQUE invoice_id) are silently
    skipped and counted as 'skipped', not 'failed'.

    Records missing invoice_id are written to FAILED_CSV and skipped.

    Args:
        invoices: List of dicts as returned by extract_ocr_data.main().
                  Each dict must have the keys produced by extract_from_pdf().

    Returns:
        LoadResult with loaded / skipped / failed counts.
    """
    result = LoadResult()

    if not invoices:
        logger.info("load_invoices: received empty list — nothing to do.")
        return result

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL;")   # safe for concurrent readers
        conn.execute("PRAGMA foreign_keys=ON;")
    except sqlite3.Error as exc:
        logger.critical("Cannot open database '%s': %s", DB_PATH, exc)
        raise

    _ensure_schema(conn)

    for invoice in invoices:
        inv_id = invoice.get("invoice_id")

        # Guard: invoice_id is the primary business key — reject if absent
        if not inv_id:
            reason = "Missing invoice_id — cannot insert without a unique key"
            logger.warning("[SKIP] %s | source=%s",
                           reason, invoice.get("source_file", "?"))
            _write_failed(invoice, reason)
            result.failed += 1
            result.errors.append(f"UNKNOWN: {reason}")
            continue

        row = {
            "invoice_id":        inv_id,
            "invoice_date":      invoice.get("invoice_date"),
            "vendor_name":       invoice.get("vendor_name"),
            "subtotal":          invoice.get("subtotal"),
            "tax_amount":        invoice.get("tax_amount"),
            "grand_total":       invoice.get("grand_total"),
            # validation_passed is set by extract_ocr_data.py (int 0/1)
            # Default to 1 so rows loaded outside the pipeline aren't penalised
            "validation_passed": int(invoice.get("validation_passed", 1)),
            "validation_note":   invoice.get("validation_note", ""),
            "source_file":       invoice.get("source_file"),
            "loaded_at":         datetime.now(timezone.utc).isoformat(),
        }

        try:
            with conn:   # per-row transaction: commit on success, rollback on error
                cursor = conn.execute(_INSERT_SQL, row)

            if cursor.rowcount == 1:
                val_flag = "✓" if row["validation_passed"] else "⚠"
                logger.info(
                    "[LOAD %s] %-14s | vendor=%-25s | total=Rs.%,.2f",
                    val_flag,
                    inv_id,
                    (row["vendor_name"] or "")[:25],
                    row["grand_total"] or 0.0,
                )
                result.loaded += 1
            else:
                logger.debug("[SKIP] Duplicate invoice_id=%s — already in DB", inv_id)
                result.skipped += 1

        except sqlite3.Error as exc:
            reason = f"DB error: {exc}"
            logger.error("[FAIL] invoice_id=%s — %s", inv_id, exc)
            _write_failed(invoice, reason)
            result.failed += 1
            result.errors.append(f"{inv_id}: {reason}")

    conn.close()

    logger.info(
        "Load complete ── loaded: %d  |  skipped (duplicates): %d  |  failed: %d",
        result.loaded, result.skipped, result.failed,
    )
    return result


# ---------------------------------------------------------------------------
# main() — called by run_pipeline.py as load_step.main()
# ---------------------------------------------------------------------------

def main() -> Optional[LoadResult]:
    """
    Entry point for the orchestrator (run_pipeline.py Step 3).

    Reads EXTRACTED_CSV produced by extract_ocr_data.main(), converts each
    row to a dict, and calls load_invoices().

    Returns:
        LoadResult on success, None if the CSV is missing or unreadable.
    """
    if not EXTRACTED_CSV.exists():
        logger.error(
            "Extracted CSV not found: '%s'. "
            "Run extract_ocr_data.py (Step 2) before this step.",
            EXTRACTED_CSV,
        )
        return None

    try:
        df = pd.read_csv(EXTRACTED_CSV)
    except Exception as exc:   # noqa: BLE001
        logger.error("Failed to read '%s': %s", EXTRACTED_CSV, exc)
        return None

    if df.empty:
        logger.warning("'%s' is empty — nothing to load.", EXTRACTED_CSV)
        return LoadResult()

    logger.info(
        "Read %d row(s) from '%s' — beginning DB load...",
        len(df), EXTRACTED_CSV,
    )

    # Convert DataFrame rows to plain dicts; NaN → None for SQLite compatibility
    invoices = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]

    return load_invoices(invoices)


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    result = main()
    if result is None or not result.success:
        sys.exit(1)