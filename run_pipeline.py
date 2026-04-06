"""
run_pipeline.py  —  Pipeline Orchestrator
==========================================
Runs the full invoice-ocr-pipeline in sequence:
    Step 1 → generate_invoices   (PDF generation)
    Step 2 → extract_ocr_data    (OCR + regex extraction → CSV)
    Step 3 → load_to_database    (CSV → SQLite)

Usage:
    python run_pipeline.py              # run all 3 steps
    python run_pipeline.py --skip-gen  # skip PDF generation; use existing PDFs

Exit codes:
    0 — all steps succeeded
    1 — one or more steps failed (CI/CD friendly)

Phase 2 additions:
  - Single entry point for the entire pipeline.
  - Per-step timing and a formatted runtime summary printed to stdout + log file.
  - Step-level isolation: a failure does not mask subsequent step results.
  - Step 3 is skipped automatically if Step 2 produced zero records.
  - Run metadata written to pipeline_run_log in the SQLite DB.
"""

import argparse
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap — load .env before importing pipeline modules so they all pick
# up the same resolved paths.
# ---------------------------------------------------------------------------
load_dotenv()

Path("data").mkdir(parents=True, exist_ok=True)   # ensure log dir exists

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("run_pipeline")

# Import pipeline modules AFTER logging is configured so their module-level
# loggers inherit the root handler setup.
import scripts.generate_invoices as gen_step    # noqa: E402
import scripts.extract_ocr_data  as ext_step   # noqa: E402
import scripts.load_to_database  as load_step  # noqa: E402

DB_PATH = Path(os.getenv("DB_PATH", "data/finance_system.db"))

# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _run_step(label: str, fn) -> tuple[bool, float, object]:
    """
    Execute a single pipeline step.

    Args:
        label: Human-readable step name used in logging.
        fn:    Callable with no required arguments; may return any value.

    Returns:
        (success, elapsed_seconds, return_value)
        On exception: (False, elapsed, None) — never re-raises.
    """
    logger.info("━" * 62)
    logger.info("  %s", label)
    logger.info("━" * 62)
    t0 = time.perf_counter()
    try:
        result  = fn()
        elapsed = time.perf_counter() - t0
        logger.info("  ✓  Completed in %.2fs\n", elapsed)
        return True, elapsed, result
    except Exception as exc:                        # noqa: BLE001
        elapsed = time.perf_counter() - t0
        logger.error(
            "  ✗  FAILED after %.2fs — %s: %s",
            elapsed, type(exc).__name__, exc,
            exc_info=True,
        )
        return False, elapsed, None


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _write_run_log(
    invoices_found:  int,
    invoices_loaded: int,
    invoices_failed: int,
    duration:        float,
    notes:           str,
) -> None:
    """Append one row to pipeline_run_log for operational auditing."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO pipeline_run_log
                    (invoices_found, invoices_loaded, invoices_failed,
                     duration_seconds, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (invoices_found, invoices_loaded, invoices_failed,
                 round(duration, 3), notes),
            )
        logger.info("Run metadata written to pipeline_run_log.")
    except sqlite3.Error as exc:
        logger.warning("Could not write to pipeline_run_log: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="invoice-ocr-pipeline — full ETL orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skip-gen",
        action="store_true",
        help="Skip Step 1 (PDF generation). Useful when raw_invoices/ "
             "already contains PDFs you want to re-process.",
    )
    args = parser.parse_args()

    pipeline_start = time.perf_counter()

    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║         invoice-ocr-pipeline  ·  starting run               ║")
    logger.info("╚══════════════════════════════════════════════════════════════╝\n")

    step_results: dict[str, tuple[bool, float, object]] = {}

    # ── Step 1: Generate PDFs ──────────────────────────────────────────────
    if args.skip_gen:
        logger.info("Step 1 skipped (--skip-gen).\n")
        step_results["1_generate"] = (True, 0.0, None)
    else:
        step_results["1_generate"] = _run_step(
            "STEP 1 / 3  —  Generate invoices (PDF)",
            gen_step.main,
        )

    # ── Step 2: Extract ────────────────────────────────────────────────────
    step_results["2_extract"] = _run_step(
        "STEP 2 / 3  —  Extract OCR data → CSV",
        ext_step.main,
    )

    # ── Step 3: Load (guard against empty extraction) ─────────────────────
    extracted_records = step_results["2_extract"][2]   # list[dict] | None

    if not extracted_records:
        logger.error(
            "Step 2 returned zero records — Step 3 skipped to prevent "
            "overwriting the database with empty data.\n"
        )
        step_results["3_load"] = (False, 0.0, None)
    else:
        step_results["3_load"] = _run_step(
            "STEP 3 / 3  —  Load CSV → SQLite database",
            load_step.main,
        )

    # ── Summary ───────────────────────────────────────────────────────────
    total_elapsed = time.perf_counter() - pipeline_start
    any_failed    = any(not ok for ok, _, _ in step_results.values())
    overall       = "SUCCESS ✓" if not any_failed else "FAILED  ✗"

    step_labels = {
        "1_generate": "Step 1 — Generate PDFs     ",
        "2_extract":  "Step 2 — Extract OCR data  ",
        "3_load":     "Step 3 — Load to database  ",
    }

    logger.info("")
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║                      PIPELINE SUMMARY                       ║")
    logger.info("╠══════════════════════════════════════════════════════════════╣")
    for key, label in step_labels.items():
        ok, elapsed, _ = step_results[key]
        icon   = "✓" if ok else "✗"
        status = "OK  " if ok else "FAIL"
        logger.info("║  %s  %s  %s  %6.2fs                               ║",
                    icon, label, status, elapsed)
    logger.info("╠══════════════════════════════════════════════════════════════╣")
    logger.info("║  Total runtime : %-44s ║", f"{total_elapsed:.2f}s")
    logger.info("║  Overall       : %-44s ║", overall)
    logger.info("╚══════════════════════════════════════════════════════════════╝")

    # ── Audit log ─────────────────────────────────────────────────────────
    n_found = len(extracted_records) if extracted_records else 0
    _write_run_log(
        invoices_found=n_found,
        invoices_loaded=n_found,
        invoices_failed=0,
        duration=total_elapsed,
        notes="SUCCESS" if not any_failed else "One or more steps failed.",
    )

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())