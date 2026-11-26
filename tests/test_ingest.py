"""Tests for the bronze rules written at the top of pipeline/bronze.py."""

from conftest import FakeApi, make_rows

from pipeline.ingest import run


def count(con, sql: str) -> int:
    return con.execute(sql).fetchall()[0][0]


def test_all_rows_land_in_bronze_and_pass(config, con):
    api = FakeApi({"EPD_202601": make_rows("202601", 5), "EPD_202602": make_rows("202602", 7)})

    entries = run(config, api, con)

    assert [entry["status"] for entry in entries] == ["PASS", "PASS"]
    assert count(con, "SELECT COUNT(*) FROM bronze.epd_raw") == 12


def test_bronze_columns_are_lower_case_text_with_lineage(config, con):
    api = FakeApi({"EPD_202601": make_rows("202601", 2), "EPD_202602": make_rows("202602", 2)})
    run(config, api, con)

    columns = dict(
        con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'bronze' AND table_name = 'epd_raw'"
        ).fetchall()
    )
    assert columns["items"] == "VARCHAR"
    assert columns["actual_cost"] == "VARCHAR"
    assert columns["_source_resource"] == "VARCHAR"
    assert columns["_ingested_at"] == "TIMESTAMP"
    assert count(con, "SELECT COUNT(*) FROM bronze.epd_raw WHERE _source_resource IS NULL") == 0


def test_running_twice_does_not_duplicate(config, con):
    api = FakeApi({"EPD_202601": make_rows("202601", 5), "EPD_202602": make_rows("202602", 7)})

    run(config, api, con)
    run(config, api, con)

    assert count(con, "SELECT COUNT(*) FROM bronze.epd_raw") == 12


def test_count_mismatch_is_reported_as_fail(config, con):
    api = FakeApi(
        {"EPD_202601": make_rows("202601", 5), "EPD_202602": make_rows("202602", 7)},
        lie_about_count=3,
    )

    entries = run(config, api, con)

    assert {entry["status"] for entry in entries} == {"FAIL"}
    assert "API says 8, bronze has 5" in entries[0]["message"]


def test_missing_month_is_logged_not_crashed(config, con):
    api = FakeApi({"EPD_202601": make_rows("202601", 5)})  # no February file

    entries = run(config, api, con)

    assert [entry["status"] for entry in entries] == ["PASS", "MISSING"]


def test_every_load_is_written_to_the_load_log(config, con):
    api = FakeApi({"EPD_202601": make_rows("202601", 5)})
    run(config, api, con)

    logged = con.execute(
        "SELECT month, status, api_row_count, loaded_row_count FROM bronze.load_log ORDER BY month"
    ).fetchall()
    assert logged == [("202601", "PASS", 5, 5), ("202602", "MISSING", None, None)]


def test_a_new_source_column_is_added_not_rejected(config, con):
    january = make_rows("202601", 2)
    february = [dict(row, SNOMED_CODE="123456") for row in make_rows("202602", 2)]
    api = FakeApi({"EPD_202601": january, "EPD_202602": february})

    entries = run(config, api, con)

    assert [entry["status"] for entry in entries] == ["PASS", "PASS"]
    assert count(con, "SELECT COUNT(*) FROM bronze.epd_raw WHERE snomed_code = '123456'") == 2
    assert count(con, "SELECT COUNT(*) FROM bronze.epd_raw WHERE snomed_code IS NULL") == 2


def test_one_broken_month_does_not_stop_the_others(config, con):
    class BreaksOnJanuary(FakeApi):
        def run_sql(self, resource, sql):
            if resource.endswith("202601"):
                raise RuntimeError("portal timed out")
            return super().run_sql(resource, sql)

    api = BreaksOnJanuary({"EPD_202601": make_rows("202601", 5), "EPD_202602": make_rows("202602", 7)})

    entries = run(config, api, con)

    assert [entry["status"] for entry in entries] == ["ERROR", "PASS"]
    assert "portal timed out" in entries[0]["message"]
