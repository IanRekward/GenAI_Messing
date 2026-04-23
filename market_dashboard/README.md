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

- Python 3.10 or newer (check with `python --version` or `python3 --version`)
- A code editor (VS Code recommended)
- 5 minutes to grab two free API keys

## Setup (one time, ~10 min)

### 1. Open the project in VS Code

Unzip this folder somewhere sensible (e.g., `~/projects/market_dashboard`). Open the folder in VS Code: **File → Open Folder → select `market_dashboard`**.

Open VS Code's terminal: **View → Terminal** (or `` Ctrl+` ``).

### 2. Install Python dependencies

In the terminal, with the `market_dashboard` folder open:

```bash
pip install -r requirements.txt
```

If you get permission errors, try `pip install --user -r requirements.txt`. If you have Python 2 installed, use `pip3` instead of `pip`.

### 3. Get your free API keys

You need two keys (both free, both 30-second signups):

- **FRED API key**: https://fredaccount.stlouisfed.org/apikeys — register, click "Request API Key," paste the description, copy the 32-character key
- **EIA API key**: https://www.eia.gov/opendata/register.php — fill the short form, key emails to you immediately

Optional but recommended:
- **Anthropic API key** (for news triage): https://console.anthropic.com — sign up, create a key. The morning news brief uses Claude Haiku which costs fractions of a cent per run.

### 4. Configure your keys

Copy `.env.example` to a new file called `.env`:

```bash
cp .env.example .env
```

(On Windows: `copy .env.example .env`)

Open `.env` in VS Code and paste your keys in. Save.

### 5. Run it

```bash
python run_dashboard.py
```

First run takes ~30-60 seconds (downloading historical data for z-score calculations). Subsequent runs are faster (~10-15 sec) because data is cached locally in `data/`.

When done, it'll print the path to the dashboard. Open it in your browser:

```bash
# Mac
open output/dashboard.html

# Linux
xdg-open output/dashboard.html

# Windows
start output/dashboard.html
```

Or just double-click the file in VS Code's explorer.

## Daily use

Just run `python run_dashboard.py` each morning. The dashboard updates and you scan it. Done.

To force a clean refresh (ignore cache), delete the `data/` folder contents first or pass `--no-cache`:

```bash
python run_dashboard.py --no-cache
```

## Configuration

Edit weights in `config/weights.yaml`. Edit thresholds in `config/thresholds.yaml`. No code changes required — just edit the YAML and re-run.

If a particular indicator is too noisy or you want to suppress it, set its weight to 0 in `weights.yaml`. The dashboard will still display it but it won't affect the composite.

## Manual override fields

A few indicators (AAII sentiment, Iran trigger states, BDC NAV marks) need manual updates because there's no clean free API. Edit these in `data/manual_overrides.json` (created on first run). The dashboard will use your latest manual values.

## Phone alerts

The dashboard sends push notifications when:
- **Composite band escalates** (e.g., orange → red) — always
- **A new red trigger fires** that wasn't red on the previous run
- **Two or more new orange triggers** appear in the same run

To enable, sign up at [pushover.net](https://pushover.net) (~$5 one-time for the iOS/Android app), create an Application, and put the app token + your user key in `.env`.

Alternatively, use Twilio SMS — fill in the `TWILIO_*` fields in `.env` instead. Twilio is per-message, more expensive, but works without installing an app.

If neither is configured, alerts print to your terminal instead.

State is tracked in `data/alert_state.json` so you don't get spammed with the same alert every run. To skip alerts on a given run, pass `--no-alerts`.

## History tracking

Every run logs to `data/history.csv` with the composite, all bucket scores, and trigger counts. The dashboard renders a 90-day trend chart at the top using this data.

The history file is a plain CSV — open it in Excel or load it into pandas if you want to do your own analysis. It will accumulate over time; if you want to wipe and start fresh, just delete the file.

## Pushing to git

See `GIT_SETUP.md` in this folder for a step-by-step walkthrough, including a one-paste prompt you can hand to Claude Code on your laptop to do the whole git initialization and remote push for you.

## Project structure

```
market_dashboard/
├── README.md                  ← you are here
├── GIT_SETUP.md               ← how to push to your git repo
├── requirements.txt           ← Python dependencies
├── .env.example               ← template for your API keys
├── .env                       ← your actual keys (created by you, never commit)
├── .gitignore                 ← keeps .env, cache, output out of git
├── config/
│   ├── weights.yaml           ← bucket and indicator weights
│   └── thresholds.yaml        ← yellow/orange/red trigger levels
├── src/
│   ├── fetch.py               ← API calls to FRED, EIA, Yahoo
│   ├── indicators.py          ← z-score & percentile calculations
│   ├── scoring.py             ← weighted composite calculation
│   ├── triggers.py            ← threshold evaluation
│   ├── history.py             ← CSV logging + trend chart SVG
│   ├── alerts.py              ← Pushover / Twilio phone alerts
│   ├── news.py                ← RSS feed parsing + Claude triage
│   └── dashboard.py           ← HTML output generation
├── data/                      ← cached data, history, manual overrides, alert state
├── output/
│   └── dashboard.html         ← regenerated on each run
└── run_dashboard.py           ← entry point — run this
```

## Troubleshooting

**"ModuleNotFoundError"** — you didn't install dependencies, or you're using a different Python than where you installed them. Try `python -m pip install -r requirements.txt`.

**"FRED API rate limit"** — you've hit the limit (120 req/min). Wait a minute and re-run. Caching prevents this on normal use.

**Yahoo Finance returns empty** — yfinance occasionally rate-limits. Run again in a minute, or comment out failing indicators temporarily.

**Dashboard renders but numbers look stale** — check the "Last refreshed" timestamp at the top. If today's date isn't there, your cache is stale; run with `--no-cache`.

**News triage is slow or fails** — it requires the Anthropic API key. If you don't have one, set `ENABLE_NEWS_TRIAGE=false` in your `.env` and the dashboard will skip that section.

**Phone alerts not firing** — check that your `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` are set correctly in `.env` (they shouldn't start with `your_`). You can also force an alert test by deleting `data/alert_state.json` and re-running — anything currently in red/orange will alert. To skip alerts entirely on a run, use `--no-alerts`.

**Trend chart shows "will appear after multiple runs"** — that's expected on your first run. After 2+ runs, the 90-day chart appears. Each run logs to `data/history.csv`.

## What this is NOT

- Not financial advice. This is an analytical framework you built for yourself.
- Not a trading system. No execution, no order routing.
- Not a replacement for thinking. The model is a starting point, not a black box.

## Adjusting the model

Want to add an indicator? Edit `src/fetch.py` to add the data source, `src/indicators.py` to add the calculation, and `config/weights.yaml` to weight it. The framework is designed for easy extension.

Want to test a different weighting scheme? Just edit `config/weights.yaml` and re-run. No data is re-downloaded if cache is fresh.
