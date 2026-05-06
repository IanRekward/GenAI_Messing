from __future__ import annotations

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


def generate(universe_path: Path, thresholds_path: Path) -> dict | None:
    universe = yaml.safe_load(universe_path.read_text())
    thresholds = yaml.safe_load(thresholds_path.read_text())

    tickers = universe["sectors"] + universe["broad"]
    spread_threshold = thresholds["spread_pct"] / 100
    mom_window = thresholds["momentum_window"]
    ma_window = thresholds["ma_window"]
    hold_days = thresholds["hold_days"]

    # Calendar days needed: ma_window trading days ~= 1.4x calendar days
    lookback = f"{int(ma_window * 1.6) + 10}d"
    raw = yf.download(tickers, period=lookback, auto_adjust=True, progress=False)

    closes: pd.DataFrame = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)
    closes = closes.dropna(how="all")

    if len(closes) < ma_window + 1:
        raise RuntimeError(f"Only {len(closes)} rows of data — need {ma_window + 1}")

    latest = closes.iloc[-1]
    prev_mom = closes.iloc[-(mom_window + 1)]
    momentum = (latest / prev_mom - 1).dropna()

    ma = closes.tail(ma_window).mean()

    ranked = momentum.sort_values(ascending=False)
    buy_ticker = ranked.index[0]
    sell_ticker = ranked.index[-1]

    buy_mom = ranked.iloc[0]
    sell_mom = ranked.iloc[-1]
    spread = buy_mom - sell_mom

    if spread < spread_threshold:
        return None

    # Don't trade against longer trend: buy target must be above 20d MA
    buy_price = latest[buy_ticker]
    buy_ma = ma[buy_ticker]
    if buy_price <= buy_ma:
        return None

    buy_name = _NAMES.get(buy_ticker, buy_ticker)
    sell_name = _NAMES.get(sell_ticker, sell_ticker)
    spread_pct = spread * 100
    buy_pct = buy_mom * 100
    sell_pct = sell_mom * 100

    thesis = (
        f"{buy_ticker} ({buy_name}) {buy_pct:+.1f}% vs "
        f"{sell_ticker} ({sell_name}) {sell_pct:+.1f}% over 5 days. "
        f"Spread: {spread_pct:.1f}%. "
        f"Signal: rotate 5-10% from {sell_ticker} -> {buy_ticker}. "
        f"Hold {hold_days}-{hold_days + 2} days. "
        f"{buy_ticker} above 20d MA (${buy_price:.2f} vs ${buy_ma:.2f}), trend confirmed."
    )

    return {
        "signal": True,
        "buy": buy_ticker,
        "sell": sell_ticker,
        "buy_momentum_pct": round(buy_pct, 2),
        "sell_momentum_pct": round(sell_pct, 2),
        "spread_pct": round(spread_pct, 2),
        "buy_price": round(float(buy_price), 2),
        "buy_ma": round(float(buy_ma), 2),
        "thesis": thesis,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    base = Path(__file__).parent.parent
    result = generate(base / "config" / "universe.yaml", base / "config" / "thresholds.yaml")
    if result:
        print(result["thesis"])
        print()
        print(f"Buy:    {result['buy']}  {result['buy_momentum_pct']:+.1f}%  @ ${result['buy_price']}")
        print(f"Sell:   {result['sell']}  {result['sell_momentum_pct']:+.1f}%")
        print(f"Spread: {result['spread_pct']:.1f}%")
    else:
        print("No sector rotation signal today (spread below threshold or buy target below 20d MA).")
