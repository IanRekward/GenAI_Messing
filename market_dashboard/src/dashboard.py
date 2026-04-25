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
from src.analogs import find_analog

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
.no-mb{margin-bottom:0!important}
.detail-section{margin-bottom:14px}
.detail-section>details{background:#161b22;border-radius:8px;padding:12px 16px;margin-bottom:6px}
.detail-section>details>summary{cursor:pointer;font-weight:600;font-size:.9rem;list-style:none;display:flex;justify-content:space-between;align-items:center}
.detail-section>details>summary::-webkit-details-marker{display:none}
.detail-section>details[open]>summary{margin-bottom:8px}
.tip{position:relative;cursor:help;border-bottom:1px dotted #6e7681}
.tip::after{content:attr(data-tip);position:absolute;left:0;top:110%;background:#1c2128;color:#c9d1d9;padding:8px 12px;border-radius:6px;border:1px solid #30363d;font-size:.76rem;line-height:1.5;width:280px;z-index:200;white-space:normal;display:none;pointer-events:none;font-weight:400}
.tip:hover::after,.tip:focus::after{display:block}
@media(max-width:600px){
  .hdr{flex-direction:column;align-items:flex-start;gap:6px}
  .composite{flex-direction:column;gap:8px}
  .tc-row{flex-wrap:wrap;gap:12px}
  .tip::after{left:auto;right:0;width:220px}
  .bucket-grid{grid-template-columns:1fr}
}
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
        f'<h2 style="margin-bottom:6px;font-size:.9rem;color:#6e7681">REVIEW PROMPTS</h2>'
        f'<div style="font-size:.75rem;color:#6e7681;margin-bottom:8px">'
        f'Questions to guide your response given current conditions</div>'
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


def _load_ind_weights() -> dict[str, dict[str, float]]:
    """Return {bkey: {ikey: float}} pulled live from config/weights.yaml."""
    path = Path("config/weights.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {
            bkey: {ikey: float(icfg["weight"]) for ikey, icfg in bcfg.get("indicators", {}).items()}
            for bkey, bcfg in data.get("buckets", {}).items()
        }
    except Exception:
        return {}


_CALENDAR_INDICATOR_MAP: list[tuple[str, str | None, str | None]] = [
    ("CPI",            "cpi_yoy",                "Inflation"),
    ("PPI",            None,                     None),
    ("Jobless Claims", "jobless_claims",         "Economic Momentum"),
    ("NFP",            "jobless_claims",         "Economic Momentum"),
    ("Non-Farm",       "jobless_claims",         "Economic Momentum"),
    ("GDP",            None,                     None),
    ("PCE",            None,                     None),
    ("Retail Sales",   None,                     None),
    ("FOMC",           "ten_year",               "Rates"),
    ("Auction",        "treasury_auction_stress","Rates"),
    ("PMI",            None,                     None),
    ("ISM",            None,                     None),
]


def _calendar_indicator_badge(label: str) -> str:
    """Return an indicator badge or 'not in model' tag for a calendar event label."""
    label_lower = label.lower()
    for keyword, ind_key, bucket_label in _CALENDAR_INDICATOR_MAP:
        if keyword.lower() in label_lower:
            if ind_key:
                return (
                    f'<span style="font-size:.68rem;color:#4d9de0;'
                    f'background:#0d2030;padding:1px 5px;border-radius:3px;'
                    f'margin-left:6px;white-space:nowrap">'
                    f'→ {ind_key} ({bucket_label})</span>'
                )
            else:
                return (
                    f'<span style="font-size:.68rem;color:#484f58;'
                    f'background:#161b22;padding:1px 5px;border-radius:3px;'
                    f'margin-left:6px">not in model</span>'
                )
    return (
        f'<span style="font-size:.68rem;color:#484f58;'
        f'background:#161b22;padding:1px 5px;border-radius:3px;'
        f'margin-left:6px">not in model</span>'
    )


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
        badge = _calendar_indicator_badge(ev["label"])
        rows += (
            f'<div style="display:flex;align-items:center;padding:3px 0;'
            f'border-bottom:1px solid #21262d;font-size:.83rem">'
            f'<span style="color:#6e7681;min-width:90px">{day_label}</span>'
            f'<span style="display:flex;align-items:center;flex-wrap:wrap;gap:2px">'
            f'{dot}{ev["label"]}{badge}</span>'
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


def _load_escalation_paths() -> dict:
    path = Path("config/escalation_paths.yaml")
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return (data or {}).get("buckets", {})
    except Exception:
        return {}


def _build_escalation_card(scoring: dict) -> str:
    """
    Show forward-looking escalation scenarios for orange/red buckets.
    Only shown when composite >= 40 and at least one bucket is orange/red.
    """
    if scoring.get("composite", 0) < 40:
        return ""
    paths = _load_escalation_paths()
    if not paths:
        return ""

    blocks = ""
    for bkey, bucket in scoring.get("buckets", {}).items():
        if bucket.get("band") not in ("orange", "red"):
            continue
        path_cfg = paths.get(bkey)
        if not path_cfg:
            continue
        bc = _color(bucket["band"])
        scenario = str(path_cfg.get("scenario", "")).replace("\n", " ").strip()
        watch = path_cfg.get("watch", "")
        historical = path_cfg.get("historical", "")
        watch_html = (
            f'<div style="margin-top:4px;font-size:.78rem;color:#8b949e">'
            f'<b>Watch:</b> {watch}</div>'
        ) if watch else ""
        hist_html = (
            f'<div style="font-size:.75rem;color:#484f58;margin-top:2px">'
            f'{historical}</div>'
        ) if historical else ""
        blocks += (
            f'<details style="margin-bottom:8px">'
            f'<summary style="cursor:pointer;font-weight:600;font-size:.85rem;'
            f'color:{bc};list-style:none;display:flex;justify-content:space-between;'
            f'align-items:center">'
            f'<span>{bucket["label"]}</span>'
            f'<span style="font-size:.7rem;color:#6e7681;font-weight:400">'
            f'{bucket["band"].upper()} · click to expand</span>'
            f'</summary>'
            f'<div style="margin-top:8px;padding-left:4px">'
            f'<div style="font-size:.83rem;line-height:1.55;color:#c9d1d9">{scenario}</div>'
            f'{watch_html}{hist_html}'
            f'</div>'
            f'</details>'
        )

    if not blocks:
        return ""
    return (
        f'<div class="card" style="border-left:3px solid #ff880044">'
        f'<h2 style="margin-bottom:10px;font-size:.9rem;color:#ff8800">ESCALATION SCENARIOS</h2>'
        f'<div style="font-size:.75rem;color:#6e7681;margin-bottom:8px">'
        f'Pre-mortem: plausible 60–90 day paths if current stress persists or escalates</div>'
        f'{blocks}</div>'
    )


def _build_analog_card(analogs: list) -> str:
    """Compact card showing top historical analog matches (only when composite >= 35)."""
    if not analogs:
        return ""
    rows = ""
    for i, a in enumerate(analogs):
        pct = int(a["similarity"] * 100)
        bar_w = max(4, pct)
        label_color = "#c9d1d9" if i == 0 else "#8b949e"
        tags_html = " ".join(
            f'<span style="background:#21262d;color:#8b949e;padding:1px 5px;'
            f'border-radius:3px;font-size:.68rem">{t}</span>'
            for t in a["tags"]
        )
        rows += (
            f'<div style="padding:6px 0;border-bottom:1px solid #21262d">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<span style="font-weight:600;color:{label_color}">{a["name"]}</span>'
            f'<span style="font-size:.75rem;color:#6e7681">{a["date_range"]}</span>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:8px;margin-top:3px">'
            f'<div style="flex:1;height:4px;background:#21262d;border-radius:2px">'
            f'<div style="width:{bar_w}%;height:4px;background:#4d9de0;border-radius:2px"></div>'
            f'</div>'
            f'<span style="font-size:.75rem;color:#4d9de0;min-width:32px;text-align:right">'
            f'{pct}%</span>'
            f'</div>'
            f'<div style="margin-top:3px">{tags_html}</div>'
            f'</div>'
        )
    note = (
        '<div style="margin-top:8px;font-size:.72rem;color:#484f58">'
        'Pattern similarity based on bucket score profile — not a forecast</div>'
    )
    return (
        f'<div class="card" style="border-left:3px solid #30363d">'
        f'<h2 style="margin-bottom:6px;font-size:.9rem;color:#6e7681">HISTORICAL ANALOGS</h2>'
        f'{rows}{note}</div>'
    )


def _build_bucket_health_card(scoring: dict, history: "pd.DataFrame") -> str:
    """Flag indicators with missing data and bucket scores frozen for ≥3 runs."""
    issues = []

    for bkey, bucket in scoring["buckets"].items():
        for ikey, ind in bucket["indicators"].items():
            if ind.get("percentile") is None:
                issues.append(f"{ind['label']}: no live data (using fallback score)")

    if len(history) >= 3:
        for bkey, bucket in scoring["buckets"].items():
            col = f"bucket_{bkey}"
            if col not in history.columns:
                continue
            recent = history[col].dropna().tail(3)
            if len(recent) >= 3 and recent.nunique() == 1:
                issues.append(
                    f"{bucket['label']}: bucket score unchanged for ≥3 runs "
                    f"(value: {recent.iloc[-1]:.1f} — possible stale source)"
                )

    if not issues:
        return ""

    items_html = "".join(
        f'<li style="color:#c9d1d9;margin:3px 0">{i}</li>' for i in issues
    )
    n = len(issues)
    return (
        f'<details style="margin-bottom:14px">'
        f'<summary style="color:#ffcc00;cursor:pointer;font-size:.82rem;font-weight:700">'
        f'&#9888; DATA QUALITY ({n} issue{"s" if n != 1 else ""})'
        f'<span style="color:#8b949e;font-weight:400;margin-left:8px">'
        f'(click to expand)</span></summary>'
        f'<ul style="margin:8px 0 0 16px;padding:0;font-size:.80rem">{items_html}</ul>'
        f'</details>'
    )


def _build_signal_quality_card(
    history: "pd.DataFrame",
    env: dict,
    signal_quality_stats: dict | None,
) -> str:
    """Compact card with rolling composite IC + recent alert hit rate.

    Returns "" if SPX fetch fails or history is too short to be meaningful.
    """
    from src.evaluation import rolling_composite_ic
    from src.fetch import fetch_yfinance_series

    REPORT_PATH = OUTPUT_DIR / "backtest_report.html"
    _VERDICT = [
        (0.15, "Tracking", "#22cc44"),
        (0.05, "Weak signal", "#ffcc00"),
        (0.00, "Miscalibrated", "#ff4444"),
    ]

    try:
        spx = fetch_yfinance_series("^GSPC", env, years=2)
        ic_result = rolling_composite_ic(history, spx)
    except Exception:
        return ""

    ic = ic_result["ic"]
    n_obs = ic_result["n_obs"]

    # Verdict
    if ic is None:
        verdict, verdict_color = "Insufficient history", "#6e7681"
        ic_display = "—"
    else:
        ic_display = f"{ic:.2f}"
        verdict, verdict_color = "Miscalibrated", "#ff4444"
        for threshold, label, color in _VERDICT:
            if ic >= threshold:
                verdict, verdict_color = label, color
                break

    # Data freshness — most recent history row
    try:
        last_ts = pd.to_datetime(history["timestamp"]).max().strftime("%Y-%m-%d")
    except Exception:
        last_ts = "unknown"

    ic_panel = (
        f'<div style="min-width:80px">'
        f'<div style="font-size:1.6rem;font-weight:700;color:{verdict_color}">{ic_display}</div>'
        f'<div style="font-size:.72rem;color:#6e7681">rolling IC ({n_obs} obs, 21d horizon)</div>'
        f'<div style="font-size:.70rem;color:#484f58;margin-top:2px">as of {last_ts}</div>'
        f'</div>'
    )

    # Alert hit rate panel
    pm = signal_quality_stats or {}
    scored = pm.get("scored_count", 0)
    total = pm.get("total_alerts", 0)
    hit_rate = pm.get("hit_rate_7d_pct")
    if total == 0:
        hr_display = "No alerts scored yet"
        hr_sub = "60-day window"
    elif scored == 0:
        hr_display = f"{total} alert{'s' if total != 1 else ''} fired"
        hr_sub = "T+7 outcomes pending"
    else:
        hr_display = f"{hit_rate:.0f}% still elevated at T+7"
        hr_sub = f"{scored}/{total} alerts scored (60d)"

    hr_panel = (
        f'<div style="min-width:120px">'
        f'<div style="font-size:.95rem;font-weight:600;color:#c9d1d9">{hr_display}</div>'
        f'<div style="font-size:.72rem;color:#6e7681">{hr_sub}</div>'
        f'</div>'
    )

    verdict_badge = (
        f'<div style="margin-top:10px">'
        f'<span style="background:{verdict_color}22;color:{verdict_color};'
        f'font-weight:700;font-size:.78rem;padding:3px 10px;border-radius:4px">'
        f'{verdict.upper()}</span>'
        f'<span style="font-size:.72rem;color:#6e7681;margin-left:10px">'
        f'IC ≥ 0.15 = Tracking · 0.05–0.15 = Weak · &lt;0.05 = Miscalibrated</span>'
        f'</div>'
    )

    report_link = ""
    if REPORT_PATH.exists():
        report_link = (
            f'<div style="text-align:right;margin-top:8px;font-size:.78rem">'
            f'<a href="backtest_report.html" target="_blank" '
            f'style="color:#58a6ff;text-decoration:none">'
            f'View full backtest report →</a></div>'
        )

    # Data alignment checks
    BT_CSV = OUTPUT_DIR / "backtest_full.csv"
    alignment_html = ""
    try:
        now = datetime.now()
        # Backtest freshness — mod time of the CSV
        if BT_CSV.exists():
            import os as _os
            bt_mtime = datetime.fromtimestamp(_os.path.getmtime(BT_CSV))
            bt_str = bt_mtime.strftime("%Y-%m-%d %H:%M")
            bt_age_h = (now - bt_mtime).total_seconds() / 3600
        else:
            bt_str = "not found"
            bt_age_h = float("inf")

        # Live composite timestamp
        comp_ts_str = history["timestamp"].max() if not history.empty else None
        comp_str = pd.to_datetime(comp_ts_str).strftime("%Y-%m-%d %H:%M") if comp_ts_str else "unknown"

        # Gap between backtest and live composite
        gap_warn = ""
        if comp_ts_str and BT_CSV.exists():
            comp_dt = pd.to_datetime(comp_ts_str)
            gap_h = abs((bt_mtime - comp_dt.to_pydatetime()).total_seconds()) / 3600
            if gap_h > 2:
                gap_warn = (
                    f'<span style="color:#ffcc00;margin-left:8px">&#9888; '
                    f'{gap_h:.0f}h apart — re-run backtest to resync</span>'
                )

        stale_warn = ""
        if bt_age_h > 48:
            stale_warn = (
                f'<span style="color:#ffcc00;margin-left:8px">&#9888; '
                f'backtest is {bt_age_h/24:.0f}d old — consider re-running</span>'
            )

        alignment_html = (
            f'<div style="margin-top:10px;font-size:.72rem;color:#6e7681;line-height:1.7">'
            f'<span style="color:#8b949e">backtest:</span> {bt_str}'
            f'<span style="color:#484f58;margin:0 6px">·</span>'
            f'<span style="color:#8b949e">composite:</span> {comp_str}'
            f'{gap_warn}{stale_warn}'
            f'</div>'
        )
    except Exception:
        pass

    return (
        f'<div class="card" style="padding:14px 18px">'
        f'<h2 style="margin-bottom:10px">Model Calibration</h2>'
        f'<div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">'
        f'{ic_panel}{hr_panel}'
        f'</div>'
        f'{verdict_badge}'
        f'{alignment_html}'
        f'{report_link}'
        f'</div>'
    )


def write_dashboard(scoring: dict, news: list, history: "pd.DataFrame",
                    calendar_events: list | None = None,
                    narrative: str = "",
                    env: dict | None = None,
                    signal_quality_stats: dict | None = None) -> Path:
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
    # ── Regime-aware composite (todo 43) ────────────────────────────────────
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

    # VIX regime badge (Brief 10A — read-only telemetry)
    _regime_colors = {"low": "#22cc44", "mid": "#ffcc00", "high": "#ff8800"}
    vix_regime = scoring.get("regime")
    vix_regime_html = ""
    if vix_regime is not None:
        rc = _regime_colors.get(vix_regime, "#6e7681")
        vix_5dma = scoring.get("regime_vix_5dma")
        thresholds = scoring.get("regime_thresholds", {})
        detail = ""
        if vix_5dma is not None and thresholds:
            detail = (
                f" (smoothed VIX {vix_5dma}"
                f" — boundaries {thresholds.get('low_max')} / {thresholds.get('high_min')})"
            )
        elif vix_5dma is not None:
            detail = f" (smoothed VIX {vix_5dma})"
        vix_regime_tip = tooltips.get("vix_regime", {}).get("tip", "")
        badge_inner = f'<span style="color:{rc};font-weight:600">{vix_regime.upper()}</span>'
        if vix_regime_tip:
            badge_inner = _tip(badge_inner, vix_regime_tip)
        vix_regime_html = (
            f'<div class="score-sub" style="margin-top:3px">'
            f'<span style="color:#6e7681">VIX regime: </span>'
            f'{badge_inner}'
            f'<span style="color:#6e7681;font-size:.75rem">{detail}</span>'
            f"</div>"
        )

    # Velocity-adjusted composite — show only when adjustment is material (≥3 pts)
    regime_adj = scoring.get("composite_regime_adj")
    regime_adj_label = scoring.get("composite_regime_adj_label", "")
    regime_adj_html = ""
    if regime_adj is not None and abs(regime_adj - composite) >= 3:
        _band_fn = lambda s: "red" if s >= 70 else "orange" if s >= 50 else "yellow" if s >= 30 else "green"
        adj_band = _band_fn(regime_adj)
        adj_color = _color(adj_band)
        adj_tip = tooltips.get("regime_adjusted", {}).get("tip", "")
        inner_adj = f"{regime_adj:.0f}"
        if adj_tip:
            inner_adj = _tip(inner_adj, adj_tip)
        regime_adj_html = (
            f'<div class="score-sub" style="margin-top:3px">'
            f'<span style="color:#6e7681">Regime-adj: </span>'
            f'<span style="color:{adj_color};font-weight:600">{inner_adj}</span>'
            f'<span style="color:#6e7681;font-size:.75rem"> ({regime_adj_label})</span>'
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
    {vix_regime_html}
    {regime_adj_html}
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
    _CORR_CAPTION = {
        "decorrelated": "Stress is isolated — buckets are moving independently. Risk is concentrated, not systemic.",
        "normal": "Typical co-movement between buckets. No unusual synchronization detected.",
        "crisis_synchronous": "Buckets moving together — a hallmark of systemic stress where diversification fails.",
    }
    corr_caption = _CORR_CAPTION.get(corr_regime, "")
    corr_caption_html = (
        f'<div style="font-size:.78rem;color:#8b949e;margin-top:8px;line-height:1.45">'
        f'{corr_caption}</div>'
    ) if corr_caption else ""
    correlation_card = f"""
<div class="card" style="padding:14px 18px">
  <div style="display:flex;align-items:center;gap:20px">
    <div>
      <div style="font-size:1.6rem;font-weight:700;color:{corr_color}">{corr_display_html}</div>
      <div style="font-size:.75rem;color:#6e7681">cross-bucket corr (30d)</div>
    </div>
    <div>
      <div style="font-weight:600;color:{corr_color}">{corr_label.upper()}</div>
      <div style="font-size:.75rem;color:#6e7681">&lt;0.30 decorrelated · 0.30–0.60 normal · ≥0.60 crisis</div>
    </div>
  </div>
  {corr_caption_html}
</div>"""

    # ── Trend chart ─────────────────────────────────────────────────────────
    events = _load_events()
    trend_card = f"""
<div class="card">
  <h2>90-Day Composite Trend</h2>
  <div style="font-size:.75rem;color:#6e7681;margin-bottom:6px">Composite stress score (0–100) over the last 90 days &nbsp;·&nbsp; Green &lt;30 &nbsp;·&nbsp; Yellow 30–50 &nbsp;·&nbsp; Orange 50–70 &nbsp;·&nbsp; Red ≥70 &nbsp;·&nbsp; Today is on the right</div>
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

    bucket_health_card = _build_bucket_health_card(scoring, history)
    signal_quality_card = _build_signal_quality_card(history, env or {}, signal_quality_stats)

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
    ind_weights = _load_ind_weights()
    buckets_html = ""
    detail_blocks = ""
    for bkey, bucket in scoring["buckets"].items():
        bc = _color(bucket["band"])
        bkt_tip = bucket_tooltips.get(bkey, {}).get("tip", "")
        bucket_weight = bucket["weight"]
        bucket_pct = round(bucket_weight * 100)
        bkt_iweights = ind_weights.get(bkey, {})
        rows = ""
        bar_segments = ""
        for ikey, ind in bucket["indicators"].items():
            iw = bkt_iweights.get(ikey, 0.0)
            iw_comp = bucket_weight * iw * 100
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
            # Weight annotation under the label
            weight_html = ""
            if iw > 0:
                weight_html = (
                    f'<div style="font-size:.65rem;color:#484f58;padding-left:12px">'
                    f'{iw*100:.0f}% of bucket · {iw_comp:.1f}% of composite</div>'
                )
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
                f"<td>{_dot(ind['band'])}{label_html}{manual_tag}{desc_html}{weight_html}</td>"
                f"<td><div>{_fmt_raw(ind)}</div>{as_of_html}</td>"
                f"<td>{pct_str} {_badge(ind['band'])}</td>"
                f"</tr>"
            )
            # Bar chart segment: flex width proportional to indicator weight in bucket
            seg_color = _color(ind["band"])
            seg_tip = f'{ind["label"]}: {iw*100:.0f}% of bucket, {iw_comp:.1f}% of composite'.replace('"', '&quot;')
            bar_segments += (
                f'<div style="flex:{iw:.3f};background:{seg_color}55;border-radius:2px;'
                f'border-top:2px solid {seg_color}" title="{seg_tip}"></div>'
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
        bar_chart = (
            f'<div style="display:flex;gap:2px;margin:6px 0 8px;height:5px">{bar_segments}</div>'
        ) if bar_segments else ""
        buckets_html += f"""
<div class="bucket" style="border-color:{bc}">
  <div class="bkt-hdr">
    <div>
      <h2>{bkt_label_html}{accel_badge}</h2>
      <div style="font-size:.7rem;color:#6e7681;margin-top:1px">{bucket_pct}% of composite</div>
    </div>
    <span class="bkt-score" style="color:{bc}">{bucket['score']:.0f}<span style="color:#6e7681;font-size:.8rem;font-weight:400">/100</span>{vel_html}</span>
  </div>
  {bar_chart}
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

    # ── Historical analogs (TOP-3 item 2) ───────────────────────────────────
    analog_card = _build_analog_card(find_analog(scoring))

    # ── Escalation scenarios / pre-mortem (TOP-3 item 3) ────────────────────
    escalation_card = _build_escalation_card(scoring)

    # ── Side-by-side action row: REVIEW PROMPTS + ESCALATION SCENARIOS ───────
    if review_card and escalation_card:
        r_flush = review_card.replace('<div class="card"', '<div class="card no-mb"', 1)
        e_flush = escalation_card.replace('<div class="card"', '<div class="card no-mb"', 1)
        action_row = (
            f'<div style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:14px;align-items:flex-start">'
            f'<div style="flex:1;min-width:260px">{r_flush}</div>'
            f'<div style="flex:1;min-width:260px">{e_flush}</div>'
            f'</div>'
        )
    else:
        action_row = review_card + escalation_card

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

    run_iso = scoring["run_timestamp"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Stress Dashboard</title>
<style>{_CSS}</style>
</head>
<body data-run-ts="{run_iso}">
<div class="wrap">
  <div id="automation-banner"></div>
  <div class="hdr">
    <h1>Market Stress Dashboard</h1>
    <span class="ts">Last refreshed: {ts}</span>
  </div>
  {staleness_banner}
  {bucket_health_card}
  {composite_card}
  {action_row}
  {narrative_card}
  {analog_card}
  {correlation_card}
  {signal_quality_card}
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
<script>
(function() {{
  var ts = document.body.getAttribute('data-run-ts');
  if (!ts) return;
  var runTime = new Date(ts);
  var hoursAgo = (Date.now() - runTime.getTime()) / 3600000;
  var banner = document.getElementById('automation-banner');
  if (!banner) return;
  if (hoursAgo > 30) {{
    var h = Math.round(hoursAgo);
    banner.innerHTML = '<div style="background:#2e0d0d;border:1px solid #ff4444;border-radius:6px;padding:10px 16px;margin-bottom:14px;font-size:.82rem">'
      + '<span style="color:#ff4444;font-weight:700">&#9888; AUTOMATION OFFLINE</span>'
      + '<span style="color:#c9d1d9;margin-left:8px">Dashboard last ran ' + h + ' hours ago — morning automation may have failed. Check Task Scheduler.</span>'
      + '</div>';
  }}
}})();
</script>
</body>
</html>"""

    out.write_text(html, encoding="utf-8")
    return out
