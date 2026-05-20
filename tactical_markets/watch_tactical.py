import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.pushover import send as pushover_send

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

THESES_LOG = BASE / "data" / "theses.jsonl"

NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}


def main() -> None:
    today_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date()

    if today_et.weekday() >= 5 or today_et in NYSE_HOLIDAYS:
        return

    ran_today = False
    if THESES_LOG.exists():
        with open(THESES_LOG) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_date = (
                        datetime.fromisoformat(entry["as_of"])
                        .astimezone(ZoneInfo("America/New_York"))
                        .date()
                    )
                    if entry_date == today_et:
                        ran_today = True
                        break
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass

    if ran_today:
        print(f"Thesis confirmed for {today_et}.")
    else:
        print(f"No thesis for {today_et} — alerting.")
        pushover_send(
            "Tactical Markets MISSED",
            f"No thesis recorded for {today_et}. Scheduler may have failed.",
        )


if __name__ == "__main__":
    main()
