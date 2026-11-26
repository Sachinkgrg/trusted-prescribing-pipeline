import gzip

import pytest

from pipeline.api import ApiError, NhsbsaApi, find_resource


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200, text=""):
        self.payload = payload
        self.content = content
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    """Returns canned responses instead of calling the internet."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def make_api(responses) -> NhsbsaApi:
    api = NhsbsaApi("https://example.invalid/api/3/action", retries=1)
    api.session = FakeSession(responses)
    return api


def test_find_resource_matches_on_month_suffix():
    names = ["EPD_SNOMED_202601", "EPD_SNOMED_202602"]
    assert find_resource(names, "202602") == "EPD_SNOMED_202602"
    assert find_resource(names, "202612") is None


def test_find_resource_refuses_to_guess_between_two_matches():
    with pytest.raises(ApiError):
        find_resource(["EPD_202601", "EPD_SNOMED_202601"], "202601")


def test_list_resources_reads_names():
    api = make_api([FakeResponse({"success": True, "result": {"resources": [{"name": "EPD_202601"}]}})])
    assert api.list_resources("any") == ["EPD_202601"]


def test_run_sql_reads_the_nested_records():
    payload = {"success": True, "result": {"result": {"records": [{"ITEMS": 3}]}}}
    api = make_api([FakeResponse(payload)])
    assert api.run_sql("EPD_202601", "SELECT 1") == {"records": [{"ITEMS": 3}]}


def test_run_sql_returns_download_links_for_large_results():
    payload = {
        "success": True,
        "result": {"records_truncated": "true", "gc_urls": [{"url": "https://example.invalid/big.csv.gz"}]},
    }
    api = make_api([FakeResponse(payload)])
    assert api.run_sql("EPD_202601", "SELECT 1") == {"download_urls": ["https://example.invalid/big.csv.gz"]}


def test_count_rows_reads_the_single_value():
    payload = {"success": True, "result": {"result": {"records": [{"row_count": 42}]}}}
    api = make_api([FakeResponse(payload)])
    assert api.count_rows("EPD_202601", "pco_code = 'X'") == 42


def test_api_failure_raises_a_clear_error():
    api = make_api([FakeResponse({"success": False, "error": {"message": "bad sql"}})])
    with pytest.raises(ApiError):
        api.run_sql("EPD_202601", "SELEKT")


def test_download_unzips_gzip_files(tmp_path):
    api = make_api([FakeResponse(content=gzip.compress(b"A,B\n1,2\n"))])
    target = tmp_path / "file.csv"
    api.download("https://example.invalid/big.csv.gz", target)
    assert target.read_text() == "A,B\n1,2\n"


def test_rejected_request_shows_the_portals_reason_and_is_not_retried():
    reply = FakeResponse(
        {"success": False, "error": {"message": "column pco_code does not exist"}}, status_code=400
    )
    api = NhsbsaApi("https://example.invalid/api/3/action", retries=3)
    api.session = FakeSession([reply])  # only one reply: a retry would crash the fake

    with pytest.raises(ApiError, match="column pco_code does not exist"):
        api.run_sql("EPD_202601", "SELECT * FROM x WHERE pco_code = 'X'")
    assert len(api.session.calls) == 1


def test_server_error_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("pipeline.api.time.sleep", lambda seconds: None)
    api = NhsbsaApi("https://example.invalid/api/3/action", retries=3)
    api.session = FakeSession(
        [
            FakeResponse(status_code=503, text="busy"),
            FakeResponse({"success": True, "result": {"result": {"records": [{"ITEMS": 1}]}}}),
        ]
    )
    assert api.run_sql("EPD_202601", "SELECT 1") == {"records": [{"ITEMS": 1}]}
    assert len(api.session.calls) == 2
