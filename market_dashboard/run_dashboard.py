"""
Market Stress Dashboard — entry point.

Run with:
    python run_dashboard.py

Optional flags:
    --no-cache         Force fresh data fetch (ignore cached series)
    --no-news          Skip the news triage step
    --quiet            Suppress per-step console output
    --publish          Copy dashboard to GitHub Pages repo and push
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from src.config import validate_config, ConfigError
from src.scoring import compute_composite, load_weights, load_thresholds, COMPUTED_HANDLERS
from src.triggers import annotate_results
from src.news import get_news_brief
from src.dashboard import write_dashboard
from src.fetch import load_manual_overrides
from src.history import log_run, load_history, prune_history
from src.alerts import send_alerts, send_heartbeat, send_weekly_digest, score_past_alerts
from src.calendar import fetch_upcoming_events
from src.narrative import generate_narrative
from src.history import (
    compute_composite_momentum, compute_bucket_momentum,
    classify_shock_type, compute_regime_adjusted_composite,
)


def _indicator_source_type(weights: dict, key: str) -> str:
    """Walk weights.yaml structure to find an indicator's source type; return '' if missing."""
    for bucket_data in weights.get("buckets", {}).values():
        if key in bucket_data.get("indicators", {}):
            ind_cfg = bucket_data["indicators"][key]
            return ind_cfg.get("source", {}).get("type", "")
    return ""


def _log_remediation(indicator: str, outcome: str, reason: str) -> None:
    """Log a remediation attempt to data/alert_log.jsonl."""
    import json
    Path("data").mkdir(exist_ok=True)
    with open("data/alert_log.jsonl", "a") as f:
        f.write(json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event_type": "remediation_attempt",
            "indicator": indicator,
            "outcome": outcome,
            "reason": reason,
        }) + "\n")


