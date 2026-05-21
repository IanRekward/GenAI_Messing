"""Backfill null SPY / sell-leg benchmarks in trades.jsonl.

Why this is separate from exit_position: EOD bars for the exit day don't exist
yet at exit fill time (we exit at ~9:40 ET; bars materialize after close). Retry
inside the exit path can't help. This script runs after the close and fills
nulls in place.

Usage:
    python src/backfill_benchmarks.py             # backfill any closed trade with null benchmarks
    python src/backfill_benchmarks.py --dry-run   # show what would change, write nothing
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yfinance as yf

from trade_logger import TRADES_PATH


def get_return_pct(ticker: str, start: datetime, end: datetime) -> float | None:
    # yf.Ticker().history() returns flat columns; yf.download() returns MultiIndex
    # columns even for single tickers, which breaks float(data["Close"].iloc[0]).
    start_str = start.date().isoformat()
    end_str = (end.date() + timedelta(days=1)).isoformat()
    data = yf.Ticker(ticker).history(start=start_str, end=end_str, auto_adjust=True)
    if data.empty or len(data) < 2:
        return None
    first = float(data["Close"].iloc[0])
    last = float(data["Close"].iloc[-1])
    return round((last - first) / first * 100, 4)


def backfill(dry_run: bool = False) -> int:
    if not TRADES_PATH.exists():
        print(f"No trades file at {TRADES_PATH}")
        return 0
    with open(TRADES_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    changed = 0
    for record in records:
        if record.get("status") != "closed":
            continue
        spy_missing = record.get("spy_return_pct") is None
        leg_missing = record.get("sell_leg_return_pct") is None
        if not (spy_missing or leg_missing):
            continue
        try:
            entry_time = datetime.fromisoformat(record["entry_time"])
            exit_time = datetime.fromisoformat(record["exit_time_actual"])
        except (KeyError, ValueError) as e:
            print(f"  skip {record['trade_id'][:8]}: bad timestamps ({e})")
            continue

        if spy_missing:
            spy = get_return_pct("SPY", entry_time, exit_time)
            if spy is not None:
                print(f"  {record['trade_id'][:8]} SPY: null -> {spy:+.4f}")
                record["spy_return_pct"] = spy
                changed += 1
            else:
                print(f"  {record['trade_id'][:8]} SPY: still null (yfinance returned nothing)")
        if leg_missing:
            leg = get_return_pct(record["sell_leg"], entry_time, exit_time)
            if leg is not None:
                print(f"  {record['trade_id'][:8]} {record['sell_leg']}: null -> {leg:+.4f}")
                record["sell_leg_return_pct"] = leg
                changed += 1
            else:
                print(f"  {record['trade_id'][:8]} {record['sell_leg']}: still null")

    if changed == 0:
        print("Nothing to backfill.")
        return 0
    if dry_run:
        print(f"\nDry run: would update {changed} field(s) across {sum(1 for r in records if r.get('status')=='closed')} closed trade(s). Wrote nothing.")
        return changed

    with open(TRADES_PATH, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    print(f"\nWrote {changed} backfilled field(s) to {TRADES_PATH}")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
