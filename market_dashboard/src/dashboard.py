"""
HTML dashboard generation.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from src.history import build_trend_svg, compute_composite_momentum
from src.indicator_detail import build_indicator_detail

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
.detail-section{margin-bottom:14px}
.detail-section>details{background:#161b22;border-radius:8px;padding:12px 16px;margin-bottom:6px}
.detail-section>details>summary{cursor:pointer;font-weight:600;font-size:.9rem;list-style:none;display:flex;justify-content:space-between;align-items:center}
.detail-section>details>summary::-webkit-details-marker{display:none}
.detail-section>details[open]>summary{margin-bottom:8px}
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


def _fmt_momentum(mom: dict, band_color: str) -> str:
    """Render a one-line momentum summary for the composite card."""
    v7 = mom.get("velocity_7d")
    regime = mom.get("regime", "insufficient")
    if v7 is None or regime == "insufficient":
        return '<div class="score-sub" style="margin-top:4px">— (need 8+ days)</div>'
    arrow = "&#8593;" if v7 > 0 else ("&#8595;" if v7 < 0 else "&#8594;")
    sign = "+" if v7 > 0 else ""
    color = "#ff6b6b" if v7 > 0 else ("#4dbb6a" if v7 < 0 else "#6e7681")
    label = regime.replace("_", " ")
    return (
        f'<div class="score-sub" style="margin-top:4px;color:{color}">'
        f'{arrow} {sign}{v7:.1f} pts / 7d <span style="color:#6e7681">({label})</span>'
        f"</div>"
    )


def _load_events() -> list:
    path = Path("config/events.yaml")
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get("events", []) if data else []
    except Exception:
        return []


def _load_thresholds() -> dict:
    path = Path("config/thresholds.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get("indicators", {}) if data else {}
    except Exception:
        return {}


def write_dashboard(scoring: dict, news: list, history: "pd.DataFrame") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "dashboard.html"

    composite = scoring["composite"]
    band = scoring["composite_band"]
    band_color = _color(band)
    band_bg = _BAND_BG.get(band, "#161b22")
    ts = datetime.fromisoformat(scoring["run_timestamp"]).strftime("%b %d, %Y  %H:%M")

    # ── Momentum ────────────────────────────────────────────────────────────
    mom = compute_composite_momentum(history)
    mom_html = _fmt_momentum(mom, band_color)

    # ── Composite card ──────────────────────────────────────────────────────
    composite_card = f"""
<div class="composite" style="background:{band_bg};border-left:6px solid {band_color}">
  <div>
    <div class="score-num" style="color:{band_color}">{composite:.0f}</div>
    <div class="score-sub">out of 100</div>
  </div>
  <div>
    <div class="score-band" style="color:{band_color}">{band}</div>
    {mom_html}
    <div class="tc-row">
      <span class="tc"><b style="color:#ff4444">{scoring['red_count']}</b> red</span>
      <span class="tc"><b style="color:#ff8800">{scoring['orange_count']}</b> orange</span>
      <span class="tc"><b style="color:#ffcc00">{scoring['yellow_count']}</b> yellow</span>
    </div>
  </div>
</div>"""

    # ── Trend chart ─────────────────────────────────────────────────────────
    events = _load_events()
    trend_card = f"""
<div class="card">
  <h2>90-Day Composite Trend</h2>
  {build_trend_svg(history, events)}
</div>"""

    # ── Bucket grid ─────────────────────────────────────────────────────────
    thresholds = _load_thresholds()
    buckets_html = ""
    detail_blocks = ""
    for bkey, bucket in scoring["buckets"].items():
        bc = _color(bucket["band"])
        rows = ""
        for ikey, ind in bucket["indicators"].items():
            manual_tag = '<span class="manual-tag">(manual)</span>' if ind.get("manual") else ""
            pct = ind.get("percentile")
            pct_str = f"{pct:.0f}th" if pct is not None else "—"
            label_html = (
                f'<a href="#{ikey}_detail" style="color:inherit;text-decoration:none">'
                f"{ind['label']}"
                f"</a>"
            )
            rows += (
                f"<tr>"
                f"<td>{_dot(ind['band'])}{label_html}{manual_tag}</td>"
                f"<td>{_fmt_raw(ind)}</td>"
                f"<td>{pct_str} {_badge(ind['band'])}</td>"
                f"</tr>"
            )
            # Build collapsible detail block
            thresh_cfg = thresholds.get(ikey)
            detail_fragment = build_indicator_detail(ikey, ind, thresh_cfg)
            badge_html = _badge(ind["band"])
            detail_blocks += (
                f'<details><summary><span>{ind["label"]}</span>'
                f'<span style="font-weight:400;font-size:.8rem">'
                f'{_fmt_raw(ind)} &nbsp;{badge_html}</span></summary>'
                f"{detail_fragment}"
                f"</details>"
            )
        buckets_html += f"""
<div class="bucket" style="border-color:{bc}">
  <div class="bkt-hdr">
    <h2>{bucket['label']}</h2>
    <span class="bkt-score" style="color:{bc}">{bucket['score']:.0f}<span style="color:#6e7681;font-size:.8rem;font-weight:400">/100</span></span>
  </div>
  <table><tbody>{rows}</tbody></table>
</div>"""

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
  {news_html}
  <div class="card detail-section">
    <h2 style="margin-bottom:10px">Indicator Details</h2>
    {detail_blocks}
  </div>
  {errors_html}
  <div class="footer">Not financial advice &nbsp;·&nbsp; Data: FRED, Yahoo Finance &nbsp;·&nbsp; Scores are percentile ranks vs {scoring.get('history_years', 10)}-year history</div>
</div>
</body>
</html>"""

    out.write_text(html, encoding="utf-8")
    return out
