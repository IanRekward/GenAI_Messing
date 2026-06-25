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

from src import fetch as _fetch
from src.backtest import run_standard_backtests, FETCH_YEARS
from src.evaluation import (
    run_full_evaluation, build_forward_drawdown, build_binary_events,
    headline_table, indicator_ic_table, roc_pr_metrics, ic_summary_dict,
)
from src.indicators import band_from_score, BAND_COLOR as _BAND_COLOR

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
.pos{color:#22cc44} .neg{color:#ff4444} .neu{color:#8b949e} .warn{color:#ff8800}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.72rem;font-weight:700;text-transform:uppercase}
.flag-weak{background:#2d1b1b;color:#ff4444} .flag-unstable{background:#2d2400;color:#ff8800}
.flag-ok{background:#0d2e14;color:#22cc44}
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


def _ic_flag(ic, weak_threshold: float = 0.05) -> str:
    if ic is None or ic != ic:
        return ""
    if ic < weak_threshold:
        return '<span class="badge flag-weak">WEAK</span>'
    if ic >= 0.15:
        return '<span class="badge flag-ok">STRONG</span>'
    return ""


def _fmt_ic_row(ic, lo, hi, threshold=0.05):
    ic_str = _fmt(ic)
    if lo is None or np.isnan(lo):
        ci_str = '<span class="neu">-</span>'
    else:
        ci_str = f'<span class="neu">[{lo:.3f}, {hi:.3f}]</span>'
    return ic_str, ci_str, _ic_flag(ic, threshold)


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
    colors = ["#58a6ff", "#22cc44", "#ff8800", "#ff4444"]
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
    df = indicator_ic_table(signal_df, target)
    if df.empty:
        return ""

    rows_html = ""
    for _, row in df.iterrows():
        ic = row["ic"]
        rows_html += (
            f"<tr><td>{row['indicator']}</td>"
            f"<td class='num'>{_fmt(ic)}</td>"
            f"<td>{_ic_flag(ic)}</td></tr>"
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
        band = band_from_score(score_at)
        badge_color = _BAND_COLOR[band]

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
        color = _BAND_COLOR["green"] if ic > 0 else _BAND_COLOR["red"]
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
# Explainer sections (Brief 22)
# ---------------------------------------------------------------------------

def _section_explainer() -> str:
    """Two collapsible sections explaining the report. Insert above headline table."""
    return """
<div class="card" style="border-left:3px solid #58a6ff;background:#0d1f2e">
<details>
<summary style="cursor:pointer;font-size:1rem;font-weight:600;color:#e6edf3">
Methodology and caveats — for finance / stats readers
<span style="color:#8b949e;font-size:.85rem;font-weight:400;margin-left:8px">click to expand</span>
</summary>
<div style="margin-top:14px;line-height:1.65;font-size:.92rem">

<p><b>What this report measures.</b> Each row is a Spearman rank correlation
(IC) between the model's composite stress score on date T and a
forward-looking outcome over the subsequent 1–6 months — primarily peak
S&amp;P 500 drawdown, secondarily HY OAS widening and a multi-asset stress
index. Spearman is preferred over Pearson because the composite is bounded
[0, 100] and outcome distributions are heavy-tailed; rank correlation is
robust to both.</p>

<p><b>Reading the IC table.</b> An IC of <b>0.15+</b> is considered strong
for a daily-frequency macro stress signal — it is the threshold above
which institutional risk teams typically take a signal seriously. <b>0.05
to 0.15</b> is detectable signal that's worth keeping but not strong on
its own. <b>Below 0.05</b> is statistically indistinguishable from noise
at this sample size, even if the headline number is positive. The 95%
confidence intervals are computed via block bootstrap with quarterly
blocks (63 business days) to preserve autocorrelation — they will be
substantially wider than naive bootstrap CIs and that is correct. If a CI
crosses zero, the IC is not significantly different from random.</p>

<p><b>Why these specific targets.</b> Forward SPX drawdown is the headline
because it is what the user actually cares about — capital preservation —
and because drawdown distributions are non-Gaussian in ways that the
composite is designed to anticipate. HY widening and the multi-asset
stress index are sanity checks: a real stress signal should predict all
three, not just one. If the composite hits SPX drawdowns but misses HY
widening, that's a hint the signal is overfit to equity vol. The
benchmark columns (VIX alone, HY OAS alone, NFCI, 3-factor average) test
whether the composite adds anything over its own components — if VIX
alone matches the composite, the other 25 indicators are dead weight.</p>

<p><b>Regime stratification.</b> The single-number IC averages across
calm and stress periods, which can hide regime-dependent performance. The
regime-stratified table breaks IC out by VIX tercile (bottom third =
calm, top third = stress). A model with strong stress-regime IC and weak
calm-regime IC is <i>better</i> than one with uniform mediocre IC — calm-period
noise is harmless because the user does nothing on calm days. Conversely,
strong calm-regime IC and weak stress-regime IC is the worst pattern: the
model is most confident exactly when it shouldn't be.</p>

<p><b>Known limitations.</b> (1) <b>No look-ahead bias is structural</b> —
each date T uses only data from [T&minus;10y, T] for percentile computation —
but indicator <i>selection</i> is post-hoc, chosen with the benefit of
knowing 2008 / 2020 / 2022 happened. The 2000–2017 subset model exists
specifically to test out-of-sample. (2) <b>Survivorship</b> — indicators
in the current model are ones that survived discretionary review. Failed
prior candidates are not preserved, so the headline IC is biased upward.
(3) <b>Manual indicators</b> (<code>repo_stress</code>, <code>iran_trigger</code>) are always
zero historically because no historical series exists; this slightly
deflates pre-2018 composite levels. (4) <b>FRED licensing</b> — ICE BofA
OAS series are limited to ~3 years on the FRED API regardless of
requested start date; the engine handles this by skipping unavailable
indicators and renormalizing bucket weights, so the pre-2018 subset model
is structurally smaller than the post-2018 full model.</p>

<p><b>Recalibration cycle.</b> Bucket weights and indicator weights are
re-tuned via <code>src/recalibrate.py</code>, which applies a 2&times;2 matrix
on each indicator's pre-2016 and post-2016 IC. Strong/strong &rarr; keep;
strong/weak &rarr; reduce 4&times;; weak/strong &rarr; keep (new signal); weak/weak &rarr;
drop. Re-running this requires both backtest CSVs to be fresh. The
checkpoint cadence is documented in the project TODO.</p>

</div>
</details>
</div>

<div class="card" style="border-left:3px solid #58a6ff;background:#0d1f2e">
<details>
<summary style="cursor:pointer;font-size:1rem;font-weight:600;color:#e6edf3">
What does this report actually mean? — for non-specialists
<span style="color:#8b949e;font-size:.85rem;font-weight:400;margin-left:8px">click to expand</span>
</summary>
<div style="margin-top:14px;line-height:1.65;font-size:.92rem">

<p><b>The big picture.</b> The dashboard you saw is a kind of weather
station for financial markets. It reads 26 different gauges every day —
stock-market jumpiness, the cost of borrowing for risky companies, how
worried investors are, what the Federal Reserve is signaling, oil prices,
unemployment numbers, and so on — and combines them into one summary
number from 0 to 100. Higher means more market stress; lower means
calmer. This report is the answer to a fair question: "is that summary
number actually any good?"</p>

<p><b>The way we test it.</b> We replay history. Imagine pretending it's
March 1, 2008. We compute the dashboard's stress score using <i>only</i>
the data that existed on that date — no peeking ahead. Then we look at
what the stock market actually did over the following weeks and months
and ask: when the score was high back then, did bad things tend to
follow? When the score was low, did the market mostly behave? We do this
every business day going back to 2000 (for the older subset) and 2018
(for the newer full model), and we measure how reliably high scores
preceded losses. That measurement — the "IC" you see throughout the
report — is essentially "how often was the dashboard right, on a scale
where 0 means useless and higher means more useful."</p>

<p><b>What counts as good.</b> Forecasting markets is hard, and you
should be deeply skeptical of anyone who claims a perfect score. For
this kind of broad early-warning gauge, an IC above 0.15 is genuinely
good news — it means the signal is meaningfully better than guessing,
even if it's far from a crystal ball. Between 0.05 and 0.15 is "real but
modest" — useful in combination with other information, not on its own.
Below 0.05 is essentially noise. The colored badges next to each row in
the IC tables tell you which bucket each row falls into.</p>

<p><b>Why it's not a crystal ball.</b> Three honest limits to bear in
mind. <b>First</b>, the model was built knowing what crises happened
between 2008 and today, so it's been quietly tuned in hindsight to catch
those events. The 2000–2017 subset is included specifically to check
that the model still works on a period the designers didn't optimize for
— but even there, the choice of which gauges to include benefits from
hindsight. <b>Second</b>, future crises will not look exactly like past
ones. The 2008 crisis and the 2020 COVID crash and the 2022 inflation
shock all triggered different gauges in different orders. A new kind of
crisis — say, an AI-driven flash crash, or a sovereign-debt episode in a
country we don't track — could move markets without our gauges seeing it.
<b>Third</b>, the dashboard tells you when stress is rising. It does not
tell you what to do about it. A high score is a prompt to think
carefully about your situation, not an instruction to sell.</p>

<p><b>Reading the rest of this report.</b> The "headline" table at the
top shows the model's score against three different definitions of "bad
outcome" — biggest stock drop, biggest credit-market widening, and an
overall stress index. The tables further down break performance out by
indicator (which gauges are pulling weight, which aren't), by VIX tercile
(does the model work better when markets are already nervous, or when
they're calm?), and by year (was 2017 a fluke or representative?). The
ROC curves are a different way of asking the same question — they show
how often the model gives a true alarm vs a false alarm at different
sensitivity settings. The event case studies pick specific historical
crises and show what the model said in advance and during them.</p>

<p><b>The bottom line.</b> If you take only one thing away: this report
exists so the model is not a black box. It tells you, with numbers and
caveats, where the model is reliable and where it isn't. The dashboard's
job is to help its user think more carefully about market risk, not to
replace that thinking — and this report is the receipts.</p>

</div>
</details>
</div>
"""


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
    sections = []

    def _run_and_render(signal_df: pd.DataFrame, label: str,
                        dump_summary: bool = False) -> str:
        print(f"  Running evaluation for {label}...")
        results = run_full_evaluation(signal_df, spx, hy_oas, nfci, vix)

        composite = signal_df["composite"].dropna()

        if dump_summary:
            summary = ic_summary_dict(
                results, len(composite),
                datetime.now().isoformat(timespec="seconds"),
            )
            summary_path = os.path.join(os.path.dirname(output_path) or ".",
                                        "backtest_ic_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            print(f"  Wrote {summary_path}")
        spx_aligned = spx.reindex(composite.index, method="ffill")
        target_30d = build_forward_drawdown(spx_aligned, 30)

        # Benchmark VIX percentile
        vix_pct = None
        if vix is not None:
            vix_pct = vix.rolling(window=252 * 10, min_periods=252).rank(pct=True) * 100
            vix_pct = vix_pct.reindex(composite.index, method="ffill")

        # Events
        hy_aligned = hy_oas.reindex(composite.index, method="ffill") if (hy_oas is not None and len(hy_oas) > 50) else None
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

    sections.append(_section_explainer())
    html_full = _run_and_render(df_full, "Full Model (2018 &ndash; present)",
                                dump_summary=True)
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
    _bt_kw = {"years": FETCH_YEARS, "cache_subdir": "backtest", "cache_hours": 168.0}
    spx = _fetch.fetch_yfinance_series("^GSPC", env, **_bt_kw)
    vix = _fetch.fetch_yfinance_series("^VIX", env, **_bt_kw)
    try:
        hy_oas = _fetch.fetch_fred_series("BAMLH0A0HYM2", env, **_bt_kw)
    except Exception:
        hy_oas = None
    try:
        nfci = _fetch.fetch_fred_series("NFCI", env, **_bt_kw)
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
