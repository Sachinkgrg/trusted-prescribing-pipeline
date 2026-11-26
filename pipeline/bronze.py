"""The bronze layer: data exactly as it arrived, plus where and when it came from.

Rules for bronze:
  1. Every column is text. We do not clean or convert anything here.
  2. Every row records its source file and load time.
  3. Loading the same month twice replaces it. It never duplicates it.
  4. Every load is written to bronze.load_log, pass or fail.
"""

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb

LOAD_LOG_SQL = """
CREATE TABLE IF NOT EXISTS bronze.load_log (
    run_id            VARCHAR,
    source_name       VARCHAR,
    month             VARCHAR,
    resource          VARCHAR,
    api_row_count     BIGINT,
    loaded_row_count  BIGINT,
    status            VARCHAR,
    message           VARCHAR,
    logged_at         TIMESTAMP
)
"""


def connect(warehouse_path: Path) -> duckdb.DuckDBPyConnection:
    """Open the warehouse file, creating it and the bronze schema if needed."""
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute(LOAD_LOG_SQL)
    return con


def write_landing_csv(records: list[dict], target: Path) -> None:
    """Save API records to a CSV in the landing folder, untouched."""
    columns = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def _quote(name: str) -> str:
    """Quote a column name so odd characters cannot break the SQL."""
    return '"' + name.replace('"', '""') + '"'


def _check_table_name(table: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
        raise ValueError(f"Table name must be lower case letters, digits, underscores: {table!r}")


def load_landing_file(
    con: duckdb.DuckDBPyConnection, table: str, resource: str, landing_file: Path
) -> int:
    """Load one landing CSV into bronze.<table>. Returns rows now held for that resource."""
    _check_table_name(table)

    with landing_file.open("r", newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))

    file_literal = "'" + landing_file.as_posix().replace("'", "''") + "'"
    select_list = ", ".join(f"{_quote(col)} AS {_quote(col.lower())}" for col in header)
    source_sql = (
        f"SELECT {select_list}, "
        f"CAST(? AS VARCHAR) AS _source_resource, "
        f"CAST(? AS TIMESTAMP) AS _ingested_at "
        f"FROM read_csv({file_literal}, all_varchar=true, header=true)"
    )
    loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # First load ever: create an empty table with the right columns.
    con.execute(
        f"CREATE TABLE IF NOT EXISTS bronze.{table} AS {source_sql} LIMIT 0",
        [resource, loaded_at],
    )

    # If the source has gained a column since last time, add it rather than fail.
    existing = {
        row[0]
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'bronze' AND table_name = ?",
            [table],
        ).fetchall()
    }
    for col in header:
        if col.lower() not in existing:
            con.execute(f"ALTER TABLE bronze.{table} ADD COLUMN {_quote(col.lower())} VARCHAR")

    # Replace this resource's rows in one transaction, so a re-run never duplicates.
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM bronze.{table} WHERE _source_resource = ?", [resource])
        con.execute(f"INSERT INTO bronze.{table} BY NAME {source_sql}", [resource, loaded_at])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return con.execute(
        f"SELECT COUNT(*) FROM bronze.{table} WHERE _source_resource = ?", [resource]
    ).fetchall()[0][0]


def log_load(con: duckdb.DuckDBPyConnection, entry: dict) -> None:
    """Write one line to the load log."""
    con.execute(
        "INSERT INTO bronze.load_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            entry["run_id"],
            entry["source_name"],
            entry["month"],
            entry.get("resource"),
            entry.get("api_row_count"),
            entry.get("loaded_row_count"),
            entry["status"],
            entry.get("message", ""),
            datetime.now(timezone.utc).replace(tzinfo=None),
        ],
    )
