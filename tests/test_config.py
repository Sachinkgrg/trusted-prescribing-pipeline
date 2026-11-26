import pytest

from pipeline.config import load_config, month_range


def test_month_range_crosses_a_year_end():
    assert month_range("202511", "202602") == ["202511", "202512", "202601", "202602"]


def test_month_range_single_month():
    assert month_range("202608", "202608") == ["202608"]


@pytest.mark.parametrize("first,last", [("202613", "202701"), ("2026-01", "202602"), ("202603", "202601")])
def test_month_range_rejects_bad_input(first, last):
    with pytest.raises(ValueError):
        month_range(first, last)


def test_real_config_file_loads():
    config = load_config()
    assert config.sources, "config/sources.yml should define at least one source"
    for source in config.sources:
        assert source.months
        assert source.where.strip()
