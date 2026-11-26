"""Look before you load: what does the portal actually hold?

Run from the project folder:

    python -m pipeline.discover                    (resources and column names)
    python -m pipeline.discover --area "NORTH EAST"  (area codes matching some text)

Use this to check the config is asking for something that exists.
"""

import argparse
from pathlib import Path

from pipeline.api import ApiError, NhsbsaApi, find_resource
from pipeline.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explore the NHSBSA Open Data Portal.")
    parser.add_argument("--area", help="Show area codes whose name contains this text")
    parser.add_argument("--config", default="config/sources.yml")
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    api = NhsbsaApi(config.base_url, config.timeout_seconds, config.retries)

    for source in config.sources:
        names = api.list_resources(source.dataset_id)
        print(f"\nSource: {source.name}")
        print(f"Dataset: {source.dataset_id} ({len(names)} resources on the portal)")

        found = {month: find_resource(names, month) for month in source.months}
        for month, resource in found.items():
            print(f"  {month}: {resource or 'NOT FOUND'}")

        available = [resource for resource in found.values() if resource]
        if not available:
            print("  None of the configured months exist. Some resource names on the portal:")
            for name in sorted(names)[-5:]:
                print(f"    {name}")
            continue
        latest = available[-1]

        # 1. One row with no filter at all, so we see the real column names.
        try:
            sample = api.run_sql(latest, f"SELECT * FROM `{latest}` LIMIT 1")
        except ApiError as error:
            print(f"\n  Could not read a sample row from {latest}:\n    {error}")
            continue
        records = sample.get("records", [])
        if records:
            print(f"\n  Columns in {latest}:")
            for column, value in records[0].items():
                print(f"    {column:<32} e.g. {value}")
        else:
            print(f"\n  {latest} returned no rows at all.")

        # 2. Now the filter from the config.
        print(f"\n  Testing the config filter: {source.where}")
        try:
            matched = api.count_rows(latest, source.where)
            print(f"    Rows matching in {latest}: {matched:,}")
            if matched == 0:
                print("    No rows match. Check 'where' in the config.")
        except ApiError as error:
            print(f"    The filter was rejected:\n    {error}")

        if args.area:
            text = args.area.upper().replace("'", "")
            sql = (
                f"SELECT DISTINCT icb_name, pco_code, pco_name FROM `{latest}` "
                f"WHERE icb_name LIKE '%{text}%' OR pco_name LIKE '%{text}%' "
                f"ORDER BY icb_name, pco_name"
            )
            print(f"\n  Areas matching '{text}':")
            try:
                for row in api.run_sql(latest, sql).get("records", []):
                    print("    " + " | ".join(str(value) for value in row.values()))
            except ApiError as error:
                print(f"    The area search was rejected:\n    {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
