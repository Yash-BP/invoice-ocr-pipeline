"""
main.py — Single-command pipeline runner
=========================================
Convenience wrapper that runs all three pipeline steps in sequence.
Prefer run_pipeline.py for production use (it adds per-step timing,
a structured summary banner, and an audit log to the DB).

Fix: replaced os.system() subprocess calls with direct module imports.
     os.system() silently swallows errors — a failing step would print
     nothing and the next step would run on bad/missing data.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def main() -> int:
    print("=" * 70)
    print("🚀  SME Invoice OCR Automation Pipeline")
    print("    Full ETL Pipeline Starting...")
    print("=" * 70)

    # ── Step 1: Generate invoices ──────────────────────────────────────────
    print("\n1️⃣  Generating realistic Indian GST invoices...")
    try:
        import scripts.generate_invoices as gen
        gen.main()
    except Exception as exc:
        logger.error("Step 1 FAILED — %s: %s", type(exc).__name__, exc)
        return 1

    # ── Step 2: Extract OCR data ───────────────────────────────────────────
    print("\n2️⃣  Extracting data via OCR + regex...")
    try:
        import scripts.extract_ocr_data as ext
        records = ext.main()
    except Exception as exc:
        logger.error("Step 2 FAILED — %s: %s", type(exc).__name__, exc)
        return 1

    if not records:
        logger.error("Step 2 returned zero records — aborting load step.")
        return 1

    # ── Step 3: Load to database ───────────────────────────────────────────
    print("\n3️⃣  Loading data into SQLite database...")
    try:
        import scripts.load_to_database as load
        load.main()
    except Exception as exc:
        logger.error("Step 3 FAILED — %s: %s", type(exc).__name__, exc)
        return 1

    print("\n" + "=" * 70)
    print("✅  PIPELINE COMPLETED SUCCESSFULLY")
    print("📁  Outputs:")
    print("    → data/extracted_invoices.csv")
    print("    → data/finance_system.db")
    print("    → Run: streamlit run dashboard.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())