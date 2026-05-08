import os

import requests


def send(title: str, message: str) -> bool:
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
