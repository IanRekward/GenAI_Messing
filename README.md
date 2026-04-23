# Market Stress Dashboard

A personal market-monitoring dashboard that pulls free public data, scores it against a 9-bucket weighted model, evaluates trigger thresholds, and renders a single HTML dashboard you open in your browser.

Built for daily morning use. Refresh once per day, scan composite score, check active triggers, get on with your life.

## What it does

1. Pulls live data from FRED, EIA, and Yahoo Finance (no paid APIs needed)
2. Calculates z-scores and percentile rankings vs rolling history
3. Computes a composite stress score (0-100) using weighted buckets
4. Evaluates each indicator against yellow/orange/red thresholds
5. **Logs every run to a CSV** so you can see the trend over time on the dashboard
6. **Sends phone alerts** (via Pushover or Twilio) when red triggers fire or composite escalates
7. (Optional) Pulls overnight news headlines and uses Claude to triage them against your trigger watchlist
8. Renders everything to `output/dashboard.html`

## Prerequisites

- Python 3.10 or newer
- A code editor (VS Code recommended)

## Setup (one time, ~10 min)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Get your free API keys

- **FRED API key**: https://fredaccount.stlouisfed.org/apikeys
- **Anthropic API key** (for news triage): https://console.anthropic.com

### 3. Configure

Copy `.env.example` to `.env` and paste your keys in.

### 4. Run

```bash
python run_dashboard.py
```

Optional flags: `--no-cache` `--no-news` `--no-alerts` `--publish` `--quiet`

## Mobile access

Pass `--publish` to push the dashboard to GitHub Pages after each run:

```bash
python run_dashboard.py --publish
```

Dashboard URL: https://ianrekward.github.io/GenAI_Messing/

## Project structure

```
market_dashboard/
├── config/weights.yaml        ← bucket and indicator weights
├── config/thresholds.yaml     ← yellow/orange/red trigger levels
├── src/
│   ├── fetch.py
│   ├── indicators.py
│   ├── scoring.py
│   ├── triggers.py
│   ├── history.py
│   ├── alerts.py
│   ├── news.py
│   └── dashboard.py
├── data/                      ← cached data, history, alert state
├── output/dashboard.html      ← regenerated on each run
└── run_dashboard.py           ← entry point
```

## What this is NOT

Not financial advice. Not a trading system. Not a replacement for thinking.
