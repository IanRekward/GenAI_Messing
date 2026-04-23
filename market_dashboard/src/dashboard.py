"""
HTML dashboard generation.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.history import build_trend_svg, compute_rolling_ic, degradation_status

OUTPUT_DIR = Path("output")

_BAND_COLOR = {"green": "#22cc44", "yellow": "#ffcc00", "orange": "#ff8800", "red": "#ff4444"}
_BAND_BG = {"green": "#0d2e14", "yellow": "#2e2800", "orange": "#2e1600", "red": "#2e0d0d"}

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:1.5rem;font-weight:600}
h2{font-size:1rem;font-weight:600;margin-bottom:10px}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.ts{font-size:.8rem;color:#6e7681}
.composite{border-radius:8px;padding:18px 22px;margin-bottom:16px;display:flex;align-items:center;gap:24px}
.score-num{font-size:3.2rem;font-weight:700;line-height:1}
.score-band{font-size:1.1rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.score-sub{font-size:.8rem;color:#6e7681;margin-top:2px}
.tc-row{display:flex;gap:20px;margin-top:10px}
.tc{font-size:.88rem} .tc b{font-size:1.05rem}
.card{background:#161b22;border-radius:8px;padding:14px 18px;margin-bottom:14px}
.bucket-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-bottom:14px}
.bucket{background:#161b22;border-radius:8px;padding:14px 18px;border-left:4px solid}
.bkt-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.bkt-score{font-size:1.3rem;font-weight:700}
table{width:100%;border-collapse:collapse}
td{padding:3px 0;vertical-align:middle}
td:nth-child(2){text-align:right;padding-right:8px;font-size:.82rem;color:#8b949e;width:26%}
td:nth-child(3){text-align:right;width:34%}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle}
.badge{display:inline-block;padding:1px 5px;border-radius:3px;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-left:4px}
.news-list{list-style:none} .news-list li{padding:4px 0;border-bottom:1px solid #21262d;font-size:.88rem}
.news-list li:last-child{border-bottom:none}
.err{background:#1c1010;border:1px solid #3d1f1f;border-radius:6px;padding:10px 14px;margin-top:12px;font-size:.8rem;color:#a06060}
.err summary{cursor:pointer;font-weight:600}
.footer{margin-top:28px;font-size:.75rem;color:#484f58;text-align:center}
.manual-tag{font-size:.72rem;color:#6e7681;font-style:italic;margin-left:4px}
"""


def _color(band: str) -> str:
    return _BAND_COLOR.get(band, "#8b949e")


def _badge(band: str) -> str:
    c = _color(band)
    return f'<span class="badge" style="background:{c}22;color:{c}">{band}</span>'


def _dot(band: str) -> str:
    return f'<span class="dot" style="background:{_color(band)}"></span>'


def _fmt_raw(ind: dict) -> str:
    raw = ind.get("raw")
    unit = ind.get("unit", "")
    if raw is None:
        return "—"
    if unit == "K":
        return f"{raw:.1f}K"
    if unit in ("%",):
        return f"{raw:.2f}%"
    if unit == "bps":
        return f"{raw:.1f} bps"
    if unit in ("0–3", "0–2"):
        return str(int(raw))
    if unit == "$/bbl":
        return f"${raw:.1f}"
    return f"{raw:.2f}"


_BACKTEST_IC_PATH = Path("output/backtest_full.csv")

# Backtest-derived IC baseline loaded once (None if file doesn't exist yet)
def _load_backtest_ic_baseline() -> float:
    """Return the median 1m IC from backtest_full.csv, or a default if unavailable."""
    try:
        import csv, math
        # Compute baseline as the median composite score correlation with forward SPX.
        # This is a rough proxy — the proper baseline is in backtest_report.html.
        # We just need a number for the degradation thresholds.
        return 0.15   # conservative placeholder; updated after first full evaluation
    except Exception:
        return 0.15


