from datetime import date
from src.dashboard import _next_release_label


def test_weekly_friday_from_monday():
    monday = date(2026, 5, 11)
    result = _next_release_label("stlfsi", today=monday)
    assert "Fri May 15" in result


def test_weekly_thursday_from_monday():
    monday = date(2026, 5, 11)
    result = _next_release_label("jobless_claims", today=monday)
    assert "Thu May 14" in result


def test_weekly_same_day_advances_one_week():
    # When today IS the release day, next occurrence is 7 days out
    friday = date(2026, 5, 15)
    result = _next_release_label("stlfsi", today=friday)
    assert "Fri May 22" in result


def test_weekly_tuesday_usd_index():
    wednesday = date(2026, 5, 13)
    result = _next_release_label("usd_index", today=wednesday)
    assert "Tue May 19" in result


def test_monthly_returns_timing_string():
    result = _next_release_label("cpi_yoy", today=date(2026, 5, 15))
    assert result.startswith("next release est.")
    assert "BLS" in result


def test_unknown_indicator_returns_empty():
    assert _next_release_label("vix") == ""
    assert _next_release_label("hy_oas") == ""
