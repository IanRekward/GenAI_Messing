"""
RSS headline fetching and Claude Haiku triage.
Set ENABLE_NEWS_TRIAGE=false in .env to skip entirely.
"""
from __future__ import annotations

import re
from pathlib import Path

import feedparser
import yaml

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
    "most market-relevant stories. Prefer official-source items (Fed, ECB, "
    "Treasury, BLS) when summarizing, but include important wire-service and "
    "publisher stories too. Focus on systemic risk, macro policy, and "
    "credit/liquidity signals. Skip individual stock moves."
)

_CATEGORY_RANK = {"official": 0, "wire": 1, "publisher": 2}


def _load_news_feeds() -> list[dict]:
    path = Path("config/news_feeds.yaml")
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("feeds", []) if data else []


def _title_tokens(title: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\b\w{4,}\b", title)}


def _dedup_headlines(items: list[dict], threshold: float = 0.7) -> list[dict]:
    kept: list[dict] = []
    kept_tokens: list[set[str]] = []
    for item in items:
        toks = _title_tokens(item["title"])
        if not toks:
            continue
        dup_idx = -1
        for i, prior_toks in enumerate(kept_tokens):
            denom = len(toks | prior_toks)
            if denom and len(toks & prior_toks) / denom >= threshold:
                dup_idx = i
                break
        if dup_idx == -1:
            kept.append(item)
            kept_tokens.append(toks)
        else:
            if _CATEGORY_RANK[item["category"]] < _CATEGORY_RANK[kept[dup_idx]["category"]]:
                kept[dup_idx] = item
                kept_tokens[dup_idx] = toks
    return kept


def _log_feed_failure(name: str, reason: str) -> None:
    try:
        from src.alerts import _log_alert
        _log_alert({
            "type": "news_feed_failure",
            "feed": name,
            "reason": reason[:200],
        })
    except Exception:
        pass


def _pull_headlines() -> list[dict]:
    """Return [{title, url, source, category}] from all configured feeds, deduped."""
    items: list[dict] = []
    for feed in _load_news_feeds():
        try:
            parsed = feedparser.parse(feed["url"])
            if not parsed.entries:
                _log_feed_failure(feed["name"], "0 entries returned")
                continue
            for entry in parsed.entries[:feed["max_items"]]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if title:
                    items.append({
                        "title": title,
                        "url": link,
                        "source": feed["name"],
                        "category": feed["category"],
                    })
        except Exception as exc:
            _log_feed_failure(feed["name"], str(exc))
            continue
    return _dedup_headlines(items)


def _filter_relevant(headlines: list[str]) -> list[str]:
    relevant = [h for h in headlines if any(kw in h.lower() for kw in WATCHLIST)]
    return relevant if relevant else headlines[:20]


def _best_match_url(bullet: str, items: list[dict]) -> str:
    """Word-overlap heuristic: find the source item with the most title words in the bullet."""
    words = {w.lower() for w in re.findall(r'\b\w{4,}\b', bullet)}
    if not words:
        return ""
    best_score, best_url = 0.0, ""
    for item in items:
        title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b', item["title"])}
        if not title_words:
            continue
        score = len(words & title_words) / len(words)
        if score > best_score:
            best_score, best_url = score, item["url"]
    return best_url if best_score >= 0.25 else ""


def _best_match_item(bullet: str, items: list[dict]) -> dict:
    """Return the best-matching item dict (or empty dict) for source attribution."""
    words = {w.lower() for w in re.findall(r'\b\w{4,}\b', bullet)}
    if not words:
        return {}
    best_score, best_item = 0.0, {}
    for item in items:
        title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b', item["title"])}
        if not title_words:
            continue
        score = len(words & title_words) / len(words)
        if score > best_score:
            best_score, best_item = score, item
    return best_item if best_score >= 0.25 else {}


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
        items = _pull_headlines()
        headlines = [i["title"] for i in items]
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
    """Return list of {text, url, source} dicts. Returns [] when triage is off or key is missing."""
    if env.get("ENABLE_NEWS_TRIAGE", "true").lower() != "true":
        return []
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return []

    items = _pull_headlines()
    if not items:
        return []

    all_titles = [i["title"] for i in items]
    relevant_titles = _filter_relevant(all_titles)
    relevant_items = [i for i in items if i["title"] in set(relevant_titles)]
    hl_text = "\n".join(
        f"- [{i['source']}] {i['title']}" for i in relevant_items[:30]
    )

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
        if bullets:
            result = []
            for b in bullets[:6]:
                matched = _best_match_item(b, relevant_items)
                result.append({
                    "text": b,
                    "url": matched.get("url", ""),
                    "source": matched.get("source", ""),
                })
            return result
        return [{"text": text, "url": "", "source": ""}]
    except Exception as exc:
        return [{"text": f"News triage unavailable: {exc}", "url": "", "source": ""}]
