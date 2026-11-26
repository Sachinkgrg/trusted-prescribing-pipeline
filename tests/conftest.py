"""Shared test helpers.

The tests never call the real portal. FakeApi stands in for it, so the
tests are fast, repeatable and work offline.
"""

from pathlib import Path

import pytest

from pipeline import bronze
from pipeline.config import Config, Source


class FakeApi:
    """Pretends to be the NHSBSA portal, holding rows we give it."""

    def __init__(self, data: dict[str, list[dict]], lie_about_count: int = 0):
        self.data = data  # resource name -> rows
        self.lie_about_count = lie_about_count  # makes the count query disagree

    def list_resources(self, dataset_id: str) -> list[str]:
        return list(self.data)

    def count_rows(self, resource: str, where: str) -> int:
        return len(self.data[resource]) + self.lie_about_count

    def run_sql(self, resource: str, sql: str) -> dict:
        return {"records": self.data[resource]}


def make_rows(month: str, count: int) -> list[dict]:
    return [
        {
            "YEAR_MONTH": month,
            "PRACTICE_CODE": f"A{number:05d}",
            "BNF_CODE": "0501013B0AAABAB",
            "ITEMS": str(number + 1),
            "ACTUAL_COST": "12.34",
        }
        for number in range(count)
    ]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        base_url="https://example.invalid/",
        timeout_seconds=5,
        retries=1,
        warehouse_path=tmp_path / "warehouse.duckdb",
        landing_dir=tmp_path / "landing",
        sources=[
            Source(
                name="epd_test",
                dataset_id="test-dataset",
                bronze_table="epd_raw",
                months=["202601", "202602"],
                where="pco_code = 'X'",
            )
        ],
    )


@pytest.fixture
def con(config: Config):
    connection = bronze.connect(config.warehouse_path)
    yield connection
    connection.close()
