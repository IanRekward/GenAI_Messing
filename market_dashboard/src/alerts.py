"""
Phone alerts via Pushover (preferred) or Twilio SMS (fallback).
State is persisted in data/alert_state.json to suppress duplicate alerts.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    import pandas as pd

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "alert_state.json"

_BAND_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"composite_band": "green", "red_indicators": [], "orange_indicators": []}


def _save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _send_pushover(title: str, message: str, env: dict) -> bool:
    token = env.get("PUSHOVER_APP_TOKEN", "")
    user = env.get("PUSHOVER_USER_KEY", "")
    if not token or token.startswith("your_") or not user or user.startswith("your_"):
        return False
    try:
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user, "title": title, "message": message},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _send_twilio(message: str, env: dict) -> bool:
    sid = env.get("TWILIO_ACCOUNT_SID", "")
    token = env.get("TWILIO_AUTH_TOKEN", "")
    from_num = env.get("TWILIO_FROM_NUMBER", "")
    to_num = env.get("TWILIO_TO_NUMBER", "")
    if not all([sid, token, from_num, to_num]) or sid.startswith("your_"):
        return False
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"From": from_num, "To": to_num, "Body": message},
            auth=(sid, token),
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def _indicator_label(scoring: dict, ref: str) -> str:
    bkey, ikey = ref.split(".", 1)
    return scoring["buckets"].get(bkey, {}).get("indicators", {}).get(ikey, {}).get("label", ikey)


def send_alerts(scoring: dict, env: dict, history: "pd.DataFrame | None" = None) -> int:
    """Build alert messages, dispatch, and persist state. Returns count sent."""
    from src.history import compute_composite_momentum, cross_bucket_correlation, correlation_regime
    prev = _load_state()
    messages: list[str] = []

    # 1a. Composite band escalation
    cur_band = scoring["composite_band"]
    prev_band = prev.get("composite_band", "green")
    if _BAND_ORDER.get(cur_band, 0) > _BAND_ORDER.get(prev_band, 0):
        messages.append(
            f"COMPOSITE ESCALATED: {prev_band.upper()} → {cur_band.upper()}\n"
            f"Score: {scoring['composite']:.1f}/100"
        )

    # 1b. Composite band de-escalation
    if _BAND_ORDER.get(cur_band, 0) < _BAND_ORDER.get(prev_band, 0):
        messages.append(
            f"COMPOSITE IMPROVED: {prev_band.upper()} → {cur_band.upper()}\n"
            f"Score: {scoring['composite']:.1f}/100 — stress is easing."
        )

    # 2. New red indicators
    cur_reds = [
        f"{bk}.{ik}"
        for bk, bkt in scoring["buckets"].items()
        for ik, ind in bkt["indicators"].items()
        if ind.get("band") == "red"
    ]
    new_reds = [r for r in cur_reds if r not in set(prev.get("red_indicators", []))]
    if new_reds:
        labels = [_indicator_label(scoring, r) for r in new_reds]
        messages.append(f"NEW RED TRIGGERS ({len(new_reds)}): {', '.join(labels)}")

    # 3. Two or more new orange indicators
    cur_oranges = [
        f"{bk}.{ik}"
        for bk, bkt in scoring["buckets"].items()
        for ik, ind in bkt["indicators"].items()
        if ind.get("band") == "orange"
    ]
    new_oranges = [r for r in cur_oranges if r not in set(prev.get("orange_indicators", []))]
    if len(new_oranges) >= 2:
        labels = [_indicator_label(scoring, r) for r in new_oranges[:5]]
        messages.append(f"2+ NEW ORANGE TRIGGERS: {', '.join(labels)}")

    # 4. Rapid rise without band change (early warning)
    if history is not None and not history.empty:
        mom = compute_composite_momentum(history)
        v7 = mom.get("velocity_7d")
        if v7 is not None and v7 >= 10 and cur_band in ("yellow", "orange"):
            rise_key = f"rapid_rise_{cur_band}"
            if rise_key not in prev.get("rapid_rise_alerts", []):
                messages.append(
                    f"RAPID RISE: composite +{v7:.0f} pts in 7 days "
                    f"({mom['regime'].replace('_', ' ')}). "
                    f"Watch for imminent band escalation."
                )
                prev.setdefault("rapid_rise_alerts", []).append(rise_key)
        # Reset rapid_rise tracker on band change
        if cur_band != prev_band:
            prev["rapid_rise_alerts"] = []

    # 5b. Sustained crisis-synchronous cross-bucket correlation (3+ consecutive days)
    if history is not None and not history.empty:
        corr_val = cross_bucket_correlation(history)
        regime = correlation_regime(corr_val)
        streak = prev.get("corr_regime_streak", 0)
        if regime == "crisis_synchronous":
            streak += 1
        else:
            streak = 0
        prev["corr_regime_streak"] = streak
        if streak == 3:  # fires exactly once, on the 3rd day
            messages.append(
                f"CROSS-BUCKET CORRELATION ELEVATED: {corr_val:.2f} (3 days sustained). "
                f"Buckets moving in lockstep — typical pre-crisis or risk-off signature."
            )

    # 5. Data staleness — first occurrence only per indicator
    stale_now = set(scoring.get("stale_indicators", []))
    stale_prev = set(prev.get("stale_indicators", []))
    new_stale = stale_now - stale_prev
    if new_stale:
        labels = []
        for bk, bkt in scoring["buckets"].items():
            for ik in bkt["indicators"]:
                if ik in new_stale:
                    labels.append(_indicator_label(scoring, f"{bk}.{ik}"))
        messages.append(
            f"STALE DATA ({len(new_stale)}): {', '.join(labels[:5])}"
            f"{' +more' if len(labels) > 5 else ''} — "
            f"last observation gap exceeds expected cadence. Check FRED/Yahoo."
        )

    # Accumulate weekly alert count
    weekly_alert_count = prev.get("weekly_alert_count", 0)
    if messages:
        weekly_alert_count += 1

    new_state = {
        "composite_band": cur_band,
        "red_indicators": cur_reds,
        "orange_indicators": cur_oranges,
        "rapid_rise_alerts": prev.get("rapid_rise_alerts", []),
        "stale_indicators": list(stale_now),
        "corr_regime_streak": prev.get("corr_regime_streak", 0),
        "weekly_alert_count": weekly_alert_count,
        "weekly_digest_date": prev.get("weekly_digest_date", ""),
    }

    if not messages:
        _save_state(new_state)
        return 0

    body = "\n\n".join(messages)
    title = f"Market Stress: {cur_band.upper()} ({scoring['composite']:.0f}/100)"

    sent = 0
    if _send_pushover(title, body, env):
        sent = 1
    elif _send_twilio(f"{title}\n{body}", env):
        sent = 1
    else:
        print(f"\n  ALERT — {title}")
        for line in body.splitlines():
            print(f"  {line}")
        sent = 1

    _save_state(new_state)
    return sent


def send_weekly_digest(scoring: dict, env: dict, history: "pd.DataFrame | None" = None) -> bool:
    """Send a Monday morning digest summarizing the prior week. Returns True if sent."""
    import pandas as pd
    today = date.today()
    if today.weekday() != 0:  # 0 = Monday
        return False

    state = _load_state()
    this_monday = today.isoformat()
    if state.get("weekly_digest_date") == this_monday:
        return False  # already sent today

    weekly_alerts = state.get("weekly_alert_count", 0)

    # 7-day composite range from history
    range_str = "—"
    velocity_str = ""
    movers_str = ""
    if history is not None and not history.empty:
        from src.history import compute_composite_momentum
        h = history.copy()
        h["timestamp"] = pd.to_datetime(h["timestamp"])
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=7)
        week = h[h["timestamp"] >= cutoff]
        if not week.empty:
            lo, hi = week["composite"].min(), week["composite"].max()
            range_str = f"{lo:.0f}–{hi:.0f}"

        # Momentum velocity
        mom = compute_composite_momentum(history)
        v7 = mom.get("velocity_7d")
        if v7 is not None:
            sign = "+" if v7 > 0 else ""
            velocity_str = f"\nVelocity 7d: {sign}{v7:.1f} pts ({mom['regime'].replace('_', ' ')})"

        # Biggest bucket movers over 7 days
        bucket_cols = [c for c in h.columns if c.startswith("bucket_")]
        if bucket_cols and len(h) >= 2:
            today_row = h.sort_values("timestamp").iloc[-1]
            past = h[h["timestamp"] <= pd.Timestamp.today() - pd.Timedelta(days=7)]
            if not past.empty:
                past_row = past.sort_values("timestamp").iloc[-1]
                moves = {
                    col.replace("bucket_", ""): float(today_row[col]) - float(past_row[col])
                    for col in bucket_cols
                    if col in today_row and col in past_row
                }
                top = sorted(moves.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                if top:
                    parts = [f"{k} {'+' if v > 0 else ''}{v:.1f}" for k, v in top if abs(v) >= 0.5]
                    if parts:
                        movers_str = f"\nBiggest movers: {', '.join(parts)}"

    composite = scoring["composite"]
    band = scoring["composite_band"]
    title = f"Weekly Digest: {band.upper()} ({composite:.0f}/100)"
    body = (
        f"7-day composite range: {range_str}"
        f"{velocity_str}"
        f"{movers_str}"
        f"\nAlerts this week: {weekly_alerts}"
        f"\nhttps://ianrekward.github.io/GenAI_Messing/"
    )

    sent = _send_pushover(title, body, env)

    # Reset weekly counter and mark digest sent
    state["weekly_digest_date"] = this_monday
    state["weekly_alert_count"] = 0
    _save_state(state)
    return sent


def send_heartbeat(scoring: dict, env: dict) -> bool:
    """Send a daily Pushover confirmation for the first 31 days of scheduled runs."""
    state = _load_state()
    today = date.today().isoformat()

    start = state.get("heartbeat_start")
    if not start:
        state["heartbeat_start"] = today
        _save_state(state)
        start = today

    days_elapsed = (date.today() - date.fromisoformat(start)).days
    if days_elapsed >= 31:
        return False

    days_left = 31 - days_elapsed
    title = f"Dashboard OK – day {days_elapsed + 1}/31"
    body = (
        f"Composite: {scoring['composite']:.0f}/100 ({scoring['composite_band'].upper()})\n"
        f"Triggers: {scoring['red_count']} red, "
        f"{scoring['orange_count']} orange, {scoring['yellow_count']} yellow\n"
        f"{days_left} confirmation{'s' if days_left != 1 else ''} remaining\n"
        f"https://ianrekward.github.io/GenAI_Messing/"
    )
    return _send_pushover(title, body, env)
