"""LLM news sentiment scoring prototype.

Forward-going only — fetches recent news per ticker from Alpaca, scores each via
Claude Haiku, aggregates per-ticker daily sentiment to research/data/sentiment.jsonl.
Historical backtest deferred (Phase 3 decision).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from anthropic import Anthropic

from alpaca_connector import load_env

OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "sentiment.jsonl"
LIVE_SIGNAL_UNIVERSE = ["XLK", "XLF", "XLE", "XLI", "XLV", "XLY", "XLC", "XLU", "XLRE", "IWM", "QQQ", "SPY"]
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HOURS_LOOKBACK = 24
ARTICLES_PER_SYMBOL = 5

SCORING_PROMPT = """Score the financial sentiment of this news article from the perspective of a holder of {ticker}. Return ONLY a JSON object, no preamble or trailing text.

Format: {{"score": -1, "reason": "brief"}}  where score is one of -1 (bearish), 0 (neutral), or 1 (bullish), and reason is at most 12 words.

Headline: {headline}
Summary: {summary}"""


def _alpaca_news_client() -> NewsClient:
    return NewsClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
    )


def fetch_news(symbol: str, hours: int = HOURS_LOOKBACK, limit: int = ARTICLES_PER_SYMBOL) -> list:
    """Fetch up to `limit` recent articles for one symbol from Alpaca."""
    client = _alpaca_news_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    request = NewsRequest(symbols=symbol, start=start, end=end, limit=limit, exclude_contentless=True)
    response = client.get_news(request)
    return response.data.get("news", [])


def score_sentiment(anthropic_client: Anthropic, ticker: str, headline: str, summary: str) -> dict:
    """Score one article via Claude Haiku. Returns {score: -1|0|1, reason: str}."""
    prompt = SCORING_PROMPT.format(
        ticker=ticker,
        headline=headline or "(none)",
        summary=(summary or "(none)")[:600],
    )
    response = anthropic_client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    try:
        result = json.loads(text)
        score = int(result.get("score", 0))
        if score not in (-1, 0, 1):
            score = 0
        reason = str(result.get("reason", ""))[:120]
        return {"score": score, "reason": reason}
    except Exception:
        return {"score": 0, "reason": f"parse_error: {text[:60]}"}


def score_today(symbols: list[str]) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env — see https://console.anthropic.com/")
    anthropic_client = Anthropic(api_key=api_key)

    records = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for symbol in symbols:
        articles = fetch_news(symbol)
        if not articles:
            records.append({
                "timestamp": timestamp, "ticker": symbol, "article_count": 0,
                "avg_score": None, "positive": 0, "neutral": 0, "negative": 0,
                "headlines": [], "scored": [],
            })
            continue

        scored = []
        for article in articles:
            headline = getattr(article, "headline", "") or ""
            summary = getattr(article, "summary", "") or ""
            result = score_sentiment(anthropic_client, symbol, headline, summary)
            scored.append({
                "headline": headline[:160],
                "score": result["score"],
                "reason": result["reason"],
            })

        scores = [s["score"] for s in scored]
        records.append({
            "timestamp": timestamp,
            "ticker": symbol,
            "article_count": len(scored),
            "avg_score": round(sum(scores) / len(scores), 3),
            "positive": sum(1 for s in scores if s == 1),
            "neutral": sum(1 for s in scores if s == 0),
            "negative": sum(1 for s in scores if s == -1),
            "headlines": [s["headline"] for s in scored],
            "scored": scored,
        })

    return records


def append_records(records: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    load_env()
    print(f"Scoring sentiment for {len(LIVE_SIGNAL_UNIVERSE)} tickers (last {HOURS_LOOKBACK}h, up to {ARTICLES_PER_SYMBOL} per ticker)...")
    print()
    try:
        records = score_today(LIVE_SIGNAL_UNIVERSE)
    except RuntimeError as e:
        print(f"ABORT: {e}")
        sys.exit(1)
    append_records(records)

    print("=== Sentiment summary ===")
    print(f"{'ticker':6} {'count':>6} {'avg':>7}  +/o/-")
    for r in records:
        if r["article_count"] == 0:
            print(f"  {r['ticker']:5}    0       —")
        else:
            print(f"  {r['ticker']:5} {r['article_count']:>6} {r['avg_score']:+.2f}  {r['positive']}/{r['neutral']}/{r['negative']}")
    print()
    print(f"Records appended to {OUTPUT_PATH}")
