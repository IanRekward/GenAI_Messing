from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent.parent
MACRO_LATEST = BASE.parent / "market_dashboard" / "data" / "latest.json"
BOT_DATA = BASE.parent / "tactical_markets_trading" / "data"
STATE_PATH = BASE / "data" / "briefing_state.json"

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

# NYSE holidays. Update yearly — if today is in 2028+ this won't catch holidays.
NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}

MACRO_KEYS = ["run_timestamp", "composite", "composite_band", "composite_short",
              "composite_short_band", "regime", "shock_type", "red_count"]
BOT_KEYS = ["completed_at", "mode", "equity", "open_position_count",
            "entry_ok", "had_execution_failures"]


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def last_trading_day(before: date) -> date:
    d = before - timedelta(days=1)
    while d.weekday() >= 5 or d in NYSE_HOLIDAYS:
        d -= timedelta(days=1)
    return d


def _drift_check(data: dict, keys: list[str], fname: str, warnings: list) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        warnings.append({"type": "schema_drift", "file": fname, "missing": missing})


def regime_line(macro: dict | None, now_et: datetime, warnings: list) -> tuple[str, dict]:
    snap = {"regime": None, "composite_band": None, "composite": None}
    if macro is None:
        warnings.append({"type": "macro_unreadable"})
        return "Regime unknown (MACRO latest.json unreadable)", snap
    _drift_check(macro, MACRO_KEYS, "latest.json", warnings)
    snap = {"regime": macro.get("regime"), "composite_band": macro.get("composite_band"),
            "composite": macro.get("composite")}

    prefix = ""
    ts_raw = macro.get("run_timestamp")
    if ts_raw:
        # run_timestamp is tz-naive local time on a CT machine
        try:
            age_h = (now_et.astimezone(CT) - datetime.fromisoformat(ts_raw).replace(tzinfo=CT)).total_seconds() / 3600
            if age_h > 36:
                prefix = f"⚠ MACRO STALE ({age_h:.0f}h) · "
                warnings.append({"type": "macro_stale", "hours": round(age_h, 1)})
        except ValueError:
            warnings.append({"type": "schema_drift", "file": "latest.json", "missing": ["run_timestamp:unparseable"]})

    def f(k, spec="{}"):
        v = macro.get(k)
        return spec.format(v) if v is not None else "?"

    line = (f"{prefix}Regime {f('regime')} · composite {f('composite')} {f('composite_band')}"
            f" (short {f('composite_short')} {f('composite_short_band')}) · shock {f('shock_type')}")
    if macro.get("red_count"):
        line += f" · {macro['red_count']} red"
    if macro.get("stale_indicators") or macro.get("errors"):
        line += " · ⚠ MACRO internal issues"
        warnings.append({"type": "macro_internal", "stale": macro.get("stale_indicators"),
                         "errors": macro.get("errors")})
    return line, snap


def bot_lines(run: dict | None, account: dict | None, now_et: datetime, warnings: list) -> tuple[list[str], dict]:
    snap = {"entry_ok": None, "entry_gate_reason": None, "open_position_count": None,
            "equity": None, "drawdown_pct": None, "bot_completed_at": None, "mode": None}
    if run is None:
        warnings.append({"type": "bot_unreadable"})
        return ["Bot unknown (last_successful_run.json unreadable)"], snap
    _drift_check(run, BOT_KEYS, "last_successful_run.json", warnings)
    snap.update({k: run.get(k) for k in
                 ["entry_ok", "entry_gate_reason", "open_position_count", "equity", "mode"]})
    snap["bot_completed_at"] = run.get("completed_at")

    fresh = ""
    completed_disp = "?"
    if run.get("completed_at"):
        try:
            completed_et = datetime.fromisoformat(run["completed_at"]).astimezone(ET)
            completed_disp = completed_et.strftime("%a %H:%M ET")
            # bot writes only on trading-day cycles — hours-based staleness
            # false-alarms every Monday, so compare trading dates instead
            if completed_et.date() < last_trading_day(now_et.date()):
                fresh = f"⚠ BOT STALE (last run {completed_et.date()}) · "
                warnings.append({"type": "bot_stale", "last_run_date": str(completed_et.date())})
        except ValueError:
            warnings.append({"type": "schema_drift", "file": "last_successful_run.json",
                             "missing": ["completed_at:unparseable"]})

    if run.get("entry_ok") is False:
        gate = f"⚠ entries BLOCKED ({run.get('entry_gate_reason') or 'no reason given'})"
        warnings.append({"type": "kill_switch", "reason": run.get("entry_gate_reason")})
    else:
        gate = "entries OK" if run.get("entry_ok") else "entries ?"

    equity = run.get("equity")
    eq_disp = f"${equity:,.0f}" if isinstance(equity, (int, float)) else "$?"
    dd_disp = ""
    peak = (account or {}).get("peak_equity")
    if isinstance(equity, (int, float)) and isinstance(peak, (int, float)) and peak > 0:
        snap["drawdown_pct"] = round((equity - peak) / peak * 100, 2)
        dd_disp = f" ({snap['drawdown_pct']:+.1f}% off peak)"
    elif account is None:
        warnings.append({"type": "account_unreadable"})

    lines = [f"{fresh}Bot {completed_disp} · {run.get('mode') or '?'} · {gate} · "
             f"{run.get('open_position_count', '?')} pos · {eq_disp}{dd_disp}"]
    if run.get("had_execution_failures"):
        lines.append("⚠ bot had execution failures")
        warnings.append({"type": "execution_failures"})
    return lines, snap


