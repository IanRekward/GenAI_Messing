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


def compute_composite_momentum(history: pd.DataFrame) -> dict:
    """
    Returns velocity and acceleration of the composite score.

    Keys:
      velocity_7d:      score change over last 7 calendar days (None if <8 rows)
      velocity_30d:     score change over last 30 calendar days (None if <31 rows)
      acceleration_7d:  velocity_7d minus prior week's velocity (None if <15 rows)
      regime:           str — one of accelerating_up / decelerating_up /
                        accelerating_down / decelerating_down / flat / insufficient
    """
    if history.empty or len(history) < 2:
        return {"velocity_7d": None, "velocity_30d": None,
                "acceleration_7d": None, "regime": "insufficient"}

    df = history[["timestamp", "composite"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df = df.sort_values("timestamp").groupby("date").last().reset_index()
    df = df.sort_values("date").reset_index(drop=True)

    if len(df) < 2:
        return {"velocity_7d": None, "velocity_30d": None,
                "acceleration_7d": None, "regime": "insufficient"}

    latest = df.iloc[-1]
    latest_date = pd.Timestamp(latest["date"])
    latest_score = float(latest["composite"])

    def _score_at(days_ago: int) -> float | None:
        target = latest_date - pd.Timedelta(days=days_ago)
        past = df[pd.to_datetime(df["date"]) <= target]
        if past.empty:
            return None
        return float(past.iloc[-1]["composite"])

    s7 = _score_at(7)
    s30 = _score_at(30)
    s14 = _score_at(14)

    v7 = round(latest_score - s7, 2) if s7 is not None else None
    v30 = round(latest_score - s30, 2) if s30 is not None else None
    v7_prior = round(s7 - s14, 2) if (s7 is not None and s14 is not None) else None
    a7 = round(v7 - v7_prior, 2) if (v7 is not None and v7_prior is not None) else None

    _FLAT = 3.0
    if v7 is None:
        regime = "insufficient"
    elif abs(v7) < _FLAT:
        regime = "flat"
    elif v7 > 0:
        regime = "accelerating_up" if (a7 is not None and a7 > 0) else "decelerating_up"
    else:
        regime = "accelerating_down" if (a7 is not None and a7 < 0) else "decelerating_down"

    return {"velocity_7d": v7, "velocity_30d": v30,
            "acceleration_7d": a7, "regime": regime}


def build_trend_svg(history: pd.DataFrame, events: list | None = None) -> str:
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

    timestamps = history["timestamp"].tolist()
    t_min = pd.to_datetime(timestamps[0]).timestamp()
    t_max = pd.to_datetime(timestamps[-1]).timestamp()

    def x(i: int) -> float:
        return PL + (i / (n - 1)) * pw if n > 1 else float(PL)

    def x_date(dt) -> float | None:
        t = pd.to_datetime(dt).timestamp()
        if t_max == t_min or not (t_min <= t <= t_max):
            return None
        return PL + ((t - t_min) / (t_max - t_min)) * pw

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

    # Event markers
    event_markers = ""
    for ev in (events or []):
        ex = x_date(ev["date"])
        if ex is None:
            continue
        label = ev.get("label", "")
        event_markers += (
            f'<line x1="{ex:.1f}" y1="{PT}" x2="{ex:.1f}" y2="{PT+ph}" '
            f'stroke="#6e7681" stroke-width="1" stroke-dasharray="3,3"/>'
            f'<text x="{ex:.1f}" y="{PT-2}" font-size="9" fill="#6e7681" '
            f'text-anchor="middle" transform="rotate(-35,{ex:.1f},{PT-2})">{label}</text>'
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
        f"{bg}{grid}{event_markers}{line}{dot}{date_labels}"
        f"</svg>"
    )