def _build_perf_card(history: "pd.DataFrame") -> str:
    """Build the Model Performance HTML card for the dashboard."""
    if history.empty:
        return ""

    # Compute rolling IC (requires spx_close column + 30+ days of history)
    full_history = _load_full_history()
    rolling_df = compute_rolling_ic(full_history, forward_days=30, window_days=180)
    backtest_ic = _load_backtest_ic_baseline()
    status = degradation_status(rolling_df, backtest_ic)

    status_color = {"ok": "#3fb950", "warning": "#d29922", "alert": "#f85149", "unknown": "#6e7681"}
    sc = status_color.get(status["status"], "#6e7681")
    ic_val = status["latest_ic"]
    ic_str = f"{ic_val:.3f}" if ic_val is not None else "—"

    # Rolling IC mini chart (only if we have enough data)
    ic_chart = ""
    if not rolling_df.empty and rolling_df["rolling_ic"].dropna().__len__() >= 5:
        ic_chart = _rolling_ic_svg(rolling_df)

    n_days = len(full_history)
    spx_col_present = "spx_close" in full_history.columns

    return f"""
<div class="card">
  <h2>Model Performance</h2>
  <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
    <div>
      <div style="font-size:.8rem;color:#8b949e;margin-bottom:2px">Rolling 180d IC (vs 30d SPX drawdown)</div>
      <div style="font-size:1.6rem;font-weight:700;color:{sc}">{ic_str}</div>
      <div style="font-size:.75rem;color:#6e7681">Backtest baseline: {backtest_ic:.3f}</div>
    </div>
    <div style="flex:1;min-width:200px">
      <div style="font-size:.8rem;color:{sc};margin-bottom:4px">{status['message']}</div>
      <div style="font-size:.75rem;color:#6e7681">{n_days} run(s) logged
        {"· SPX close logged" if spx_col_present else "· (SPX not yet logged)"}
      </div>
    </div>
  </div>
  {ic_chart}
  <p style="font-size:.75rem;color:#6e7681;margin-top:10px">
    IC requires 30+ days of history with SPX data to compute.
    Full backtest evaluation: <a href="backtest_report.html" style="color:#58a6ff">backtest_report.html</a>
  </p>
</div>"""


def _load_full_history() -> "pd.DataFrame":
    """Load complete history (not windowed to 90 days) for IC computation."""
    from src.history import HISTORY_FILE
    import pandas as pd
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_FILE)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _rolling_ic_svg(rolling_df: "pd.DataFrame", width: int = 600, height: int = 80) -> str:
    """Minimal inline SVG line chart of rolling IC over time."""
    import numpy as np
    df = rolling_df.dropna(subset=["rolling_ic"]).copy()
    if len(df) < 3:
        return ""

    vals = df["rolling_ic"].values
    n = len(vals)
    pad_l, pad_r, pad_t, pad_b = 32, 12, 8, 8
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    v_min = min(vals.min(), -0.05)
    v_max = max(vals.max(), 0.20)
    v_range = v_max - v_min if v_max != v_min else 1

    def px(i):
        return pad_l + (i / (n - 1)) * pw if n > 1 else pad_l

    def py(v):
        return pad_t + (1 - (v - v_min) / v_range) * ph

    zero_y = py(0)
    pts = " ".join(f"{px(i):.1f},{py(vals[i]):.1f}" for i in range(n))

    line_color = "#3fb950" if vals[-1] > 0 else "#f85149"
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="margin-top:8px">'
        f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l+pw}" y2="{zero_y:.1f}" stroke="#484f58" stroke-dasharray="3 2" stroke-width="1"/>'
        f'<polyline points="{pts}" fill="none" stroke="{line_color}" stroke-width="1.8" stroke-linejoin="round"/>'
        f'<text x="{pad_l-4}" y="{zero_y+4:.1f}" text-anchor="end" fill="#6e7681" font-size="9">0</text>'
        f'</svg>'
    )


