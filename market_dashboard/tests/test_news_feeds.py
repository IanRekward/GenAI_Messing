"""Tests for Brief 20 — news feed config validation and headline dedup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.config import _validate_news_feeds, ConfigError
from src.news import _dedup_headlines, _is_recent, NEWS_RECENCY_HOURS


def test_news_feeds_yaml_validates():
    """config/news_feeds.yaml must pass schema validation without error."""
    _validate_news_feeds()


def test_dedup_keeps_highest_tier_source():
    """When two items share the same headline, keep the official-tier source."""
    items = [
        {
            "title": "Federal Reserve raises interest rates by 25 basis points",
            "url": "https://publisher.com/article",
            "source": "MarketWatch",
            "category": "publisher",
        },
        {
            "title": "Federal Reserve raises interest rates by 25 basis points",
            "url": "https://federalreserve.gov/press",
            "source": "Fed Press Releases",
            "category": "official",
        },
    ]
    result = _dedup_headlines(items)
    assert len(result) == 1
    assert result[0]["source"] == "Fed Press Releases"
    assert result[0]["category"] == "official"


def test_dedup_below_threshold_keeps_both():
    """Items with low token overlap are not considered duplicates."""
    items = [
        {
            "title": "Crude oil prices surge amid Middle East tensions",
            "url": "https://a.com/1",
            "source": "Yahoo Finance",
            "category": "publisher",
        },
        {
            "title": "Federal Reserve signals rate pause after inflation data",
            "url": "https://b.com/2",
            "source": "MarketWatch",
            "category": "publisher",
        },
    ]
    result = _dedup_headlines(items)
    assert len(result) == 2


def test_is_recent_drops_old_items():
    """Items older than the recency window are filtered out."""
    old = (datetime.now(timezone.utc) - timedelta(days=30)).timetuple()
    assert not _is_recent(old)


def test_is_recent_keeps_fresh_items():
    """Items within the recency window pass through."""
    fresh = (datetime.now(timezone.utc) - timedelta(hours=4)).timetuple()
    assert _is_recent(fresh)


def test_is_recent_passes_through_missing_date():
    """Items with no parsed date pass through (some feeds omit dates)."""
    assert _is_recent(None)
    assert _is_recent(())


def test_is_recent_window_boundary():
    """Items just inside the cutoff are kept; just outside are dropped."""
    inside = (datetime.now(timezone.utc) - timedelta(hours=NEWS_RECENCY_HOURS - 1)).timetuple()
    outside = (datetime.now(timezone.utc) - timedelta(hours=NEWS_RECENCY_HOURS + 1)).timetuple()
    assert _is_recent(inside)
    assert not _is_recent(outside)
