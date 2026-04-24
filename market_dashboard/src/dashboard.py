"""
HTML dashboard generation.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from src.history import (
    build_trend_svg, compute_composite_momentum, compute_bucket_momentum,
    cross_bucket_correlation, correlation_regime, classify_shock_type,
)
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
td{padding:1px 0;vertical-align:middle}
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
.tip{position:relative;cursor:help;border-bottom:1px dotted #6e7681}
.tip::after{content:attr(data-tip);position:absolute;left:0;top:110%;background:#1c2128;color:#c9d1d9;padding:8px 12px;border-radius:6px;border:1px solid #30363d;font-size:.76rem;line-height:1.5;width:280px;z-index:200;white-space:normal;display:none;pointer-events:none;font-weight:400}
.tip:hover::after,.tip:focus::after{display:block}
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
    if unit == "σ":
        sign = "+" if raw > 0 else ""
        return f"{sign}{raw:.2f}σ"
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


def _load_review_prompts() -> dict:
    path = Path("config/review_prompts.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return (data or {}).get("bands", {})
    except Exception:
        return {}


def _build_review_card(band: str, shock_type: str) -> str:
    """
    Return a collapsible review-prompts card for the given composite band.
    Shows the band-specific questions plus recovery questions when applicable.
    """
    prompts_cfg = _load_review_prompts()
    keys_to_show: list[str] = []

    if band in ("yellow", "orange", "red"):
        keys_to_show.append(band)
    if shock_type == "recovery" and "recovery" in prompts_cfg:
        keys_to_show.append("recovery")

    if not keys_to_show:
        return ""

    _HEADER_COLOR = {"yellow": "#ffcc00", "orange": "#ff8800",
                     "red": "#ff4444", "recovery": "#22cc44"}

    blocks = ""
    for key in keys_to_show:
        cfg = prompts_cfg.get(key, {})
        qs = cfg.get("prompts", [])
        label = cfg.get("label", key.title())
        if not qs:
            continue
        hc = _HEADER_COLOR.get(key, "#6e7681")
        items = "".join(
            f'<li style="padding:4px 0;border-bottom:1px solid #21262d;font-size:.85rem">{q}</li>'
            for q in qs
        )
        blocks += (
            f'<details style="margin-bottom:8px">'
            f'<summary style="cursor:pointer;font-weight:600;font-size:.88rem;color:{hc};'
            f'list-style:none;display:flex;justify-content:space-between;align-items:center">'
            f'<span>{label}</span>'
            f'<span style="font-size:.72rem;color:#6e7681;font-weight:400">click to expand</span>'
            f"</summary>"
            f'<ul style="list-style:none;margin-top:8px;padding-left:4px">{items}</ul>'
            f"</details>"
        )

    if not blocks:
        return ""

    return (
        f'<div class="card" style="border-left:3px solid #30363d">'
        f'<h2 style="margin-bottom:10px;font-size:.9rem;color:#6e7681">REVIEW PROMPTS</h2>'
        f"{blocks}"
        f"</div>"
    )


def _load_tooltips() -> dict:
    path = Path("config/tooltips.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except Exception:
        return {}


def _tip(text: str, tip_str: str, tag: str = "span") -> str:
    """Wrap text in a CSS tooltip span. tip_str is HTML-escaped automatically."""
    if not tip_str:
        return text
    safe = tip_str.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<{tag} class="tip" data-tip="{safe}" tabindex="0">'
        f"{text}</{tag}>"
    )


def _load_thresholds() -> dict:
    path = Path("config/thresholds.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get("indicators", {}) if data else {}
    except Exception:
        return {}


def _build_calendar_card(events: list) -> str:
    if not events:
        return ""
    _TYPE_DOT = {"fomc": "#d29922", "auction": "#4d9de0", "economic": "#8b949e"}
    rows = ""
    for ev in events:
        d = ev["date"]
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            day_label = dt.strftime("%b %d  %a")
        except ValueError:
            day_label = d
        dot_col = _TYPE_DOT.get(ev.get("type", "economic"), "#8b949e")
        dot = f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:{dot_col};margin-right:6px;vertical-align:middle"></span>'
        rows += (
            f'<div style="display:flex;align-items:center;padding:3px 0;'
            f'border-bottom:1px solid #21262d;font-size:.83rem">'
            f'<span style="color:#6e7681;min-width:90px">{day_label}</span>'
            f'<span>{dot}{ev["label"]}</span>'
            f"</div>"
        )
    legend = (
        '<div style="display:flex;gap:16px;margin-top:10px;font-size:.75rem;color:#6e7681">'
        '<span><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#d29922;margin-right:4px;vertical-align:middle"></span>FOMC</span>'
        '<span><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#4d9de0;margin-right:4px;vertical-align:middle"></span>Auction</span>'
        '<span><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#8b949e;margin-right:4px;vertical-align:middle"></span>Economic</span>'
        "</div>"
    )
    return f'<div class="card"><h2>Upcoming Macro Events (14 days)</h2>{rows}{legend}</div>'


def write_dashboard(scoring: dict, news: list, history: "pd.DataFrame",
                    calendar_events: list | None = None,
                    narrative: str = "") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "dashboard.html"

    composite = scoring["composite"]
    band = scoring["composite_band"]
    band_color = _color(band)
    band_bg = _BAND_BG.get(band, "#161b22")
    ts = datetime.fromisoformat(scoring["run_timestamp"]).strftime("%b %d, %Y  %H:%M")
    tooltips = _load_tooltips()

    # ── Momentum ────────────────────────────────────────────────────────────
    mom = compute_composite_momentum(history)
    mom_html = _fmt_momentum(mom, band_color)

    # ── Shock-type classification (todo 42) ──────────────────────────────────
    _SHOCK_COLOR = {
        "fast_shock": "#ff4444", "slow_burn": "#ffcc00",
        "recovery": "#22cc44",   "calm": "#6e7681", "insufficient": "",
    }
    _SHOCK_LABEL = {
        "fast_shock": "FAST SHOCK", "slow_burn": "SLOW BURN",
        "recovery": "RECOVERY",     "calm": "CALM",
    }
    shock_type = classify_shock_type(history, scoring)
    shock_html = ""
    if shock_type in _SHOCK_LABEL:
        sc = _SHOCK_COLOR.get(shock_type, "#6e7681")
        shock_tip = tooltips.get("shock_type", {}).get(shock_type, "")
        inner = _tip(_SHOCK_LABEL[shock_type], shock_tip) if shock_tip else _SHOCK_LABEL[shock_type]
        shock_html = (
            f'<div class="score-sub" style="margin-top:4px">'
            f'<span style="color:{sc};font-weight:600;font-size:.78rem">{inner}</span>'
            f"</div>"
        )

    # ── Composite card ──────────────────────────────────────────────────────
    composite_tip = tooltips.get("composite", {}).get("tip", "")
    band_tip = tooltips.get("bands", {}).get(band, "")
    mom_tip = tooltips.get("momentum", {}).get("tip", "")
    composite_score_html = _tip(f"{composite:.0f}", composite_tip)
    band_label_html = _tip(band, band_tip)
    # ── Regime-aware (short-window) composite (todo 43) ─────────────────────
    composite_short = scoring.get("composite_short")
    composite_short_band = scoring.get("composite_short_band", "green")
    short_years = scoring.get("history_years_short", 3)
    regime_html = ""
    if composite_short is not None:
        sc_color = _color(composite_short_band)
        delta = composite_short - composite
        delta_str = (f"<span style='color:#ff6b6b'>▲+{delta:.1f}</span>" if delta > 3
                     else f"<span style='color:#4dbb6a'>▼{delta:.1f}</span>" if delta < -3
                     else "")
        regime_tip = tooltips.get("regime_window", {}).get("tip", "")
        inner = f"{composite_short:.0f}"
        if regime_tip:
            inner = _tip(inner, regime_tip)
        regime_html = (
            f'<div class="score-sub" style="margin-top:3px">'
            f'<span style="color:#6e7681">{short_years}yr window: </span>'
            f'<span style="color:{sc_color};font-weight:600">{inner}</span>'
            f'<span style="color:#6e7681"> {composite_short_band}</span>'
            f' {delta_str}'
            f"</div>"
        )

    composite_card = f"""
