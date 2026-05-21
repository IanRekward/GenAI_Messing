"""
Run logging and trend-chart generation.
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.indicators import BAND_COLOR as _BAND_COLOR

DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "history.csv"


def _weights_hash() -> str:
    """MD5 of config/weights.yaml for provenance tracking."""
    try:
        content = Path("config/weights.yaml").read_bytes()
        return hashlib.md5(content).hexdigest()[:8]
    except Exception:
        return ""


def _code_sha() -> str:
    """Short git HEAD SHA from the _genai_tmp sibling repo, or empty string."""
    genai_dir = Path(__file__).resolve().parent.parent.parent / "_genai_tmp"
    try:
        result = subprocess.run(
            ["git", "-C", str(genai_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def log_run(scoring: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    row: dict = {
        "timestamp": scoring["run_timestamp"],
        "composite": scoring["composite"],
        "composite_band": scoring["composite_band"],
        "red_count": scoring["red_count"],
        "orange_count": scoring["orange_count"],
        "yellow_count": scoring["yellow_count"],
        "weights_hash": _weights_hash(),
        "code_sha": _code_sha(),
        "regime": scoring.get("regime"),
        "composite_naive": scoring.get("composite_naive"),
        "composite_regime_weighted": scoring.get("composite_regime_weighted"),
    }
    for bkey, bucket in scoring["buckets"].items():
        row[f"bucket_{bkey}"] = bucket["score"]

    df_new = pd.DataFrame([row])
    if HISTORY_FILE.exists():
        df_combined = pd.concat([pd.read_csv(HISTORY_FILE), df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_csv(HISTORY_FILE, index=False)


SIDECAR_FILE = DATA_DIR / "latest.json"
SIDECAR_SCHEMA_VERSION = 1


def _strip_series(buckets: dict) -> dict:
    out = {}
    for bkey, b in buckets.items():
        out[bkey] = {
            "label": b["label"], "weight": b["weight"],
            "score": b["score"], "score_short": b.get("score_short"),
            "band": b["band"],
            "indicators": {
                ikey: {k: v for k, v in i.items() if k != "_series"}
                for ikey, i in b["indicators"].items()
            },
        }
    return out


def write_latest_sidecar(scoring: dict, shock_type: str | None = None) -> None:
    import json
    payload = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "run_timestamp": scoring["run_timestamp"],
        "composite": scoring["composite"],
        "composite_naive": scoring.get("composite_naive"),
        "composite_regime_weighted": scoring.get("composite_regime_weighted"),
        "regime_weights_applied": scoring.get("regime_weights_applied", False),
        "composite_band": scoring["composite_band"],
        "composite_short": scoring.get("composite_short"),
        "composite_short_band": scoring.get("composite_short_band"),
        "composite_regime_adj": scoring.get("composite_regime_adj"),
        "composite_regime_adj_label": scoring.get("composite_regime_adj_label"),
        "regime": scoring.get("regime"),
        "shock_type": shock_type,
        "red_count": scoring["red_count"],
        "orange_count": scoring["orange_count"],
        "yellow_count": scoring["yellow_count"],
        "stale_indicators": scoring.get("stale_indicators", []),
        "errors": scoring.get("errors", []),
        "warnings": scoring.get("warnings", []),
        "buckets": _strip_series(scoring["buckets"]),
        "weights_hash": _weights_hash(),
        "code_sha": _code_sha(),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SIDECAR_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(SIDECAR_FILE)


_ARCHIVE_FILE = DATA_DIR / "history_archive.parquet"
_MAX_HISTORY_DAYS = 730  # ~2 years


def prune_history() -> None:
    """Move rows older than 2 years from history.csv to history_archive.parquet."""
    if not HISTORY_FILE.exists():
        return
    df = pd.read_csv(HISTORY_FILE)
    if df.empty:
        return
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    cutoff = datetime.now() - timedelta(days=_MAX_HISTORY_DAYS)
    old = df[df["timestamp"] < cutoff]
    if old.empty:
        return
    # Append old rows to archive
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _ARCHIVE_FILE.exists():
        existing = pd.read_parquet(_ARCHIVE_FILE)
        old = pd.concat([existing, old], ignore_index=True).drop_duplicates(subset=["timestamp"])
    old.to_parquet(_ARCHIVE_FILE, index=False)
    # Keep only recent rows in live file
    df[df["timestamp"] >= cutoff].reset_index(drop=True).to_csv(HISTORY_FILE, index=False)


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


def compute_bucket_momentum(history: pd.DataFrame) -> dict:
    """Return {bucket_key: velocity_7d} for every bucket_* column in history. None if < 8 days."""
    if history.empty or len(history) < 2:
        return {}
    bucket_cols = [c for c in history.columns if c.startswith("bucket_")]
    if not bucket_cols:
        return {}

    df = history[["timestamp"] + bucket_cols].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df = df.sort_values("timestamp").groupby("date").last().reset_index()
    df = df.sort_values("date").reset_index(drop=True)

    latest = df.iloc[-1]
    latest_date = pd.Timestamp(latest["date"])
    target = latest_date - pd.Timedelta(days=7)
    past_rows = df[pd.to_datetime(df["date"]) <= target]

    result: dict = {}
    for col in bucket_cols:
        bkey = col[len("bucket_"):]
        if past_rows.empty:
            result[bkey] = None
        else:
            try:
                result[bkey] = round(float(latest[col]) - float(past_rows.iloc[-1][col]), 2)
            except (ValueError, KeyError):
                result[bkey] = None
    return result


_FAST_SHOCK_V7   = 8.0   # pts/7d threshold for "fast" single-trigger
_FAST_BROAD_V7   = 4.0   # pts/7d when multiple buckets accelerating
_FAST_MIN_BUCKETS = 3    # how many accelerating buckets triggers broad fast-shock
_RECOVERY_V7     = -5.0  # pts/7d; falling from elevated composite
_RECOVERY_MIN    = 30.0  # composite must be above this to be "recovery" not just "calm"
_SLOWBURN_MIN    = 40.0  # composite must be above this to be "slow burn"


def classify_shock_type(history: "pd.DataFrame", scoring: dict) -> str:
    """
    Classify the current market stress regime using composite momentum and bucket velocities.

    Returns one of:
      fast_shock    — composite rose ≥8 pts/7d, or ≥4 pts with 3+ buckets accelerating
      slow_burn     — composite ≥40 and moving slowly (lingering elevated stress)
      recovery      — composite falling from an elevated level (≥30) at ≥5 pts/7d
      calm          — composite below threshold, no significant velocity
      insufficient  — not enough history to classify
    """
    mom = compute_composite_momentum(history)
    bkt_vel = compute_bucket_momentum(history)

    v7 = mom.get("velocity_7d")
    if v7 is None:
        return "insufficient"

    composite = float(scoring.get("composite", 0.0))
    n_accel = sum(1 for v in bkt_vel.values() if v is not None and v > 3.0)

    if composite > _RECOVERY_MIN and v7 <= _RECOVERY_V7:
        return "recovery"
    if v7 >= _FAST_SHOCK_V7 or (v7 >= _FAST_BROAD_V7 and n_accel >= _FAST_MIN_BUCKETS):
        return "fast_shock"
    if composite >= _SLOWBURN_MIN and abs(v7) < _FAST_SHOCK_V7:
        return "slow_burn"
    return "calm"


def compute_regime_adjusted_composite(
    composite: float, shock_type: str, momentum: dict
) -> tuple[float, str]:
    """
    Apply a regime-based adjustment to the composite score.

    Returns (adjusted_composite, label_string).
      fast_shock  → velocity premium  (+v7 * 0.3, capped at +10)
      slow_burn   → persistence premium (+composite * 5%, capped at +5)
      recovery    → recovery discount  (v7 * 0.2, capped at −8, v7 is negative)
      calm / insufficient → no change
    """
    v7 = momentum.get("velocity_7d")

    if shock_type == "fast_shock" and v7 is not None and v7 > 0:
        adj = min(v7 * 0.3, 10.0)
        return round(min(composite + adj, 100.0), 1), f"+{adj:.1f} velocity premium"

    if shock_type == "recovery" and v7 is not None and v7 < 0:
        adj = max(v7 * 0.2, -8.0)
        return round(max(composite + adj, 0.0), 1), f"{adj:.1f} recovery discount"

    if shock_type == "slow_burn":
        adj = min(composite * 0.05, 5.0)
        return round(min(composite + adj, 100.0), 1), f"+{adj:.1f} persistence premium"

    return composite, ""


_REGIME_HYSTERESIS = 1.0  # VIX points required to cross a boundary


def classify_vix_regime(vix_series: pd.Series, prev_regime: str | None = None) -> dict:
    """
    Classify current VIX into low / mid / high tercile regime.

    Uses a 5-day smoothed VIX and hysteresis (±1.0 VIX pts at each boundary)
    to prevent flapping. Boundaries are the 33rd / 67th percentile of the
    trailing 10-year VIX series passed in.

    Returns dict with: regime, regime_vix_5dma, regime_thresholds, regime_changed,
    and regime_short_history=True when < 252 trading days of data.
    """
    vix_series = vix_series.dropna()

    smoothed_series = vix_series.rolling(5).mean().dropna()
    current_smoothed = float(smoothed_series.iloc[-1]) if len(smoothed_series) >= 1 else None

    if len(vix_series) < 252:
        return {
            "regime": "mid",
            "regime_vix_5dma": round(current_smoothed, 1) if current_smoothed is not None else None,
            "regime_thresholds": {},
            "regime_changed": False,
            "regime_short_history": True,
        }

    low_max = float(np.percentile(vix_series, 33))
    high_min = float(np.percentile(vix_series, 67))

    # Raw classification without hysteresis
    if current_smoothed <= low_max:
        raw_regime = "low"
    elif current_smoothed >= high_min:
        raw_regime = "high"
    else:
        raw_regime = "mid"

    # Apply hysteresis: only cross a boundary if exceeded by the buffer
    if prev_regime is None:
        regime = raw_regime
    else:
        regime = prev_regime
        buf = _REGIME_HYSTERESIS
        if prev_regime == "low" and current_smoothed > low_max + buf:
            regime = "mid"
        elif prev_regime == "mid" and current_smoothed < low_max - buf:
            regime = "low"
        elif prev_regime == "mid" and current_smoothed > high_min + buf:
            regime = "high"
        elif prev_regime == "high" and current_smoothed < high_min - buf:
            regime = "mid"

    return {
        "regime": regime,
        "regime_vix_5dma": round(current_smoothed, 1),
        "regime_thresholds": {"low_max": round(low_max, 1), "high_min": round(high_min, 1)},
        "regime_changed": regime != prev_regime if prev_regime is not None else False,
        "regime_short_history": False,
    }


def cross_bucket_correlation(history: pd.DataFrame, window_days: int = 30) -> float | None:
    """
    Mean absolute pairwise Spearman correlation across all bucket_* score columns
    over the last window_days rows.  Returns None if insufficient data.
    """
    from scipy.stats import spearmanr

    if history.empty:
        return None

    bucket_cols = [c for c in history.columns if c.startswith("bucket_")]
    if len(bucket_cols) < 2:
        return None

    df = history[["timestamp"] + bucket_cols].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df = df.sort_values("timestamp").groupby("date").last().reset_index()
    df = df.sort_values("date").tail(window_days).reset_index(drop=True)

    if len(df) < 5:
        return None

    data = df[bucket_cols].copy()
    # Drop columns with more than 50% NaN or near-constant (std < 0.5 pts)
    data = data.dropna(axis=1, thresh=max(1, len(data) // 2))
    data = data.loc[:, data.std() >= 0.5]
    if data.shape[1] < 2:
        return None

    result = spearmanr(data.values, nan_policy="omit")
    corr_matrix = np.array(result.statistic) if result.statistic.ndim == 2 else np.array([[1.0, result.statistic], [result.statistic, 1.0]])
    n = corr_matrix.shape[0]
    if n < 2:
        return None
    idx = np.triu_indices(n, k=1)
    return float(np.abs(corr_matrix[idx]).mean())


def correlation_regime(value: float | None) -> str:
    """Classify cross-bucket correlation into a named regime."""
    if value is None:
        return "insufficient"
    if value < 0.30:
        return "decorrelated"
    if value < 0.60:
        return "normal"
    return "crisis_synchronous"


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
