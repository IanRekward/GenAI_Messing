"""
Market Stress Dashboard — entry point.

Run with:
    python run_dashboard.py

Optional flags:
    --no-cache         Force fresh data fetch (ignore cached series)
    --no-news          Skip the news triage step
    --quiet            Suppress per-step console output
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from src.scoring import compute_composite, load_weights, load_thresholds
from src.triggers import annotate_results
from src.news import get_news_brief
from src.dashboard import write_dashboard
from src.fetch import load_manual_overrides
from src.history import log_run, load_history
from src.alerts import send_alerts


def main():
    parser = argparse.ArgumentParser(description="Generate the market stress dashboard")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh data download")
    parser.add_argument("--no-news", action="store_true", help="Skip news triage")
    parser.add_argument("--no-alerts", action="store_true", help="Skip phone alerts")
    parser.add_argument("--quiet", action="store_true", help="Less console output")
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

    # Load configs
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
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
        sent = send_alerts(scoring, env)
        if not args.quiet and sent == 0:
            print("  No new alerts to send.")
    elif not args.quiet:
        print("\n[5/5] Alerts skipped (--no-alerts)")

    # Write dashboard
    output_path = write_dashboard(scoring, news, history)

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
