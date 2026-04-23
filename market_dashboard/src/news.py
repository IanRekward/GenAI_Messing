"""
RSS headline fetching and Claude Haiku triage.
Set ENABLE_NEWS_TRIAGE=false in .env to skip entirely.
"""
from __future__ import annotations

from pathlib import Path

import feedparser
import yaml

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/",
    "https://finance.yahoo.com/rss/topstories",
    "https://www.wsj.com/xml/rss/3_7085.xml",
]

WATCHLIST = [
    "fed", "federal reserve", "rate", "inflation", "recession", "credit",
    "yield", "vix", "volatility", "bank", "liquidity", "spread",
    "oil", "crude", "energy", "china", "iran", "ukraine", "russia",
    "tariff", "trade", "default", "debt", "treasury", "geopolit",
    "crisis", "collapse", "contagion", "shock",
]

_SYSTEM = (
    "You are a concise financial analyst. Given a list of news headlines, "
    "return exactly 4–5 bullet points (start each with '•') summarising the "
    "most market-relevant stories. Focus on systemic risk, macro policy, and "
    "credit/liquidity signals. Skip individual stock moves."
)


def _pull_headlines(max_per_feed: int = 12) -> list[str]:
    headlines: list[str] = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title", "").strip()
                if title:
                    headlines.append(title)
        except Exception:
            continue
    return headlines


def _filter_relevant(headlines: list[str]) -> list[str]:
    relevant = [h for h in headlines if any(kw in h.lower() for kw in WATCHLIST)]
    return relevant if relevant else headlines[:20]


def _load_news_keywords() -> dict:
    path = Path("config/news_keywords.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get("indicators", {}) if data else {}
    except Exception:
        return {}


def filter_headlines_for_triggers(headlines: list[str], triggered_keys: set[str]) -> list[str]:
    """Return headlines that match any keyword for the triggered indicator keys."""
    kw_cfg = _load_news_keywords()
    if not kw_cfg or not triggered_keys:
        return []
    keywords: list[str] = []
    for key in triggered_keys:
        keywords.extend(kw_cfg.get(key, []))
    if not keywords:
        return []
    return [h for h in headlines if any(kw.lower() in h.lower() for kw in keywords)]


def get_trigger_news_context(triggered_keys: set[str], env: dict) -> str:
    """
    Fetch headlines, filter for triggered-indicator keywords, ask Haiku for context.
    Returns a short summary string, or "" if skipped/unavailable.
    """
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_") or not triggered_keys:
        return ""
    try:
        headlines = _pull_headlines()
        relevant = filter_headlines_for_triggers(headlines, triggered_keys)
        if not relevant:
            relevant = _filter_relevant(headlines)[:15]
        if not relevant:
            return ""

        hl_text = "\n".join(f"- {h}" for h in relevant[:20])
        indicator_names = ", ".join(sorted(triggered_keys))
        prompt = (
            f"The following indicators just triggered a stress alert: {indicator_names}.\n"
            f"Given these news headlines, provide 2–3 bullet points of context "
            f"explaining what may be driving the stress signal:\n{hl_text}"
        )

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=(
                "You are a concise financial analyst. Focus on macro risk, credit, "
                "and liquidity signals. Start each bullet with '•'."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        bullets = [
            line.lstrip("•-* ").strip()
            for line in text.splitlines()
            if line.strip() and line.strip()[0] in "•-*"
        ]
        return "\n".join(f"• {b}" for b in bullets[:4]) if bullets else text[:300]
    except Exception:
        return ""


def get_news_brief(env: dict) -> list[dict]:
    """Return list of {text} dicts. Returns [] when triage is off or key is missing."""
    if env.get("ENABLE_NEWS_TRIAGE", "true").lower() != "true":
        return []
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return []

    headlines = _pull_headlines()
    if not headlines:
        return []

    relevant = _filter_relevant(headlines)
    hl_text = "\n".join(f"- {h}" for h in relevant[:30])

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Headlines:\n{hl_text}"}],
        )
        text = resp.content[0].text.strip()
        bullets = [
            line.lstrip("•-* ").strip()
            for line in text.splitlines()
            if line.strip() and line.strip()[0] in "•-*"
        ]
        return [{"text": b} for b in bullets[:6]] if bullets else [{"text": text}]
    except Exception as exc:
        return [{"text": f"News triage unavailable: {exc}"}]