def _publish_to_github(dashboard_path: Path, quiet: bool = False) -> None:
    """Copy dashboard.html to _genai_tmp/docs/index.html and push to GitHub."""
    genai_tmp = Path(__file__).resolve().parent.parent / "_genai_tmp"
    docs_dir = genai_tmp / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / "index.html"
    shutil.copy2(dashboard_path, dest)

    report_src = dashboard_path.parent / "backtest_report.html"
    if report_src.exists():
        shutil.copy2(report_src, docs_dir / "backtest_report.html")

    def _git(*args):
        return subprocess.run(["git"] + list(args), cwd=genai_tmp,
                              capture_output=True, text=True)

    _git("add", "docs/index.html", "docs/backtest_report.html")

    # Check if there's actually a change staged
    diff = _git("diff", "--cached", "--quiet")
    if diff.returncode == 0:
        if not quiet:
            print("  Publish: dashboard unchanged, nothing to push.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _git("commit", "-m", f"Publish dashboard {timestamp}")

    push = _git("push", "origin", "main")
    if not quiet:
        if push.returncode == 0:
            print("  Publish: dashboard pushed to GitHub Pages.")
        else:
            print(f"  Publish: push failed — {push.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description="Generate the market stress dashboard")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh data download")
    parser.add_argument("--no-news", action="store_true", help="Skip news triage")
    parser.add_argument("--no-alerts", action="store_true", help="Skip phone alerts")
    parser.add_argument("--quiet", action="store_true", help="Less console output")
    parser.add_argument("--publish", action="store_true", help="Push dashboard to GitHub Pages")
    parser.add_argument("--heartbeat", action="store_true", help="Send daily Pushover confirmation for 31 days")
    args = parser.parse_args()

    # Load env vars from .env
    load_dotenv()
    env = dict(os.environ)
    if args.no_news:
        env["ENABLE_NEWS_TRIAGE"] = "false"
    if args.no_cache:
        env["CACHE_HOURS"] = "0"

    if not args.quiet:
        print("=" * 60)
        print(" Market Stress Dashboard")
        print("=" * 60)

    # Load and validate configs — aborts with a clear message on any drift
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    try:
        validate_config(weights, thresholds, frozenset(COMPUTED_HANDLERS.keys()))
    except ConfigError as e:
        print(f"\n  CONFIG ERROR: {e}\n")
        sys.exit(1)
    manual = load_manual_overrides()

    # Score everything
    if not args.quiet:
        print("\n[1/5] Computing indicator scores...")
    scoring = compute_composite(weights, env, manual)

    # Apply thresholds
    if not args.quiet:
        print("\n[2/5] Evaluating triggers...")
    scoring = annotate_results(scoring, thresholds)

    # ── Stale data + DQ remediation (Brief 17) ─────────────────────────
    stale_keys = set(scoring.get("stale_indicators", []))
    failed_keys = {
        ikey
        for bdata in scoring["buckets"].values()
        for ikey, ind in bdata["indicators"].items()
        if ind.get("percentile") is None
    }
    # Exclude computed indicators (their fetch is derived, can't force-refresh)
    remediation_keys = {
        k for k in (stale_keys | failed_keys)
        if _indicator_source_type(weights, k) != "computed"
    }

    if remediation_keys:
        reasons = {k: ("stale" if k in stale_keys else "percentile_none")
                   for k in remediation_keys}
        env_r = {**env, "_remediation_keys": remediation_keys}
        scoring = compute_composite(weights, env_r, manual)
        scoring = annotate_results(scoring, thresholds)

        # Determine outcome per key
        still_stale = set(scoring.get("stale_indicators", []))
        still_failed = {
            ikey for bdata in scoring["buckets"].values()
            for ikey, ind in bdata["indicators"].items()
            if ind.get("percentile") is None
        }
        still_broken = still_stale | still_failed
        for k in remediation_keys:
            outcome = "failed" if k in still_broken else "success"
            _log_remediation(k, outcome, reasons[k])

    # Log to history (must run AFTER remediation so history.csv reflects fresh data)
    if not args.quiet:
        print("\n[3/5] Logging to history...")
    log_run(scoring)
    prune_history()
    history = load_history(days=90)

    # News
    news = []
    if not args.no_news:
        if not args.quiet:
            print("\n[4/5] Pulling and triaging news...")
        news = get_news_brief(env)
    elif not args.quiet:
        print("\n[4/5] News triage skipped (--no-news)")

    # Score any past alerts whose T+7/14/30 windows have elapsed
    score_past_alerts(history)

    from src.alerts import get_postmortem_stats
    pm_stats = get_postmortem_stats(days=60)

    # Alerts
    if not args.no_alerts:
        if not args.quiet:
            print("\n[5/5] Checking alerts...")
        sent = send_alerts(scoring, env, history)
        if not args.quiet and sent == 0:
            print("  No new alerts to send.")
    elif not args.quiet:
        print("\n[5/5] Alerts skipped (--no-alerts)")

    # Upcoming macro events for calendar card
    calendar_events: list = []
    try:
        calendar_events = fetch_upcoming_events(env)
    except Exception:
        pass

    # Daily narrative paragraph (Claude Haiku synthesis)
    mom = compute_composite_momentum(history)
    bkt_vel = compute_bucket_momentum(history)
    shock_type = classify_shock_type(history, scoring)
    regime_adj, regime_adj_label = compute_regime_adjusted_composite(
        scoring["composite"], shock_type, mom
    )
    scoring["composite_regime_adj"] = regime_adj
    scoring["composite_regime_adj_label"] = regime_adj_label
    history_summary = {
        "shock_type": shock_type,
        "velocity_7d": mom.get("velocity_7d"),
        "regime": mom.get("regime", "insufficient"),
        "bucket_velocities": bkt_vel,
    }
    narrative, narrative_layman = generate_narrative(scoring, history_summary, env)

    # Write dashboard
    output_path = write_dashboard(scoring, news, history,
                                  calendar_events=calendar_events,
                                  narrative=narrative,
                                  narrative_layman=narrative_layman,
                                  env=env,
                                  signal_quality_stats=pm_stats)

    # Weekly digest (sends automatically on Mondays)
    if not args.no_alerts:
        send_weekly_digest(scoring, env, history)

    # Heartbeat confirmation for first 31 days
    if args.heartbeat:
        send_heartbeat(scoring, env)

    # Optionally publish to GitHub Pages
    if args.publish:
        if not args.quiet:
            print("\n[6/6] Publishing to GitHub Pages...")
        _publish_to_github(output_path, args.quiet)

    # Summary print
    if not args.quiet:
        print("\n" + "=" * 60)
        print(f" Composite stress: {scoring['composite']:.1f}/100  ({scoring['composite_band'].upper()})")
        print(f" Triggers: {scoring['red_count']} red, {scoring['orange_count']} orange, {scoring['yellow_count']} yellow")
        print(f" History rows: {len(history)}")
        print(f" Output: {output_path.absolute()}")
        print("=" * 60)
        print(f"\n  Open in browser:  file://{output_path.absolute()}")


if __name__ == "__main__":
    main()
