import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
BRIEFINGS = BASE / "data" / "briefings.jsonl"

WARN_EVENT = {"kill_switch": "kill_switch_change", "bot_stale": "bot_run_change"}


def load() -> list[dict]:
    entries = []
    if BRIEFINGS.exists():
        for ln in BRIEFINGS.read_text().splitlines():
            try:
                e = json.loads(ln)
                e["_date"] = datetime.fromisoformat(e["as_of"]).astimezone(
                    ZoneInfo("America/New_York")).date()
                entries.append(e)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return entries


def detect_events(entries: list[dict]) -> list[tuple[date, str]]:
    events = []
    ok = [e for e in entries if "snapshot" in e]
    for prev, cur in zip(ok, ok[1:]):
        p, c = prev["snapshot"], cur["snapshot"]
        if p.get("entry_ok") is not None and c.get("entry_ok") is not None \
                and p["entry_ok"] != c["entry_ok"]:
            events.append((cur["_date"], "kill_switch_change"))
        p_stale = any(w["type"] == "bot_stale" for w in prev.get("warnings", []))
        c_stale = any(w["type"] == "bot_stale" for w in cur.get("warnings", []))
        if p_stale != c_stale:
            events.append((cur["_date"], "bot_run_change"))
    return events


def main() -> None:
    entries = load()
    if not entries:
        print("No briefings logged yet — nothing to score.")
        return
    print(f"Briefings: {len(entries)} entries, "
          f"{sum(1 for e in entries if 'error' in e)} error days, "
          f"{sum(1 for e in entries if not e.get('pushover_sent'))} unsent days "
          f"({entries[0]['_date']} → {entries[-1]['_date']})")

    counts = Counter(w["type"] for e in entries for w in e.get("warnings", []))
    print("\n⚠ counts by type:" if counts else "\n⚠ counts by type: none yet")
    for t, n in counts.most_common():
        print(f"  {t}: {n}")
    for w in entries[-1].get("warnings", []):
        if w["type"] == "pending":
            print(f"  currently pending {w['age_days']}d: {w['desc']}")

    events = detect_events(entries)
    print("\nEvents:" if events else "\nEvents: none detected yet")
    for d, kind in events:
        print(f"  {d}: {kind}")

    for wtype, ev in WARN_EVENT.items():
        warned_days = [e["_date"] for e in entries
                       if any(w["type"] == wtype for w in e.get("warnings", []))]
        ev_days = [d for d, kind in events if kind == ev]
        if warned_days:
            hits = sum(1 for wd in warned_days if any(0 < (ed - wd).days <= 3 for ed in ev_days))
            print(f"\n{wtype} precision: {hits}/{len(warned_days)} ⚠ days followed by {ev} within 3d")
        else:
            print(f"\n{wtype} precision: n/a (no ⚠ days)")
        if ev_days:
            missed = sum(1 for ed in ev_days if not any(0 <= (ed - wd).days <= 3 for wd in warned_days))
            print(f"{wtype} recall: {len(ev_days) - missed}/{len(ev_days)} events had a prior ⚠ within 3d")
        else:
            print(f"{wtype} recall: n/a (no events)")

    print("\nProximity scoring (stop/MA ⚠) lands with phase 2b.")


if __name__ == "__main__":
    main()
