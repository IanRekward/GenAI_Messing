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


def log_run(scoring: dict) -> None:
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