def derive_trip_date(observed: date) -> date | None:
    try:
        rows = [json.loads(ln) for ln in (BOT_DATA / "trades.jsonl").read_text().splitlines() if ln.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    closed = sorted((t for t in rows if t.get("exit_time_actual")
                     and isinstance(t.get("pnl_dollars"), (int, float))),
                    key=lambda t: t["exit_time_actual"])
    last_win = max((i for i, t in enumerate(closed) if t["pnl_dollars"] > 0), default=None)
    if last_win is None:
        return None
    streak = 0
    for t in closed[last_win + 1:]:
        if t["pnl_dollars"] <= 0:
            streak += 1
            if streak == 5:
                try:
                    trip = datetime.fromisoformat(t["exit_time_actual"]).date()
                except ValueError:
                    return None
                return trip if trip <= observed else None
    return None


def update_pending(stored: dict, snap: dict, today: date) -> dict:
    pending = dict(stored)
    if snap["entry_ok"] is False:
        if "kill_switch_reset" not in pending:
            trip = derive_trip_date(today)
            pending["kill_switch_reset"] = {"first_seen": str(trip or today),
                                            "desc": "kill-switch reset"}
    elif snap["entry_ok"] is True:
        pending.pop("kill_switch_reset", None)
    return pending


def compute_deltas(old: dict | None, snap: dict, today: date) -> list[str]:
    if old is None:
        return ["first briefing — no deltas"]
    deltas: list[str] = []

    def changed(k):
        return old.get(k) is not None and snap.get(k) is not None and old[k] != snap[k]

    if changed("entry_ok"):
        deltas.append("⚠ KILL SWITCH TRIPPED — entries blocked" if snap["entry_ok"] is False
                      else "kill switch CLEARED — entries resumed")
    if changed("regime"):
        deltas.append(f"regime {old['regime']} → {snap['regime']}")
    if changed("composite_band"):
        deltas.append(f"MACRO band {old['composite_band']} → {snap['composite_band']}")
    if changed("open_position_count"):
        deltas.append(f"positions {old['open_position_count']} → {snap['open_position_count']}")
    if changed("mode"):
        deltas.append(f"bot mode {old['mode']} → {snap['mode']}")
    if old.get("drawdown_pct") is not None and snap.get("drawdown_pct") is not None:
        for t in (-5.0, -10.0):
            if old["drawdown_pct"] > t >= snap["drawdown_pct"]:
                deltas.append(f"⚠ drawdown crossed {t:.0f}% (now {snap['drawdown_pct']:+.1f}%)")
            elif snap["drawdown_pct"] > t >= old["drawdown_pct"]:
                deltas.append(f"drawdown recovered above {t:.0f}%")
    return deltas


def build_briefing(now_et: datetime) -> dict:
    warnings: list[dict] = []
    today = now_et.date()

    macro_ln, macro_snap = regime_line(read_json(MACRO_LATEST), now_et, warnings)
    b_lines, bot_snap = bot_lines(read_json(BOT_DATA / "last_successful_run.json"),
                                  read_json(BOT_DATA / "account_state.json"), now_et, warnings)
    snapshot = {**macro_snap, **bot_snap}

    state = read_json(STATE_PATH)
    old_snap = state.get("snapshot") if state else None
    deltas = compute_deltas(old_snap, snapshot, today)
    if (old_snap is not None and old_snap.get("bot_completed_at") is not None
            and snapshot.get("bot_completed_at") == old_snap["bot_completed_at"]
            and any(w["type"] == "bot_stale" for w in warnings)):
        deltas.append("⚠ bot run missed (no new cycle since last briefing)")

    pending = update_pending(state.get("pending", {}) if state else {}, snapshot, today)
    pending_bits = []
    for item in pending.values():
        age = (today - date.fromisoformat(item["first_seen"])).days
        pending_bits.append(f"⚠ pending {age}d: {item['desc']}")
        warnings.append({"type": "pending", "desc": item["desc"], "age_days": age})

    if deltas:
        section0 = deltas + pending_bits
    elif pending_bits:
        section0 = ["No changes. " + " ".join(pending_bits)]
    else:
        section0 = ["No changes."]

    message = "\n".join(section0 + [macro_ln] + b_lines)
    return {"message": message, "snapshot": snapshot, "deltas": deltas,
            "pending": pending, "warnings": warnings}


def save_state(today: date, snapshot: dict, pending: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(
        {"date": str(today), "snapshot": snapshot, "pending": pending}, indent=1))


if __name__ == "__main__":
    result = build_briefing(datetime.now(ET))
    print(result["message"])
    print("\n-- deltas:", result["deltas"])
    print("-- pending:", result["pending"])
    print("-- warnings:", result["warnings"])
