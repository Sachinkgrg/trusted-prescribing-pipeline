"""Tests for the gold layer, reconciliation and the findings report."""

from pathlib import Path

import pytest
from conftest import FakeApi
from test_silver import CHECKS, SQL_DIR, epd_row

from pipeline.ingest import run
from pipeline.report import (
    END,
    START,
    ReconciliationError,
    build_gold,
    draw_charts,
    findings_markdown,
    gather,
    reconcile,
    update_readme,
    write_findings,
)
from pipeline.silver import build_silver, load_checks, run_checks

GOLD_DIR = Path(__file__).resolve().parents[1] / "sql" / "gold"


@pytest.fixture
def warehouse(config, con):
    january = [epd_row("202601", n) for n in range(4)]
    january.append(epd_row("202601", 9, PRACTICE_CODE="Y0A12", BNF_CHEMICAL_SUBSTANCE="Doxycycline",
                           BNF_PRESENTATION_CODE="0501030I0AAABAB", ITEMS="5"))
    february = [epd_row("202602", n) for n in range(6)]
    run(config, FakeApi({"EPD_SNOMED_202601": january, "EPD_SNOMED_202602": february}), con)
    build_silver(con, SQL_DIR)
    run_checks(con, load_checks(CHECKS))
    build_gold(con, GOLD_DIR)
    return con


def test_gold_adds_back_up_to_silver(warehouse):
    totals = reconcile(warehouse)
    assert totals["lines"] == 11
    assert totals["items"] == (1 + 2 + 3 + 4) + 5 + (1 + 2 + 3 + 4 + 5 + 6)


def test_reconciliation_catches_lost_money(warehouse):
    warehouse.execute("UPDATE gold.monthly_summary SET cost_gbp = cost_gbp + 10 WHERE month_start = DATE '2026-01-01'")
    with pytest.raises(ReconciliationError, match="GBP"):
        reconcile(warehouse)


def test_substance_shares_add_to_100(warehouse):
    total = warehouse.execute("SELECT SUM(share_of_items_pct) FROM gold.substance_summary").fetchall()[0][0]
    assert total == pytest.approx(100, abs=0.2)


def test_non_standard_practice_codes_are_listed(warehouse):
    facts = gather(warehouse)
    assert [row[0] for row in facts["unusual"]] == ["Y0A12"]
    assert facts["unusual_lines"] == 1


def test_findings_charts_and_readme(warehouse, tmp_path):
    facts = gather(warehouse)
    totals = reconcile(warehouse)

    charts = draw_charts(facts, tmp_path)
    assert all(path.exists() and path.stat().st_size > 1000 for path in charts)

    findings = write_findings(facts, totals, tmp_path).read_text(encoding="utf-8")
    assert "February 2026" in findings_markdown(facts, totals)  # the busier month is the peak
    assert "Y0A12" in findings

    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n{START}\nold\n{END}\noutro\n", encoding="utf-8")
    assert update_readme("new findings", readme)
    assert readme.read_text(encoding="utf-8") == f"intro\n{START}\nnew findings\n{END}\noutro\n"
