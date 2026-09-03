import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# briefing text carries ⚠/· — the scheduled-task console is cp1252 and an
# unprintable char must never kill the run before the push
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.briefing import NYSE_HOLIDAYS, build_briefing, save_state
from src.pushover import send as pushover_send

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

BRIEFINGS_LOG = BASE / "data" / "briefings.jsonl"


def main() -> None:
    BRIEFINGS_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    now_et = now.astimezone(ZoneInfo("America/New_York"))
    today_et = now_et.date()

    if today_et.weekday() >= 5:
        print(f"Weekend ({today_et}) — no run.")
        return

    if today_et in NYSE_HOLIDAYS:
        print(f"NYSE holiday ({today_et}) — no run.")
        return

    try:
        result = build_briefing(now_et)
    except Exception as exc:
        print(f"ERROR: {exc}")
        with open(BRIEFINGS_LOG, "a") as f:
            f.write(json.dumps({
                "signal_type": "premarket_briefing",
                "error": str(exc),
                "as_of": now.isoformat(),
                "pushover_sent": False,
            }) + "\n")
        return

    print(result["message"])
    sent = pushover_send("Premarket Briefing", result["message"])
    print(f"Pushover: {'sent' if sent else 'FAILED (check .env)'}")

    with open(BRIEFINGS_LOG, "a") as f:
        f.write(json.dumps({
            "signal_type": "premarket_briefing",
            "as_of": now.isoformat(),
            "message": result["message"],
            "snapshot": result["snapshot"],
            "deltas": result["deltas"],
            "pending": result["pending"],
            "warnings": result["warnings"],
            "pushover_sent": sent,
        }) + "\n")

    # state saved only after a successful push — a failed push must
    # re-surface today's deltas tomorrow instead of marking them seen
    if sent:
        save_state(today_et, result["snapshot"], result["pending"])


def write_heartbeat() -> None:
    repo = BASE.parent / "_genai_tmp"
    hb = repo / "tactical_markets" / "data" / "heartbeat.txt"
    hb.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    hb.write_text(now.isoformat() + "\n")

    def git(*args: str) -> int:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode

    git("add", "tactical_markets/data/heartbeat.txt")
    git("commit", "-m", f"tactical heartbeat {now.astimezone(ZoneInfo('America/New_York')).date()}")
    if git("push", "origin", "main") != 0:
        # -X theirs: replayed local commits win conflicts — the newest
        # heartbeat timestamp is always the right one. Abort on failure so
        # a bad morning never leaves the repo mid-rebase for the next run.
        if git("pull", "--rebase", "--autostash", "-X", "theirs") != 0:
            git("rebase", "--abort")
        if git("push", "origin", "main") != 0:
            print("Heartbeat push FAILED — GH Action will alert.")
            return
    print("Heartbeat pushed.")


if __name__ == "__main__":
    main()
    write_heartbeat()
