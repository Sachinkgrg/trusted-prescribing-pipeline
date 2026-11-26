"""Export the reporting tables to CSV files for Power BI (or Excel).

Run from the project folder (after pipeline.report):

    python -m pipeline.export

Writes to data/exports/ (kept off GitHub, like all data):

    prescribing.csv          silver.prescribing, one row per prescription line (for slicers and detail)
    monthly_summary.csv      gold.monthly_summary
    substance_summary.csv    gold.substance_summary
    practice_summary.csv     gold.practice_summary
    dq_results.csv           the latest data quality check results
"""

import sys
from pathlib import Path

import duckdb

from pipeline.config import load_config

EXPORT_DIR = Path("data/exports")

EXPORTS = {
    "prescribing": """
        SELECT month_start, practice_code, practice_name, pco_name,
               bnf_chemical_substance AS antibiotic, bnf_presentation_name AS presentation,
               items, quantity, actual_cost_gbp, nic_gbp
        FROM silver.prescribing""",
    "monthly_summary": "SELECT * FROM gold.monthly_summary",
    "substance_summary": "SELECT * FROM gold.substance_summary",
    "practice_summary": "SELECT * FROM gold.practice_summary",
    "dq_results": """
        SELECT check_name, severity, description, failing_rows, status, checked_at
        FROM silver.dq_results
        WHERE run_id = (SELECT run_id FROM silver.dq_results ORDER BY checked_at DESC LIMIT 1)""",
}


def export(con, out_dir: Path = EXPORT_DIR) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, sql in EXPORTS.items():
        path = (out_dir / f"{name}.csv").as_posix().replace("'", "''")
        con.execute(f"COPY ({sql}) TO '{path}' (HEADER, DELIMITER ',')")
        counts[name] = con.execute(f"SELECT COUNT(*) FROM ({sql})").fetchall()[0][0]
    return counts


def main() -> int:
    config = load_config()
    if not config.warehouse_path.exists():
        print("No warehouse yet. Run the pipeline first.")
        return 1
    con = duckdb.connect(str(config.warehouse_path), read_only=True)
    try:
        counts = export(con)
    finally:
        con.close()
    for name, n in counts.items():
        print(f"{(EXPORT_DIR / (name + '.csv')).as_posix():<40}{n:>8,} rows")
    print(f"\nOpen these in Power BI: Get data > Text/CSV > {EXPORT_DIR.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
