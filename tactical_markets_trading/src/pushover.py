import os

import requests

# Single canonical brand for every notification. Historically call sites used
# ad-hoc prefixes ("ENSEMBLE:", "Ensemble", "Tactical Trading", "Reconciler:"),
# which read as haphazard in the phone notification list. send() now collapses
# the app-level prefixes into one consistent brand so titles are uniform without
# touching every call site. Component words like "Reconciler" are preserved.
_PREFIX = "Tactical Trading"

# Longest-first so "Tactical Trading:" matches before "Tactical Trading".
_LEGACY_BRAND_PREFIXES = ("Tactical Trading:", "Tactical Trading", "ENSEMBLE:", "Ensemble")


def _format_title(title: str) -> str:
    """Normalize a raw title to the canonical brand: strip any legacy app-level
    prefix and re-apply '<brand> — '. Component-level words (e.g. 'Reconciler')
    are left intact."""
    cleaned = title.strip()
    for legacy in _LEGACY_BRAND_PREFIXES:
        if cleaned.lower().startswith(legacy.lower()):
            cleaned = cleaned[len(legacy):].lstrip(": ").strip()
            break
    return f"{_PREFIX} — {cleaned}" if cleaned else _PREFIX


def send(title: str, message: str) -> bool:
    title = _format_title(title)
    token = os.environ.get("PUSHOVER_TOKEN", "")
    user = os.environ.get("PUSHOVER_USER", "")
    if not token or not user:
        print(f"[pushover not configured] {title}: {message}")
        return False
    try:
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user, "title": title, "message": message},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[pushover http {resp.status_code}] {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[pushover failed] {e}")
        return False
