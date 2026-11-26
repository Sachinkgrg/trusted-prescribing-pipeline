"""Step 2 of the pipeline: bronze -> silver, then data quality checks.

Run from the project folder:

    python -m pipeline.silver

It:
  1. runs every SQL file in sql/silver/ in name order (the cleaning)
  2. runs every check in config/checks.yml (the quality checks)
  3. saves the check results to silver.dq_results, so there is a history
  4. prints the results and a first look at the numbers

Exit code is 1 if any error-level check fails, so automation can stop.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

from pipeline.config import load_config

SQL_DIR = Path("sql/silver")
CHECKS_FILE = Path("config/checks.yml")

DQ_RESULTS_SQL = """
CREATE TABLE IF NOT EXISTS silver.dq_results (
    run_id        VARCHAR,
    check_name    VARCHAR,
    severity      VARCHAR,
    description   VARCHAR,
    failing_rows  BIGINT,
    status        VARCHAR,
    checked_at    TIMESTAMP
)
"""


def build_silver(con: duckdb.DuckDBPyConnection, sql_dir: Path = SQL_DIR) -> list[str]:
    """Run each .sql file in order. Returns the file names that ran."""
    files = sorted(Path(sql_dir).glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No .sql files found in {sql_dir}")
    for path in files:
        con.execute(path.read_text(encoding="utf-8"))
    return [path.name for path in files]


def load_checks(path: Path = CHECKS_FILE) -> list[dict]:
    checks = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["checks"]
    for check in checks:
        missing = {"name", "severity", "description", "sql"} - set(check)
        if missing:
            raise ValueError(f"Check {check.get('name', '?')} is missing {sorted(missing)}")
        if check["severity"] not in ("error", "warn"):
            raise ValueError(f"Check {check['name']}: severity must be error or warn")
    return checks


def run_checks(con: duckdb.DuckDBPyConnection, checks: list[dict]) -> list[dict]:
    """Run every check, save the results, and return them."""
    con.execute(DQ_RESULTS_SQL)
    run_id = uuid.uuid4().hex[:8]
    checked_at = datetime.now(timezone.utc).replace(tzinfo=None)

    results = []
    for check in checks:
        failing = int(con.execute(check["sql"]).fetchall()[0][0] or 0)
        if failing == 0:
            status = "PASS"
        else:
            status = "FAIL" if check["severity"] == "error" else "WARN"
        result = {**check, "failing_rows": failing, "status": status}
        results.append(result)
        con.execute(
            "INSERT INTO silver.dq_results VALUES (?, ?, ?, ?, ?, ?, ?)",
            [run_id, check["name"], check["severity"], check["description"],
             failing, status, checked_at],
        )
    return results


def print_results(results: list[dict]) -> None:
    print("\nData quality checks")
    print("-" * 78)
    for r in results:
        print(f"{r['status']:<5} {r['name']:<28} {r['failing_rows']:>7,} rows  {r['description']}")
    print("-" * 78)
    counts = {status: sum(r["status"] == status for r in results) for status in ("PASS", "WARN", "FAIL")}
    print(f"{counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failed")


def print_monthly_summary(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        """
        SELECT strftime(month_start, '%Y-%m')      AS month,
               COUNT(DISTINCT practice_code)       AS practices,
               SUM(items)                          AS items,
               SUM(actual_cost_gbp)                AS cost
        FROM silver.prescribing
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    print("\nAntibacterial prescribing, Newcastle Gateshead (silver.prescribing)")
    print(f"{'Month':<9}{'Practices':>10}{'Items':>12}{'Cost (GBP)':>15}")
    for month, practices, items, cost in rows:
        print(f"{month:<9}{practices:>10,}{items or 0:>12,}{cost or 0:>15,.2f}")


def main() -> int:
    config = load_config()
    if not config.warehouse_path.exists():
        print("No warehouse yet. Run:  python -m pipeline.ingest")
        return 1

    con = duckdb.connect(str(config.warehouse_path))
    try:
        ran = build_silver(con)
        total = con.execute("SELECT COUNT(*) FROM silver.prescribing").fetchall()[0][0]
        print(f"Built silver.prescribing from {', '.join(ran)}: {total:,} rows")
        results = run_checks(con, load_checks())
        print_results(results)
        print_monthly_summary(con)
    finally:
        con.close()

    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
