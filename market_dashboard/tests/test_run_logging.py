"""Tests for Brief 28 reliability hardening: run logging + dashboard write verification."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest

import run_dashboard


def _logger_to(path: Path) -> logging.Logger:
    logger = logging.getLogger(f"test_run_logging_{path.name}")
    logger.handlers.clear()
    h = logging.FileHandler(path, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)
    return logger


def test_run_cli_logs_traceback_and_reraises(tmp_path, monkeypatch):
    log_file = tmp_path / "run.log"
    monkeypatch.setattr(run_dashboard, "_setup_run_logging", lambda: _logger_to(log_file))

    def boom():
        raise ValueError("synthetic pipeline failure")

    monkeypatch.setattr(run_dashboard, "main", boom)

    with pytest.raises(ValueError, match="synthetic pipeline failure"):
        run_dashboard.run_cli()

    contents = log_file.read_text(encoding="utf-8")
    assert "run start" in contents
    assert "run FAILED" in contents
    assert "ValueError: synthetic pipeline failure" in contents  # full traceback captured


def test_run_cli_logs_ok_summary(tmp_path, monkeypatch):
    log_file = tmp_path / "run.log"
    monkeypatch.setattr(run_dashboard, "_setup_run_logging", lambda: _logger_to(log_file))
    monkeypatch.setattr(run_dashboard, "main", lambda: {
        "composite": 43.1, "composite_band": "orange", "red_count": 1, "orange_count": 2,
    })

    run_dashboard.run_cli()

    contents = log_file.read_text(encoding="utf-8")
    assert "run ok: composite=43.1 band=orange red=1 orange=2" in contents


def test_setup_run_logging_is_configured():
    logger = run_dashboard._setup_run_logging()
    assert logger.level == logging.INFO
    assert any(
        h.__class__.__name__ == "RotatingFileHandler" for h in logger.handlers
    ), "expected a rotating file handler"


# ── _verify_dashboard_written ─────────────────────────────────────────────────

def test_verify_dashboard_written_missing(tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        run_dashboard._verify_dashboard_written(tmp_path / "nope.html", quiet=True)


def test_verify_dashboard_written_stale(tmp_path):
    f = tmp_path / "dashboard.html"
    f.write_text("<html></html>", encoding="utf-8")
    old = time.time() - 600  # 10 minutes ago, well past the 60s freshness window
    os.utime(f, (old, old))
    with pytest.raises(RuntimeError, match="stale cached file"):
        run_dashboard._verify_dashboard_written(f, quiet=True)


def test_verify_dashboard_written_fresh(tmp_path):
    f = tmp_path / "dashboard.html"
    f.write_text("<html></html>", encoding="utf-8")
    run_dashboard._verify_dashboard_written(f, quiet=True)  # must not raise
