import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.pushover import send as pushover_send
from src.sector_rotation import generate

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

UNIVERSE = BASE / "config" / "universe.yaml"
THRESHOLDS = BASE / "config" / "thresholds.yaml"
THESES_LOG = BASE / "data" / "theses.jsonl"

# NYSE holidays. Update yearly — if today is in 2028+ this won't catch holidays
# and you'll get a stale-data duplicate thesis pushed to phone.
NYSE_HOLIDAYS = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 7, 5),
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),
}


def main() -> None:
    THESES_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    today_et = now.astimezone(ZoneInfo("America/New_York")).date()

    if today_et.weekday() >= 5:
        print(f"Weekend ({today_et}) — no run.")
        return

    if today_et in NYSE_HOLIDAYS:
        print(f"NYSE holiday ({today_et}) — no run.")
        return

    try:
        results = generate(UNIVERSE, THRESHOLDS)
    except Exception as exc:
        print(f"ERROR: {exc}")
        with open(THESES_LOG, "a") as f:
            f.write(json.dumps({
                "signal": False,
                "error": str(exc),
                "as_of": now.isoformat(),
                "pushover_sent": False,
            }) + "\n")
        return

    if not results:
        print("No sector rotation signal today.")
        with open(THESES_LOG, "a") as f:
            f.write(json.dumps({
                "signal": False,
                "as_of": now.isoformat(),
                "pushover_sent": False,
            }) + "\n")
        return

    message = "\n\n".join(r["thesis"] for r in results)
    print(message)
    sent = pushover_send("Tactical Premarket", message)
    print(f"Pushover: {'sent' if sent else 'FAILED (check .env)'}")

    with open(THESES_LOG, "a") as f:
        for r in results:
            r["pushover_sent"] = sent
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
