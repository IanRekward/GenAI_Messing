"""
Daily narrative paragraph: 2-4 sentence plain-English synthesis of the current
market stress state using Claude Haiku. Cached to avoid redundant API calls.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
_CACHE_FILE = CACHE_DIR / "narrative.json"
_CACHE_HOURS = 4.0  # regenerate at most every 4 hours
_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 180


def _cache_valid() -> bool:
    return (
        _CACHE_FILE.exists()
        and (time.time() - _CACHE_FILE.stat().st_mtime) < _CACHE_HOURS * 3600
    )


def _read_cache() -> str:
    with open(_CACHE_FILE) as f:
        return json.load(f).get("narrative", "")


def _write_cache(text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump({"narrative": text}, f)


def _build_context(scoring: dict, history_summary: dict) -> str:
    composite = scoring.get("composite", 0)
    band = scoring.get("composite_band", "green")
    shock_type = history_summary.get("shock_type", "insufficient")
    v7 = history_summary.get("velocity_7d")
    regime = history_summary.get("regime", "insufficient")
    composite_short = scoring.get("composite_short")

    # Top stressor buckets (score ≥ 50) sorted by score desc
    buckets = scoring.get("buckets", {})
    bucket_list = sorted(
        [{"name": b["label"], "score": b["score"],
          "band": b["band"],
          "vel": history_summary.get("bucket_velocities", {}).get(k)}
         for k, b in buckets.items()],
        key=lambda x: -x["score"]
    )
    stressed = [b for b in bucket_list if b["score"] >= 50][:4]
    top_movers = sorted(
        [b for b in bucket_list if b.get("vel") is not None],
        key=lambda x: -abs(x["vel"])
    )[:3]

    ctx: dict = {
        "composite_10yr": composite,
        "band": band,
        "shock_type": shock_type,
        "velocity_7d": v7,
        "momentum_regime": regime,
        "stressed_buckets": [{"name": b["name"], "score": b["score"], "band": b["band"]}
                              for b in stressed],
        "top_movers_7d": [{"name": b["name"], "velocity": b["vel"]} for b in top_movers],
    }
    if composite_short is not None:
        ctx["composite_3yr"] = composite_short

    return json.dumps(ctx, separators=(",", ":"))


_SYSTEM = (
    "You are a concise market risk analyst. "
    "Write exactly 2–4 sentences of plain-English commentary about the current "
    "market stress state provided as JSON. "
    "Cover: what the composite level means, what is driving it, the momentum direction. "
    "Highlight only what is notable or unusual. "
    "Do NOT give investment advice or recommendations. "
    "Tone: informational, precise, neutral. No bullet points or headers."
)


def generate_narrative(scoring: dict, history_summary: dict, env: dict) -> str:
    """
    Generate (or return cached) a 2–4 sentence narrative for the current state.
    Returns "" on any error (missing API key, network failure, etc.).
    """
    # Respect --no-cache flag by checking env
    cache_hours_env = float(env.get("CACHE_HOURS", 12))
    if cache_hours_env > 0 and _cache_valid():
        return _read_cache()

    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        ctx = _build_context(scoring, history_summary)
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": ctx}],
        )
        text = msg.content[0].text.strip()
        _write_cache(text)
        return text
    except Exception:
        return ""
