"""
scripts/validate_accuracy.py
=============================
Accuracy validation report for the invoice OCR pipeline.

Since generate_invoices.py creates the PDFs with known values, we have
ground truth. This script re-generates the ground-truth manifest, compares
it against what was actually extracted and stored in the DB, and prints an
accuracy report showing field-by-field success rates.

Usage:
    python scripts/validate_accuracy.py

    # Or with a custom ground-truth CSV (see --help):
    python scripts/validate_accuracy.py --ground-truth path/to/truth.csv

How it works:
    1. Read processed_invoices from the DB  (what OCR extracted)
    2. Read ground_truth_invoices.csv       (what generate_invoices.py intended)
       If not found, generate it now from raw_invoices/ PDF filenames +
       a re-run of the generator with a fixed random seed.
    3. Join on invoice_id and compare each field.
    4. Print a colour-coded accuracy table.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("validate_accuracy")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH          = Path(os.getenv("DB_PATH",           "data/finance_system.db"))
GROUND_TRUTH_CSV = Path(os.getenv("GROUND_TRUTH_CSV",  "data/ground_truth_invoices.csv"))
RAW_INVOICES_DIR = Path(os.getenv("RAW_INVOICES_DIR",  "raw_invoices"))

# Tolerance for floating-point comparisons (INR)
AMOUNT_TOLERANCE = 1.00


# ---------------------------------------------------------------------------
# Load extracted data from DB
# ---------------------------------------------------------------------------

def load_extracted() -> pd.DataFrame:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at '{DB_PATH}'. Run the pipeline first."
        )
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT invoice_id, invoice_date, vendor_name, "
            "subtotal, tax_amount, grand_total FROM processed_invoices",
            conn,
        )
    return df


# ---------------------------------------------------------------------------
# Load or generate ground truth
# ---------------------------------------------------------------------------

def load_ground_truth(path: Path) -> pd.DataFrame:
    """
    Load ground_truth_invoices.csv.

    This file should be generated once by running generate_invoices.py with
    the --export-truth flag (see below). If it doesn't exist yet, we raise
    a clear error explaining how to create it.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Ground truth CSV not found at '{path}'.\n"
            "Generate it by running:\n"
            "    python scripts/generate_invoices.py --export-truth\n"
            "This writes a manifest of every invoice's intended values."
        )
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Field comparison
# ---------------------------------------------------------------------------

def _amount_match(a, b) -> bool:
    """True if both values are close within AMOUNT_TOLERANCE."""
    try:
        return abs(float(a) - float(b)) <= AMOUNT_TOLERANCE
    except (TypeError, ValueError):
        return False


def _text_match(a, b) -> bool:
    """Case-insensitive string match, treating None/NaN as empty."""
    a = str(a).strip().lower() if pd.notna(a) else ""
    b = str(b).strip().lower() if pd.notna(b) else ""
    return a == b


FIELD_COMPARATORS = {
    "invoice_date": _text_match,
    "vendor_name":  _text_match,
    "subtotal":     _amount_match,
    "tax_amount":   _amount_match,
    "grand_total":  _amount_match,
}


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_report(extracted: pd.DataFrame, truth: pd.DataFrame) -> None:
    # Join on invoice_id
    merged = truth.merge(
        extracted,
        on="invoice_id",
        how="left",
        suffixes=("_truth", "_extracted"),
    )

    total_invoices = len(merged)
    matched_invoices = merged["invoice_id"].isin(extracted["invoice_id"]).sum()

    print("\n" + "=" * 65)
    print("  OCR ACCURACY VALIDATION REPORT")
    print("=" * 65)
    print(f"  Ground truth invoices : {total_invoices}")
    print(f"  Found in DB           : {matched_invoices}")
    print(
        f"  Invoice match rate    : "
        f"{matched_invoices / total_invoices * 100:.1f}%"
    )
    print("-" * 65)
    print(f"  {'Field':<18}  {'Correct':>8}  {'Total':>7}  {'Accuracy':>9}")
    print("-" * 65)

    field_results: dict[str, tuple[int, int]] = {}

    for field, comparator in FIELD_COMPARATORS.items():
        truth_col     = f"{field}_truth"
        extracted_col = f"{field}_extracted"

        # If field only appears once (e.g. invoice_date not duplicated), handle both
        if truth_col not in merged.columns:
            truth_col = field
        if extracted_col not in merged.columns:
            extracted_col = field

        correct = sum(
            comparator(t, e)
            for t, e in zip(merged[truth_col], merged[extracted_col])
            if pd.notna(t)   # only score rows where we have ground truth
        )
        scoreable = merged[truth_col].notna().sum()
        field_results[field] = (correct, scoreable)

        accuracy = correct / scoreable * 100 if scoreable else 0.0
        bar = "█" * int(accuracy // 5) + "░" * (20 - int(accuracy // 5))
        print(f"  {field:<18}  {correct:>8}  {scoreable:>7}  {accuracy:>8.1f}%  {bar}")

    # Overall
    total_correct = sum(c for c, _ in field_results.values())
    total_possible = sum(s for _, s in field_results.values())
    overall = total_correct / total_possible * 100 if total_possible else 0.0

    print("=" * 65)
    print(
        f"  {'OVERALL':<18}  {total_correct:>8}  {total_possible:>7}  {overall:>8.1f}%"
    )
    print("=" * 65)

    # Show failed extractions
    failed_rows = []
    for _, row in merged.iterrows():
        row_issues = []
        for field, comparator in FIELD_COMPARATORS.items():
            tc = f"{field}_truth" if f"{field}_truth" in merged.columns else field
            ec = f"{field}_extracted" if f"{field}_extracted" in merged.columns else field
            if pd.notna(row.get(tc)) and not comparator(row.get(tc), row.get(ec)):
                row_issues.append(
                    f"{field}: expected '{row.get(tc)}' got '{row.get(ec)}'"
                )
        if row_issues:
            failed_rows.append((row["invoice_id"], row_issues))

    if failed_rows:
        print(f"\n  ⚠  Mismatches ({len(failed_rows)} invoices):")
        for inv_id, issues in failed_rows[:10]:  # cap output at 10
            print(f"\n  {inv_id}:")
            for issue in issues:
                print(f"    • {issue}")
        if len(failed_rows) > 10:
            print(f"\n  ... and {len(failed_rows) - 10} more.")
    else:
        print("\n  ✅  All extracted values match ground truth!")

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(ground_truth_path: Path = GROUND_TRUTH_CSV) -> None:
    try:
        extracted = load_extracted()
        logger.info("Loaded %d extracted records from DB.", len(extracted))
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return

    try:
        truth = load_ground_truth(ground_truth_path)
        logger.info("Loaded %d ground truth records.", len(truth))
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return

    generate_report(extracted, truth)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="OCR accuracy validation report")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=GROUND_TRUTH_CSV,
        help=f"Path to ground truth CSV (default: {GROUND_TRUTH_CSV})",
    )
    args = parser.parse_args()
    main(args.ground_truth)