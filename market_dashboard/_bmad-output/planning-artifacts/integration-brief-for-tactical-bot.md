# market_dashboard — integration brief for downstream consumers

Audience: developers of `tactical_markets` and `tactical_markets_trading`
who want to consume regime / health signals from this repo.
Scope: a focused integration doc — not a full architecture scan. Skips UI,
alerts, news, narrative synthesis, and recalibration internals.

Repo root: `c:\Users\rekwa\ian_projects\market_dashboard\`
Last verified against code on: 2026-05-11

---

## 1. What this tool is, in one paragraph

A daily early-warning composite of macro / market stress. 26 indicators across
**11 buckets** are fetched, transformed into 0–100 scores using **10-year
percentile rank** of the raw history (with the percentile flipped where lower
raw = more stress), aggregated to a bucket score, then to a single weighted
**composite score**. Indicator and composite values are mapped to four bands
(green / yellow / orange / red). Output is currently a static HTML dashboard
plus a tabular CSV history; **there is no published JSON API**. The strategic
horizon is 10y+; the run cadence is once-daily at 07:30 local.

---

## 2. The 11 buckets, weights, and what they measure

Bucket weights sum to 1.0. Source of truth: `config/weights.yaml`.

| # | Bucket key | Label | Wt | What it captures |
|---|---|---|---|---|
| 1 | `equity_volatility` | Equity Volatility | 0.13 | VIX level, VIX term structure, SPX 1M realized vol |
| 2 | `credit_spreads` | Credit Spreads | 0.15 | HY OAS, IG BBB OAS |
| 3 | `rates_curve` | Rates & Yield Curve | 0.12 | 10Y–2Y, 10Y level, MOVE, Treasury auction stress (10Y+30Y z-score composite) |
| 4 | `financial_conditions` | Financial Conditions | 0.13 | Chicago Fed NFCI, St. Louis Fed FSI |
| 5 | `inflation` | Inflation Pressure | 0.09 | 5Y breakeven, CPI YoY |
| 6 | `funding_liquidity` | Funding & Liquidity | 0.08 | SOFR–EFFR spread, repo stress (manual 0–3) |
| 7 | `commodities` | Commodities & Energy | 0.07 | WTI, 3-2-1 crack spread, NatGas YoY, copper/gold (inverted) |
| 8 | `economic_momentum` | Economic Momentum | 0.07 | Initial claims 4wk, unemployment rate |
| 9 | `sentiment` | Sentiment | 0.04 | CNN Fear & Greed (inverted, scraped), Iran geopolitical trigger (manual 0–2) |
| 10 | `global_spillover` | Global Spillover | 0.07 | Broad dollar, Euro HY OAS, EM Corp OAS, EEM 1M vol |
| 11 | `breadth_flow` | Market Breadth & Trend | 0.05 | Sector breadth (% sectors below 200d MA), SPX distance from 200d MA |

`invert: true` indicators (where lower raw = more stress): `yield_curve`,
`cnn_fear_greed`, `spx_200dma_distance`, `copper_gold_ratio`. Verify against
`config/weights.yaml` before relying on this list — it's a source-of-truth file.

---

## 3. Data sources and cadence

Sources are declared per-indicator in `weights.yaml` under `source.type`:

- **`fred`** (FRED API) — credit spreads, NFCI/FSI, CPI, breakeven, claims, unemployment, dollar index, Euro HY, EM corp, 10Y–2Y, etc. Requires `FRED_API_KEY` in `.env`.
- **`yfinance`** — `^VIX`, `^TNX`, `^MOVE`, `^GSPC`, `EEM`, `CL=F`, `NG=F`. No key.
- **`computed`** — handlers in `src/scoring.py:COMPUTED_HANDLERS` (CNN F&G scraper, SOFR spread, Treasury auction stress, sector breadth, SPX 200d distance, crack spread, copper/gold, VIX term structure).
- **`manual`** — read from `data/manual_overrides.json`. Currently `repo_stress`, `iran_trigger`.

Cache: `data/cache/` is a per-indicator parquet/CSV cache populated by `src/fetch.py`. Staleness is tracked into `scoring["stale_indicators"]` and surfaced to alerts. Underlying release cadences (CPI monthly, NFCI weekly, intraday tickers daily) are noted in `config/series_cadence.yaml`.

**Run cadence:** Windows Task Scheduler — `Market Dashboard Wake` 07:20, `Market Stress Dashboard` 07:30 daily. Entry point: `python run_dashboard.py --publish --heartbeat --quiet`. There is no live/streaming mode.

---

## 4. Outputs produced per run

Source: `run_dashboard.py` orchestrates fetch → score → trigger → log → narrate → write HTML → alert.

### 4a. In-memory result (the canonical scoring dict)

`src.scoring.compute_composite(weights, env, manual)` returns a dict, then
`src.triggers.annotate_results(scoring, thresholds)` mutates it in place to add
band annotations and red/orange/yellow counts. After `run_dashboard.py` is done
mutating, the shape is:

```python
{
  "composite": 49.8,                          # 0–100 (regime-weighted when enabled, else == composite_naive)
  "composite_naive": 49.8,                    # bucket-weighted average, no regime multipliers
  "composite_regime_weighted": 49.8,          # what composite would be if regime weights applied
  "regime_weights_applied": False,            # currently False — pending 2026-05-30 review
  "regime_multipliers_used": {...} | None,
  "composite_band": "orange",                 # green | yellow | orange | red
  "composite_short": 51.2,                    # same calc on 3-year percentile window (HISTORY_YEARS_SHORT)
  "composite_short_band": "orange",
  "history_years_short": 3,
  "composite_regime_adj": 52.1,               # composite + shock_type adjustment (added by run_dashboard.py post-scoring)
  "composite_regime_adj_label": "+2.3 velocity premium",
  "regime": "mid",                            # VIX-tercile classifier: low | mid | high (smoothed, with hysteresis)
  "red_count": 1, "orange_count": 0, "yellow_count": 4,
  "run_timestamp": "2026-05-11T07:30:12.345678",
  "stale_indicators": ["cpi_yoy"],
  "errors": [...],
  "buckets": {
    "equity_volatility": {
      "label": "Equity Volatility",
      "weight": 0.13,
      "score": 67.1,                          # 0–100, weighted avg of indicators
      "score_short": 62.4,                    # same on 3y window
      "band": "orange",                       # worst constituent band
      "indicators": {
        "vix": {
          "label": "VIX", "raw": 18.42,
          "zscore": 0.31, "percentile": 64.5,
          "percentile_short": 58.9,
          "score": 64.5,                      # 0–100, percentile flipped if invert
          "score_short": 58.9,
          "band": "green",
          "unit": "", "manual": False, "invert": False,
          "_series": {"dates": [...], "values": [...]}  # leading-underscore: internal/UI only
        },
        ... (vix_term_structure, sp500_1m_vol)
      }
    },
    ... (10 more buckets)
  }
}
```

Score → band mapping (`src/indicators.py:band_from_score`):
- `score >= 70` → **red**, `>=50` → **orange**, `>=30` → **yellow**, else **green**

The result dict is the most complete view but is **not serialized to disk** by
the existing pipeline.

### 4b. Persisted artifacts (what's actually on disk after a run)

| Path | Format | Purpose | Schema notes |
|---|---|---|---|
| `data/history.csv` | CSV | Per-run time-series, ~2yr rolling window | `timestamp, composite, composite_band, red_count, orange_count, yellow_count, weights_hash, code_sha, regime, composite_naive, bucket_<each_of_11>` |
| `data/history_archive.parquet` | Parquet | Same schema, rows older than 2yr |
| `data/alert_state.json` | JSON | Alert dedupe state | `composite_band, red_indicators[], orange_indicators[], rapid_rise_alerts[], stale_indicators[], corr_regime_streak, weekly_alert_count, weekly_digest_date, suppressed_alerts[], regime_previous, heartbeat_start` |
| `data/alert_log.jsonl` | JSONL | Append-only event stream | Each line `{ts, event_type, ...}`; event_types include `alert_sent`, `remediation_attempt`, etc. |
| `dashboard.html` (project root) | HTML | Static dashboard, pushed to GitHub Pages | Not machine-parseable |
| `data/cache/<key>.{parquet,csv}` | Parquet/CSV | Raw fetched series cache |

**Gap for the trading bot:** `history.csv` contains the bucket scores and the
composite, but **not the per-indicator raw / score / band** for the latest run.
Old rows in `history.csv` show some legacy `raw_*` columns (now empty / unused)
— don't try to consume those, they were dropped in `log_run`.

---

## 5. What a downstream consumer (the trading bot) actually needs

You have three integration paths. I'll rank them.

### Recommended: add a JSON sidecar emit step

The cheapest, lowest-risk integration is to have `run_dashboard.py` write a
`data/latest.json` containing the full scoring dict (minus `_series` blobs)
after `annotate_results` runs. A reader in `tactical_markets_trading` then
polls / mtime-checks that file.

Proposed `data/latest.json` shape (strip `_series`, keep everything else):

```json
{
  "schema_version": 1,
  "run_timestamp": "2026-05-11T07:30:12",
  "composite": 49.8,
  "composite_band": "orange",
  "composite_short": 51.2,
  "composite_regime_adj": 52.1,
  "regime": "mid",
  "shock_type": "slow_burn",
  "red_count": 1, "orange_count": 0, "yellow_count": 4,
  "stale_indicators": ["cpi_yoy"],
  "buckets": {
    "equity_volatility": {"score": 67.1, "band": "orange", "weight": 0.13,
      "indicators": {"vix": {"raw": 18.42, "score": 64.5, "band": "green", ...}}
    }, ...
  },
  "weights_hash": "a1b2c3d4",
  "code_sha": "abc1234"
}
```

Why this path:
- One-screen patch (~15 LOC) in `run_dashboard.py` after the existing `write_dashboard` call.
- `weights_hash` + `code_sha` give the bot a provenance check — refuse to trade if hash unknown.
- `schema_version` lets the bot fail loudly on incompatible updates.
- Doesn't touch any of the existing 195-test surface.

If you go this route I'd add a brief ROADMAP entry — "Brief: JSON sidecar for downstream consumers" — and ship it before the trading bot wires anything up.

### Acceptable: consume `history.csv` directly

Already on disk, no code changes needed in this repo. The bot reads the last
row and gets composite + 11 bucket scores + composite_band + regime. Loss: no
per-indicator detail, no stale list, no shock_type, no regime-adjusted composite,
no narrative. Fine if the bot only needs the headline.

Watch out for: CSV column order is not stable across schema additions. Read by
name, not position. The file is rewritten every run (`pd.concat → to_csv`), so
brief races are possible — read with retry on parse error.

### Not recommended: import `src.scoring` and re-run

`from src.scoring import compute_composite` works, but you'd be paying the full
fetch cost in the trading bot's process, fighting for the same FRED cache, and
coupling the bot's release cadence to the dashboard's. Don't do this unless the
bot has a genuine reason to re-score intra-day (which it probably shouldn't —
the underlying indicators don't update intra-day).

---

## 6. Concrete contracts the bot should rely on

These are the surfaces I'd consider stable enough to bet on, with stability rationale:

| Surface | Stable? | Why |
|---|---|---|
| Band thresholds (30/50/70 → yellow/orange/red) | **Stable** | Hardcoded in `indicators.band_from_score`; locked scope per CLAUDE.md |
| 11-bucket count | **Stable** | Locked scope; `_MIN_BUCKETS` check in code |
| Bucket keys (the 11 strings in §2) | **Stable-ish** | Not formally locked, but renames would break `history.csv` schema |
| Bucket weights | **Will drift** | Recalibration pipeline exists (`src/recalibrate.py`); regime weighting may flip to enabled after 2026-05-30 review. Always read from `weights.yaml` or the sidecar, never hardcode. |
| Indicator keys within a bucket | **May change** | New indicators get added; old ones can be dropped. Read defensively. |
| Score scale (0–100) | **Stable** | Locked by `percentile_to_score`. |
| `regime` values (`low`/`mid`/`high`) | **Stable** | VIX-tercile classifier, hysteresis to prevent flapping |
| `shock_type` values (`fast_shock`/`slow_burn`/`recovery`/`calm`/`insufficient`) | **Stable** | Locked enum in `history.classify_shock_type` |
| `composite_regime_adj` formula | **May drift** | Adjustment caps (+10 / −8 / +5) are tunable parameters |

### What the bot should validate per read

1. `run_timestamp` is < 26h old (else dashboard automation failed — degrade safely).
2. `weights_hash` matches a known-good list the bot keeps. New hash → don't trade on bucket-weighted signals until reviewed.
3. `stale_indicators` is empty (or known-tolerable). A stale `cpi_yoy` is benign; a stale `hy_oas` is not.
4. `errors` is empty.
5. `composite` is in [0, 100].

---

## 7. Things the brief does **not** cover (deliberately)

- Alert dispatch (Pushover/Twilio) — irrelevant to a programmatic consumer.
- News triage / narrative synthesis — `src/news.py`, `src/narrative.py`. These are dashboard UX, not signal.
- Recalibration pipeline — `src/recalibrate.py`. Producer-side only.
- Backtest / evaluation — `src/backtest.py`, `src/evaluation.py`. Read these if you want to understand how weights were chosen, not to run the bot.
- Two-repo git workflow — internal to dashboard development, irrelevant to the bot.

---

## 8. Recommended next step

Open a ROADMAP brief in this repo titled **"JSON sidecar for downstream
consumers"**. Spec: emit `data/latest.json` after `write_dashboard()`, exclude
`_series` blobs, include `schema_version: 1`, `weights_hash`, `code_sha`. ~15
LOC + one test that asserts shape against a fixture. Once shipped, the trading
bot reads from a stable contract instead of reverse-engineering `history.csv`.

I'd recommend Sonnet for the implementation — it's well-scoped execution work.
