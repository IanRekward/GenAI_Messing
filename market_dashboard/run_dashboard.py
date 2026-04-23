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
from src.scoring import compute_composite, load_weights, load_thresholds
from src.triggers import annotate_results
from src.news import get_news_brief
from src.dashboard import write_dashboard
from src.fetch import load_manual_overrides
from src.history import log_run, load_history, prune_history
from src.alerts import send_alerts, send_heartbeat, send_weekly_digest


def _publish_to_github(dashboard_path: Path, quiet: bool = False) -> None:
    """Copy dashboard.html to _genai_tmp/docs/index.html and push to GitHub."""
    genai_tmp = Path(__file__).resolve().parent.parent / "_genai_tmp"
    docs_dir = genai_tmp / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / "index.html"
    shutil.copy2(dashboard_path, dest)

    def _git(*args):
        return subprocess.run(["git"] + list(args), cwd=genai_tmp,
                              capture_output=True, text=True)

    _git("add", "docs/index.html")

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
        validate_config(weights, thresholds)
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

    # Log to history before alerts (so chart includes current run)
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

    # Alerts
    if not args.no_alerts:
        if not args.quiet:
            print("\n[5/5] Checking alerts...")
        sent = send_alerts(scoring, env, history)
        if not args.quiet and sent == 0:
            print("  No new alerts to send.")
    elif not args.quiet:
        print("\n[5/5] Alerts skipped (--no-alerts)")

    # Write dashboard
    output_path = write_dashboard(scoring, news, history)

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