<div class="composite" style="background:{band_bg};border-left:6px solid {band_color}">
  <div>
    <div class="score-num" style="color:{band_color}">{composite_score_html}</div>
    <div class="score-sub">out of 100</div>
  </div>
  <div>
    <div class="score-band" style="color:{band_color}">{band_label_html}</div>
    {mom_html}
    {shock_html}
    {regime_html}
    <div class="tc-row">
      <span class="tc"><b style="color:#ff4444">{scoring['red_count']}</b> red</span>
      <span class="tc"><b style="color:#ff8800">{scoring['orange_count']}</b> orange</span>
      <span class="tc"><b style="color:#ffcc00">{scoring['yellow_count']}</b> yellow</span>
    </div>
  </div>
</div>"""

    # ── Correlation card ────────────────────────────────────────────────────
    corr_val = cross_bucket_correlation(history)
    corr_regime = correlation_regime(corr_val)
    _CORR_COLOR = {
        "decorrelated": "#22cc44", "normal": "#8b949e",
        "crisis_synchronous": "#ff4444", "insufficient": "#6e7681",
    }
    corr_color = _CORR_COLOR.get(corr_regime, "#6e7681")
    corr_display = f"{corr_val:.2f}" if corr_val is not None else "—"
    corr_label = corr_regime.replace("_", " ")
    corr_tip = tooltips.get("correlation", {}).get("tip", "")
    corr_display_html = _tip(corr_display, corr_tip) if corr_tip else corr_display
    correlation_card = f"""
