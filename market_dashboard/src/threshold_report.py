"""
Threshold calibration report (B1, REDESIGN_2026-09-02).

Computes the historical firing rate of every yellow/orange/red threshold from
point-in-time backtest raws (plus the accumulating CNN cache, which the
backtest cannot cover), and proposes thresholds hitting target base rates.
Report-only: writes output/threshold_report.md and prints a proposed
thresholds.yaml block. Applies nothing.

Run: python -m src.threshold_report
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from src.triggers import _evaluate_band

TARGET_RATES = {"yellow": 0.30, "orange": 0.15, "red": 0.05}
LIVE_START = "2026-04-23"
SKIP = {"iran_trigger", "repo_stress"}
BACKTEST_PLACEHOLDER = {"cnn_fear_greed"}


def _load_raws(backtest_csv: str | Path, cnn_cache: str | Path | None) -> dict[str, pd.Series]:
    bt = pd.read_csv(backtest_csv, parse_dates=["date"]).set_index("date")
    raws: dict[str, pd.Series] = {}
    for col in bt.columns:
        if not col.endswith("__raw"):
            continue
        ikey = col.split("__")[1]
        if ikey in SKIP or ikey in BACKTEST_PLACEHOLDER:
            continue
        raws[ikey] = bt[col].dropna()
    if cnn_cache is not None and Path(cnn_cache).exists():
        d = json.loads(Path(cnn_cache).read_text(encoding="utf-8"))
        raws["cnn_fear_greed"] = pd.Series(
            d["values"], index=pd.to_datetime(d["dates"])
        ).dropna()
    return raws


def _firing_rates(series: pd.Series, thr: dict) -> dict[str, float]:
    bands = series.apply(lambda v: _evaluate_band(v, thr))
    n = len(bands)
    if n == 0:
        return {}
    return {b: round(100 * (bands == b).mean(), 1)
            for b in ("green", "yellow", "orange", "red")}


def _propose(series: pd.Series, direction: str) -> dict[str, float]:
    """Quantile-derived thresholds hitting TARGET_RATES cumulative band shares."""
    out = {}
    for band, rate in TARGET_RATES.items():
        q = rate if direction == "low" else 1 - rate
        out[band] = float(series.quantile(q))
    return out


def _fmt(v: float) -> float:
    """Round to ~3 significant digits without scientific notation surprises."""
    if v == 0:
        return 0.0
    magnitude = 0
    a = abs(v)
    while a < 100:
        a *= 10
        magnitude += 1
    return round(v, magnitude + 1)


def build_report(
    thresholds: dict,
    raws: dict[str, pd.Series],
    live_start: str = LIVE_START,
) -> tuple[str, dict]:
    """Return (markdown_report, proposed_thresholds_dict)."""
    lines = [
        "# Threshold calibration report",
        "",
        f"Generated {pd.Timestamp.now().isoformat(timespec='seconds')} — B1 artifact "
        f"(REDESIGN_2026-09-02). Targets: red ≤{TARGET_RATES['red']:.0%} of days, "
        f"orange ≤{TARGET_RATES['orange']:.0%}, yellow ≤{TARGET_RATES['yellow']:.0%} "
        f"(cumulative, per indicator, over its full available history).",
        "",
        "Sources: point-in-time backtest raws (2018→today); cnn_fear_greed from its "
        "accumulating live cache (16 months — flagged small-sample); iran_trigger / "
        "repo_stress excluded (manual, being replaced per D3).",
        "",
        "| indicator | dir | current y/o/r | fires y/o/r % (full) | red % live | proposed y/o/r | flag |",
        "|---|---|---|---|---|---|---|",
    ]
    proposed_all: dict[str, dict] = {}
    for ikey in sorted(raws):
        thr = thresholds.get(ikey)
        s = raws[ikey]
        if thr is None or len(s) < 60:
            lines.append(f"| {ikey} | — | — | — | — | — | no threshold or <60 obs |")
            continue
        direction = thr.get("direction", "high")
        full = _firing_rates(s, thr)
        live = _firing_rates(s[s.index >= live_start], thr)
        quantile_ref = {b: _fmt(v) for b, v in _propose(s, direction).items()}

        # The target rates are CEILINGS, not goals. A red that never fired in
        # nine years may be a genuine crisis level the sample simply lacks —
        # tightening it to the 95th percentile of a calm sample manufactures
        # false alarms, which is the exact disease this report exists to cure.
        # Proposals are emitted only for ceiling violations (loosening).
        cum_elev = full.get("yellow", 0) + full.get("orange", 0) + full.get("red", 0)
        red_hot = full.get("red", 0) > 100 * TARGET_RATES["red"] * 1.5
        always_elev = cum_elev > 100 * TARGET_RATES["yellow"] * 1.5
        # A red pinned in the live window but calm full-sample marks a
        # structural level shift the full-sample ceiling can't see (the
        # crack-spread/copper-gold failure mode that pinned the headline).
        pinned_live = live.get("red", 0) > 100 * TARGET_RATES["red"] * 3

        flags = []
        if red_hot:
            flags.append("RED TOO HOT")
        if pinned_live and not red_hot:
            flags.append("RED PINNED LIVE (structural shift)")
        if full.get("red", 0) == 0.0 and not pinned_live:
            flags.append("red never fired (judgment review, no auto-proposal)")
        if always_elev:
            flags.append("always elevated")
        if len(s) < 1500:
            flags.append(f"short sample n={len(s)}")

        if red_hot or always_elev or pinned_live:
            proposed_all[ikey] = {"direction": direction, **quantile_ref}
            prop_s = f"{quantile_ref['yellow']}/{quantile_ref['orange']}/{quantile_ref['red']}"
            live_after = _firing_rates(
                s[s.index >= live_start], {"direction": direction, **quantile_ref}
            )
            if live_after.get("red", 0) > 100 * TARGET_RATES["red"] * 3:
                flags.append(
                    f"proposal still pinned live ({live_after['red']}% red) — "
                    "needs short-window or relative transform, judgment"
                )
        else:
            prop_s = "keep"

        cur = f"{thr['yellow']}/{thr['orange']}/{thr['red']}"
        fire = f"{full.get('yellow', 0)}/{full.get('orange', 0)}/{full.get('red', 0)}"
        lines.append(
            f"| {ikey} | {direction} | {cur} | {fire} | {live.get('red', 0)} "
            f"| {prop_s} | {', '.join(flags)} |"
        )
    return "\n".join(lines) + "\n", proposed_all


def composite_cutoff_proposal(backtest_csv: str | Path) -> dict[str, float]:
    """Score-band cutoffs (currently 30/50/70) recalibrated to the same targets."""
    bt = pd.read_csv(backtest_csv, parse_dates=["date"])
    comp = bt["composite"].dropna()
    return {
        "yellow": round(float(comp.quantile(1 - TARGET_RATES["yellow"])), 1),
        "orange": round(float(comp.quantile(1 - TARGET_RATES["orange"])), 1),
        "red": round(float(comp.quantile(1 - TARGET_RATES["red"])), 1),
    }


def main() -> None:
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    thresholds = yaml.safe_load(
        Path("config/thresholds.yaml").read_text(encoding="utf-8")
    )["indicators"]
    raws = _load_raws("output/backtest_full.csv", "data/cache/cnn_fear_greed.json")
    report, proposed = build_report(thresholds, raws)

    cutoffs = composite_cutoff_proposal("output/backtest_full.csv")
    report += (
        "\n## Composite score-band cutoffs\n\n"
        f"Current 30/50/70 (never derived). Backtest-composite quantiles at the same "
        f"targets: yellow ≥{cutoffs['yellow']}, orange ≥{cutoffs['orange']}, "
        f"red ≥{cutoffs['red']}. Feeds the D1 band redesign.\n"
        "\n## Proposed thresholds.yaml values (NOT applied — D2 decision)\n\n```yaml\n"
        + yaml.safe_dump(proposed, sort_keys=True, allow_unicode=True)
        + "```\n"
    )

    out = Path("output/threshold_report.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
