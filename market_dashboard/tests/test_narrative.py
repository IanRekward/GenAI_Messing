"""Tests for src/narrative.py — narrative generation and caching."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from src.narrative import generate_narrative, _build_context


def _scoring(composite: float = 55.0, band: str = "orange") -> dict:
    return {
        "composite": composite,
        "composite_band": band,
        "composite_short": composite + 3.0,
        "buckets": {
            "equity_volatility": {"label": "Equity Volatility", "score": 72.0, "band": "red"},
            "credit_spreads":    {"label": "Credit Spreads",    "score": 58.0, "band": "orange"},
        },
    }


def _history_summary(shock_type: str = "slow_burn", v7: float = 3.5) -> dict:
    return {
        "shock_type": shock_type,
        "velocity_7d": v7,
        "regime": "accelerating_up",
        "bucket_velocities": {"equity_volatility": 6.2, "credit_spreads": 2.1},
    }


# ── _build_context ────────────────────────────────────────────────────────────

def test_build_context_includes_composite():
    ctx = json.loads(_build_context(_scoring(54.3), _history_summary()))
    assert ctx["composite_10yr"] == pytest.approx(54.3)


def test_build_context_includes_shock_type():
    ctx = json.loads(_build_context(_scoring(), _history_summary(shock_type="fast_shock")))
    assert ctx["shock_type"] == "fast_shock"


def test_build_context_short_window():
    ctx = json.loads(_build_context(_scoring(50.0, "orange"), _history_summary()))
    assert "composite_3yr" in ctx


def test_build_context_stressed_buckets_sorted():
    ctx = json.loads(_build_context(_scoring(), _history_summary()))
    scores = [b["score"] for b in ctx.get("stressed_buckets", [])]
    assert scores == sorted(scores, reverse=True)


def test_build_context_no_crash_empty_buckets():
    s = {"composite": 30.0, "composite_band": "yellow", "buckets": {}}
    ctx = json.loads(_build_context(s, _history_summary()))
    assert ctx["composite_10yr"] == 30.0


# ── generate_narrative ────────────────────────────────────────────────────────

def test_generate_narrative_returns_empty_without_api_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = generate_narrative(_scoring(), _history_summary(), {"CACHE_HOURS": "0"})
    assert result == ("", "")


def test_generate_narrative_returns_empty_on_import_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {"CACHE_HOURS": "0", "ANTHROPIC_API_KEY": "sk-ant-test"}
    with patch.dict("sys.modules", {"anthropic": None}):
        result = generate_narrative(_scoring(), _history_summary(), env)
    assert result == ("", "")


def test_generate_narrative_uses_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache_file = tmp_path / "data" / "cache" / "narrative.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"v": 2, "narrative": "Cached summary.", "narrative_layman": "Simple version."}))

    result = generate_narrative(_scoring(), _history_summary(), {"CACHE_HOURS": "12"})
    assert result[0] == "Cached summary."
    assert result[1] == "Simple version."


def test_generate_narrative_calls_claude_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {"CACHE_HOURS": "0", "ANTHROPIC_API_KEY": "sk-ant-test"}

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"expert": "Market stress is elevated at the 55th percentile.", "layman": "Markets are under above-average stress."}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = generate_narrative(_scoring(), _history_summary(), env)

    assert "55th percentile" in result[0]
    assert "above-average stress" in result[1]
    mock_client.messages.create.assert_called_once()


def test_generate_narrative_no_cache_bypass_on_zero_cache_hours(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache_file = tmp_path / "data" / "cache" / "narrative.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"narrative": "Old cached summary.", "narrative_layman": "Old simple."}))

    # CACHE_HOURS=0 means force-refresh; should bypass the cache and hit the API
    env = {"CACHE_HOURS": "0", "ANTHROPIC_API_KEY": "sk-ant-test"}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"expert": "Fresh summary.", "layman": "Fresh simple."}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = generate_narrative(_scoring(), _history_summary(), env)

    assert result[0] == "Fresh summary."
    assert result[1] == "Fresh simple."


# ── dashboard HTML wiring ──────────────────────────────────────────────────────

def test_dashboard_renders_localstorage_key(tmp_path, monkeypatch):
    """Rendered HTML must contain the localStorage key so persistence can't be silently deleted."""
    import pandas as pd
    from src.dashboard import write_dashboard

    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    scoring = {
        "composite": 55.0, "composite_naive": 55.0,
        "composite_band": "orange", "composite_short": 58.0,
        "composite_short_band": "orange", "composite_regime_adj": 55.0,
        "composite_regime_adj_label": "", "regime": "mid",
        "run_timestamp": "2026-05-11T07:30:00",
        "red_count": 0, "orange_count": 1, "yellow_count": 2,
        "stale_indicators": [], "errors": [], "history_years": 10,
        "buckets": {
            "equity_volatility": {
                "label": "Equity Volatility", "weight": 0.13,
                "score": 55.0, "score_short": 55.0, "band": "orange",
                "indicators": {
                    "vix": {
                        "label": "VIX", "raw": 18.0, "zscore": 0.3,
                        "percentile": 55.0, "percentile_short": 55.0,
                        "score": 55.0, "score_short": 55.0,
                        "band": "orange", "unit": "", "manual": False, "invert": False,
                    }
                },
            }
        },
    }

    write_dashboard(
        scoring, news=[], history=pd.DataFrame(),
        narrative="Expert text.", narrative_layman="Plain text.",
    )

    html = (tmp_path / "output" / "dashboard.html").read_text(encoding="utf-8")
    assert "dashboardNarrativeRegister" in html
