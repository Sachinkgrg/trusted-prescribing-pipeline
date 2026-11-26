"""Tests for the silver layer and the data quality checks.

The rows below use the real NHSBSA column names, so the cleaning SQL
is tested against the same shape of data it meets in production.
"""

from pathlib import Path

import pytest
from conftest import FakeApi

from pipeline.ingest import run
from pipeline.silver import build_silver, load_checks, run_checks

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "silver"
CHECKS = ROOT / "config" / "checks.yml"


def epd_row(month: str, number: int, **changes) -> dict:
    """One realistic EPD row. month is YYYYMM; the source writes it as YYYY-MM."""
    row = {
        "YEAR_MONTH": f"{month[:4]}-{month[4:]}",
        "REGIONAL_OFFICE_NAME": "NORTH EAST AND YORKSHIRE",
        "REGIONAL_OFFICE_CODE": "Y63",
        "ICB_NAME": "NHS NORTH EAST AND NORTH CUMBRIA INTEGRATED CARE BOARD",
        "ICB_CODE": "QHM",
        "PCO_NAME": "NEWCASTLE GATESHEAD",
        "PCO_CODE": "13T00",
        "PRACTICE_NAME": f"TEST SURGERY {number}",
        "PRACTICE_CODE": f"A{86000 + number}",
        "ADDRESS_1": "1 HIGH STREET",
        "ADDRESS_2": "",
        "ADDRESS_3": "NEWCASTLE",
        "ADDRESS_4": "TYNE AND WEAR",
        "POSTCODE": "NE1 1AA",
        "BNF_CHEMICAL_SUBSTANCE_CODE": "0501013B0",
        "BNF_CHEMICAL_SUBSTANCE": "Amoxicillin",
        "BNF_PRESENTATION_CODE": "0501013B0AAABAB",
        "BNF_PRESENTATION_NAME": "Amoxicillin 500mg capsules",
        "BNF_CHAPTER_PLUS_CODE": "05: Infections",
        "QUANTITY": "21",
        "ITEMS": str(number + 1),
        "TOTAL_QUANTITY": str(21 * (number + 1)),
        "ADQ_USAGE": "7",
        "NIC": "1.23",
        "ACTUAL_COST": "1.15",
        "UNIDENTIFIED": "N",
        "SNOMED_CODE": "39732411000001106",
    }
    row.update(changes)
    return row


def build(config, con, january: list[dict], february: list[dict]):
    run(config, FakeApi({"EPD_SNOMED_202601": january, "EPD_SNOMED_202602": february}), con)
    build_silver(con, SQL_DIR)
    results = run_checks(con, load_checks(CHECKS))
    return {r["name"]: r for r in results}


def clean_months():
    return [epd_row("202601", n) for n in range(3)], [epd_row("202602", n) for n in range(4)]


def count(con, sql: str) -> int:
    return con.execute(sql).fetchall()[0][0]


def test_clean_data_passes_every_check(config, con):
    results = build(config, con, *clean_months())
    assert {name: r["status"] for name, r in results.items() if r["status"] != "PASS"} == {}


def test_types_are_converted(config, con):
    build(config, con, *clean_months())
    types = dict(
        con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'silver' AND table_name = 'prescribing'"
        ).fetchall()
    )
    assert types["month_start"] == "DATE"
    assert types["items"] == "BIGINT"
    assert types["actual_cost_gbp"] == "DOUBLE"
    assert types["is_unidentified"] == "BOOLEAN"


def test_values_are_converted_correctly(config, con):
    build(config, con, *clean_months())
    month, items, cost, flag = con.execute(
        "SELECT month_start, items, actual_cost_gbp, is_unidentified FROM silver.prescribing "
        "WHERE practice_code = 'A86002' AND month_start = DATE '2026-01-01'"
    ).fetchall()[0]
    assert str(month) == "2026-01-01"
    assert items == 3
    assert cost == pytest.approx(1.15)
    assert flag is False


def test_bad_rows_are_flagged_not_deleted(config, con):
    january, february = clean_months()
    january += [
        epd_row("202601", 10, PRACTICE_CODE=""),          # missing mandatory field
        epd_row("202601", 11, ACTUAL_COST="-4.00"),       # negative cost
        epd_row("202601", 12, ITEMS="1.5"),               # not a whole number
        epd_row("202601", 13, YEAR_MONTH="Jan 2026"),     # month cannot be read
        epd_row("202601", 14, PCO_CODE="99X00"),          # wrong area
        epd_row("202601", 15, UNIDENTIFIED="maybe"),      # invalid flag
    ]
    results = build(config, con, january, february)

    assert results["mandatory_fields_present"]["status"] == "FAIL"
    assert results["numbers_are_numbers"]["status"] == "FAIL"
    assert results["month_is_a_date"]["status"] == "FAIL"
    assert results["in_scope_area"]["status"] == "FAIL"
    assert results["cost_not_negative"]["status"] == "WARN"
    assert results["unidentified_flag_valid"]["status"] == "WARN"
    assert results["no_rows_lost"]["status"] == "PASS"
    assert count(con, "SELECT COUNT(*) FROM silver.prescribing") == 3 + 6 + 4


def test_row_in_the_wrong_monthly_file_is_caught(config, con):
    january, february = clean_months()
    february.append(epd_row("202601", 20))  # a January row inside the February file
    results = build(config, con, january, february)
    assert results["month_matches_source_file"]["status"] == "FAIL"
    assert results["month_matches_source_file"]["failing_rows"] == 1


def test_duplicate_rows_are_warned(config, con):
    january, february = clean_months()
    january.append(epd_row("202601", 0))  # exact copy of an existing row
    results = build(config, con, january, february)
    assert results["no_duplicate_rows"]["status"] == "WARN"
    assert results["no_duplicate_rows"]["failing_rows"] == 1


def test_rebuilding_is_safe_and_results_keep_history(config, con):
    january, february = clean_months()
    build(config, con, january, february)
    build(config, con, january, february)
    assert count(con, "SELECT COUNT(*) FROM silver.prescribing") == 7
    assert count(con, "SELECT COUNT(DISTINCT run_id) FROM silver.dq_results") == 2


def test_every_check_in_the_real_file_is_well_formed():
    checks = load_checks(CHECKS)
    assert len(checks) >= 10
    assert len({c["name"] for c in checks}) == len(checks), "check names must be unique"
