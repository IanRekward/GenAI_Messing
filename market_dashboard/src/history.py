"""
Run logging and trend-chart generation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "history.csv"

_BAND_COLOR = {"green": "#22cc44", "yellow": "#ffcc00", "orange": "#ff8800", "red": "#ff4444"}


def log_run(scoring: dict, spx_close: float | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    row: dict = {
        "timestamp": scoring["run_timestamp"],
        "composite": scoring["composite"],
        "composite_band": scoring["composite_band"],
        "red_count": scoring["red_count"],
        "orange_count": scoring["orange_count"],
        "yellow_count": scoring["yellow_count"],
    }
    for bkey, bucket in scoring["buckets"].items():
        row[f"bucket_{bkey}"] = bucket["score"]

    # Extended schema (BACKTEST_DESIGN.md §8a): log individual indicator raws
    for bkey, bucket in scoring["buckets"].items():
        for ikey, ind in bucket.get("indicators", {}).items():
            raw = ind.get("raw")
            if raw is not None:
                row[f"raw_{bkey}__{ikey}"] = raw

    # SPX close (passed separately since it isn't in the scoring dict by default)
    if spx_close is not None:
        row["spx_close"] = spx_close

    df_new = pd.DataFrame([row])
    if HISTORY_FILE.exists():
        df_combined = pd.concat([pd.read_csv(HISTORY_FILE), df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_csv(HISTORY_FILE, index=False)


def load_history(days: int = 90) -> pd.DataFrame:
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_FILE)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    cutoff = datetime.now() - timedelta(days=days)
    return df[df["timestamp"] >= cutoff].sort_values("timestamp").reset_index(drop=True)


def compute_rolling_ic(history: pd.DataFrame, forward_days: int = 30,
                       window_days: int = 180) -> pd.DataFrame:
    """
    Compute rolling Spearman IC of the composite score vs realized forward SPX drawdown.
    Requires 'composite' and 'spx_close' columns and at least forward_days + window_days of data.

    Returns a DataFrame with columns: timestamp, rolling_ic, n_obs.
    """
    from scipy import stats as _stats
    if "spx_close" not in history.columns or len(history) < 10:
        return pd.DataFrame(columns=["timestamp", "rolling_ic", "n_obs"])

    df = history[["timestamp", "composite", "spx_close"]].dropna().copy()
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Compute realized forward max-drawdown for each row
    fwd_dd = []
    for i, row in df.iterrows():
        end_ts = row["timestamp"] + timedelta(days=forward_days)
        future = df.loc[df["timestamp"].between(row["timestamp"], end_ts), "spx_close"]
        if len(future) < 2:
            fwd_dd.append(float("nan"))
        else:
            peak, trough = future.iloc[0], future.min()
            fwd_dd.append((peak - trough) / peak if peak > 0 else float("nan"))

    df["fwd_drawdown"] = fwd_dd
    df = df.dropna(subset=["fwd_drawdown"])

    if len(df) < 10:
        return pd.DataFrame(columns=["timestamp", "rolling_ic", "n_obs"])

    # Rolling IC over a trailing window
    rows = []
    for i in range(len(df)):
        t = df["timestamp"].iloc[i]
        start = t - timedelta(days=window_days)
        w = df[df["timestamp"].between(start, t)]
        if len(w) < 10:
            rows.append({"timestamp": t, "rolling_ic": float("nan"), "n_obs": len(w)})
            continue
        r, _ = _stats.spearmanr(w["composite"].values, w["fwd_drawdown"].values)
        rows.append({"timestamp": t, "rolling_ic": float(r), "n_obs": len(w)})

    return pd.DataFrame(rows)


def degradation_status(rolling_ic_df: pd.DataFrame, backtest_ic: float = 0.15) -> dict:
    """
    Apply Q3 two-tier degradation thresholds (BACKTEST_DESIGN.md §11 Q3).

    Returns dict with keys: status ('ok'/'warning'/'alert'), latest_ic, message.
    """
    if rolling_ic_df.empty or rolling_ic_df["rolling_ic"].dropna().empty:
        return {"status": "unknown", "latest_ic": None,
                "message": "Insufficient history for IC computation (need 30+ days with SPX data)."}

    latest = rolling_ic_df["rolling_ic"].dropna().iloc[-1]
    drop_pct = (backtest_ic - latest) / backtest_ic if backtest_ic > 0 else 0

    # Warning: IC dropped >40% from baseline OR fell below 0.15
    if latest < 0.15 or drop_pct > 0.40:
        # Alert: IC dropped >60% from baseline AND stayed below 0.05 for 60+ days
        recent_60d = rolling_ic_df.dropna(subset=["rolling_ic"]).tail(60)
        if drop_pct > 0.60 and (recent_60d["rolling_ic"] < 0.05).all():
            return {
                "status": "alert",
                "latest_ic": round(float(latest), 3),
                "message": f"ALERT: IC {latest:.3f} has been below 0.05 for 60+ days (baseline: {backtest_ic:.3f}). "
                           "Model may have structurally degraded."
            }
        return {
            "status": "warning",
            "latest_ic": round(float(latest), 3),
            "message": f"Warning: Rolling IC {latest:.3f} dropped {drop_pct*100:.0f}% from backtest baseline ({backtest_ic:.3f})."
        }

    return {
        "status": "ok",
        "latest_ic": round(float(latest), 3),
        "message": f"Model performance nominal. Rolling IC: {latest:.3f} (baseline: {backtest_ic:.3f})."
    }


def build_trend_svg(history: pd.DataFrame) -> str:
    if history.empty or len(history) < 2:
        return (
            '<p style="color:#6e7681;font-style:italic;padding:8px 0">'
            "Trend chart will appear after multiple runs.</p>"
        )

    W, H = 800, 160
    PL, PR, PT, PB = 36, 16, 16, 28
    pw = W - PL - PR
    ph = H - PT - PB
    scores = history["composite"].tolist()
    n = len(scores)

    def x(i: int) -> float:
        return PL + (i / (n - 1)) * pw if n > 1 else float(PL)

    def y(v: float) -> float:
        return PT + (1.0 - v / 100.0) * ph

    # Coloured band backgrounds
    zones = [(70, 100, "#ff222218"), (50, 70, "#ff880018"), (30, 50, "#ffcc0018"), (0, 30, "#22cc4418")]
    bg = "".join(
        f'<rect x="{PL}" y="{y(hi):.1f}" width="{pw}" height="{y(lo)-y(hi):.1f}" fill="{col}"/>'
        for lo, hi, col in zones
    )

    # Horizontal gridlines
    grid = ""
    for val in (25, 50, 75):
        yg = y(val)
        grid += (
            f'<line x1="{PL}" y1="{yg:.1f}" x2="{PL+pw}" y2="{yg:.1f}" stroke="#ffffff14" stroke-width="1"/>'
            f'<text x="{PL-4}" y="{yg+4:.1f}" font-size="10" fill="#6e7681" text-anchor="end">{val}</text>'
        )

    # Score polyline
    pts = " ".join(f"{x(i):.1f},{y(s):.1f}" for i, s in enumerate(scores))
    line = f'<polyline points="{pts}" fill="none" stroke="#4d9de0" stroke-width="2" stroke-linejoin="round"/>'

    # Current-value dot
    lx, ly = x(n - 1), y(scores[-1])
    band = history["composite_band"].iloc[-1] if "composite_band" in history.columns else "green"
    dot_col = _BAND_COLOR.get(band, "#4d9de0")
    dot = f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{dot_col}"/>'

    # Date axis labels
    timestamps = history["timestamp"].tolist()
    label_indices = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
    date_labels = ""
    for i in label_indices:
        if 0 <= i < n:
            dt = pd.to_datetime(timestamps[i])
            date_labels += (
                f'<text x="{x(i):.1f}" y="{H-4}" font-size="10" fill="#6e7681" text-anchor="middle">'
                f'{dt.strftime("%m/%d")}</text>'
            )

    return (
        f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
        f"{bg}{grid}{line}{dot}{date_labels}"
        f"</svg>"
    )
