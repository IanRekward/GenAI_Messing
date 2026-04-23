"""
Backtest report generator.  Produces output/backtest_report.html.

Workflow:
  1. Load (or run) both backtest DataFrames from output/backtest_*.csv
  2. Fetch target series (SPX, VIX, HY OAS, NFCI) via the backtest cache
  3. Run full evaluation suite via evaluation.py
  4. Emit a self-contained dark-theme HTML report

See BACKTEST_DESIGN.md §7 for the full output specification.
"""
from __future__ import annotations

import json
import os
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Shared style (matches dashboard.py theme)
# ---------------------------------------------------------------------------

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6}
.wrap{max-width:1200px;margin:0 auto;padding:28px 20px}
h1{font-size:1.6rem;font-weight:700;margin-bottom:4px}
h2{font-size:1.05rem;font-weight:600;margin:24px 0 10px;color:#e6edf3;border-bottom:1px solid #21262d;padding-bottom:6px}
h3{font-size:.95rem;font-weight:600;margin:16px 0 6px;color:#8b949e}
.ts{font-size:.8rem;color:#6e7681;margin-bottom:24px}
.card{background:#161b22;border-radius:8px;padding:16px 20px;margin-bottom:16px}
.note{font-size:.82rem;color:#8b949e;margin-top:8px;font-style:italic}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:6px 8px;color:#8b949e;font-weight:600;border-bottom:2px solid #21262d;white-space:nowrap}
td{padding:5px 8px;border-bottom:1px solid #21262d;vertical-align:middle}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-size:.82rem}
tr:last-child td{border-bottom:none}
.pos{color:#3fb950} .neg{color:#f85149} .neu{color:#8b949e} .warn{color:#d29922}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.72rem;font-weight:700;text-transform:uppercase}
.flag-weak{background:#2d1b1b;color:#f85149} .flag-unstable{background:#2d2400;color:#d29922}
.flag-ok{background:#0d2e14;color:#3fb950}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.svg-wrap{overflow-x:auto}
.event-row{padding:10px 0;border-bottom:1px solid #21262d} .event-row:last-child{border-bottom:none}
.footer{margin-top:36px;font-size:.75rem;color:#484f58;text-align:center}
"""


def _fmt(v, decimals=3, suffix="", na="-"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return f'<span class="neu">{na}</span>'
    cls = "pos" if v > 0 else ("neg" if v < 0 else "neu")
    return f'<span class="{cls}">{v:.{decimals}f}{suffix}</span>'


def _fmt_ic_row(ic, lo, hi, threshold=0.05):
    ic_str = _fmt(ic)
    if lo is None or np.isnan(lo):
        ci_str = '<span class="neu">-</span>'
    else:
        ci_str = f'<span class="neu">[{lo:.3f}, {hi:.3f}]</span>'
    if ic is None or np.isnan(ic):
        flag = ""
    elif ic < threshold:
        flag = '<span class="badge flag-weak">WEAK</span>'
    elif ic >= 0.15:
        flag = '<span class="badge flag-ok">STRONG</span>'
    else:
        flag = ""
    return ic_str, ci_str, flag


# ---------------------------------------------------------------------------
# SVG ROC curve
# ---------------------------------------------------------------------------

def _roc_svg(curves: dict[str, tuple[np.ndarray, np.ndarray, float]],
             width: int = 340, height: int = 260) -> str:
    """
    Minimal inline SVG ROC chart.
    curves: {label: (fpr_array, tpr_array, auc_value)}
    """
    pad = 40
    pw, ph = width - pad - 16, height - pad - 16
    colors = ["#58a6ff", "#3fb950", "#d29922", "#f85149"]
    lines = []

    # diagonal (random baseline)
    lines.append(
        f'<line x1="{pad}" y1="{pad}" x2="{pad+pw}" y2="{pad+ph}" '
        f'stroke="#484f58" stroke-dasharray="4 3" stroke-width="1"/>'
    )

    for (label, (fpr, tpr, auc_val)), color in zip(curves.items(), colors):
        pts = " ".join(
            f"{pad + fpr[i]*pw:.1f},{pad + ph - tpr[i]*ph:.1f}"
            for i in range(len(fpr))
        )
        lines.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/>'
        )
        # Legend entry
        yi = 20 + list(curves.keys()).index(label) * 16
        lines.append(
            f'<line x1="{pad+2}" y1="{pad+ph+yi-4}" x2="{pad+18}" y2="{pad+ph+yi-4}" '
            f'stroke="{color}" stroke-width="2"/>'
        )
        lbl = f"{label} (AUC={auc_val:.3f})" if auc_val == auc_val else label
        lines.append(
            f'<text x="{pad+22}" y="{pad+ph+yi}" fill="{color}" '
            f'font-size="10" dominant-baseline="middle">{lbl}</text>'
        )

    # axes labels
    lines.append(
        f'<text x="{pad + pw//2}" y="{height-2}" text-anchor="middle" '
        f'fill="#6e7681" font-size="10">False Positive Rate</text>'
    )
    lines.append(
        f'<text x="10" y="{pad + ph//2}" text-anchor="middle" '
        f'fill="#6e7681" font-size="10" transform="rotate(-90,10,{pad+ph//2})">True Positive Rate</text>'
    )

    legend_h = len(curves) * 16 + 8
    total_h = height + legend_h
    return (
        f'<svg viewBox="0 0 {width} {total_h}" width="{width}" height="{total_h}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + "\n".join(lines)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Headline metrics HTML
# ---------------------------------------------------------------------------

def _section_headline(results: dict, run_label: str) -> str:
    from src.evaluation import headline_table
    df = headline_table(results)
    if df.empty:
        return "<p class='note'>No data.</p>"

    rows_html = ""
    for _, row in df.iterrows():
        ic_s, ci_s, flag = _fmt_ic_row(row.get("composite_ic"), row.get("ci_lo"), row.get("ci_hi"))
        vix_ic_s = _fmt(row.get("vix_ic"))
        tf_ic_s  = _fmt(row.get("3factor_ic"))
        rows_html += (
            f"<tr>"
            f"<td>{row['target']}</td>"
            f"<td>{row['horizon']}</td>"
            f"<td class='num'>{ic_s} {flag}</td>"
            f"<td class='num'>{ci_s}</td>"
            f"<td class='num'>{vix_ic_s}</td>"
            f"<td class='num'>{tf_ic_s}</td>"
            f"<td class='num'>{int(row['n_obs']) if row['n_obs']==row['n_obs'] else '-'}</td>"
            f"</tr>"
        )

    return f"""
<div class="card">
<h3>{run_label}</h3>
<div class="svg-wrap">
<table>
<tr><th>Target</th><th>Horizon</th><th>Composite IC</th><th>95% CI</th>
    <th>VIX IC</th><th>3-factor IC</th><th>N obs</th></tr>
{rows_html}
</table>
</div>
</div>"""


# ---------------------------------------------------------------------------
# Per-indicator IC ranking HTML
# ---------------------------------------------------------------------------

def _section_indicator_ic(signal_df: pd.DataFrame, target: pd.Series, label: str) -> str:
    from src.evaluation import indicator_ic_table
    df = indicator_ic_table(signal_df, target)
    if df.empty:
        return ""

    rows_html = ""
    for _, row in df.iterrows():
        ic = row["ic"]
        if ic != ic:
            flag = ""
        elif ic < 0.05:
            flag = '<span class="badge flag-weak">WEAK</span>'
        elif ic >= 0.15:
            flag = '<span class="badge flag-ok">STRONG</span>'
        else:
            flag = ""
        rows_html += (
            f"<tr><td>{row['indicator']}</td>"
            f"<td class='num'>{_fmt(ic)}</td>"
            f"<td>{flag}</td></tr>"
        )

    return f"""
<div class="card">
<h3>{label}</h3>
<table>
<tr><th>Indicator</th><th>Spearman IC</th><th>Flag</th></tr>
{rows_html}
</table>
<p class="note">IC vs 30-day SPX max drawdown.  WEAK = IC &lt; 0.05 (candidate for removal).
STRONG = IC &ge; 0.15.</p>
</div>"""


# ---------------------------------------------------------------------------
# ROC curve section
# ---------------------------------------------------------------------------

def _section_roc(composite: pd.Series, vix_pct: pd.Series | None,
                 events: pd.Series, event_name: str) -> str:
    from sklearn.metrics import roc_curve
    curves = {}
    common_c = composite.dropna().index.intersection(events.dropna().index)
    if len(common_c) > 20 and events.loc[common_c].sum() > 2:
        fpr, tpr, _ = roc_curve(events.loc[common_c].values,
                                 composite.loc[common_c].values)
        from src.evaluation import roc_pr_metrics
        auc_val = roc_pr_metrics(composite, events).get("roc_auc", np.nan)
        curves["Composite"] = (fpr, tpr, auc_val)

    if vix_pct is not None:
        common_v = vix_pct.dropna().index.intersection(events.dropna().index)
        if len(common_v) > 20 and events.loc[common_v].sum() > 2:
            fpr_v, tpr_v, _ = roc_curve(events.loc[common_v].values,
                                          vix_pct.loc[common_v].values)
            auc_v = roc_pr_metrics(vix_pct, events).get("roc_auc", np.nan)
            curves["VIX alone"] = (fpr_v, tpr_v, auc_v)

    if not curves:
        return f"<p class='note'>Insufficient data for ROC curve ({event_name}).</p>"

    return f"""
<div class="card">
<h3>ROC — {event_name}</h3>
<div class="svg-wrap">{_roc_svg(curves)}</div>
</div>"""


# ---------------------------------------------------------------------------
# Regime table
# ---------------------------------------------------------------------------

def _section_regime(results: dict, horizon: str = "1m") -> str:
    regime_data = results.get("regime", {}).get(horizon, {})
    if not regime_data:
        return "<p class='note'>No regime data for 1m horizon.</p>"

    rows_html = ""
    for tname, regimes in regime_data.items():
        for rname, vals in regimes.items():
            ic, lo, hi = vals.get("ic"), vals.get("ci_lo"), vals.get("ci_hi")
            ic_s, ci_s, flag = _fmt_ic_row(ic, lo, hi)
            rows_html += (
                f"<tr><td>{tname}</td><td>{rname}</td>"
                f"<td class='num'>{vals.get('n', '-')}</td>"
                f"<td class='num'>{ic_s} {flag}</td>"
                f"<td class='num'>{ci_s}</td></tr>"
            )

    return f"""
<div class="card">
<table>
<tr><th>Target</th><th>Regime (VIX tercile)</th><th>N obs</th>
    <th>IC</th><th>95% CI</th></tr>
{rows_html}
</table>
<p class="note">Calm = VIX bottom third; Normal = middle third; Stress = top third.</p>
</div>"""


# ---------------------------------------------------------------------------
# Event case studies
# ---------------------------------------------------------------------------

_EVENTS = [
    ("2008 GFC",            "2008-09-15", "Lehman Brothers collapse"),
    ("2011 EU Sovereign",   "2011-07-01", "European sovereign debt crisis peak"),
    ("2015 China/HY",       "2015-08-24", "China devaluation / HY blowup"),
    ("2018 Q4 Selloff",     "2018-12-24", "Fed overtightening fears"),
    ("2020 COVID Crash",    "2020-03-16", "COVID lockdown shock"),
    ("2022 Inflation",      "2022-09-30", "Fed aggressive hike cycle"),
    ("2023 SVB Failure",    "2023-03-10", "Silicon Valley Bank collapse"),
]


def _section_events(signal_df: pd.DataFrame) -> str:
    composite = signal_df["composite"]

    rows_html = ""
    for name, peak_date, desc in _EVENTS:
        peak_ts = pd.Timestamp(peak_date)
        # Find the composite value at the event date (or nearest available)
        avail = composite.dropna()
        if len(avail) == 0:
            continue

        # Score at event
        nearest = avail.index[avail.index.get_indexer([peak_ts], method="nearest")[0]]
        score_at = avail.loc[nearest]
        band = (
            "red" if score_at >= 70 else
            "orange" if score_at >= 50 else
            "yellow" if score_at >= 30 else "green"
        )
        badge_color = {"red": "#f85149", "orange": "#d29922", "yellow": "#e3b341", "green": "#3fb950"}[band]

        # Lead time: first time composite >= 50 before the event
        pre_window = avail.loc[:peak_ts]
        orange_dates = pre_window[pre_window >= 50]
        if len(orange_dates) > 0:
            first_orange = orange_dates.index[-1]
            lead = (peak_ts - first_orange).days
            lead_str = f"{lead}d lead"
        else:
            lead_str = "no lead"

        # Peak score in ±60 days around event
        window = avail.loc[peak_ts - pd.Timedelta(days=30): peak_ts + pd.Timedelta(days=60)]
        peak_score = float(window.max()) if len(window) > 0 else np.nan
        peak_date_actual = window.idxmax() if len(window) > 0 else None

        # Which bucket drove the score (highest bucket score at event date)
        bucket_cols = [c for c in signal_df.columns if c.startswith("bucket_")]
        buckets_at = signal_df.loc[nearest, bucket_cols].dropna() if nearest in signal_df.index else pd.Series()
        top_bucket = buckets_at.idxmax().replace("bucket_", "") if len(buckets_at) > 0 else "n/a"

        if peak_score != peak_score:
            peak_str = "<span class='neu'>-</span>"
        elif peak_score >= 70:
            peak_str = f'<span class="neg">{peak_score:.1f}</span>'
        elif peak_score >= 50:
            peak_str = f'<span class="warn">{peak_score:.1f}</span>'
        else:
            peak_str = f'<span class="neu">{peak_score:.1f}</span>'

        rows_html += f"""
<tr>
  <td><b>{name}</b><br><span style="color:#6e7681;font-size:.8rem">{desc}</span></td>
  <td class="num">{peak_date}</td>
  <td class="num">
    <span class="badge" style="background:{badge_color}22;color:{badge_color}">{score_at:.1f} {band.upper()}</span>
  </td>
  <td class="num">{lead_str}</td>
  <td class="num">{peak_str}</td>
  <td class="num">{top_bucket}</td>
</tr>"""

    if not rows_html:
        return "<p class='note'>Backtest range does not cover these events. Run subset model (2000+) for full coverage.</p>"

    return f"""
<div class="card">
<div class="svg-wrap">
<table>
<tr><th>Event</th><th>Peak date</th><th>Score at event</th>
    <th>Orange lead time</th><th>Peak score (±60d)</th><th>Top bucket</th></tr>
{rows_html}
</table>
</div>
<p class="note">Lead time = days from first orange signal to peak-stress date.
Score at event = composite on the event date (or nearest available).</p>
</div>"""


# ---------------------------------------------------------------------------
# Per-year IC chart (simple inline SVG bar chart)
# ---------------------------------------------------------------------------

def _year_ic_svg(per_year_df: pd.DataFrame, width: int = 560, height: int = 160) -> str:
    if per_year_df.empty:
        return ""
    df = per_year_df.dropna(subset=["ic"])
    if df.empty:
        return ""

    pad_l, pad_r, pad_t, pad_b = 36, 12, 10, 26
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    n = len(df)
    bar_w = max(4, pw // n - 2)

    ic_min = min(df["ic"].min(), -0.05)
    ic_max = max(df["ic"].max(), 0.05)
    ic_range = ic_max - ic_min
    zero_y = pad_t + ph - int((-ic_min / ic_range) * ph)

    rects = []
    for i, (yr, row) in enumerate(df.iterrows()):
        ic = row["ic"]
        x = pad_l + i * (pw // n)
        bar_h = int(abs(ic) / ic_range * ph)
        color = "#3fb950" if ic > 0 else "#f85149"
        y = zero_y - bar_h if ic > 0 else zero_y
        rects.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{color}" opacity="0.8"/>')
        # year label (every 2nd to avoid crowding)
        if i % 2 == 0:
            rects.append(
                f'<text x="{x + bar_w//2}" y="{height - 4}" text-anchor="middle" '
                f'fill="#6e7681" font-size="9">{yr}</text>'
            )

    # zero line
    rects.append(
        f'<line x1="{pad_l}" y1="{zero_y}" x2="{width - pad_r}" y2="{zero_y}" '
        f'stroke="#484f58" stroke-width="1"/>'
    )
    # y-axis labels
    for val, label in [(ic_max, f"{ic_max:.2f}"), (0, "0"), (ic_min, f"{ic_min:.2f}")]:
        y = pad_t + ph - int((val - ic_min) / ic_range * ph)
        rects.append(
            f'<text x="{pad_l - 4}" y="{y}" text-anchor="end" dominant-baseline="middle" '
            f'fill="#6e7681" font-size="9">{label}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">' + "".join(rects) + "</svg>"
    )


# ---------------------------------------------------------------------------
# Full report assembly
# ---------------------------------------------------------------------------

def generate_report(
    df_full: pd.DataFrame,
    df_subset: pd.DataFrame | None,
    spx: pd.Series,
    vix: pd.Series | None,
    hy_oas: pd.Series | None,
    nfci: pd.Series | None,
    output_path: str = "output/backtest_report.html",
) -> None:
    from src.evaluation import (
        run_full_evaluation, build_forward_drawdown, indicator_ic_table, headline_table
    )

    sections = []

    def _run_and_render(signal_df: pd.DataFrame, label: str) -> str:
        print(f"  Running evaluation for {label}...")
        results = run_full_evaluation(signal_df, spx, hy_oas, nfci, vix)

        composite = signal_df["composite"].dropna()
        spx_aligned = spx.reindex(composite.index, method="ffill")
        target_30d = build_forward_drawdown(spx_aligned, 30)

        # Benchmark VIX percentile
        vix_pct = None
        if vix is not None:
            vix_pct = vix.rolling(window=252 * 10, min_periods=252).rank(pct=True) * 100
            vix_pct = vix_pct.reindex(composite.index, method="ffill")

        # Events
        hy_aligned = hy_oas.reindex(composite.index, method="ffill") if (hy_oas is not None and len(hy_oas) > 50) else None
        from src.evaluation import build_binary_events
        events_df = build_binary_events(spx_aligned, hy_aligned)

        html = f"<h2>{label}</h2>"
        html += _section_headline(results, "Spearman IC vs Forward S&P 500 Drawdown")
        html += f'<h2>Per-Indicator IC — {label}</h2>'
        html += _section_indicator_ic(signal_df, target_30d, "IC vs 30-day forward SPX drawdown")
        html += f'<h2>ROC Curves — {label}</h2>'
        html += '<div class="grid2">'
        html += _section_roc(composite, vix_pct, events_df["major_drawdown"], "Major Drawdown (>10% / 90d)")
        html += _section_roc(composite, vix_pct, events_df["moderate_drawdown"], "Moderate Drawdown (>5% / 30d)")
        html += '</div>'
        html += f'<h2>Regime Stratification (VIX terciles) — {label}</h2>'
        html += _section_regime(results, "1m")
        html += f'<h2>Per-Year IC Stability — {label}</h2>'
        per_year = results.get("per_year", {}).get("1m", {}).get("spx_drawdown", pd.DataFrame())
        if isinstance(per_year, pd.DataFrame) and not per_year.empty:
            html += f'<div class="card"><div class="svg-wrap">{_year_ic_svg(per_year)}</div>'
            html += "<p class='note'>Bars above zero = positive IC (model predicted stress); below zero = negative IC (model misfired).</p>"
            html += "</div>"
        html += f'<h2>Event Case Studies — {label}</h2>'
        html += _section_events(signal_df)
        return html

    html_full = _run_and_render(df_full, "Full Model (2018 &ndash; present)")
    sections.append(html_full)

    if df_subset is not None and len(df_subset) > 100:
        html_sub = _run_and_render(df_subset, "Subset Model (2000 &ndash; 2017)")
        sections.append(html_sub)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    full_range = f"{df_full.index.min().date()} to {df_full.index.max().date()}"

    body = "\n".join(sections)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backtest Report — Market Stress Model</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Backtest Report — Market Stress Model</h1>
  <div class="ts">Generated {now} &nbsp;|&nbsp; Full model range: {full_range}</div>
  {body}
  <div class="footer">Market Stress Dashboard &mdash; Backtesting evaluation report</div>
</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Report saved: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(weights_path: str = "config/weights.yaml", output_path: str = "output/backtest_report.html") -> None:
    """Run backtests (if needed) and generate the HTML report."""
    import os
    sys_path_fix()

    from dotenv import load_dotenv
    load_dotenv()
    env = dict(os.environ)

    from src.backtest import run_standard_backtests, _bt_fred, _bt_yf, FETCH_YEARS
    from src.evaluation import run_full_evaluation

    weights = yaml.safe_load(open(weights_path))

    # Load or run backtests
    full_path   = "output/backtest_full.csv"
    subset_path = "output/backtest_subset.csv"

    if os.path.exists(full_path):
        print(f"Loading existing {full_path}")
        df_full = pd.read_csv(full_path, index_col=0, parse_dates=True)
    else:
        print("Running full-model backtest (2018+)...")
        df_full, _ = run_standard_backtests(weights, env)

    df_subset = None
    if os.path.exists(subset_path):
        print(f"Loading existing {subset_path}")
        df_subset = pd.read_csv(subset_path, index_col=0, parse_dates=True)

    # Fetch target series
    print("Fetching target series...")
    spx  = _bt_yf("^GSPC", env)
    vix  = _bt_yf("^VIX", env)
    try:
        hy_oas = _bt_fred("BAMLH0A0HYM2", env)
    except Exception:
        hy_oas = None
    try:
        nfci = _bt_fred("NFCI", env)
    except Exception:
        nfci = None

    print("Generating HTML report...")
    generate_report(df_full, df_subset, spx, vix, hy_oas, nfci, output_path)
    print(f"Done.  Open: file://{os.path.abspath(output_path)}")


def sys_path_fix() -> None:
    import sys
    if "." not in sys.path:
        sys.path.insert(0, ".")


if __name__ == "__main__":
    sys_path_fix()
    run()
