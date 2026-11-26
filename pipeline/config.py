"""Read config/sources.yml and turn it into simple Python objects."""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path("config/sources.yml")


@dataclass
class Source:
    name: str
    dataset_id: str
    bronze_table: str
    months: list[str]
    where: str


@dataclass
class Config:
    base_url: str
    timeout_seconds: int
    retries: int
    warehouse_path: Path
    landing_dir: Path
    sources: list[Source]


def month_range(first: str, last: str) -> list[str]:
    """Every month from first to last inclusive, as YYYYMM strings.

    month_range("202511", "202602") -> ["202511", "202512", "202601", "202602"]
    """
    for value in (first, last):
        if len(value) != 6 or not value.isdigit() or not 1 <= int(value[4:]) <= 12:
            raise ValueError(f"Month must be YYYYMM, got {value!r}")
    if first > last:
        raise ValueError(f"Month range is backwards: {first} to {last}")

    months = []
    year, month = int(first[:4]), int(first[4:])
    while f"{year}{month:02d}" <= last:
        months.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    sources = []
    for item in raw["sources"]:
        sources.append(
            Source(
                name=item["name"],
                dataset_id=item["dataset_id"],
                bronze_table=item["bronze_table"],
                months=month_range(str(item["months"]["from"]), str(item["months"]["to"])),
                where=item["where"],
            )
        )

    return Config(
        base_url=raw["api"]["base_url"],
        timeout_seconds=int(raw["api"]["timeout_seconds"]),
        retries=int(raw["api"]["retries"]),
        warehouse_path=Path(raw["warehouse"]["path"]),
        landing_dir=Path(raw["warehouse"]["landing_dir"]),
        sources=sources,
    )
