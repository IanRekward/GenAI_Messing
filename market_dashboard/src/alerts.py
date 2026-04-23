"""
Phone alerts via Pushover (preferred) or Twilio SMS (fallback).
State is persisted in data/alert_state.json to suppress duplicate alerts.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

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


def send_alerts(scoring: dict, env: dict) -> int:
    """Build alert messages, dispatch, and persist state. Returns count sent."""
    prev = _load_state()
    messages: list[str] = []

    # 1. Composite band escalation
    cur_band = scoring["composite_band"]
    prev_band = prev.get("composite_band", "green")
    if _BAND_ORDER.get(cur_band, 0) > _BAND_ORDER.get(prev_band, 0):
        messages.append(
            f"COMPOSITE ESCALATED: {prev_band.upper()} → {cur_band.upper()}\n"
            f"Score: {scoring['composite']:.1f}/100"
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

    new_state = {
        "composite_band": cur_band,
        "red_indicators": cur_reds,
        "orange_indicators": cur_oranges,
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
