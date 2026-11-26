"""Have a quick look at what is in the warehouse.

Run from the project folder:

    python -m pipeline.peek
"""

from pathlib import Path

import duckdb

from pipeline.config import load_config


def main() -> int:
    config = load_config(Path("config/sources.yml"))
    if not config.warehouse_path.exists():
        print("No warehouse yet. Run:  python -m pipeline.ingest")
        return 1

    con = duckdb.connect(str(config.warehouse_path), read_only=True)

    print("Latest result for each month (bronze.load_log):")
    con.sql(
        """
        SELECT source_name, month, resource, api_row_count, loaded_row_count, status,
               strftime(logged_at, '%Y-%m-%d %H:%M') AS logged_at_utc
        FROM bronze.load_log
        QUALIFY ROW_NUMBER() OVER (PARTITION BY source_name, month ORDER BY logged_at DESC) = 1
        ORDER BY source_name, month
        """
    ).show(max_rows=100)

    for source in config.sources:
        table = f"bronze.{source.bronze_table}"
        try:
            total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchall()[0][0]
        except duckdb.CatalogException:
            print(f"{table} does not exist yet.")
            continue
        print(f"{table}: {total:,} rows. Five examples:")
        con.sql(f"SELECT * FROM {table} LIMIT 5").show(max_width=160)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