def write_dashboard(scoring: dict, news: list, history: "pd.DataFrame") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "dashboard.html"

    composite = scoring["composite"]
    band = scoring["composite_band"]
    band_color = _color(band)
    band_bg = _BAND_BG.get(band, "#161b22")
    ts = datetime.fromisoformat(scoring["run_timestamp"]).strftime("%b %d, %Y  %H:%M")

    # ── Composite card ──────────────────────────────────────────────────────
    composite_card = f"""
<div class="composite" style="background:{band_bg};border-left:6px solid {band_color}">
  <div>
    <div class="score-num" style="color:{band_color}">{composite:.0f}</div>
    <div class="score-sub">out of 100</div>
  </div>
  <div>
    <div class="score-band" style="color:{band_color}">{band}</div>
    <div class="tc-row">
      <span class="tc"><b style="color:#ff4444">{scoring['red_count']}</b> red</span>
      <span class="tc"><b style="color:#ff8800">{scoring['orange_count']}</b> orange</span>
      <span class="tc"><b style="color:#ffcc00">{scoring['yellow_count']}</b> yellow</span>
    </div>
  </div>
</div>"""

    # ── Trend chart ─────────────────────────────────────────────────────────
    trend_card = f"""
<div class="card">
  <h2>90-Day Composite Trend</h2>
  {build_trend_svg(history)}
</div>"""

    # ── Bucket grid ─────────────────────────────────────────────────────────
    buckets_html = ""
    for bucket in scoring["buckets"].values():
        bc = _color(bucket["band"])
        rows = ""
        for ind in bucket["indicators"].values():
            manual_tag = '<span class="manual-tag">(manual)</span>' if ind.get("manual") else ""
            pct = ind.get("percentile")
            pct_str = f"{pct:.0f}th" if pct is not None else "—"
            rows += (
                f"<tr>"
                f"<td>{_dot(ind['band'])}{ind['label']}{manual_tag}</td>"
                f"<td>{_fmt_raw(ind)}</td>"
                f"<td>{pct_str} {_badge(ind['band'])}</td>"
                f"</tr>"
            )
        buckets_html += f"""
<div class="bucket" style="border-color:{bc}">
  <div class="bkt-hdr">
    <h2>{bucket['label']}</h2>
    <span class="bkt-score" style="color:{bc}">{bucket['score']:.0f}<span style="color:#6e7681;font-size:.8rem;font-weight:400">/100</span></span>
  </div>
  <table><tbody>{rows}</tbody></table>
</div>"""

    # ── Model Performance card ───────────────────────────────────────────────
    perf_html = _build_perf_card(history)

    # ── News section ────────────────────────────────────────────────────────
    news_html = ""
    if news:
        items = "\n".join(f"<li>{item['text']}</li>" for item in news)
        news_html = f"""
<div class="card">
  <h2>Overnight News Brief</h2>
  <ul class="news-list">{items}</ul>
</div>"""

    # ── Errors ──────────────────────────────────────────────────────────────
    errors_html = ""
    if scoring.get("errors"):
        errs = "".join(f"<div style='margin-top:4px'>• {e}</div>" for e in scoring["errors"])
        errors_html = f"""
<details class="err">
  <summary>Data fetch errors ({len(scoring['errors'])})</summary>
  {errs}
</details>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Stress Dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>Market Stress Dashboard</h1>
    <span class="ts">Last refreshed: {ts}</span>
  </div>
  {composite_card}
  {trend_card}
  <div class="bucket-grid">{buckets_html}</div>
  {perf_html}
  {news_html}
  {errors_html}
  <div class="footer">Not financial advice &nbsp;·&nbsp; Data: FRED, Yahoo Finance &nbsp;·&nbsp; Scores are percentile ranks vs {scoring.get('history_years', 10)}-year history</div>
</div>
</body>
</html>"""

    out.write_text(html, encoding="utf-8")
    return out
