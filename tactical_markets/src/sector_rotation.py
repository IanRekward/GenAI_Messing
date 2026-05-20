from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

_NAMES = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLI": "Industrials", "XLV": "Health Care", "XLY": "Consumer Discretionary",
    "XLC": "Communication", "XLU": "Utilities", "XLRE": "Real Estate",
    "IWM": "Russell 2000", "QQQ": "Nasdaq 100", "SPY": "S&P 500",
}


def generate(universe_path: Path, thresholds_path: Path) -> list[dict]:
    universe = yaml.safe_load(universe_path.read_text())
    thresholds = yaml.safe_load(thresholds_path.read_text())

    tickers = universe["sectors"] + universe["broad"]
    spread_threshold = thresholds["spread_pct"] / 100
    mom_window = thresholds["momentum_window"]
    ma_window = thresholds["ma_window"]
    hold_days = thresholds["hold_days"]

    lookback = f"{int(ma_window * 1.6) + 10}d"
    raw = yf.download(tickers, period=lookback, auto_adjust=True, progress=False)

    closes: pd.DataFrame = raw["Close"].dropna(how="all")

    if len(closes) < ma_window + 1:
        raise RuntimeError(f"Only {len(closes)} rows of data — need {ma_window + 1}")

    latest = closes.iloc[-1]
    prev_mom = closes.iloc[-(mom_window + 1)]
    momentum = (latest / prev_mom - 1).dropna()
    ma = closes.tail(ma_window).mean()

    ranked = momentum.sort_values(ascending=False)
    as_of = datetime.now(timezone.utc).isoformat()

    results: list[dict] = []
    used_buys: set[str] = set()
    used_sells: set[str] = set()

    while True:
        buy = next((t for t in ranked.index if t not in used_buys), None)
        sell = next((t for t in reversed(ranked.index) if t not in used_sells), None)
        if buy is None or sell is None or buy == sell:
            break

        buy_mom = ranked[buy]
        sell_mom = ranked[sell]
        spread = buy_mom - sell_mom

        if spread < spread_threshold:
            break

        if latest[buy] <= ma[buy]:
            used_buys.add(buy)
            continue

        buy_name = _NAMES.get(buy, buy)
        sell_name = _NAMES.get(sell, sell)
        spread_pct = spread * 100
        buy_pct = buy_mom * 100
        sell_pct = sell_mom * 100
        buy_price = float(latest[buy])
        buy_ma = float(ma[buy])

        thesis = (
            f"{buy} ({buy_name}) {buy_pct:+.1f}% vs "
            f"{sell} ({sell_name}) {sell_pct:+.1f}% over {mom_window} days. "
            f"Spread: {spread_pct:.1f}%. "
            f"Signal: rotate 5-10% from {sell} -> {buy}. "
            f"Hold {hold_days}-{hold_days + 2} days. "
            f"{buy} above 20d MA (${buy_price:.2f} vs ${buy_ma:.2f}), trend confirmed."
        )

        confidence = round(1 / (1 + math.exp(-(spread_pct - 1.5) / 2.0)), 3)

        results.append({
            "signal": True,
            "signal_type": "sector_rotation",
            "buy": buy,
            "sell": sell,
            "buy_momentum_pct": round(buy_pct, 2),
            "sell_momentum_pct": round(sell_pct, 2),
            "spread_pct": round(spread_pct, 2),
            "confidence": confidence,
            "buy_price": round(buy_price, 2),
            "buy_ma": round(buy_ma, 2),
            "thesis": thesis,
            "as_of": as_of,
        })
        used_buys.add(buy)
        used_sells.add(sell)

    return results


if __name__ == "__main__":
    base = Path(__file__).parent.parent
    results = generate(base / "config" / "universe.yaml", base / "config" / "thresholds.yaml")
    if not results:
        print("No sector rotation signal today (no pairs above gate, or buy targets below 20d MA).")
    else:
        for i, r in enumerate(results, 1):
            print(f"--- Thesis {i} ---")
            print(r["thesis"])
            print(f"Buy:    {r['buy']}  {r['buy_momentum_pct']:+.1f}%  @ ${r['buy_price']}")
            print(f"Sell:   {r['sell']}  {r['sell_momentum_pct']:+.1f}%")
            print(f"Spread: {r['spread_pct']:.1f}%")
            print()