<div class="card" style="display:flex;align-items:center;gap:20px;padding:14px 18px">
  <div>
    <div style="font-size:1.6rem;font-weight:700;color:{corr_color}">{corr_display_html}</div>
    <div style="font-size:.75rem;color:#6e7681">cross-bucket corr (30d)</div>
  </div>
  <div>
    <div style="font-weight:600;color:{corr_color}">{corr_label.upper()}</div>
    <div style="font-size:.75rem;color:#6e7681">&lt;0.30 decorrelated · 0.30–0.60 normal · ≥0.60 crisis</div>
  </div>
</div>"""

    # ── Trend chart ─────────────────────────────────────────────────────────
    events = _load_events()
    trend_card = f"""
<div class="card">
  <h2>90-Day Composite Trend</h2>
  {build_trend_svg(history, events)}
</div>"""

    # ── Staleness banner (todo 39) ───────────────────────────────────────────
    stale_keys = set(scoring.get("stale_indicators", []))
    staleness_banner = ""
    if stale_keys:
        stale_labels = [
            ind["label"]
            for bkt in scoring["buckets"].values()
            for ik, ind in bkt["indicators"].items()
            if ik in stale_keys
        ]
        n = len(stale_labels)
        sev_color = "#ff4444" if n >= 3 else "#ffcc00"
        sev_bg = "#2e0d0d" if n >= 3 else "#2e2800"
        label_list = ", ".join(stale_labels[:6]) + (" +more" if n > 6 else "")
        staleness_banner = (
            f'<div style="background:{sev_bg};border:1px solid {sev_color};'
            f'border-radius:6px;padding:10px 16px;margin-bottom:14px;font-size:.82rem">'
            f'<span style="color:{sev_color};font-weight:700">&#9888; STALE DATA</span>'
            f'<span style="color:#c9d1d9;margin-left:8px">'
            f'{n} indicator{"s" if n != 1 else ""} may be behind schedule: {label_list}'
            f"</span></div>"
        )

    # ── Bucket momentum (todo 37) ────────────────────────────────────────────
    bucket_vel = compute_bucket_momentum(history)
    # Top-3 accelerating: buckets with highest positive 7d velocity
    top3_accel = set(
        sorted(
            [k for k, v in bucket_vel.items() if v is not None and v > 0],
            key=lambda k: bucket_vel[k],
            reverse=True,
        )[:3]
    )

    # ── Bucket grid ─────────────────────────────────────────────────────────
    thresholds = _load_thresholds()
    ind_tooltips = tooltips.get("indicators", {})
    bucket_tooltips = tooltips.get("buckets", {})
    buckets_html = ""
    detail_blocks = ""
    for bkey, bucket in scoring["buckets"].items():
        bc = _color(bucket["band"])
        bkt_tip = bucket_tooltips.get(bkey, {}).get("tip", "")
        rows = ""
        for ikey, ind in bucket["indicators"].items():
            manual_tag = '<span class="manual-tag">(manual)</span>' if ind.get("manual") else ""
            pct = ind.get("percentile")
            pct_str = f"{pct:.0f}th" if pct is not None else "—"
            itip = ind_tooltips.get(ikey, {}).get("tip", "")
            inner_label = _tip(ind["label"], itip) if itip else ind["label"]
            label_html = (
                f'<a href="#{ikey}_detail" style="color:inherit;text-decoration:none">'
                f"{inner_label}"
                f"</a>"
            )
            # Short description: first sentence of tooltip (up to first ". ")
            short_desc = ""
            if itip:
                dot_idx = itip.find(". ")
                short_desc = itip[:dot_idx] if 0 < dot_idx < 100 else (itip[:80] if len(itip) > 80 else itip)
            desc_html = (
                f'<div style="font-size:.72rem;color:#6e7681;padding-left:12px;line-height:1.3">'
                f'{short_desc}</div>'
            ) if short_desc else ""
            # "as of" date from last series observation
            series_data = ind.get("_series")
            as_of_html = ""
            if series_data and series_data.get("dates"):
                as_of_html = (
                    f'<div style="font-size:.68rem;color:#6e7681;margin-top:1px">'
                    f'as of {series_data["dates"][-1]}</div>'
                )
            rows += (
                f"<tr>"
                f"<td>{_dot(ind['band'])}{label_html}{manual_tag}{desc_html}</td>"
                f"<td><div>{_fmt_raw(ind)}</div>{as_of_html}</td>"
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
        bkt_label_html = _tip(bucket["label"], bkt_tip) if bkt_tip else bucket["label"]
        # Velocity display for this bucket
        vel = bucket_vel.get(bkey)
        vel_html = ""
        if vel is not None:
            arrow = "&#9650;" if vel > 0 else ("&#9660;" if vel < 0 else "&#8594;")
            vel_color = "#ff6b6b" if vel > 0 else ("#4dbb6a" if vel < 0 else "#6e7681")
            sign = "+" if vel > 0 else ""
            vel_html = (
                f'<div style="font-size:.72rem;color:{vel_color};margin-top:1px">'
                f'{arrow} {sign}{vel:.1f} / 7d</div>'
            )
        # Top-3 accelerating badge
        accel_badge = ""
        if bkey in top3_accel:
            accel_badge = '<span style="font-size:.62rem;color:#ff8800;margin-left:6px;font-weight:700">&#9650;FAST</span>'
        buckets_html += f"""
