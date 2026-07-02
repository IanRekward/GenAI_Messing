"""
Per-indicator detail HTML fragment: 10yr SVG chart + stats table.
Used by dashboard.py to build the collapsible "Indicator Details" section.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.indicators import BAND_COLOR as _BAND_COLOR
from src.config import load_yaml_safe

_EXPLAINERS: dict | None = None
_INVERT: dict | None = None


def _load_explainers() -> dict:
    global _EXPLAINERS
    if _EXPLAINERS is None:
        _EXPLAINERS = load_yaml_safe("config/indicator_explainers.yaml", "indicators", {})
    return _EXPLAINERS


def _load_invert_flags() -> dict:
    """{indicator_key: bool} — whether LOWER raw value means MORE stress."""
    global _INVERT
    if _INVERT is None:
        buckets = load_yaml_safe("config/weights.yaml", "buckets", {})
        _INVERT = {
            ikey: bool(cfg.get("invert", False))
            for b in buckets.values()
            for ikey, cfg in b.get("indicators", {}).items()
        }
    return _INVERT


def _explainer_html(ikey: str) -> str:
    ex = _load_explainers().get(ikey)
    if not ex:
        return '<p style="font-size:.78rem;color:#6e7681;margin-top:10px;font-style:italic">(explainer coming soon)</p>'
    advanced = str(ex.get("advanced", "")).strip()
    layman = str(ex.get("layman", "")).strip()
    model_role = str(ex.get("model_role", "")).strip()
    parts = '<div style="margin-top:14px;border-top:1px solid #21262d;padding-top:10px">'
    if advanced:
        parts += (
            '<details style="margin-bottom:6px">'
            '<summary style="cursor:pointer;font-size:.8rem;font-weight:600;'
            'color:#4d9de0;list-style:none">What this measures — practitioners</summary>'
            f'<p style="font-size:.82rem;color:#c9d1d9;line-height:1.55;'
            f'margin-top:6px;padding:0 0 4px 8px">{advanced}</p>'
            '</details>'
        )
    if layman:
        parts += (
            '<details>'
            '<summary style="cursor:pointer;font-size:.8rem;font-weight:600;'
            'color:#4d9de0;list-style:none">Plain English</summary>'
            f'<p style="font-size:.82rem;color:#c9d1d9;line-height:1.55;'
            f'margin-top:6px;padding:0 0 4px 8px">{layman}</p>'
            '</details>'
        )
    if model_role:
        parts += (
            f'<p style="font-size:.72rem;color:#6e7681;margin-top:8px">{model_role}</p>'
        )
    parts += '</div>'
    return parts

_THRESH_COLOR = {
    "yellow": _BAND_COLOR["yellow"],
    "orange": _BAND_COLOR["orange"],
    "red":    _BAND_COLOR["red"],
}


def _build_detail_svg(series: pd.Series, threshold_cfg: dict | None) -> str:
    """Inline SVG showing full history with threshold lines."""
    W, H = 560, 130
    PL, PR, PT, PB = 46, 12, 12, 26
    pw = W - PL - PR
    ph = H - PT - PB

    vals = series.values.astype(float)
    dates = pd.to_datetime(series.index)
    n = len(vals)
    if n < 2:
        return ""

    # Auto-scale y-axis, including threshold levels
    candidates = list(vals)
    if threshold_cfg:
        for key in ("yellow", "orange", "red"):
            v = threshold_cfg.get(key)
            if v is not None:
                candidates.append(float(v))

    data_min = min(candidates)
    data_max = max(candidates)
    padding = max((data_max - data_min) * 0.08, 0.01)
    y_min = data_min - padding
    y_max = data_max + padding

    t_min = dates[0].timestamp()
    t_max = dates[-1].timestamp()

    def xv(i: int) -> float:
        t = dates[i].timestamp()
        return PL + ((t - t_min) / (t_max - t_min)) * pw if t_max > t_min else PL

    def yv(v: float) -> float:
        return PT + (1.0 - (v - y_min) / (y_max - y_min)) * ph

    # Gridlines + y labels
    grid = ""
    n_ticks = 4
    for i in range(n_ticks + 1):
        val = y_min + (y_max - y_min) * i / n_ticks
        yg = yv(val)
        grid += (
            f'<line x1="{PL}" y1="{yg:.1f}" x2="{PL+pw}" y2="{yg:.1f}" '
            f'stroke="#ffffff10" stroke-width="1"/>'
            f'<text x="{PL-3}" y="{yg+3:.1f}" font-size="9" fill="#6e7681" '
            f'text-anchor="end">{val:.1f}</text>'
        )

    # Threshold horizontal lines
    thresh_lines = ""
    if threshold_cfg:
        for level in ("yellow", "orange", "red"):
            tv = threshold_cfg.get(level)
            if tv is None:
                continue
            ty = yv(float(tv))
            if PT <= ty <= PT + ph:
                color = _THRESH_COLOR[level]
                thresh_lines += (
                    f'<line x1="{PL}" y1="{ty:.1f}" x2="{PL+pw}" y2="{ty:.1f}" '
                    f'stroke="{color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.6"/>'
                    f'<text x="{PL+pw+2}" y="{ty+3:.1f}" font-size="8" fill="{color}">'
                    f'{level[0].upper()}</text>'
                )

    # Polyline
    pts = " ".join(f"{xv(i):.1f},{yv(v):.1f}" for i, v in enumerate(vals))
    line = f'<polyline points="{pts}" fill="none" stroke="#4d9de0" stroke-width="1.5" stroke-linejoin="round"/>'

    # Current dot
    cx, cy = xv(n - 1), yv(vals[-1])
    dot = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="#4d9de0"/>'

    # Yearly x-axis labels
    year_labels = ""
    seen_years: set[int] = set()
    for i, dt in enumerate(dates):
        yr = dt.year
        if yr not in seen_years:
            seen_years.add(yr)
            xi = xv(i)
            year_labels += (
                f'<text x="{xi:.1f}" y="{H-4}" font-size="9" fill="#6e7681" '
                f'text-anchor="middle">{yr}</text>'
            )

    return (
        f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="display:block">'
        f"{grid}{thresh_lines}{line}{dot}{year_labels}"
        f"</svg>"
    )


def _fmt_thr(v: float) -> str:
    """Compact threshold value with a proper minus sign."""
    return f"{float(v):g}".replace("-", "−")


def _how_to_read_html(ikey: str, label: str, threshold_cfg: dict | None) -> str:
    """A short, chart-specific 'how to read this' block placed under the SVG.

    Auto-generated so every indicator gets one and it stays correct: it names the
    indicator's real threshold values, colors them, and states the true stress
    direction (from the threshold `direction`, falling back to the weights
    `invert` flag). An optional `how_to_read` field in indicator_explainers.yaml
    overrides the generated text for a given indicator.
    """
    override = str(_load_explainers().get(ikey, {}).get("how_to_read", "")).strip()

    has_levels = bool(threshold_cfg) and all(
        threshold_cfg.get(k) is not None for k in ("yellow", "orange", "red")
    )
    if threshold_cfg and threshold_cfg.get("direction"):
        higher_is_stress = threshold_cfg["direction"] == "high"
    else:
        higher_is_stress = not _load_invert_flags().get(ikey, False)

    if override:
        body = override
    else:
        dir_word = "higher" if higher_is_stress else "lower"
        toward = ("climbing toward the top of the chart" if higher_is_stress
                  else "sinking toward the bottom of the chart")
        cross = "rises above" if higher_is_stress else "falls below"

        sentences = [
            f"The blue line is <b>{label}</b> over roughly the last decade; the dot "
            f"marks the latest reading, and the stats below put it in context."
        ]
        if has_levels:
            def _lvl(level: str) -> str:
                return (f'<span style="color:{_THRESH_COLOR[level]}">{level} '
                        f'({_fmt_thr(threshold_cfg[level])})</span>')
            sentences.append(
                f"The dashed lines are the model&rsquo;s alert levels: when the line "
                f"{cross} the {_lvl('yellow')}, {_lvl('orange')}, or {_lvl('red')} "
                f"level, this indicator flips to that band and pushes more stress into "
                f"the overall score."
            )
            sentences.append(
                f"For this metric <b>{dir_word} = more stress</b>, so a line {toward} "
                f"&mdash; especially past the orange and red dashes &mdash; is the shape "
                f"to watch."
            )
        else:
            sentences.append(
                f"This indicator has no fixed alert levels; its band comes from where "
                f"today&rsquo;s reading ranks against its own 10-year history (the "
                f"percentile below). For this metric <b>{dir_word} = more stress</b>, so "
                f"a line {toward} is the direction that signals rising risk."
            )
        body = " ".join(sentences)

    return (
        f'<div style="margin-top:10px;background:#0d1117;border:1px solid #21262d;'
        f'border-radius:6px;padding:10px 12px">'
        f'<div style="font-size:.78rem;font-weight:700;color:#4d9de0;margin-bottom:4px">'
        f'How to read this chart</div>'
        f'<p style="font-size:.82rem;color:#c9d1d9;line-height:1.55;margin:0">{body}</p>'
        f'</div>'
    )


def build_indicator_detail(
    ikey: str,
    ind_result: dict,
    threshold_cfg: dict | None = None,
) -> str:
    """Return an HTML <div id='{ikey}_detail'> block with chart + stats."""
    label = ind_result.get("label", ikey)
    series_data = ind_result.get("_series")
    unit = ind_result.get("unit", "")
    raw = ind_result.get("raw")
    pct = ind_result.get("percentile")
    band = ind_result.get("band", "green")

    bc = _BAND_COLOR.get(band, "#8b949e")

    how_read_html = ""
    if ind_result.get("manual") or series_data is None:
        chart_html = (
            '<p style="color:#6e7681;font-style:italic;font-size:.8rem;padding:6px 0">'
            "Manual indicator — no time series available.</p>"
        )
        stats_html = ""
    else:
        series = pd.Series(
            series_data["values"],
            index=pd.to_datetime(series_data["dates"]),
        )
        chart_html = _build_detail_svg(series, threshold_cfg)
        how_read_html = _how_to_read_html(ikey, label, threshold_cfg)

        # Stats table
        s_min = series.min()
        s_max = series.max()
        s_med = series.median()
        last_date = pd.to_datetime(series_data["dates"][-1]).strftime("%b %d, %Y")
        raw_str = f"{raw:.3f} {unit}".strip() if raw is not None else "—"
        pct_str = f"{pct:.0f}th" if pct is not None else "—"

        def _f(v: float) -> str:
            return f"{v:.3f} {unit}".strip()

        stats_html = f"""
<table style="margin-top:8px;font-size:.78rem;border-collapse:collapse;width:100%">
  <tr>
    <td style="color:#6e7681;padding:2px 10px 2px 0">Current</td>
    <td><b style="color:{bc}">{raw_str}</b></td>
    <td style="color:#6e7681;padding:2px 10px 2px 16px">Percentile</td>
    <td>{pct_str}</td>
  </tr>
  <tr>
    <td style="color:#6e7681;padding:2px 10px 2px 0">10yr min</td>
    <td>{_f(s_min)}</td>
    <td style="color:#6e7681;padding:2px 10px 2px 16px">10yr max</td>
    <td>{_f(s_max)}</td>
  </tr>
  <tr>
    <td style="color:#6e7681;padding:2px 10px 2px 0">10yr median</td>
    <td>{_f(s_med)}</td>
    <td style="color:#6e7681;padding:2px 10px 2px 16px">Last obs.</td>
    <td>{last_date}</td>
  </tr>
</table>"""

    return (
        f'<div id="{ikey}_detail" style="padding-top:6px">'
        f"{chart_html}"
        f"{how_read_html}"
        f"{stats_html}"
        f"{_explainer_html(ikey)}"
        f"</div>"
    )
