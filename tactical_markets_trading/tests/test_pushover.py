"""Tests for src/pushover.py title-branding normalization."""
import pushover


def test_format_title_strips_ensemble_prefix():
    assert pushover._format_title("ENSEMBLE: BUY XLK 60 @ $184") == "Tactical Trading — BUY XLK 60 @ $184"


def test_format_title_strips_bare_ensemble():
    assert pushover._format_title("Ensemble ABORT") == "Tactical Trading — ABORT"


def test_format_title_collapses_existing_brand():
    assert pushover._format_title("Tactical Trading DRIFT (2 event(s))") == "Tactical Trading — DRIFT (2 event(s))"


def test_format_title_preserves_component_word():
    # "Reconciler" is a component, not an app brand — keep it.
    assert pushover._format_title("Reconciler CRASHED") == "Tactical Trading — Reconciler CRASHED"


def test_format_title_bare_brand_only():
    assert pushover._format_title("Tactical Trading") == "Tactical Trading"
