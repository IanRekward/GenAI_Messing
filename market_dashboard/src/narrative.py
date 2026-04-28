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
_MAX_TOKENS = 400


def _cache_valid() -> bool:
    return (
        _CACHE_FILE.exists()
        and (time.time() - _CACHE_FILE.stat().st_mtime) < _CACHE_HOURS * 3600
    )


def _read_cache() -> tuple[str, str]:
    data = json.load(open(_CACHE_FILE))
    return data.get("narrative", ""), data.get("narrative_layman", "")


def _write_cache(expert: str, layman: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump({"narrative": expert, "narrative_layman": layman}, f)


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
    "Given market stress data as JSON, write two short summaries and respond ONLY with valid JSON "
    "matching this schema exactly: {\"expert\": \"...\", \"layman\": \"...\"}. "
    "expert: 2–4 sentences for a finance professional. Cover composite level, key drivers, momentum direction. "
    "Highlight only what is notable or unusual. Tone: precise, neutral, no recommendations. "
    "layman: 2–4 sentences for someone with no finance background. "
    "Explain what the score means in everyday terms, which areas of the market are under stress, "
    "and what (if anything) a cautious non-expert should be aware of — not what to do. "
    "No jargon, no acronyms. No investment advice in either version."
)


def generate_narrative(scoring: dict, history_summary: dict, env: dict) -> tuple[str, str]:
    """
    Generate (or return cached) expert + layman narrative pair for the current state.
    Returns ("", "") on any error (missing API key, network failure, etc.).
    """
    cache_hours_env = float(env.get("CACHE_HOURS", 12))
    if cache_hours_env > 0 and _cache_valid():
        return _read_cache()

    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return ("", "")

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
        raw = msg.content[0].text.strip()
        try:
            # Strip markdown code fences if present (```json ... ```)
            if raw.startswith("```"):
                raw = raw.split("```")[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            parsed = json.loads(raw)
            expert = parsed.get("expert", raw)
            layman = parsed.get("layman", "")
        except (json.JSONDecodeError, AttributeError):
            expert, layman = raw, ""
        _write_cache(expert, layman)
        return (expert, layman)
    except Exception:
        return ("", "")