<div class="bucket" style="border-color:{bc}">
  <div class="bkt-hdr">
    <h2>{bkt_label_html}{accel_badge}</h2>
    <span class="bkt-score" style="color:{bc}">{bucket['score']:.0f}<span style="color:#6e7681;font-size:.8rem;font-weight:400">/100</span>{vel_html}</span>
  </div>
  <table><tbody>{rows}</tbody></table>
</div>"""

    # ── News section ────────────────────────────────────────────────────────
    news_html = ""
    if news:
        li_parts = []
        for item in news:
            text = item["text"]
            url = item.get("url", "")
            if url:
                li_parts.append(
                    f'<li><a href="{url}" target="_blank" rel="noopener"'
                    f' style="color:inherit">{text}</a></li>'
                )
            else:
                li_parts.append(f"<li>{text}</li>")
        news_html = f"""
<div class="card">
  <h2>Overnight News Brief</h2>
  <ul class="news-list">{"".join(li_parts)}</ul>
</div>"""

    # ── Review prompts (todo 46) ────────────────────────────────────────────
    review_card = _build_review_card(band, shock_type)

    # ── Errors ──────────────────────────────────────────────────────────────
    errors_html = ""
    if scoring.get("errors"):
        errs = "".join(f"<div style='margin-top:4px'>• {e}</div>" for e in scoring["errors"])
        errors_html = f"""
<details class="err">
  <summary>Data fetch errors ({len(scoring['errors'])})</summary>
  {errs}
</details>"""

    # ── Narrative card (todo 1) ──────────────────────────────────────────────
    narrative_card = ""
    if narrative:
        narrative_card = (
            f'<div class="card" style="border-left:3px solid #4d9de0;font-size:.88rem;'
            f'line-height:1.6;color:#c9d1d9">{narrative}'
            f'<div style="margin-top:6px;font-size:.72rem;color:#484f58">'
            f'AI-generated summary (Claude) · not financial advice</div></div>'
        )

    # ── Calendar card ───────────────────────────────────────────────────────
    calendar_card = _build_calendar_card(calendar_events or [])

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
  {staleness_banner}
  {narrative_card}
  {composite_card}
  {review_card}
  {correlation_card}
  {trend_card}
  {calendar_card}
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
