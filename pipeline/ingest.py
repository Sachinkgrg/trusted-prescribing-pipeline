"""Step 1 of the pipeline: API -> landing files -> bronze tables.

Run from the project folder:

    python -m pipeline.ingest                  (every month in the config)
    python -m pipeline.ingest --month 202608   (one month only)

For each month the pipeline:
  1. finds the matching resource on the portal
  2. asks the API how many rows match the filter
  3. pulls those rows and saves them to data/landing/
  4. loads them into the bronze table
  5. checks loaded rows = API rows and writes the result to bronze.load_log

Statuses:  PASS     counts match
           FAIL     counts do not match
           MISSING  the portal has no file for that month
           ERROR    something broke (the message says what)
"""

import argparse
import sys
import uuid
from pathlib import Path

from pipeline import bronze
from pipeline.api import NhsbsaApi, find_resource
from pipeline.config import Config, Source, load_config


def ingest_month(source: Source, month: str, resource_names, api, con, landing_dir: Path) -> dict:
    """Load one month for one source and return the log entry."""
    entry = {"source_name": source.name, "month": month, "status": "ERROR"}

    resource = find_resource(resource_names, month)
    if resource is None:
        entry.update(status="MISSING", message="No resource on the portal for this month")
        return entry
    entry["resource"] = resource

    expected = api.count_rows(resource, source.where)
    entry["api_row_count"] = expected

    landing_file = landing_dir / source.name / f"{resource}.csv"
    result = api.run_sql(resource, f"SELECT * FROM `{resource}` WHERE {source.where}")

    if "download_urls" in result:
        if len(result["download_urls"]) != 1:
            entry["message"] = f"Expected 1 download link, got {len(result['download_urls'])}"
            return entry
        landing_file.parent.mkdir(parents=True, exist_ok=True)
        api.download(result["download_urls"][0], landing_file)
    elif result["records"]:
        bronze.write_landing_csv(result["records"], landing_file)
    else:
        entry["loaded_row_count"] = 0
        entry["status"] = "PASS" if expected == 0 else "FAIL"
        entry["message"] = "API returned no rows"
        return entry

    loaded = bronze.load_landing_file(con, source.bronze_table, resource, landing_file)
    entry["loaded_row_count"] = loaded

    if loaded == expected:
        entry["status"] = "PASS"
    else:
        entry["status"] = "FAIL"
        entry["message"] = f"Row counts differ: API says {expected}, bronze has {loaded}"
    return entry


def run(config: Config, api, con, only_month: str | None = None) -> list[dict]:
    """Load every configured source and month. Returns all log entries."""
    run_id = uuid.uuid4().hex[:8]
    entries = []

    for source in config.sources:
        resource_names = api.list_resources(source.dataset_id)
        months = [only_month] if only_month else source.months

        for month in months:
            try:
                entry = ingest_month(
                    source, month, resource_names, api, con, config.landing_dir
                )
            except Exception as error:  # one bad month must not stop the rest
                entry = {
                    "source_name": source.name,
                    "month": month,
                    "status": "ERROR",
                    "message": f"{type(error).__name__}: {error}",
                }
            entry["run_id"] = run_id
            bronze.log_load(con, entry)
            entries.append(entry)

            print(
                f"{entry['month']}  {entry.get('resource', '-'):<22}"
                f"api={entry.get('api_row_count', '-')!s:<8}"
                f"loaded={entry.get('loaded_row_count', '-')!s:<8}"
                f"{entry['status']}  {entry.get('message', '')}"
            )
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load NHSBSA data into the bronze layer.")
    parser.add_argument("--month", help="Load one month only, as YYYYMM")
    parser.add_argument("--config", default="config/sources.yml")
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    api = NhsbsaApi(config.base_url, config.timeout_seconds, config.retries)
    con = bronze.connect(config.warehouse_path)
    try:
        entries = run(config, api, con, only_month=args.month)
    finally:
        con.close()

    problems = [entry for entry in entries if entry["status"] != "PASS"]
    print(f"\n{len(entries) - len(problems)} of {len(entries)} loads passed.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
