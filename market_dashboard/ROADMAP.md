# Market Dashboard — Architectural Roadmap (Phase 6+)

Produced by Opus 4.7 on 2026-04-23 as a senior-architect review of the current
system. Hand individual briefs to Sonnet for execution. Briefs are numbered and
designed to be self-contained — Sonnet should be able to read one brief and
execute without needing the others.

---

## CRITICAL PRE-WORK — READ THIS FIRST

**The active `config/weights.yaml` is NOT the Phase 5 recalibrated 10-bucket
version.** It reverted to the original 9-bucket pre-recalibration file at some
point between 2026-04-23 14:32 and 15:14 runs. The correct 10-bucket, recalibrated
config is in `config/weights.yaml.bak`.

Evidence:
- `history.csv` rows before 15:14 have `raw_global_spillover__*` values; rows
  after 15:14 have empty cells for those columns.
- `src/scoring.py` still contains router entries for `usd_index`,
  `euro_hy_oas`, `em_corp_oas`, `eem_vol` (they are currently dead code).
- `config/weights.yaml.bak` (173 lines) has the 10-bucket structure with
  rebalanced weights (equity 0.15, credit 0.17, rates 0.12, etc.).
- `config/weights.yaml` (149 lines) has the 9-bucket original with pre-
  rebalance weights (equity 0.18, credit 0.20, rates 0.13, etc.).

**Step 0 (do before any other brief):**
1. `cp config/weights.yaml.bak config/weights.yaml`
2. Run `python run_dashboard.py --no-alerts --quiet` once.
3. Verify `data/history.csv`'s newest row has non-empty
   `raw_global_spillover__usd_index` etc.
4. Commit the restored file with a message explaining the revert was caught.
5. **Do not delete `weights.yaml.bak` yet** — Brief 1 will add validation that
   prevents a recurrence, and you want the evidence intact until that ships.

---

## Architectural review — top 5 weaknesses

### 1. No contract between code and config
`scoring.py._fetch_indicator` hardcodes every indicator in a giant if/elif
chain. `weights.yaml` lists its own set. `thresholds.yaml` lists a third. No
validation that the three agree. This is how the 9-vs-10 bucket drift above
went undetected — the system runs fine when they disagree, just with the
wrong model. Brief 1 fixes this by making `weights.yaml` authoritative and
adding startup validation.

### 2. Zero test coverage on statistical primitives
`compute_percentile`, `realized_vol_series`, `yoy_series`, `point_in_time_*`,
`ew_ic`, `block_bootstrap_ci` — all unvalidated. `compute_percentile` has an
off-by-one bug that returns `(n-1)/n * 100` instead of `100.0` when the current
value is the series maximum. These primitives feed every score, backtest, and
recalibration. Brief 2 adds a ~15-test suite that guards them.

### 3. Fetch layer is too trusting of upstream
- `requests.get` has no retries.
- yfinance empty results get caught by the outer scoring try/except and rendered
  as `band="green"` — a failed fetch looks identical to a calm reading.
- Cache mtime is the only staleness check; if FRED silently stops publishing a
  series, the last value serves forever.
- No schema version on cached JSON.
Addressed in Brief 9 (retry/circuit-breaker) and Brief 5 (staleness alerts).

### 4. Composite score has no time-derivative signal
Everything is level-based ("where am I vs 10yr history"). Blind to velocity.
VIX 25 rising from 15 in a week is very different from VIX 25 coasting down
from 30 — the model scores them identically. Rate-of-change typically picks up
regime shifts earlier than level percentiles. Brief 3 adds this.

### 5. Two band-logic systems disagree silently
`indicators[*].band` comes from raw-value thresholds. `indicators[*].score`
comes from percentile rank. They frequently conflict (current dashboard: VIX
at 63rd percentile with `band="green"` because raw 18.89 is below the 20
yellow threshold). Users have no way to know which is authoritative. Pick one
source of truth or explicitly present both as distinct concepts. Called out
in the pre-feature refactor list below.

---

## Prioritized feature roadmap

Ranked by value/effort. Do items 1–2 before any feature work; they make
everything downstream safe.

| # | Brief | Feature | Value | Effort | Depends on |
|---|-------|---------|-------|--------|------------|
| 1 | B1 | Config schema validation + data-driven registry | High | S | Step 0 |
| 2 | B2 | Minimum viable test suite | High | S | — |
| 3 | B3 | Rate-of-change signal layer | High | M | B1, B2 |
| 4 | B4 | Historical events overlay + indicator drill-down | Med-High | M | B1 |
| 5 | B5 | Correlation-breakdown signal | High | M-L | B1, B2 |
| 6 | B6 | Data staleness alerts | High | S | B1 |
| 7 | B7 | Retry + circuit-breaker in fetch layer | Med | S | B2 |
| 8 | B8 | Deescalation alerts + weekly digest | Med | S | — |
| 9 | B9 | News-to-trigger cross-reference | Med | M | B1 |
| 10 | B10 | Regime-aware weighting | High | L | B2, B3 |
| 11 | B11 | Audit log for alerts | Low-Med | S | — |
| 12 | B12 | Provenance stamp on each run | Low | S | B1 |
| 13 | B13 | History pruning/archival | Low | S | — |
| 14 | B14 | Dashboard tooltips — plain-English explanations of every element | High | M | B4 |

Briefs 1–5 are written in full below. Briefs 6–14 are sketched and can be
expanded when the user is ready to pick them up.

---

## Pre-feature refactor (do after Step 0, before briefs)

1. Ship Brief 1 before editing any config file again.
2. Ship Brief 2 before Brief 3 (rate of change depends on history.csv layout
   being stable and tested).
3. After Brief 1 ships and passes, delete `config/weights.yaml.bak` (git is
   the backup, keeping stale configs around is how drift happens).
4. Add a git pre-commit hook script at `.git/hooks/pre-commit` that runs
   `python -c "from src.config import load_config; load_config()"`. One line,
   catches the whole class of drift bugs before they land.
5. Document the score-vs-band distinction in the README, or pick one
   authoritative source. Currently users can't reconcile them.

---

# Implementation briefs

Every brief follows this structure:
- **Problem** — what's broken
- **Design decision** — the approach, with rationale
- **Files to change** — exact paths
- **Edge cases** — things Sonnet might miss
- **Success criteria** — objectively testable
- **Dependencies** — briefs that must ship first

---

## Brief 1 — Config schema validation + data-driven indicator registry

**Dependencies:** Step 0 (restore 10-bucket weights.yaml).

**Problem:** `src/scoring.py._fetch_indicator` hardcodes every indicator in an
if/elif chain. `config/weights.yaml`, `config/thresholds.yaml`, and `scoring.py`
have no enforced contract. When they drift, the system runs anyway with the
wrong model. Already happened once (Step 0 above).

**Design decision:** Make `config/weights.yaml` the authoritative indicator
registry. Each indicator gets a `source:` field describing how to fetch it.
Replace the if/elif chain with a dispatch table keyed on `source.type`. Add a
single `load_config()` that validates everything at startup and aborts on drift.

**Files to change:**

1. **`config/weights.yaml`** — add `source:` to every indicator. Three source
   types:
   ```yaml
   vix:
     label: VIX
     weight: 0.65
     source:
       type: yfinance
       ticker: "^VIX"
     invert: false
     unit: ""

   sp500_1m_vol:
     source:
       type: yfinance
       ticker: "^GSPC"
       transform: realized_vol_series   # optional; applied after fetch

   hy_oas:
     source:
       type: fred
       series_id: "BAMLH0A0HYM2"

   sofr_spread:
     source:
       type: computed
       handler: sofr_spread              # matches a registered handler name

   aaii_bull_bear:
     source:
       type: manual
   ```

2. **New file `src/config.py`**:
   - `ConfigError(Exception)` — raised on any validation failure.
   - `@dataclass(frozen=True) class IndicatorConfig` — label, weight, source,
     invert, unit, manual, scale.
   - `@dataclass(frozen=True) class BucketConfig` — label, weight, indicators
     dict.
   - `@dataclass(frozen=True) class Config` — buckets dict, thresholds dict.
   - `def load_config(weights_path, thresholds_path) -> Config`:
     - Load both YAML files.
     - Validate bucket weights sum to 1.0 (tolerance 1e-6). On failure raise
       `ConfigError("Bucket weights sum to 0.97, expected 1.0 ± 1e-6")`.
     - Validate indicator weights per bucket sum to 1.0 (same tolerance).
     - Validate every indicator has a valid `source` with `type` in
       {`yfinance`, `fred`, `computed`, `manual`}.
     - Validate `source.type == "computed"` entries reference a handler
       registered in `scoring.COMPUTED_HANDLERS`.
     - Validate every entry in `thresholds.yaml` under `indicators:` maps to
       an indicator that exists in weights.yaml. Extra thresholds are an error
       (usually a typo).
     - Validate no indicator key is reused across buckets (currently enforced
       only by chance).
     - Return frozen `Config` object.

3. **`src/scoring.py`** — replace `_fetch_indicator` body with a dispatch
   table:
   ```python
   COMPUTED_HANDLERS = {
       "sofr_spread": _compute_sofr_spread,   # (env, years) -> (raw, series)
       "realized_vol": _compute_realized_vol,
       "yoy": _compute_yoy,
   }

   def _fetch_indicator(key, icfg, env, manual):
       src = icfg.source
       if src["type"] == "manual":
           return float(manual.get(key, 0)), None
       if src["type"] == "yfinance":
           s = fetch.fetch_yfinance_series(src["ticker"], env, years)
           transform = src.get("transform")
           if transform == "realized_vol_series":
               s = ind.realized_vol_series(s)
           return float(s.iloc[-1]), s
       if src["type"] == "fred":
           s = fetch.fetch_fred_series(src["series_id"], env, years)
           scale = float(icfg.scale or 1.0)
           if scale != 1.0:
               s = s * scale
           transform = src.get("transform")
           if transform == "yoy_series":
               s = ind.yoy_series(s)
           return float(s.iloc[-1]), s
       if src["type"] == "computed":
           handler = COMPUTED_HANDLERS[src["handler"]]
           return handler(env, years)
       raise ConfigError(f"Unknown source type: {src['type']}")
   ```

4. **`run_dashboard.py`** — call `load_config()` as first real action after
   `load_dotenv()`. On `ConfigError`, print a friendly message and
   `sys.exit(1)`.

**Edge cases:**
- Backward compat: detect old-format weights (no `source:` field) and raise
  `ConfigError` with a hint pointing to migration. Don't silently fall back.
- Indicators whose scale needs to apply (`jobless_claims`): keep `scale:` as a
  top-level field, not inside `source`. The scale is a presentation concern,
  not a fetch concern.
- Thresholds for manual-only indicators (`aaii_bull_bear`, `iran_trigger`,
  `repo_stress`) — allow them if present, don't require them.
- Float tolerance for weight sums: use `abs(sum - 1.0) < 1e-6`.
- Unicode in YAML: ensure `yaml.safe_load` is used (not `yaml.load`). Already
  is — verify after refactor.

**Success criteria:**
- `pytest tests/test_config.py` passes (see Brief 2).
- Corrupting any field in `weights.yaml` (weight=0.99, missing source, unknown
  source type) causes `python run_dashboard.py` to abort with a specific error
  message naming the offending field.
- Running the dashboard with the current 10-bucket config produces identical
  composite scores to pre-refactor (regression check — snapshot the scoring
  dict before and after).

---

## Brief 2 — Minimum viable test suite

**Dependencies:** None (can ship in parallel with Brief 1 or before).

**Problem:** Zero automated tests. Refactoring is unsafe. Statistical
primitives have known bugs (`compute_percentile` off-by-one).

**Design decision:** Pytest with ~15 targeted tests. Don't chase coverage —
aim for tripwires on the parts that matter most. Tests must run in under 5
seconds, hit no network. Add a GitHub Actions workflow so pushed code is
validated automatically.

**Files to create:**

1. **`tests/__init__.py`** (empty).

2. **`tests/conftest.py`** — shared fixtures:
   - `synthetic_price_series()` — 10yr of daily geometric Brownian motion
     prices, fixed seed.
   - `short_series()` — 5-element series for short-series guards.
   - `known_percentile_series()` — `[1, 2, 3, 4, 5]` for hand-calculable
     percentile tests.
   - `valid_config_dict()` — minimal valid weights/thresholds as dicts.
   - `mock_network(monkeypatch)` — patches `requests.get` and
     `yfinance.download` to raise if called. Tests that need data must use
     fixtures, not real fetches.

3. **`tests/test_indicators.py`** — ~6 tests:
   - `compute_percentile` on `[1,2,3,4,5]` with current=5 returns 100.0
     (catches the off-by-one).
   - `compute_percentile` on `[1,2,3,4,5]` with current=3 returns 40.0.
   - `compute_percentile` on 5-element series returns 50.0 (short-series
     guard kicks in before the off-by-one).
   - `compute_zscore` on constant `[5,5,5,5,5,5,5,5,5,5]` returns 0.0 (no
     division by zero).
   - `realized_vol_series` on zero-return series returns ~0%.
   - `yoy_series` on 13-month series where each month = 1.01 × prior returns
     ~12.68% at index 12.

4. **`tests/test_triggers.py`** — ~4 tests:
   - High-direction: raw above red threshold → band="red".
   - Low-direction (yield curve `direction: low`): raw below red → band="red".
   - raw=None → band="green" (not a crash).
   - Composite band resolution: `red=3, orange=0, composite=40` → "red"
     (3+ reds wins over score).
   - Composite band resolution: `red=0, orange=0, composite=75` → "red"
     (score ≥ 70 wins).

5. **`tests/test_scoring.py`** — ~3 tests:
   - Mock `_fetch_indicator` to return fixed (raw, series) pairs. Run
     `compute_composite` with a minimal 2-bucket config. Assert composite
     matches hand-calculated weighted average.
   - Test that if one indicator raises, its error gets caught, score defaults
     to 50.0, error appears in `scoring["errors"]`, and bucket computation
     continues with remaining indicators.
   - Test `invert=true`: mock an indicator to 80th percentile, assert the
     score stored is 20.

6. **`tests/test_config.py`** (pair with Brief 1):
   - Valid config loads without error, returns `Config` dataclass.
   - Bucket weights summing to 0.97 → `ConfigError` with "sum" in message.
   - Missing `source` on an indicator → `ConfigError` naming the indicator.
   - Threshold referencing nonexistent indicator → `ConfigError`.
   - Indicator key reused across buckets → `ConfigError`.

7. **`tests/test_smoke.py`** — 1 end-to-end test:
   - Mock all network calls.
   - Pass the actual current `config/weights.yaml` and `config/thresholds.yaml`
     to `compute_composite`.
   - Assert result has keys `composite`, `composite_band`, `buckets`,
     `errors`.
   - Assert `0 <= composite <= 100`.
   - Assert every bucket in weights.yaml appears in
     `result["buckets"]`.

8. **`.github/workflows/tests.yml`**:
   ```yaml
   name: tests
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: { python-version: "3.11" }
         - run: pip install -r requirements.txt pytest pytest-mock
         - run: pytest -q
   ```

9. **`requirements.txt`** — add `pytest`, `pytest-mock`.

**Edge cases:**
- Windows-safe paths: use `tmp_path` fixture, `Path(__file__).parent`, never
  raw `/` or `\\`.
- Deterministic random: `np.random.seed(42)` or pass seed to generators.
- Don't import from `src/` via relative paths; the `sys.path.insert(0, ...)`
  in the existing codebase works, but tests should use a `conftest.py`
  that adds the project root.
- `mock_network` must fail loudly on accidental real network access — catches
  the class of bug where a test silently hits production.

**Success criteria:**
- `pytest -q` from project root passes in < 5 seconds.
- Deliberately breaking `compute_percentile` (e.g. replace `<` with `<=`)
  causes a test failure that names the indicators test.
- GitHub Actions workflow runs and passes on push.

---

## Brief 3 — Rate-of-change signal layer

**Dependencies:** Briefs 1 and 2.

**Problem:** Model is entirely level-based. A composite of 50 rising from 30
over a week is treated identically to a composite of 50 falling from 70. Rate
of change picks up regime shifts earlier than level percentiles; the current
model is blind to this.

**Design decision:** Add an auxiliary "momentum" layer computed from the
composite history. Do NOT fold it into the composite score itself — that
would change the model's meaning and invalidate the backtest. Surface it as
a separate number on the dashboard with its own alert rule.

**Files to change:**

1. **`src/history.py`** — add:
   ```python
   def compute_composite_momentum(history: pd.DataFrame) -> dict:
       """
       Returns a dict with:
         velocity_7d:  composite[today] - composite[today-7d]  (None if <8 rows)
         velocity_30d: composite[today] - composite[today-30d] (None if <31 rows)
         acceleration_7d: velocity_7d - previous 7d's velocity (None if <15 rows)
         regime: one of 'accelerating_up', 'decelerating_up',
                 'accelerating_down', 'decelerating_down', 'flat', 'insufficient'
       All deltas are in composite-score points (0–100 scale).
       """
   ```

   Implementation notes:
   - Dedupe: if history has multiple rows with same date (multiple runs/day),
     keep the last (chronologically) per calendar day before computing deltas.
   - Use calendar days, not row indices — history may have gaps.
   - `regime = 'flat'` when `abs(velocity_7d) < 3` (points).
   - `regime` cases:
     - velocity_7d > 3 AND acceleration_7d > 0 → accelerating_up
     - velocity_7d > 3 AND acceleration_7d <= 0 → decelerating_up
     - velocity_7d < -3 AND acceleration_7d < 0 → accelerating_down
     - velocity_7d < -3 AND acceleration_7d >= 0 → decelerating_down

2. **`src/dashboard.py`** — small momentum indicator inside the composite
   card, under the band label:
   ```
   ORANGE ↑ +8 pts / 7d (accelerating)
   ```
   - Arrow: ↑ for positive, ↓ for negative, → for flat.
   - Color: match the direction semantics (red = rising stress, green =
     falling).
   - If momentum data insufficient, render "— (need 8+ days)".

3. **`src/alerts.py`** — new trigger inside `send_alerts`:
   ```python
   # 4. Rapid escalation without band change
   mom = compute_composite_momentum(history)
   if mom["velocity_7d"] is not None and mom["velocity_7d"] >= 10 \
      and cur_band in ("yellow", "orange"):
       state_key = f"rapid_rise_{cur_band}"
       if state_key not in prev.get("rapid_rise_alerts", []):
           messages.append(
               f"RAPID RISE: composite +{mom['velocity_7d']:.0f} pts in 7 days "
               f"({mom['regime']}). Watch for imminent band escalation."
           )
   ```
   - Persist `rapid_rise_alerts` in alert_state.json keyed by band, so you get
     one alert per band (not daily).
   - Reset `rapid_rise_alerts` when composite band changes.

**Edge cases:**
- History with <8 rows: return all-None momentum, dashboard shows placeholder
  text. No crash.
- Multiple runs same day: dedupe to last before computing deltas.
- Weekends/holidays when FRED doesn't publish: calendar-day delta still works;
  composite may be stable, velocity near zero, fine.
- Composite is already clipped to [0, 100], so velocity is bounded to
  [-100, +100]. No need for further clipping.

**Success criteria:**
- `pytest tests/test_history.py::test_compute_composite_momentum` covers:
  - Insufficient rows → all None.
  - Flat composite history → velocity_7d=0, regime=flat.
  - Linearly rising history (+5/day) → velocity_7d=35, regime depends on
    acceleration (should be decelerating_up from const velocity).
- Dashboard renders the momentum line even on day 1 (placeholder text).
- After 8+ days of data, momentum shows real values.
- Synthetic test: rapidly rising composite (mock history with +15 in a week)
  + yellow band + no prior rapid_rise alert → alert fires.

---

## Brief 4 — Historical events overlay + indicator drill-down

**Dependencies:** Brief 1 (for config-driven indicator iteration).

**Problem:** The 90-day trend chart has no context. Users can't tell if 50 is
historically normal or whether they're near past crisis levels. Individual
indicators have no detail view — you can't see a 10yr VIX chart.

**Design decision:** Two parts. Part A (events overlay) is an hour of work and
a huge UX win. Part B (drill-down) takes half a day and makes the dashboard
self-contained for research.

### Part A — Events overlay

**Files to change:**

1. **New file `config/events.yaml`**:
   ```yaml
   # Significant market events for historical context overlays.
   events:
     - date: 2008-09-15
       label: "Lehman"
     - date: 2011-08-08
       label: "US downgrade"
     - date: 2020-03-16
       label: "COVID"
     - date: 2022-09-28
       label: "UK gilts"
     - date: 2023-03-10
       label: "SVB"
   ```

2. **`src/history.py::build_trend_svg`** — accept `events: list[dict] | None`
   parameter. For each event whose date falls within the visible window,
   render:
   - Vertical dashed line at the event's x position.
   - Rotated label (`transform="rotate(-45)"`) at the top of the line,
     color `#8b949e`, font-size 10.

3. **`src/dashboard.py`** — load `config/events.yaml`, pass events into
   `build_trend_svg`.

### Part B — Indicator drill-down

**Files to create:**

1. **`src/indicator_detail.py`** — generates an HTML fragment per indicator:
   ```python
   def build_indicator_detail(
       ikey: str,
       icfg: IndicatorConfig,
       series: pd.Series,   # 10yr history
       threshold: dict | None,
   ) -> str:
       """Return HTML <details> block with 10yr chart + stats."""
   ```
   - Inline SVG chart, same pattern as `build_trend_svg` but:
     - 10yr x-axis with yearly tick labels.
     - Horizontal dashed lines at yellow/orange/red thresholds when applicable.
     - Current value marker + value label.
   - Summary stats table below the chart:
     - Current value
     - Current percentile (from scoring result)
     - 10yr min / max / median
     - Last update date

**Files to change:**

2. **`src/dashboard.py`**:
   - For each indicator, generate the detail fragment wrapped in
     `<details><summary>{label}</summary>{fragment}</details>`.
   - In the existing bucket table, change the label cell to be clickable
     (plain `<a href="#{ikey}_detail">` + the detail block gets `id="{ikey}_detail"`).
   - Insert the detail fragments in a new section below the bucket grid:
     "Indicator details" collapsed by default.

**Data access:** `compute_composite` needs to pass the raw series through to
the dashboard, not just the single current value. Easiest: add a new key
`scoring["buckets"][bkey]["indicators"][ikey]["_series_last_90"]` — a trimmed
90-point list of (date, value) pairs. Don't include the full 10yr because
history.csv doesn't store it — fetch it on the fly from the cache during
dashboard render.

Alternative (cleaner): write a helper `fetch.load_cached_series(key)` that
pulls straight from `data/cache/{key}.json` without the TTL check (we already
just ran fetch, so cache is fresh). Dashboard calls this per indicator.

**Edge cases:**
- Indicators with `manual: true` have no cached series → skip the chart,
  show only current value + unit.
- `source.type == "computed"` indicators (sofr_spread, cpi_yoy): the
  _computed_ series isn't cached, only the underlying raw series. For drill-
  down, recompute on the fly using the same helpers in `_fetch_indicator`.
- Events older than 10yr: filter to visible window before rendering.
- `<details>` is pure HTML — works on GitHub Pages, works on mobile Safari.
  No JS needed.
- Keep the detail blocks inline in one HTML file; don't try per-indicator
  separate pages (breaks the static-hosting simplicity).

**Success criteria:**
- Current dashboard renders an event overlay line on the 90-day trend for any
  event in the visible window.
- Clicking an indicator label expands a detail block showing a 10yr chart
  with threshold lines.
- No JS required; works on GitHub Pages and iPhone Safari.

---

## Brief 5 — Correlation-breakdown signal

**Dependencies:** Briefs 1 and 2.

**Problem:** Real crises are characterized by correlation regime shifts — all
risk assets move together. The current composite averages bucket scores;
it cannot detect whether buckets are moving in lockstep (risk-off crisis) or
decoupling (regime change). This is information the current model ignores.

**Design decision:** Compute rolling pairwise Spearman correlation across the
10 bucket score time series. Report a single scalar "cross-bucket correlation"
on the dashboard. Fire a Pushover alert when it crosses from normal into
"crisis synchronous" and stays there for 3+ consecutive days (persistence
gate to avoid noise).

**Files to change:**

1. **`src/history.py`** — new functions:
   ```python
   def cross_bucket_correlation(history: pd.DataFrame, window_days: int = 30) -> float | None:
       """
       Mean absolute pairwise Spearman correlation across all bucket_* score
       columns over the last window_days.
       Returns None if insufficient data, else a float in [0, 1].
       """

   def correlation_regime(value: float | None) -> str:
       """Returns 'decorrelated' | 'normal' | 'crisis_synchronous' | 'insufficient'."""
   ```
   Thresholds:
   - value < 0.30 → decorrelated
   - 0.30 ≤ value < 0.60 → normal
   - value ≥ 0.60 → crisis_synchronous

   Implementation:
   - Dedupe history to one row per calendar day (keep latest).
   - Filter to last `window_days` rows.
   - Select all `bucket_*` columns. Drop columns with >50% NaN. Drop
     near-constant columns (std < 0.5 points) — typically the manual-only
     sentiment bucket.
   - `scipy.stats.spearmanr(df.values)` returns a matrix if given 2D array.
     Take the upper triangle (exclude diagonal), take absolute values, mean
     them.

2. **`src/dashboard.py`** — new small card near Model Performance:
   ```html
   <div class="card">
     <h2>Cross-bucket correlation (30d)</h2>
     <div>0.42 <span class="badge">NORMAL</span></div>
     <p class="score-sub">Mean absolute correlation across 10 buckets.
     &lt;0.30 decorrelated, 0.30–0.60 normal, ≥0.60 crisis.</p>
   </div>
   ```
   Use the existing `_BAND_COLOR` palette: decorrelated→green,
   normal→yellow-ish neutral, crisis_synchronous→red.

3. **`src/alerts.py`** — new trigger:
   ```python
   # 5. Sustained crisis-synchronous correlation
   corr = cross_bucket_correlation(history, window_days=30)
   regime = correlation_regime(corr)
   state["corr_regime_streak"] = state.get("corr_regime_streak", 0)
   if regime == "crisis_synchronous":
       state["corr_regime_streak"] += 1
   else:
       state["corr_regime_streak"] = 0
   if state["corr_regime_streak"] == 3:   # fires once, on the 3rd day
       messages.append(
           f"CROSS-BUCKET CORRELATION ELEVATED: {corr:.2f} (3 days sustained). "
           f"Buckets moving in lockstep — typical pre-crisis or risk-off signature."
       )
   ```
   Persist `corr_regime_streak` in alert_state.json.

**Edge cases:**
- First ~30 days of history: return None, show "insufficient" on dashboard,
  skip the alert logic.
- Manual-only sentiment bucket is usually flat between manual updates → filter
  out via the std threshold.
- Scipy `spearmanr` with 2D array: double-check whether it returns a matrix
  or a tuple. As of scipy 1.11+, it returns a `SignificanceResult` with
  `.statistic` being the matrix. Sonnet should write a test for this.
- NaN handling: use `nan_policy='omit'` in spearmanr.
- Don't count the diagonal (which is 1.0 by definition) — use upper-triangle
  indices.

**Success criteria:**
- `pytest tests/test_history.py::test_cross_bucket_correlation` covers:
  - Insufficient rows → None.
  - Fully uncorrelated synthetic buckets (independent random walks) →
    correlation near 0.
  - Fully synchronous buckets (all identical) → correlation = 1.0.
- Dashboard renders the card with a real number after 30+ days history.
- Synthetic test: inject 3 consecutive days of history where correlation >
  0.70 → streak counter hits 3 → alert message appears in `messages`.

---

## Briefs 6–13 (sketches — expand when ready to execute)

### Brief 6 — Data staleness alerts
Per-indicator "last observation date". If gap > N days (configurable per
series type — FRED daily 3d, FRED weekly 10d, FRED monthly 40d), add to
`scoring.errors` AND send a Pushover warning on first occurrence. New file
`config/series_cadence.yaml`.

### Brief 7 — Retry + circuit-breaker in fetch layer
Wrap `requests.get` and `yf.download` with exponential backoff (tenacity or
hand-rolled — 3 retries, 1s/4s/16s). On persistent failure, fall back to
stale cache with a warning surfaced to the dashboard.

### Brief 8 — Deescalation alerts + weekly digest
Mirror of the escalation alert: fire when composite band improves. Weekly
digest on Mondays summarizing the previous week's range, biggest movers,
alerts sent.

### Brief 9 — News-to-trigger cross-reference
When an alert fires, filter the morning's news headlines for keywords related
to the triggering indicator. Pass the filtered subset into the Haiku context
prompt. Requires a keyword→indicator map in config.

### Brief 10 — Regime-aware weighting (split into 10A / 10B / 10C)
Original sketch: run different bucket weights based on VIX tercile. Opus
expanded the design 2026-04-25 — the work is split into three sequential
briefs to checkpoint cleanly. See **Brief 10A**, **Brief 10B**, **Brief 10C**
at the bottom of this file.

### Brief 11 — Audit log for alerts
Persist every alert (title + body + Haiku response + timestamp) to
`data/alert_log.jsonl`. Makes it possible to review Haiku hallucinations and
alert volume over time.

### Brief 12 — Provenance stamp on each run
Add columns `weights_hash`, `code_sha` to history.csv. Lets you tell, when a
score changes unexpectedly, whether the data changed or the calculation did.

### Brief 13 — History pruning/archival
Current history.csv grows forever. Cap at ~2 years; archive older rows into
`data/history_archive.parquet`. Backtest engine already uses separate cache,
so no impact on it.

### Brief 14 — Dashboard tooltips (plain-English explanations of every element)

**Dependencies:** Brief 4B (indicator drill-down ships first — tooltips build
on that infrastructure).

**Problem:** Many indicators are opaque even to finance professionals. "SOFR
Spread to EFFR" or "NFCI" mean nothing without context. The dashboard gives
numbers and bands but no explanation of what each thing measures, why it
matters, or how to interpret it alongside the rest of the model.

**Design decision:** CSS-only hover tooltips — no JavaScript, works on static
GitHub Pages. Every tappable/hoverable element gets a `title` attribute (for
mobile long-press and screen readers) AND a CSS `:hover` tooltip bubble (for
desktop). Content is authored in `config/tooltips.yaml` so it can be updated
without touching Python code.

**Files to create:**

1. **`config/tooltips.yaml`** — plain-English descriptions for every element:
   ```yaml
   composite:
     title: "Composite Stress Score"
     what: "A weighted average of all 10 buckets, scored 0–100. Higher = more stress."
     interpret: "Under 30 is calm. 30–50 is elevated but normal. Above 50 means at
       least one area of the market is flashing warning signs. Above 70 is rare and
       serious — historically precedes significant drawdowns within 3–6 months."
     why: "No single indicator predicts crashes reliably. This composite synthesizes
       credit, volatility, rates, funding, commodities, and global signals into one
       number so you can scan quickly without reading 20 charts."

   bands:
     green: "Below 30: calm conditions. History suggests low near-term drawdown risk."
     yellow: "30–50: elevated. Worth monitoring but not actionable on its own."
     orange: "50–70: stressed. At least one bucket is firing warnings. Consider
       reducing risk in the affected area."
     red: "Above 70: high stress. Historically associated with elevated drawdown risk
       in the following 30–90 days. Review your positions."

   buckets:
     equity_volatility:
       what: "Measures fear and uncertainty in the stock market."
       why: "Spikes in VIX and realized vol are early warning signs of panic selling.
         High equity vol often precedes or accompanies credit and funding stress."
     credit_spreads:
       what: "Measures how much extra yield investors demand to hold corporate bonds
         over risk-free Treasuries."
       why: "Widening spreads mean lenders are getting nervous about default risk.
         Historically, HY spread blowouts precede recessions by 6–12 months."
     # ... one entry per bucket ...

   indicators:
     vix:
       what: "The CBOE Volatility Index — the market's expectation of S&P 500 volatility
         over the next 30 days, derived from options prices."
       interpret: "Below 15 = calm. 15–25 = normal. 25–35 = elevated fear.
         Above 35 = panic. The all-time high was ~89 during the 2008 crisis."
       why: "VIX is the market's single most-watched fear gauge. Sustained elevated
         VIX means institutions are paying up to hedge, which tends to be
         self-reinforcing."
     sofr_spread:
       what: "The gap between SOFR (what banks actually charge each other overnight)
         and the Fed's target rate (EFFR). Measured in basis points (0.01%)."
       interpret: "Near zero is normal. A spread above 10–15 bps suggests banks are
         charging each other more than the Fed's benchmark — a sign of liquidity
         stress in the overnight funding market."
       why: "A precursor to 2008 was the LIBOR-OIS spread blowing out. SOFR spread
         is the modern equivalent. Small moves matter: a 20 bps spread is a
         loud warning."
     # ... one entry per indicator ...
   ```

2. **`src/dashboard.py`** — load tooltips.yaml, add tooltip markup:
   - Composite score card: wrap the number and band in a `<span>` with CSS
     tooltip showing `what` + `interpret`.
   - Each band badge: tooltip showing the band description.
   - Each bucket header: tooltip with bucket `what` + `why`.
   - Each indicator row: tooltip with indicator `what` + `interpret` + `why`.
   - Percentile column: persistent small note "Percentile rank vs 10yr history"
     on first row of each bucket (not per-row — clutters mobile).

3. **CSS additions in `_CSS`**:
   ```css
   .tip{position:relative;cursor:help}
   .tip::after{content:attr(data-tip);position:absolute;left:0;top:100%;
     background:#1c2128;color:#c9d1d9;padding:8px 12px;border-radius:6px;
     border:1px solid #30363d;font-size:.78rem;line-height:1.5;width:280px;
     z-index:100;white-space:normal;display:none;pointer-events:none}
   .tip:hover::after,.tip:focus::after{display:block}
   ```
   CSS-only, no JS. `data-tip` attribute holds the tooltip text.
   For mobile: add `title` attribute with the same text (long-press on iOS
   shows the title as a native tooltip).

**Content principles for tooltips.yaml:**
- Every entry answers three questions: what does this measure, how do I
  interpret the current reading, and why should I care.
- Use plain English. No acronyms without expansion on first use.
- Include historical anchors: "During 2008, VIX hit 89." "A SOFR spread
  above 20 bps is rare — last seen in Sept 2019."
- Keep each tooltip under 300 characters for the CSS bubble. Put the longer
  version in the drill-down detail page (Brief 4B).
- Cross-context notes: if VIX and HY spreads are both elevated, that's more
  serious than either alone. The tooltip for VIX should mention this.

**Edge cases:**
- Missing tooltip key: dashboard renders without the tooltip (no crash).
  Log a warning to the errors list so missing entries are visible.
- Mobile `data-tip` CSS trick: works on iOS Safari and Chrome Android via
  `:focus` pseudo-class when the element is tapped. The `tabindex="0"` on
  the `.tip` span enables this.
- GitHub Pages: pure CSS, no JS needed, static hosting compatible.
- Long tooltip text: cap at 280px wide with `white-space:normal`. Long
  entries will wrap. Test on mobile (375px viewport).

**Success criteria:**
- Hovering over every indicator label shows a tooltip with `what`,
  `interpret`, and `why` content.
- Works on iPhone Safari (tap → tooltip shows via `:focus` + `tabindex`).
- No JS, works on GitHub Pages.
- All 10 buckets and all ~22 indicators have tooltip entries in
  tooltips.yaml (no missing keys).
- A missing key in tooltips.yaml produces a warning in the errors section,
  not a crash.

---

## Brief 15 — Backtest signal-quality card + link to full report

**Dependencies:** existing `src/evaluation.py` (uses `build_forward_drawdown`,
`spearman_ic`), `src/alerts.py::get_postmortem_stats` (already shipped), and
`data/history.csv` (at least ~60 rows to be meaningful). The full
`output/backtest_report.html` must already exist on disk (generated via
`python -m src.backtest_report`). Cached `^GSPC` series in `data/cache/`
(populated every run via `spx_200dma_distance` indicator).

**Problem:** The project has a comprehensive 112 KB statistical backtest
report at `output/backtest_report.html` — nobody on the dashboard knows it
exists because nothing links to it. The main dashboard also gives no signal of
**recent** model quality: has this composite actually been right lately, or
has it drifted? A user glancing at today's score at 7:30 AM has no calibration
context.

A second, quieter problem: TODO.md previously claimed "Phase 4 — Live
performance tracking (rolling IC + degradation on dashboard)" shipped.
A `grep` on `output/dashboard.html` shows zero backtest content. That phase
did not actually land on the dashboard — only the offline report shipped. This
brief closes the gap.

**Design decision — opinionated scope calls:**

1. **One card, not a page port.** The comprehensive report is for monthly
   review; the main dashboard is for daily glance. Render a compact card plus
   a prominent link to the full report. Do not try to cram tables, per-target
   IC, or bootstrap CIs onto the main dashboard.
2. **Two metrics only on the card** (plus a one-line verdict):
   - **Rolling composite IC (252 trading days)** — Spearman correlation between
     daily composite and 21-day forward SPX drawdown over the last year of
     `history.csv`.
   - **Recent alert hit rate (60 calendar days)** — reuse the existing
     `get_postmortem_stats(days=60)` from `src/alerts.py` (currently only used
     in the Monday digest — surface it daily).
   The TODO had listed four candidate metrics (lead time, false-positive rate,
   SPX drawdown overlay). **Dropped on purpose.** Lead time and FP rate need
   event matching that belongs in the full report; a price overlay on the
   90-day composite trend chart would visually fight the existing event
   overlay at morning-glance cognitive load.
3. **Absolute thresholds for the verdict**, no dynamic baseline:
   - IC ≥ 0.15 → **Tracking** (green)
   - 0.05 ≤ IC < 0.15 → **Weak signal** (yellow)
   - IC < 0.05 → **Miscalibrated** (orange/red)
   - insufficient data (< 60 history rows) → **Insufficient history** (neutral)
   Thresholds are justifiable from the academic literature on financial
   forecasting ICs (0.05–0.10 is industry-standard weak, 0.15+ is strong).
4. **Reuse `build_forward_drawdown` and `spearman_ic` from evaluation.py**
   verbatim. Do not write a parallel IC function — divergence with the backtest
   report is the failure mode to avoid.
5. **Target horizon is 21 trading days forward SPX drawdown** — that matches
   the classic 1-month horizon used in the backtest report's headline table.
6. **Sign convention.** `build_forward_drawdown` returns positive values in
   [0, 1] where higher = worse drawdown. High composite should predict high
   drawdown → Spearman IC is **positive** when the model works. No sign flip
   needed; the verdict text reads naturally.

**Files to change:**

1. **`src/evaluation.py`** — add one new helper near the existing IC functions:
   ```python
   def rolling_composite_ic(
       history: pd.DataFrame,
       spx: pd.Series,
       window_days: int = 252,
       horizon_days: int = 21,
   ) -> dict:
       """
       Compute Spearman IC of composite vs forward SPX drawdown over the most
       recent window_days of history.csv.

       Returns dict:
         {
           "ic": float | None,          # None if insufficient data
           "n_obs": int,                # number of (composite, target) pairs used
           "horizon_days": int,         # echo for display
           "window_days": int,          # echo for display
         }

       Reuses build_forward_drawdown() and spearman_ic() — do not duplicate.
       """
   ```
   Implementation:
   - Convert `history["timestamp"]` → DatetimeIndex, dedupe to one row per day
     (keep latest), set as index.
   - Extract `composite` column → pd.Series.
   - Reindex both `composite` and `spx` to a common business-day index
     (`spx.reindex(composite.index, method="ffill")`) — the dashboard runs
     daily but SPX has weekend gaps.
   - Build target: `build_forward_drawdown(spx_aligned, horizon_days)`.
   - Slice both to the most recent `window_days` rows.
   - Drop rows where either is NaN (the last `horizon_days` of target will be
     NaN because future isn't known — intended).
   - If fewer than 30 aligned non-NaN pairs remain, return `{"ic": None, ...}`.
   - Otherwise call `spearman_ic(composite_slice, target_slice)`.

2. **`src/dashboard.py`** — two additions:

   a. New card builder:
   ```python
   def _build_signal_quality_card(
       history: "pd.DataFrame",
       env: dict,
       alert_log_stats: dict,
   ) -> str:
       """
       Compact card with rolling composite IC + recent alert hit rate.
       Returns "" if backtest_report.html does not exist or history too short.
       """
   ```
   - Lazy-import `rolling_composite_ic` from `src.evaluation` and
     `fetch_yfinance_series` from `src.fetch`. Wrap the whole thing in
     try/except so a computation failure degrades to an empty string (the
     card is optional; never break the dashboard).
   - Fetch SPX (`fetch_yfinance_series("^GSPC", env, years=2)` — 2 years is
     enough for a 252-day IC window; keeps the fetch cheap).
   - Compute IC via `rolling_composite_ic(history, spx)`.
   - Read `alert_log_stats = get_postmortem_stats(days=60)` (pass in — caller
     already has it from alerts subsystem; see step 3 below).
   - If `backtest_report.html` exists at `output/backtest_report.html`,
     include a "View full backtest report →" link; the link target is
     `backtest_report.html` (relative path — works locally and on GitHub Pages
     if both files are copied to /docs).
   - Layout: match the compact cross-bucket correlation card style (`.card`
     with `display:flex`, two numeric panels side-by-side, verdict under them,
     link at the bottom right). Use the existing `_BAND_COLOR` palette for the
     verdict color.

   b. Wire into `write_dashboard(...)`:
   - Add `_build_signal_quality_card` call near the other cards. Place it
     directly **below the cross-bucket correlation card** — they're the two
     "model meta" cards and belong together.
   - The function needs access to `env` and to the postmortem stats.
     `write_dashboard` already receives `scoring` and `history`; add a keyword
     arg `signal_quality_stats: dict | None = None` so the caller can pass in
     the pre-computed postmortem dict (avoids re-reading alert_log.jsonl).
   - If the card returns empty string, just omit it — do not reserve space.

3. **`run_dashboard.py`** — wire the data:
   - After the existing `score_past_alerts(history)` call, add:
     ```python
     from src.alerts import get_postmortem_stats
     pm_stats = get_postmortem_stats(days=60)
     ```
   - In the `write_dashboard(...)` call, pass `signal_quality_stats=pm_stats`
     and `env=env`. (write_dashboard currently doesn't take env — extend
     signature with `env: dict | None = None`.)
   - In the `--publish` path, copy `output/backtest_report.html` to
     `_genai_tmp/docs/backtest_report.html` alongside `index.html` so the link
     works on GitHub Pages. Do this only if the source file exists
     (`backtest_report.html.exists()`) so the publish step never fails because
     the report hasn't been generated.

4. **`tests/test_rolling_ic.py`** (new) — two tests:
   - `test_rolling_composite_ic_perfect_predictor`: build a synthetic history
     where composite is a noise-free monotone function of realised forward
     drawdown (e.g., composite[t] = 100 * drawdown[t+21]) → IC should be ≈ 1.0.
   - `test_rolling_composite_ic_insufficient_data`: pass in a 10-row
     history → expect `ic=None` and `n_obs < 30`.
   - Do NOT test with real network calls. Build SPX via `pd.Series(np.cumsum(np.random.randn(400)) + 100, index=pd.date_range("2024-01-01", periods=400, freq="B"))`.

**Edge cases:**

- `history.csv` has fewer than 60 rows → card renders with verdict
  "Insufficient history" and no IC number. Do not hide the card entirely;
  its presence tells the user the metric exists and is waiting to mature.
- SPX fetch fails (network dead, yfinance rate-limited) → card returns "";
  never break the dashboard on network failure.
- `output/backtest_report.html` missing → still render the card, just omit
  the "View full report" link.
- The last `horizon_days` of history have NaN targets by construction — the
  function must drop them before computing IC. Otherwise the IC is computed
  over garbage.
- Multiple history rows per day (the dashboard can be re-run). Dedupe to one
  row per date (keep latest) before aligning with SPX.
- If SPX and history diverge by timezone (history is ISO timestamps, SPX is
  trading-day dates) → normalize both to `.normalize()` (strip time component)
  before joining.
- `alert_log.jsonl` empty or missing → `get_postmortem_stats` already returns
  `{}` safely; the card handles that ("No alerts scored yet").

**Success criteria:**

- `pytest tests/test_rolling_ic.py` — both tests green.
- Full suite still 181+ passing (the existing alert tests must not regress).
- `python run_dashboard.py --no-alerts --quiet` runs clean; generated
  `output/dashboard.html` contains a new card titled "Model Calibration" (or
  "Signal Quality" — Sonnet picks one and sticks with it) placed immediately
  after the cross-bucket correlation card, with:
  - A labelled IC number (e.g., "IC: 0.18").
  - A labelled hit-rate line (e.g., "Recent alerts: 3/5 still elevated at T+7").
  - A coloured verdict badge.
  - A "View full backtest report →" link pointing to `backtest_report.html`
    (only if that file exists).
- Open the link; it loads the existing report in a new tab.
- Verify the IC number is in the same ballpark as the 21-day horizon cell in
  `backtest_report.html` (they won't match exactly — the card uses the last
  252 rows only, the full report uses the whole history — but they should be
  within ±0.1 of each other; if not, the alignment logic is wrong).
- `--publish` copies both files to `/docs`.

**Non-goals (explicitly out of scope for this brief):**

- Rolling IC time-series chart. The card is a point estimate, not a trend.
  If Ian wants a trend chart of IC over time, that's a follow-up brief.
- Per-indicator IC display on the main dashboard. Already in the full report;
  no need to duplicate.
- Any change to `backtest_report.py` itself. The full report stays as-is.
- Regenerating the backtest when the dashboard runs. The backtest is a
  separate, manual cadence (quarterly at most); nothing here should trigger
  it.

---

## Recommended execution order

1. **Step 0** — restore weights.yaml from .bak (15 min, do first).
2. **Brief 2** — test suite (half day). Ship even before Brief 1, so Brief 1's
   changes are tested.
3. **Brief 1** — config validation + data-driven registry (half day).
4. **Brief 4 Part A** — events overlay (1 hour, morale win).
5. **Brief 3** — rate of change (half day).
6. **Brief 6** — data staleness (half day).
7. **Brief 4 Part B** — indicator drill-down (half day).
8. **Brief 5** — correlation breakdown (half day).
9. Briefs 7–13 based on priority at the time.

Rough budget: 3 days of Sonnet work for Briefs 1–5. Budget another 2 days if
you want through Brief 8.

---

## Brief 16 — VIX term-structure indicator

**Dependencies:** None. yfinance ticker `^VIX3M` is live (verified 2026-04-25,
returns ~15 years of history). Existing `equity_volatility` bucket has room.

**Problem:** The existing `equity_volatility` bucket measures the *level* of
expected vol (VIX) and the *recent realised* vol (sp500_1m_vol). Neither tells
you whether the market expects current vol to **persist or revert**. The VIX
term structure — specifically VIX (30-day) vs VIX3M (90-day) — answers that.

When VIX > VIX3M (backwardated curve), the market is pricing immediate stress
that's expected to fade in 90 days. Backwardation has preceded most major
equity events (Aug 2015 China devaluation, Feb 2018 Volmageddon, March 2020
COVID, Sept 2022 rate shock). When VIX < VIX3M (contango — the normal state),
front-month vol is below longer-dated, meaning markets expect calm.

This signal is orthogonal to raw VIX level. Two days both with VIX = 25:
- Contango (VIX/VIX3M = 0.92): market pricing reversion, mean-reverting trade
- Backwardation (VIX/VIX3M = 1.10): panic now, expect persistence

**Design decisions — opinionated and locked:**

1. **Use the VIX/VIX3M ratio**, not VIX9D/VIX. The 30-day vs 90-day pair is the
   industry standard (used in academic literature on VIX ETP rolls, e.g.
   VXX/VXZ). VIX9D/VIX is noisier and less studied. Ratio (not difference) so
   the signal is scale-invariant — works the same whether VIX = 12 or 50.
2. **Lives in `equity_volatility`**, not `rates_curve`. It's a direct
   measurement of equity option-implied vol; rates_curve already has MOVE
   (the rates analogue).
3. **Type: `computed`** with handler `vix_term_structure`. Two yfinance fetches
   (^VIX, ^VIX3M), aligned and divided. Pattern matches existing handlers like
   `_handler_sofr_spread`.
4. **`invert: false`** — higher ratio = more stress (backwardation). Percentile
   ranking handles the fact that contango is the historical norm.
5. **Bucket weight redistribution:**
   - **Old:** vix 0.65, sp500_1m_vol 0.35
   - **New:** vix 0.50, vix_term_structure 0.25, sp500_1m_vol 0.25
   - Rationale: VIX stays dominant (it's the level signal), term structure gets
     meaningful but not dominant weight, realized vol slightly de-weighted but
     still material as a "actual vs implied" cross-check.
6. **Bucket weight in composite stays at 0.13.** Do not re-tune cross-bucket
   weights — that's recalibrate.py's job.
7. **Threshold bands** (raw VIX/VIX3M ratio):
   - `direction: high`
   - yellow: 0.95 (flat curve — front-month catching up to longer-dated)
   - orange: 1.00 (mild backwardation — first warning)
   - red: 1.05 (sustained backwardation — historically rare, ~top 5% of days)
8. **No overlap with shock-type classification.** Shock-type uses composite
   velocity. Term structure is a per-indicator level signal. They're
   complementary, not redundant.

**Files to change:**

1. **`config/weights.yaml`** — `equity_volatility` block:
   ```yaml
   equity_volatility:
     label: Equity Volatility
     weight: 0.13
     indicators:
       vix:
         label: VIX
         weight: 0.50
         source: { type: yfinance, ticker: "^VIX" }
         invert: false
         unit: ""
       vix_term_structure:
         label: "VIX Term Structure (30d/90d)"
         weight: 0.25
         source:
           type: computed
           handler: vix_term_structure
         invert: false
         unit: "ratio"
       sp500_1m_vol:
         label: "S&P 500 1M Realized Vol"
         weight: 0.25
         source:
           type: yfinance
           ticker: "^GSPC"
           transform: realized_vol_series
         invert: false
         unit: "%"
   ```
   Verify weights still sum to 1.0 within the bucket and the cross-bucket sum
   is unchanged.

2. **`src/scoring.py`** — add handler near `_handler_sofr_spread`:
   ```python
   def _handler_vix_term_structure(key, cfg, env, manual, years):
       vix = fetch.fetch_yfinance_series("^VIX", env, years)
       vix3m = fetch.fetch_yfinance_series("^VIX3M", env, years)
       combined = pd.concat([vix.rename("vix"), vix3m.rename("vix3m")], axis=1)
       combined = combined.dropna()
       ratio = combined["vix"] / combined["vix3m"]
       return float(ratio.iloc[-1]), ratio
   ```
   Register in `COMPUTED_HANDLERS`.

3. **`src/config.py`** — add `"vix_term_structure"` to `KNOWN_INDICATOR_KEYS`.

4. **`config/thresholds.yaml`** — add:
   ```yaml
   vix_term_structure:
     direction: high
     yellow: 0.95
     orange: 1.00
     red: 1.05
   ```

5. **`config/tooltips.yaml`** — add under `indicators:`:
   ```yaml
   vix_term_structure:
     tip: "VIX (30-day) divided by VIX3M (90-day). Below ~0.95 = contango (calm — front-month vol cheaper than longer-dated). Above 1.0 = backwardated (front-month panic). Above 1.05 has preceded most major equity events (2015, 2018, 2020, 2022)."
   ```

6. **`tests/test_vix_term_structure.py`** — one focused test:
   - Mock fetch_yfinance_series to return synthetic VIX and VIX3M.
   - Call `_handler_vix_term_structure` and assert ratio matches expectation.
   - Build VIX = [15, 20, 25] and VIX3M = [20, 20, 20] → ratio = [0.75, 1.0, 1.25].
   - Assert returned series matches and last value = 1.25.

**Edge cases:**
- ^VIX3M fetch fails → handler raises, scoring catches, indicator gets fallback
  score 50.0 (existing pattern).
- VIX3M series has weekend gaps that VIX doesn't (or vice versa) → `dropna()`
  after concat handles it. Don't `ffill` — that would invent ratio data.
- Very early in VIX3M history (pre-2008) → series will be shorter; percentile
  computation still works on whatever's available.

**Success criteria:**
- `pytest tests/` passes (184/184 with new test).
- `python run_dashboard.py --no-cache --no-news --no-alerts --quiet` succeeds.
- Dashboard renders the new indicator under equity_volatility with raw value
  ~0.85–1.10 (depends on day) and a band assignment.
- Weights summary on the bucket header shows the new split (vix 50%, term
  structure 25%, realized vol 25%).
- Tooltip renders on hover.

**Non-goals:**
- VIX9D, VXN, VVIX. Considered and rejected — single clean addition is
  better than three competing additions on a morning-glance dashboard.
- A separate "term structure inversion" alert. The existing band system
  (red threshold 1.05) already triggers if it's sustained; no new alert
  type needed.

---

## Brief 10A — Regime classification telemetry (read-only)

**Dependencies:** None. Uses existing VIX series from
`config/weights.yaml::equity_volatility.vix`.

**Problem:** Brief 10's full design (regime-aware weighting) is a 3+ day lift
that touches scoring, backtest, recalibrate, and the dashboard. Shipping it
all at once is too big a checkpoint. Brief 10A introduces *only* the regime
classification — visible on the dashboard and logged to history — without
changing how scoring computes the composite. This lets Ian see how the regime
moves over a few weeks of operation before flipping the switch on weight
adjustment in Brief 10C.

**Design decisions — locked:**

1. **Three regimes**: `low`, `mid`, `high`. Boundaries computed dynamically
   from the trailing 10-year VIX distribution (33rd and 67th percentiles).
   Roughly: low ≤ ~14, mid 14–22, high > ~22 (will drift with the window).
2. **Smoothed input + hysteresis** to prevent flapping at boundaries:
   - Classifier input: 5-day moving average of VIX (`vix.rolling(5).mean()`).
   - Hysteresis: regime *change* requires the smoothed VIX to cross the
     boundary by ≥ 1.0 VIX point. Computed by maintaining the previous
     regime in `data/alert_state.json` and only transitioning when the new
     reading clears the threshold by the buffer.
3. **Live computation**, not from history. The 10-year tercile boundaries are
   computed at every run from the same VIX series the equity_volatility
   bucket uses. No new fetch.
4. **Add to scoring dict**:
   ```python
   {
     "regime": "mid",                    # "low" | "mid" | "high"
     "regime_vix_5dma": 18.4,
     "regime_thresholds": {"low_max": 13.6, "high_min": 21.8},
     "regime_changed": False,            # True if today != yesterday
   }
   ```
5. **History column**: add `regime` (string) to `log_run()` in
   `src/history.py`. Existing rows backfill NaN.
6. **Dashboard display**: small badge in the existing composite card,
   immediately under the `composite_short` line. Format:
   `VIX regime: MID (smoothed VIX 18.4 — boundaries 13.6 / 21.8)`.
   Use existing `_BAND_COLOR`-style palette: low=green, mid=yellow,
   high=orange. (Not red — high VIX regime alone isn't an alert.)
7. **No alert** on regime change in 10A. That's a follow-up if 10C ships.

**Files to change:**

1. **`src/history.py`** — new function `classify_vix_regime(vix_series)` that
   returns the dict above. Pure function — easy to test.
2. **`src/scoring.py`** — call `classify_vix_regime()` after the VIX fetch in
   the equity_volatility bucket loop; merge result into the returned scoring
   dict. Hysteresis state read from `data/alert_state.json` key
   `regime_previous`.
3. **`src/alerts.py`** — extend `_load_state` / `_save_state` to round-trip
   `regime_previous`. No alert dispatch logic changes.
4. **`src/history.py::log_run()`** — add `"regime": scoring.get("regime")`
   to the row dict.
5. **`src/dashboard.py`** — render the regime badge in the composite card
   block (near the `composite_short` rendering at lines ~470–490). Reuse
   the `_tip` helper if a tooltip is desired.
6. **`config/tooltips.yaml`** — add:
   ```yaml
   regime:
     tip: "Current VIX regime, classified by trailing 10-year tercile. Low = bottom third of historical VIX (calm). Mid = middle third. High = top third (elevated). Smoothed (5d MA) and hysteretic (1.0 VIX buffer) so it doesn't flap at boundaries. Brief 10C uses this to weight buckets differently per regime."
   ```
7. **`tests/test_regime_classification.py`** — three tests:
   - `test_regime_classification_low_mid_high`: synthetic VIX series, assert
     correct boundaries and regime assignment.
   - `test_regime_hysteresis`: smoothed VIX hovers at the mid/high boundary,
     assert no flip until it clears by 1.0.
   - `test_regime_handles_short_history`: VIX series < 1 year, assert
     fallback to "mid" with a warning flag in the dict.

**Edge cases:**
- VIX series < 252 trading days (~1yr) → fall back to `regime="mid"`,
  set `regime_thresholds={}`, log a warning. The hysteresis state reset.
- VIX fetch failure → no regime computed, scoring dict gets
  `"regime": None`. Dashboard shows "VIX regime: unavailable".
- First run ever (no `regime_previous` in state) → just set the initial
  regime, no hysteresis check on first observation.
- alert_state.json missing → existing `_load_state` returns `{}`, regime
  init proceeds normally.

**Success criteria:**
- `pytest tests/` passes (with three new tests added → 187/187 if Brief 16
  shipped first).
- Dry run `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  succeeds and writes a `regime` column to history.csv.
- Generated dashboard.html shows the regime badge under composite_short.
- Composite score is **unchanged** vs the prior run (Brief 10A is read-only).
- Run twice in a row with the same VIX value — `regime_changed` is False on
  the second run.

**Non-goals:**
- Changing how composite is computed. That's Brief 10C.
- Backtest extension. That's Brief 10B.
- An alert on regime change. Add only if 10C ships and Ian asks for it.

---

## Brief 10B — Backtest + recalibrate regime extension

**Dependencies:** Brief 10A shipped (regime classifier exists in
`src/history.py::classify_vix_regime`).

**Problem:** Before flipping on regime-aware weighting at score time
(Brief 10C), we need empirical evidence that bucket IC actually differs across
regimes. Brief 10B extends the backtest engine to compute per-regime per-bucket
IC, and adds a recalibrate mode that proposes a `regime_weights:` block for
weights.yaml.

**Design decisions — locked:**

1. **Backtest output gets a new column**: `regime` (low/mid/high) for each
   day. Computed using point-in-time VIX terciles (NO lookahead — at date T,
   use only VIX from `[T-10yr, T]`).
2. **New per-regime IC table** in `src/evaluation.py`:
   ```python
   def per_regime_bucket_ic(
       backtest_df: pd.DataFrame,
       spx: pd.Series,
       horizon_days: int = 21,
   ) -> pd.DataFrame:
       """Returns DataFrame indexed by bucket, columns = (low, mid, high)."""
   ```
   Uses existing `spearman_ic` + `build_forward_drawdown`.
3. **New recalibrate mode**: `python -m src.recalibrate --regime`.
   Reads `output/backtest_full.csv`, computes per-regime per-bucket IC, and
   proposes a `regime_weights:` block printed to stdout. Does NOT write to
   weights.yaml automatically (that's a manual review step — Ian inspects,
   accepts, edits, then pastes in).
4. **Multipliers, not absolute weights.** The proposed block uses multipliers
   relative to the current base weight, so accepting it doesn't override
   human-curated base weights:
   ```yaml
   regime_weights:
     enabled: false              # Brief 10B leaves this off — only telemetry
     classifier:
       type: vix_tercile
       smoothing_days: 5
       hysteresis_vix: 1.0
     multipliers:
       low:
         equity_volatility: 0.7   # de-emphasize equity vol in calm regime
         sentiment: 1.4           # sentiment matters more in calm
         credit_spreads: 0.8
         ...
       mid:                       # all 1.0 by default — neutral regime
         equity_volatility: 1.0
         ...
       high:
         equity_volatility: 1.2
         credit_spreads: 1.3
         funding_liquidity: 1.5   # funding stress dominates in crisis
         ...
   ```
5. **Multiplier ceiling/floor**: clip suggested multipliers to [0.3, 2.0].
   Anything outside that range is "we don't have enough data" not "this
   bucket is 5x more important".
6. **Multiplier proposal heuristic**: for each (regime, bucket), the
   recalibrator proposes:
   ```
   multiplier = clip(per_regime_ic[bucket] / mean_regime_ic, 0.3, 2.0)
   ```
   i.e., buckets that predict better in this regime get up-weighted
   proportional to their IC dominance. Clamped, with a bias toward 1.0 if
   sample size is small (< 50 days in regime).
7. **No live composite change** in Brief 10B. The output is purely a proposal
   block in stdout for Ian to review. Brief 10C wires it into compute_composite.

**Files to change:**

1. **`src/backtest.py`** — in `run_backtest()`, after computing the row's
   composite, call `classify_vix_regime(vix.loc[:date])` (point-in-time)
   and store as `row["regime"]`. Existing row dict gains one column.
2. **`src/evaluation.py`** — add `per_regime_bucket_ic()` function as above.
3. **`src/recalibrate.py`** — add `--regime` flag and a new function
   `propose_regime_weights(backtest_df, spx)` that prints the YAML block.
   Reuse the existing argparse setup; new flag is mutually exclusive with
   `--apply` (regime mode is preview-only).
4. **`tests/test_per_regime_ic.py`** — two tests:
   - `test_per_regime_ic_returns_correct_shape`: synthetic backtest_df with
     a `regime` column; assert returned DataFrame is `(buckets, 3)`.
   - `test_per_regime_ic_handles_empty_regime`: one regime has 0 rows;
     assert that regime's column is all NaN, no crash.

**Edge cases:**
- A regime with < 30 days of backtest data → IC computed but flagged
  unreliable; multiplier biased toward 1.0 (use weighted average with prior).
- `output/backtest_full.csv` missing → recalibrate --regime exits with a
  clear "Run backtest first" message.
- Sample-size weighting: when only ~50 days are in a regime, the proposed
  multiplier should be `0.5 * proposed + 0.5 * 1.0` (Bayesian shrinkage
  toward neutral). Below 30 days → multiplier forced to 1.0.

**Success criteria:**
- `pytest tests/` passes (with two new tests).
- `python -m src.backtest` succeeds and writes `regime` column to
  `output/backtest_full.csv`.
- `python -m src.recalibrate --regime` prints a parseable YAML block to
  stdout (verifiable by piping to `python -c "import sys, yaml; yaml.safe_load(sys.stdin)"`).
- The proposed multipliers are reasonable (no extreme values; sentiment
  multiplier in low regime > 1.0; credit_spreads multiplier in high regime
  > 1.0 — these are basic sanity checks against finance intuition).
- weights.yaml is **not modified** by --regime mode.

**Non-goals:**
- Auto-applying multipliers. That's a deliberate human-in-the-loop step.
- Re-running the full backtest with regime weights to validate. That's the
  validation step in Brief 10C.

---

## Brief 10C — Apply regime weights at score time

**Dependencies:** Brief 10A (classifier) AND Brief 10B (regime weights block
in weights.yaml). Ian must have reviewed and pasted the proposed
`regime_weights:` block from `recalibrate --regime` into weights.yaml.

**Problem:** With a classifier and a vetted multiplier table, flip the switch
to make `compute_composite()` actually apply per-regime weights. Render a
side-by-side comparison so Ian can see the regime-adjusted score next to the
naive baseline.

**Design decisions — locked:**

1. **Apply only to `composite`**, not `composite_short`. composite_short
   stays on base weights as the "naive" reference. This avoids conflating
   two adjustments (regime weighting + 3yr window) and gives Ian a clean
   anchor.
2. **Multipliers applied to bucket weights**, not indicator weights:
   ```python
   if regime_cfg["enabled"] and regime in regime_cfg["multipliers"]:
       multipliers = regime_cfg["multipliers"][regime]
       for bkey in bucket_results:
           m = multipliers.get(bkey, 1.0)        # missing bucket → 1.0
           bucket_results[bkey]["weight"] *= m
       # Renormalize so total weight still sums to ~1
       total = sum(b["weight"] for b in bucket_results.values())
       for b in bucket_results.values():
           b["weight"] = b["weight"] / total
   ```
3. **Renormalisation**: after multipliers, total bucket weight is renormalized
   to 1.0 so the composite stays in [0, 100]. Without renormalisation, a
   regime with mostly >1.0 multipliers would push composite scores upward.
4. **Default `enabled: false`**. Ian must explicitly flip the switch in
   weights.yaml. First flip should be after a side-by-side telemetry day:
   - Ship 10C with the dashboard *displaying* both scores (regime + naive)
     even when `enabled: false`, by computing both internally.
   - After a few days observation, Ian flips `enabled: true`. The visible
     change is which one labels as "Composite" vs "naive baseline".
5. **Add to scoring dict**:
   ```python
   "composite_naive": 47.3,            # always computed (base weights)
   "composite_regime_weighted": 51.8,  # always computed when regime config exists
   "composite": 51.8,                  # = regime_weighted if enabled, else naive
   "regime_weights_applied": True,
   "regime_multipliers_used": {"equity_volatility": 1.2, ...},
   ```
6. **Dashboard**: under the existing composite, add a small subline:
   ```
   Composite (regime-weighted, MID): 51.8
   Naive baseline (equal regimes):    47.3   ▲+4.5
   ```
   When `enabled: false`, swap which is labelled which (naive is primary,
   regime-weighted shown as "preview").
7. **History column**: log both `composite` and `composite_naive` so the
   delta is queryable in backtests.
8. **Validation backtest**: re-run backtest with `regime_weights.enabled:
   true` vs `false`; compare ICs. Document delta in a markdown note in
   `output/`. If regime IC < naive IC, do NOT flip enabled (revert to false
   and surface the result to Ian).

**Files to change:**

1. **`src/scoring.py::compute_composite()`** — implement the multiplier
   application + renormalisation. Read `regime_weights:` block from
   `weights.yaml` (extend `load_weights` if needed). Always compute both
   composite_naive and composite_regime_weighted; pick which one is the
   primary based on `enabled` flag.
2. **`src/config.py`** — extend `validate_config()` to validate the new
   `regime_weights:` block: classifier type known, all listed buckets exist
   in `weights["buckets"]`, multipliers in [0.3, 2.0], all 3 regimes present
   with at least an empty dict.
3. **`src/dashboard.py`** — add the side-by-side display under the composite
   card. Reuse the `regime_html`/`regime_adj_html` patterns at lines ~470–510.
4. **`src/history.py::log_run()`** — add `composite_naive` column.
5. **`config/weights.yaml`** — add a stub `regime_weights:` block with
   `enabled: false` and the multiplier table from Brief 10B's output.
6. **`tests/test_regime_weights_application.py`** — three tests:
   - `test_regime_disabled_returns_naive`: enabled=false → composite ==
     composite_naive.
   - `test_regime_enabled_applies_multipliers`: enabled=true with simple
     2x multiplier on one bucket; assert composite shifts in the expected
     direction.
   - `test_regime_renormalisation_preserves_range`: all multipliers = 2.0;
     assert composite still in [0, 100] (renormalisation works).
7. **Validation note**: after implementation, generate
   `output/regime_validation.md` containing the IC comparison table
   (regime-weighted vs naive, full + per-regime).

**Edge cases:**
- `regime_weights:` block missing entirely → behaves as if enabled=false,
  composite == composite_naive, no error. Just warn once at startup.
- `regime` is None (Brief 10A's failure mode) → fall back to base weights
  for this run, log a warning, both composites equal.
- Multiplier for a bucket is missing in current regime → use 1.0 (already
  in the design above).
- Hysteresis edge: if regime just changed, composite will jump. That's
  expected and visible — the regime tag changes color in the dashboard.
  No special handling. Brief 3 momentum will reflect the jump as a velocity
  spike one day; that's accurate signal, not noise.

**Success criteria:**
- `pytest tests/` passes (with three new tests, ~190 total).
- Dry run with `enabled: false` produces composite == composite_naive
  (regression check — nothing about live scoring should change yet).
- Dry run with `enabled: true` produces composite ≠ composite_naive in any
  regime where multipliers ≠ 1.0.
- Dashboard renders both scores side-by-side with the delta.
- `output/regime_validation.md` is generated after a backtest pass and shows
  whether regime-weighted IC > naive IC.
- weights_hash in history.csv changes only when weights.yaml changes (not on
  every regime transition — the hash is of the file, not the applied
  weights). This preserves provenance semantics.

**Non-goals:**
- Optimization sweep over multiplier values. The multipliers come from
  Brief 10B's recalibrate proposal and human review.
- Adding more regimes (4 quartiles, 5 quintiles, etc.). Three is enough
  for the data we have. Revisit only after a year of operation.
- Per-bucket regime classifiers (e.g., classify credit regime separately
  from equity regime). Single classifier keeps the model interpretable.

---

## Brief 17 — Stale data + data quality auto-remediation

**Authored by:** Sonnet 4.6 (2026-04-25 v1).
**Revised by:** Opus 4.7 (2026-04-25 v2) — corrected three load-bearing errors
in the v1 brief: (a) function name `score_all` doesn't exist (it's
`compute_composite` + `annotate_results`); (b) pipeline placement was unsafe
(would have double-written history.csv and fired alerts on stale data);
(c) force-fetch dispatch was specified at the wrong layer (leaf fetch functions
don't see the logical indicator key). Read v2 only — v1 is superseded.

**Status:** DESIGN LOCKED. Sonnet can proceed straight to implementation.

**Dependencies:** Brief 7 (retry/backoff in fetch layer — already shipped).

---

### Problem

The dashboard's DATA QUALITY card (`_build_bucket_health_card`) and the staleness
banner detect problems but offer no fix:

1. **`percentile: None` indicators** — these failed to fetch this run and fell
   back to a score of 50.0 (neutral). They are invisible failures: the composite
   looks reasonable but one or more inputs are fabricated.
2. **Stale indicators** — `check_series_staleness()` flags indicators whose most
   recent observation is older than the configured cadence threshold. The cache
   file exists and was used, but its data is outdated.

Both cases silently degrade signal quality with no recovery attempt. The system
should try once more before giving up.

---

### How the current fetch/scoring pipeline works (verified against code)

- `run_dashboard.py` calls `compute_composite(weights, env, manual)` from
  `src/scoring.py` (line 305 of scoring.py), then `annotate_results(scoring,
  thresholds)` from `src/triggers.py`. There is no `score_all()` — that name
  appeared in v1 of this brief in error.
- `compute_composite()` iterates `weights["buckets"]`, calls
  `_fetch_indicator(key, cfg, env, manual)` per indicator (line 96 of
  scoring.py), runs percentile/banding, and builds the scoring dict.
- `_fetch_indicator()` dispatches by `cfg["source"]["type"]` to either
  `fetch_fred_series(series_id, env)`, `fetch_yfinance_series(ticker, env)`,
  `fetch_treasury_auction_results(...)`, `fetch_cnn_fear_greed(env)`, or one
  of the `COMPUTED_HANDLERS` for `type: computed`.
- Failed fetches fall back to `50.0` with `"percentile": None` in the result.
- `stale_indicators: list[str]` is populated in the scoring result by
  `check_series_staleness()` calls inside `compute_composite`.
- The leaf fetch functions read from a file cache under `data/fetch_cache/`.
  Each one reads `cache_hours = float(env.get("CACHE_HOURS", 12))` and skips
  the network when the cache file is younger than that.
- The leaf fetch functions only know the FRED `series_id` or yfinance
  `ticker` — they do NOT know the logical indicator key (`vix`, `hy_oas`,
  etc.). The dispatch from logical key → fetch happens in `_fetch_indicator`.
- After `compute_composite` + `annotate_results`, `run_dashboard.py` calls
  (in order, all before `write_dashboard`):
  1. `log_run(scoring)` — **appends a row to `data/history.csv`**.
  2. `prune_history()` + `load_history(days=90)`.
  3. `get_news_brief(env)`.
  4. `score_past_alerts(history)` + `get_postmortem_stats(...)`.
  5. `send_alerts(scoring, env, history)` — **fires Pushover/Twilio/email**.
  6. `fetch_upcoming_events(env)`.
  7. Momentum + shock-type + regime-adjusted composite computation.
  8. `generate_narrative(...)` — **paid Haiku call**.
- There is no persistent circuit breaker. Brief 7's retries are inline
  (`_retry_get` does `requests.get` up to 3× with backoff within a single
  fetch call). If all 3 retries fail, the exception propagates and scoring
  falls back to 50.0.

---

### Design decisions (locked by Opus — Sonnet executes these exactly)

**D1 — Trigger conditions.** Remediate any indicator where:
- `scoring["stale_indicators"]` contains the key, OR
- the indicator's result has `"percentile": None` (confirmed failed fetch)

Run at most one remediation attempt per indicator per run. Don't remediate
indicators that returned valid data (even if the data is old by calendar
standards — staleness alerts handle that separately).

**D2 — Pipeline placement (HARD CONSTRAINT).** Remediation runs in
`run_dashboard.py` immediately after `annotate_results()` and **before**
`log_run()`, `send_alerts()`, and `generate_narrative()`. This is a hard
constraint, not a preference:

- Before `log_run()` because `log_run` appends to `history.csv` — running it
  on stale-then-fixed scoring would write the wrong row, and the next-day
  run would back-compute momentum from corrupted history.
- Before `send_alerts()` because alerts are the most consequential output;
  firing Pushover on a 50.0 fallback that gets corrected one second later
  would cause false positives or false negatives. (This means `send_alerts`
  fires once, against the post-remediation scoring — not before AND after.)
- Before `generate_narrative()` because Haiku is paid; we don't want to
  generate narrative against scoring we know to be wrong.

If `remediation_keys` is non-empty, do a second full pass:
`compute_composite(weights, env_remediate, manual)` then
`annotate_results(scoring, thresholds)`. The second pass uses the freshened
cache and produces a clean scoring dict. **Maximum two full passes per run.
Never loop.** If `remediation_keys` is empty, skip the entire remediation
block — no overhead on clean runs.

The `momentum + shock_type + regime_adj` block (currently lines 162–170 of
`run_dashboard.py`) reads from `history` and `scoring`. Since it runs *after*
`load_history()`, and `load_history()` runs *after* `log_run()`, this block
is downstream of remediation and needs no changes.

**D3 — Force-fetch dispatch lives in `_fetch_indicator()`, NOT leaf fetch
functions.** The leaf fetch functions (`fetch_fred_series`,
`fetch_yfinance_series`, `fetch_treasury_auction_results`,
`fetch_cnn_fear_greed`) only see series IDs / tickers — they don't know the
indicator's logical key, so they can't check `key in _remediation_keys`.
The dispatch belongs one layer up:

```python
# In src/scoring.py, _fetch_indicator(key, cfg, env, manual):
remediation_keys = env.get("_remediation_keys", set())
if key in remediation_keys:
    env_local = {**env, "CACHE_HOURS": "0"}  # bypass cache for this call only
else:
    env_local = env
# ... existing dispatch, but pass env_local instead of env to leaf fetches
```

This means **leaf fetch functions don't change at all.** All the new logic is
contained in `_fetch_indicator()`. `compute_composite` already passes `env`
through to `_fetch_indicator`, so `_remediation_keys` rides along
transparently.

If the live fetch succeeds, it writes fresh data to cache as normal. If it
fails, it raises and scoring falls back to 50.0 — no infinite retry.

**D4 — Logging.** For each remediation attempt, append one JSON line to
`data/alert_log.jsonl`:

```json
{"ts": "2026-04-25T07:31:14", "event_type": "remediation_attempt",
 "indicator": "vix", "outcome": "success|failed",
 "reason": "percentile_none|stale"}
```

Do NOT reuse `_log_alert` from `src/alerts.py` — that helper is alert-shaped
(takes title, body, scoring, alert_types) and would mix concerns. Inline the
JSONL append in `run_dashboard.py`:

```python
import json
from datetime import datetime
from pathlib import Path

def _log_remediation(indicator: str, outcome: str, reason: str) -> None:
    Path("data").mkdir(exist_ok=True)
    with open("data/alert_log.jsonl", "a") as f:
        f.write(json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event_type": "remediation_attempt",
            "indicator": indicator,
            "outcome": outcome,
            "reason": reason,
        }) + "\n")
```

Write the log entry whether the remediation succeeds or fails.

**D7 — Determining success/failure for the log.** "Success" = the indicator
that was in `remediation_keys` is no longer in `stale_indicators` AND no
longer has `percentile: None` after the second pass. "Failed" = it's still
in one of those states. Compute this by comparing the post-remediation
scoring dict to the original `remediation_keys` set.

**D5 — No UI changes.** The dashboard is a static HTML artifact rendered once
per run. The DATA QUALITY card will naturally reflect the outcome: if remediation
succeeded, the indicator will no longer appear in the card. No "REFRESH STALE"
button, no server-side endpoint.

**D6 — Non-goals for this brief.** Do not remediate `computed` indicators (type
`computed` in weights.yaml — their inputs are derived from other fetches, not
directly refreshable). Do not modify the staleness banner or DATA QUALITY card
HTML — they already surface the information correctly post-remediation.

---

### Files to change

1. **`src/scoring.py`** — modify `_fetch_indicator(key, cfg, env, manual)`
   (around line 96). Add the remediation bypass at the top of the function,
   before the existing dispatch:
   ```python
   def _fetch_indicator(key, cfg, env, manual):
       remediation_keys = env.get("_remediation_keys", set())
       if key in remediation_keys:
           env = {**env, "CACHE_HOURS": "0"}  # force live fetch this call
       # ... existing dispatch unchanged
   ```
   No other changes to scoring.py. `compute_composite` already threads `env`
   through to `_fetch_indicator`, so `_remediation_keys` rides along.

2. **`src/fetch.py`** — NO CHANGES. The leaf fetch functions don't see the
   logical indicator key, so the bypass can't live here. The CACHE_HOURS=0
   override from `_fetch_indicator` reaches them through `env` and they
   already honour `env["CACHE_HOURS"]`.

3. **`run_dashboard.py`** — insert the remediation block between
   `annotate_results()` (line 121) and `log_run()` (line 126):
   ```python
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
   log_run(scoring)
   ```
   Add `_log_remediation()` (per D4) and a small `_indicator_source_type(weights,
   key)` helper (walks `weights["buckets"][b]["indicators"][key]["source"]["type"]`,
   returning `""` if missing) at module scope.

4. **`data/alert_log.jsonl`** — written at runtime, no code change.

---

### Edge cases

- **`computed` indicators** (e.g., `sofr_spread`, `treasury_auction_stress`):
  their fetch is a derived calculation, not a direct network call. Exclude them
  from `remediation_keys` by checking `weights.yaml` `source.type == "computed"`.
  These indicators will still show in the DATA QUALITY card if they're `None`.

- **Second pass re-introduces a different failure:** If the remediation fetch
  succeeds for key A but key B fails on the second pass (transient error), that's
  acceptable — we tried once and moved on. The DATA QUALITY card will still show B.

- **CNN Fear & Greed:** The `fetch_cnn_fear_greed` function has its own fallback
  to FRED UMCSENT. If it's `None` after the first pass, remediation should force-
  retry the CNN scrape first; if that still fails, the FRED fallback will kick in
  automatically. No special handling needed — the force-retry is sufficient.

- **All-indicators-None edge case:** If every indicator failed (network outage),
  remediation will attempt all of them. The second `compute_composite()` call
  will also fail for all and return the same 50.0 defaults. This is correct
  behaviour. Don't add a "minimum successful remediations" guard — it adds
  complexity with no benefit.

- **`--no-cache` flag:** This flag already sets `CACHE_HOURS=0` in `env`, which
  forces all fetches live. When `--no-cache` is set, `remediation_keys` will be
  empty (nothing will be stale or None from a fresh run) so the remediation block
  is a no-op. No interaction issue.

---

### Success criteria

- Dry run (`--no-cache --no-alerts --quiet`) completes in under 2× normal time
  (the second `compute_composite()` pass adds latency only when stale/failed
  indicators are present; on a clean run the remediation block is skipped
  entirely).
- When a manual test injects a stale indicator (edit cache mtime or delete a
  cache file under `data/fetch_cache/`), the remediation block fires, a log
  entry appears in `data/alert_log.jsonl` with `event_type:
  "remediation_attempt"`, and the indicator no longer shows as stale in the
  output HTML.
- When the live fetch fails during remediation (mock network failure in test),
  the run completes and the indicator appears in the DATA QUALITY card — no
  crash, no infinite retry, log entry shows `outcome: "failed"`.
- `pytest tests/ -q` passes with 3 new tests covering:
  1. Remediation triggers when `percentile: None` indicators are present.
  2. Remediation triggers when `stale_indicators` is non-empty.
  3. Remediation does not trigger on a clean scoring result (assert
     `compute_composite` mock is called exactly once).
- `computed`-type indicators are excluded from `remediation_keys` (verify by
  checking that a `computed` indicator with `percentile: None` does NOT trigger
  a second `compute_composite` call).
- `history.csv` has exactly one row appended per dashboard run, even when
  remediation fires (regression check — the placement-bug version of this
  brief would have appended two).
- `send_alerts()` is invoked at most once per run, against the
  post-remediation scoring (regression check — alerts must not fire on
  pre-remediation 50.0 fallbacks).

---

## Brief 19 — Commodities & Energy bucket diversification

**Dependencies:** None. All four target tickers are live on yfinance (`CL=F`,
`RB=F`, `HO=F`, `NG=F`, `HG=F`, `GC=F`). Existing `commodities` bucket structure
is config-driven — no scoring.py code references `oil_vol` by name.

> ⚠️ **Coordination with Brief 18 — DO NOT MISS:** This brief deletes
> `oil_vol` from `config/weights.yaml` and `KNOWN_INDICATOR_KEYS`. The
> explainer YAML at `config/indicator_explainers.yaml` (authored
> 2026-04-29) currently has an `oil_vol` block. **In the same commit
> that ships Brief 19, you must also delete the `oil_vol` block from
> `config/indicator_explainers.yaml`.** If you don't, the
> `_validate_indicator_explainers()` validator added by Brief 18 will
> warn on every dashboard run that an explainer exists for an indicator
> that no longer ships. The `crack_spread_321`, `natgas`, and
> `copper_gold_ratio` explainer blocks are already pre-staged in that
> file — they will activate on this commit and need no addition. See
> file step 7 below.

**Problem:** The `commodities` bucket is misnamed and undiversified. Both
indicators (`wti_crude` 0.55, `oil_vol` 0.45) derive from the same `CL=F`
contract, so the bucket is 100% WTI exposure with two views of it. This creates
two distinct weaknesses:

1. **No real diversification within the bucket.** If WTI is stable but natural
   gas is spiking on European supply contagion, or copper is collapsing on
   growth fears, the bucket reads "calm." The bucket label says "Commodities &
   Energy" but the contents are one commodity.
2. **No paper-vs-physical signal.** Flat WTI captures futures-market dislocation
   but not whether refiners can keep up — i.e., whether downstream products
   (gasoline, distillate) are actually pricing the crude move through.
   Hurricanes, refinery fires, and product embargoes (e.g. Russian distillate
   restrictions) widen the *crack spread* before they meaningfully move flat
   WTI. We currently miss this.

Additionally, `oil_vol` (1-month realized vol of CL=F) is largely redundant with
`vix` and `move_index` during real stress episodes — it co-moves with broad
risk-off vol regimes but rarely contributes independent signal at the bucket
level.

**Design decisions — opinionated and locked:**

1. **Drop `oil_vol`.** Its independent signal is weak in stress regimes where
   it would matter most. Reuse the freed weight to add genuinely orthogonal
   commodities exposure. Removal is config-only — no scoring.py references.
2. **Add three new indicators to `commodities`:**
   - `crack_spread_321` — 3-2-1 crack spread, $/bbl. Captures Ian's
     paper-vs-physical intuition in its standard industry form: the margin
     between crude (input) and refined products (what gets sold to consumers).
     Wide crack = refining bottleneck = real-economy oil stress that flat
     futures don't show.
   - `natgas` — Henry Hub front-month YoY % change. Independent supply-shock
     vector (winter cold snaps, Europe LNG contagion, storage anomalies). YoY
     transform mirrors the `cpi_yoy` pattern — strips out "what's the new
     normal price" noise and leaves the stress signal.
   - `copper_gold_ratio` — HG=F / GC=F ratio. Classic growth/risk-off proxy.
     Falls when the market prices recession (industrial demand ↓, safe-haven
     demand ↑). Independent of energy entirely — gives the bucket actual
     breadth.
3. **Bucket weight redistribution:**
   - **Old:** wti_crude 0.55, oil_vol 0.45
   - **New:** wti_crude 0.30, crack_spread_321 0.25, natgas 0.25,
     copper_gold_ratio 0.20
   - Rationale: WTI stays the largest single exposure (it's still the headline
     energy signal). Crack spread gets meaningful weight as the
     paper-vs-physical signal Ian asked for. Natgas and copper/gold get
     enough weight to actually move the bucket when their domain is in stress
     while WTI is calm.
4. **Bucket weight in composite stays at 0.07.** Cross-bucket reweighting is
   `recalibrate.py`'s job, not this brief's.
5. **Keep the bucket label "Commodities & Energy".** Rename was tempting but
   adds no signal — the bucket genuinely contains both energy (WTI, crack
   spread, natgas) and a non-energy commodity (copper). Existing dashboard
   templates, alert references, and history columns all use `commodities` as
   the key — leave them.
6. **`crack_spread_321`: type `computed`, handler `crack_spread_321`.**
   Formula in $/bbl: `(2 × RBOB × 42 + 1 × ULSD × 42) / 3 - WTI`. RBOB and
   ULSD (HO=F) are quoted $/gal, WTI in $/bbl, 42 gal/bbl conversion is
   correct. `direction: high`, `invert: false`.
7. **`copper_gold_ratio`: type `computed`, handler `copper_gold_ratio`.**
   Simple ratio HG=F / GC=F (units cancel meaningfully — copper $/lb over
   gold $/oz, treated as a unitless rank-able series). Lower = stress, so
   `invert: true`, `direction: low`.
8. **`natgas`: type `yfinance` ticker `NG=F` with `transform: yoy_series`.**
   No new computed handler needed — reuses existing `_TRANSFORMS["yoy_series"]`.
   `direction: high`, `invert: false`.
9. **Threshold bands** are starting estimates calibrated against rough
   long-run distributions. After ~2 weeks of live data, re-check actual
   percentile placement and tune if any band is unreachable or always-on:
   - `crack_spread_321` (direction: high, $/bbl):
     yellow 35, orange 45, red 55
   - `natgas` (direction: high, % YoY):
     yellow 30, orange 60, red 100
   - `copper_gold_ratio` (direction: low, raw ratio HG/GC):
     yellow 0.0021, orange 0.0018, red 0.0015
10. **No new alerts in this brief.** The existing band/composite alert
    machinery picks up the new indicators automatically once they're scored.
    Adding indicator-specific alerts is a follow-on if a bucket-level signal
    proves useful.
11. **History schema migration is automatic.** New `raw_commodities__*`
    columns appear on first run; old `raw_commodities__oil_vol` will go
    unwritten and read empty for new rows. This matches the established
    pattern (no migration code needed; `log_run` writes whatever keys are
    present).

**Files to change:**

1. **`config/weights.yaml`** — replace the entire `commodities` block:

   ```yaml
   commodities:
     label: "Commodities & Energy"
     weight: 0.07
     indicators:
       wti_crude:
         label: WTI Crude Oil
         weight: 0.30
         source:
           type: yfinance
           ticker: "CL=F"
         invert: false
         unit: "$/bbl"
       crack_spread_321:
         label: "3-2-1 Crack Spread"
         weight: 0.25
         source:
           type: computed
           handler: crack_spread_321
         invert: false
         unit: "$/bbl"
       natgas:
         label: "Henry Hub Natural Gas (YoY)"
         weight: 0.25
         source:
           type: yfinance
           ticker: "NG=F"
           transform: yoy_series
         invert: false
         unit: "%"
       copper_gold_ratio:
         label: "Copper / Gold Ratio"
         weight: 0.20
         source:
           type: computed
           handler: copper_gold_ratio
         invert: true
         unit: "ratio"
   ```

   Verify: bucket weight 0.07 unchanged; indicator weights sum to 1.0.

2. **`src/scoring.py`** — add two handlers near `_handler_vix_term_structure`:

   ```python
   def _handler_crack_spread_321(key, cfg, env, manual, years):
       wti  = fetch.fetch_yfinance_series("CL=F", env, years)
       rbob = fetch.fetch_yfinance_series("RB=F", env, years)
       ulsd = fetch.fetch_yfinance_series("HO=F", env, years)
       combined = pd.concat(
           [wti.rename("wti"), rbob.rename("rbob"), ulsd.rename("ulsd")],
           axis=1,
       ).dropna()
       crack = (2 * combined["rbob"] * 42 + combined["ulsd"] * 42) / 3 - combined["wti"]
       return float(crack.iloc[-1]), crack

   def _handler_copper_gold_ratio(key, cfg, env, manual, years):
       copper = fetch.fetch_yfinance_series("HG=F", env, years)
       gold   = fetch.fetch_yfinance_series("GC=F", env, years)
       combined = pd.concat(
           [copper.rename("copper"), gold.rename("gold")], axis=1
       ).dropna()
       ratio = combined["copper"] / combined["gold"]
       return float(ratio.iloc[-1]), ratio
   ```

   Register both in `COMPUTED_HANDLERS`:

   ```python
   COMPUTED_HANDLERS: dict = {
       ...existing entries...,
       "crack_spread_321":   _handler_crack_spread_321,
       "copper_gold_ratio":  _handler_copper_gold_ratio,
   }
   ```

3. **`src/config.py`** — in `KNOWN_INDICATOR_KEYS`:
   - **Remove:** `"oil_vol"`
   - **Add:** `"crack_spread_321"`, `"natgas"`, `"copper_gold_ratio"`

4. **`config/thresholds.yaml`** — in the `# --- Commodities & Energy ---`
   section:
   - **Remove the entire `oil_vol:` block.**
   - **Keep the `wti_crude:` block as-is.**
   - **Add:**

   ```yaml
   crack_spread_321:           # 3-2-1 crack spread, $/bbl; wide = refining bottleneck
     direction: high
     yellow: 35.0
     orange: 45.0
     red: 55.0

   natgas:                     # Henry Hub front-month YoY %; high = supply stress
     direction: high
     yellow: 30.0
     orange: 60.0
     red: 100.0

   copper_gold_ratio:          # HG=F / GC=F; low = risk-off / growth fears
     direction: low
     yellow: 0.0021
     orange: 0.0018
     red: 0.0015
   ```

5. **`config/tooltips.yaml`** — under `indicators:`:
   - **Remove the `oil_vol:` entry** (lines 97–98).
   - **Add three new entries near `wti_crude:`:**

   ```yaml
   crack_spread_321:
     tip: "3-2-1 crack spread ($/bbl): refining margin between crude (input) and gasoline + distillate (output). Standard industry stress metric. Wide crack = refiners can't keep up — hurricanes, refinery fires, product embargoes. Captures real-economy oil stress that flat WTI misses."
   natgas:
     tip: "Henry Hub natural gas front-month, YoY % change. Independent supply-shock vector — winter cold snaps, European LNG contagion, storage anomalies. YoY framing strips out 'new normal' price drift."
   copper_gold_ratio:
     tip: "Copper futures / gold futures (HG=F / GC=F). Classic growth-vs-fear proxy: copper rises with industrial demand, gold rises with safe-haven demand. Low ratio = market pricing recession. Lower readings = more stress."
   ```

6. **`config/indicator_explainers.yaml`** — coordination with Brief 18:
   - **Delete the `oil_vol:` block entirely** (the indicator no longer
     ships, so the explainer would orphan and trigger a validation warning).
   - **Leave `crack_spread_321`, `natgas`, and `copper_gold_ratio` as-is.**
     They were pre-staged in this file when Brief 18's content was authored
     on 2026-04-29 specifically so this brief doesn't need to add them.
     Verify all three blocks are present before committing — if Brief 18's
     wiring has shipped between then and now, the `_validate_indicator_explainers()`
     check should pass cleanly.
   - **Do not edit the `# ── Brief 19 (designed, not yet shipped) ─` header
     comment** — instead, after this brief ships, change that comment block
     to `# ── Commodities & Energy (Brief 19, shipped) ─` so future readers
     know the staging is resolved. Small but keeps the file honest.

7. **`tests/test_commodities_bucket.py`** — new file with three focused tests:

   - **`test_crack_spread_321_arithmetic`** — Mock `fetch.fetch_yfinance_series`
     to return synthetic series for `CL=F`, `RB=F`, `HO=F`. Use simple values
     so the formula is hand-verifiable, e.g. WTI=[60,70,80], RBOB=[2.0,2.5,3.0]
     ($/gal), ULSD=[2.0,2.5,3.0]. Expected crack on the last row:
     `(2*3.0*42 + 1*3.0*42)/3 - 80 = 126 - 80 = 46.0`. Assert handler returns
     `(46.0, series)` and series last value matches.

   - **`test_copper_gold_ratio_arithmetic`** — Mock copper=[4.0, 5.0],
     gold=[2000.0, 2000.0]. Expected ratio last = `5.0/2000.0 = 0.0025`.

   - **`test_commodities_bucket_validates`** — Load
     `config/weights.yaml` and `config/thresholds.yaml`, call
     `validate_config()`, assert no error. Assert the `commodities` bucket
     has exactly four indicators with keys
     `{wti_crude, crack_spread_321, natgas, copper_gold_ratio}` and
     indicator weights sum to 1.0 within `_WEIGHT_TOLERANCE`.

   Mocking pattern: see `tests/test_vix_term_structure.py` for the canonical
   shape (patch `fetch.fetch_yfinance_series`).

**Edge cases:**

- One leg of crack spread (RB=F, HO=F, CL=F) returns short or empty series →
  `dropna()` after concat handles mismatched-date rows; if the result is
  empty, `crack.iloc[-1]` raises and the outer scoring try/except falls back
  to score 50.0 (existing pattern). Don't add bespoke error handling.
- `NG=F` has < 1 year of data (shouldn't happen — series goes back 25+ years
  on yfinance, but defensively): `yoy_series` will return NaN → outer
  scoring catches → fallback 50.0.
- HG=F or GC=F have weekend/holiday gaps that don't align → `dropna()` after
  concat handles it. Do NOT `ffill` — would invent ratio data.
- First post-deploy run will have no prior `raw_commodities__crack_spread_321`
  history → percentile is computed against whatever the freshly-fetched
  series provides (10y from yfinance, full history available immediately).
  No backfill of `data/history.csv` needed.
- `recalibrate.py` will see new indicator keys on its next run. Its design
  is key-agnostic (operates on whatever keys are in the current config), so
  no changes needed; the next recalibration cycle will naturally include
  these.

**Success criteria:**

- `pytest tests/ -q` passes (198/198 with the three new tests, assuming
  baseline 195/195 from CLAUDE.md memory note).
- Pre-commit hook runs `validate_config()` cleanly after the YAML change.
- `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  succeeds end-to-end. Inspect output:
  - `commodities` bucket on the dashboard shows four rows (wti_crude,
    crack_spread_321, natgas, copper_gold_ratio) with raw values and bands.
  - The bucket header weight display shows the new split (30/25/25/20).
  - Tooltips render on hover for all three new indicators.
- `data/history.csv` newest row has non-empty
  `raw_commodities__crack_spread_321`,
  `raw_commodities__natgas`, and
  `raw_commodities__copper_gold_ratio` columns;
  `raw_commodities__oil_vol` is absent (or empty for new rows).
- Composite score before/after change should differ only modestly — the
  bucket weight in composite is unchanged at 0.07, and the new indicators
  on a calm day should percentile to roughly mid-range. A composite swing
  of more than ~3 points on a quiet day is suspicious; investigate.

**Non-goals:**

- **Brent-WTI spread.** Geographic dislocation signal; partially overlaps
  with `global_spillover` thinking. Adds dimensionality without clear new
  signal at the bucket level. Reconsider only if a future episode shows
  WTI calm but Brent stressed and the composite missed it.
- **Retail gasoline minus wholesale RBOB.** Marketing-margin noise; lags
  crude by 2–6 weeks. Wrong tool for an early-warning dashboard.
- **Bucket renaming.** "Commodities & Energy" still describes contents
  accurately. Rename = pure churn (history schema, dashboard templates,
  alert keys all use the `commodities` key already).
- **Separate "consumer energy burden" display card.** Worth doing later as
  its own non-scored panel (gasoline/diesel/heating-oil retail prices, for
  Ian's qualitative read on real-economy energy cost). Track separately as
  a future Phase H item — do NOT bundle into this brief.
- **Per-indicator alert types.** New indicators inherit the existing
  band/composite alert machinery. Bucket-specific alert thresholds can be
  added later if a real episode shows the bucket-level signal mattering
  enough to warrant its own escalation rule.

---

## Brief 20 — Expand free wire-service news coverage

**Dependencies:** None. Pure expansion of `src/news.py`'s feed list plus
config-extraction and dedup hygiene. No new external paid services, no
scraping, no paywall bypass.

**Problem:** `src/news.py:RSS_FEEDS` (lines 13–18) hardcodes only four feeds:
Reuters businessNews, MarketWatch, Yahoo Finance, WSJ markets. Three concrete
weaknesses:

1. **Missing the highest-signal sources entirely.** Federal Reserve press
   releases, Treasury press releases, BLS news releases (CPI/NFP), BEA news
   releases (GDP/PCE), and ECB press releases are *the source of truth* for
   most market-moving macro news — every wire-service story about CPI is a
   summary of the BLS release that's already public. We're reading
   downstream when the upstream feed is free, official, and never breaks.
2. **Underusing the wire services that already lead publishers.** Reuters and
   AP wires are upstream of WSJ/FT/Bloomberg for most breaking news. We have
   one Reuters feed (businessNews); we're missing Reuters Markets, Reuters
   World (for geopolitical context that feeds the `iran_trigger` and global
   spillover bucket), and AP Business entirely.
3. **No source attribution in dashboard output.** `get_news_brief()` returns
   `[{text, url}]` with no indication of which feed each headline came from.
   You can't quickly judge "is this a Fed press release or a MarketWatch
   summary" — both render identically.

Additional code-level issues that come into scope when we touch this file:

- **Feed list lives in code, not config.** Adding/removing a feed requires a
  code change, against this project's "config is authoritative" principle
  (CLAUDE.md). Should live in `config/news_feeds.yaml`.
- **No headline dedup.** Same story carried by Reuters, AP, and a publisher
  burns Haiku tokens three times and clutters the brief.
- **Silent feed deaths.** A feed that 404s or returns empty is swallowed by
  the existing `try/except: continue` (line 47–48). When a publisher kills
  an RSS endpoint, we never know.

**Design decisions — opinionated and locked:**

1. **Move `RSS_FEEDS` to `config/news_feeds.yaml`**, matching the project's
   data-driven config pattern. Each feed entry has `name`, `url`,
   `category`, and `max_items`. Ian can add/remove feeds without a code
   change.
2. **Three-tier feed taxonomy** in the YAML, used for dedup priority and
   downstream weighting decisions:
   - `official` — Fed, Treasury, BLS, BEA, ECB, NY Fed press releases.
     Highest signal density per item; never paywalled; structurally stable.
   - `wire` — Reuters, AP. Upstream of most publisher coverage.
   - `publisher` — MarketWatch, Yahoo, WSJ headlines (free RSS surface),
     Bloomberg free feeds, FT Alphaville. Aggregation and commentary.
3. **Per-feed `max_items`**, not the current global constant of 12:
   - `official` feeds: 12 (publish less, every item matters)
   - `wire` feeds: 12 (existing default)
   - `publisher` feeds: 8 (often noisy with stock-mover headlines we filter
     out anyway)
4. **Headline dedup by Jaccard similarity ≥ 0.7** on token sets (4+ chars,
   lowercase). When duplicates exist, keep the one from the highest-tier
   source (`official` > `wire` > `publisher`). This both reduces Haiku token
   spend and ensures the displayed source is the most authoritative.
5. **Source attribution end-to-end.** `_pull_headlines()` returns
   `[{title, url, source, category}]`; `get_news_brief()` returns
   `[{text, url, source}]`; dashboard renders `Source: Headline text`
   format with the source bolded or muted (Sonnet's choice — match
   existing typography in `dashboard.py`).
6. **Feed health goes to the existing audit log.** When a feed returns 0
   entries or raises, append one line to `data/alert_log.jsonl` with
   `{type: "news_feed_failure", feed: name, reason: str, ts: ...}`. Reuses
   Brief 11 infrastructure; no new file. Don't fail the run on any single
   feed's death — keep the existing graceful-degradation pattern.
7. **Validate `news_feeds.yaml` at startup.** Add `_validate_news_feeds()`
   to `src/config.py`'s `validate_config()` chain. Schema: at least one
   feed; each feed has all four fields; `category` ∈ {`official`, `wire`,
   `publisher`}; `max_items` is a positive int. The pre-commit hook then
   catches schema breakage before deploy.
8. **Don't parallelize fetch.** `feedparser` is synchronous; the round-trip
   cost across 8–12 feeds at 7:30 AM is ~10s, well within the dashboard's
   budget. Adding `aiohttp` or threadpool here is premature.
9. **Don't add feed-level signal weighting yet.** Tempting to weight
   `official` headlines higher when feeding Haiku, but that's empirical
   tuning that needs weeks of operation to validate. Ship the breadth
   expansion first; weighting is a follow-on if it proves needed.

**Files to change:**

1. **NEW `config/news_feeds.yaml`** — starter feed set. Sonnet should
   `feedparser.parse()` each URL once before committing and drop any that
   return zero entries; document the drop in the commit message. URLs
   below are best-known-good as of 2026-04-27 but RSS endpoints move
   without notice. Where a publisher's RSS landing page lists current
   URLs, prefer that over hardcoded guesses:

   ```yaml
   # Free RSS feeds for news_brief headline ingestion.
   # Categories used for dedup priority and per-feed item caps:
   #   official  — government / central bank press releases (highest signal)
   #   wire      — Reuters, AP, etc. (upstream of most publishers)
   #   publisher — aggregation, commentary, paywalled-body headlines

   feeds:
     # --- Official ---
     - name: "Fed Press Releases"
       url: "https://www.federalreserve.gov/feeds/press_all.xml"
       category: official
       max_items: 12
     - name: "Fed Speeches"
       url: "https://www.federalreserve.gov/feeds/speeches.xml"
       category: official
       max_items: 12
     - name: "BLS News Releases"
       url: "https://www.bls.gov/feed/news_release/rss.xml"
       category: official
       max_items: 12
     - name: "BEA News"
       url: "https://www.bea.gov/news/rss.xml"
       category: official
       max_items: 12
     - name: "Treasury Press Releases"
       url: "https://home.treasury.gov/news/press-releases/feed"
       category: official
       max_items: 12
     - name: "ECB Press Releases"
       url: "https://www.ecb.europa.eu/rss/press.html"
       category: official
       max_items: 12

     # --- Wire ---
     - name: "Reuters Business"
       url: "https://feeds.reuters.com/reuters/businessNews"
       category: wire
       max_items: 12
     - name: "Reuters World"
       url: "https://feeds.reuters.com/Reuters/worldNews"
       category: wire
       max_items: 12
     - name: "AP Business"
       url: "https://feeds.apnews.com/rss/apf-business"
       category: wire
       max_items: 12

     # --- Publisher ---
     - name: "MarketWatch"
       url: "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/"
       category: publisher
       max_items: 8
     - name: "Yahoo Finance"
       url: "https://finance.yahoo.com/rss/topstories"
       category: publisher
       max_items: 8
     - name: "WSJ Markets"
       url: "https://www.wsj.com/xml/rss/3_7085.xml"
       category: publisher
       max_items: 8
     - name: "FT Alphaville"
       url: "https://www.ft.com/alphaville?format=rss"
       category: publisher
       max_items: 8
   ```

   At minimum 8 feeds must validate live. If fewer than 8 do, halt the
   brief and surface the failures — under-shipping is fine; shipping a
   list dominated by dead URLs isn't.

2. **`src/news.py`** — three changes:

   a. **Replace the `RSS_FEEDS` constant** with a loader:

   ```python
   def _load_news_feeds() -> list[dict]:
       path = Path("config/news_feeds.yaml")
       data = yaml.safe_load(path.read_text(encoding="utf-8"))
       return data.get("feeds", [])
   ```

   b. **Rewrite `_pull_headlines()`** to use per-feed `max_items`, attach
   source/category metadata, and log feed health:

   ```python
   def _pull_headlines() -> list[dict]:
       items: list[dict] = []
       for feed in _load_news_feeds():
           try:
               parsed = feedparser.parse(feed["url"])
               if not parsed.entries:
                   _log_feed_failure(feed["name"], "0 entries returned")
                   continue
               for entry in parsed.entries[:feed["max_items"]]:
                   title = entry.get("title", "").strip()
                   link  = entry.get("link", "").strip()
                   if title:
                       items.append({
                           "title":    title,
                           "url":      link,
                           "source":   feed["name"],
                           "category": feed["category"],
                       })
           except Exception as exc:
               _log_feed_failure(feed["name"], str(exc))
               continue
       return _dedup_headlines(items)
   ```

   c. **Add `_dedup_headlines()` and `_log_feed_failure()`** helpers:

   ```python
   _CATEGORY_RANK = {"official": 0, "wire": 1, "publisher": 2}

   def _title_tokens(title: str) -> set[str]:
       return {w.lower() for w in re.findall(r"\b\w{4,}\b", title)}

   def _dedup_headlines(items: list[dict], threshold: float = 0.7) -> list[dict]:
       kept: list[dict] = []
       kept_tokens: list[set[str]] = []
       for item in items:
           toks = _title_tokens(item["title"])
           if not toks:
               continue
           dup_idx = -1
           for i, prior_toks in enumerate(kept_tokens):
               denom = len(toks | prior_toks)
               if denom and len(toks & prior_toks) / denom >= threshold:
                   dup_idx = i
                   break
           if dup_idx == -1:
               kept.append(item)
               kept_tokens.append(toks)
           else:
               # Replace with higher-priority source if applicable.
               if _CATEGORY_RANK[item["category"]] < _CATEGORY_RANK[kept[dup_idx]["category"]]:
                   kept[dup_idx] = item
                   kept_tokens[dup_idx] = toks
       return kept

   def _log_feed_failure(name: str, reason: str) -> None:
       try:
           from src.alerts import _log_alert  # reuse Brief 11 audit channel
           _log_alert({
               "type":   "news_feed_failure",
               "feed":   name,
               "reason": reason[:200],
           })
       except Exception:
           pass  # never let logging kill the run
   ```

   d. **Update `get_news_brief()`** to thread `source` through to the
   returned dicts: `[{text, url, source}]`. The Haiku prompt should also
   show source per headline (e.g. `- [Reuters] Fed signals...`), so the
   model can distinguish authority levels in its summary. Update the
   `_SYSTEM` prompt to mention "prefer official-source items when
   summarizing, but include important wire-service stories."

3. **`src/dashboard.py`** — find where `get_news_brief()` output is rendered
   (search for the news brief section header). Add source label rendering:
   change the line that emits each bullet to include `<span class="news-source">{source}</span> {text}` (or whatever
   class name fits the existing CSS palette — Sonnet picks). If no
   matching style exists, add a small muted-grey class. Source label is
   shown only when non-empty.

4. **`src/config.py`** — add to `validate_config()`:

   ```python
   _VALID_NEWS_CATEGORIES = frozenset({"official", "wire", "publisher"})

   def _validate_news_feeds() -> None:
       path = Path("config/news_feeds.yaml")
       if not path.exists():
           return  # absence is OK — news.py will emit empty brief
       data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
       feeds = data.get("feeds", [])
       if not feeds:
           raise ConfigError("config/news_feeds.yaml has no 'feeds' entries.")
       for i, f in enumerate(feeds):
           for k in ("name", "url", "category", "max_items"):
               if k not in f:
                   raise ConfigError(f"news_feeds.yaml entry {i} missing field '{k}'.")
           if f["category"] not in _VALID_NEWS_CATEGORIES:
               raise ConfigError(
                   f"news_feeds.yaml entry '{f['name']}' has invalid category "
                   f"'{f['category']}' — must be one of {sorted(_VALID_NEWS_CATEGORIES)}."
               )
           if not isinstance(f["max_items"], int) or f["max_items"] < 1:
               raise ConfigError(
                   f"news_feeds.yaml entry '{f['name']}' has invalid max_items "
                   f"{f['max_items']!r} — must be a positive int."
               )
   ```

   Wire it into `validate_config()`. The pre-commit hook then guards
   against schema breakage.

5. **NEW `tests/test_news_feeds.py`** — three focused tests:

   - **`test_news_feeds_yaml_validates`** — load the actual
     `config/news_feeds.yaml`, call `_validate_news_feeds()`, assert no
     error. Acts as canary if Ian edits the YAML and breaks schema.
   - **`test_dedup_keeps_highest_tier_source`** — feed two synthetic items
     with identical titles, one `category: publisher` and one
     `category: official`. Assert `_dedup_headlines()` returns one item
     and its `source` is from the official-tier feed.
   - **`test_dedup_below_threshold_keeps_both`** — two items with low
     token overlap (e.g. titles that share zero 4+ char words). Assert
     both kept.

6. **`config/series_cadence.yaml`, `config/tooltips.yaml`** — no changes
   needed.

**Edge cases:**

- A feed URL is valid but the publisher started returning HTML instead of
  XML (rare but happens) → `feedparser.parse()` returns an object with
  empty `.entries`. Handled by the `if not parsed.entries` check; logs
  failure and continues.
- A YAML edit introduces a duplicate `name` field → not currently caught
  by validation. Not worth catching — duplicate names cause confusing
  logs but don't break anything. Skip.
- Dedup on near-empty titles (<2 tokens) → `_title_tokens` returns small
  set, Jaccard denominator small, false-positive dedups likely. The
  `if not toks: continue` guard handles zero-token; for 1-token titles,
  accept the small false-positive rate (very few 1-token financial
  headlines exist).
- Audit log file missing → `_log_alert` from `src/alerts.py` already
  handles this gracefully (see Brief 11). The wrapping `try/except`
  belt-and-suspenders is intentional — feed health logging must never
  break the run.
- All feeds dead → existing graceful path: dashboard shows "(no news
  brief)" or whatever the current empty-list rendering does.

**Success criteria:**

- `pytest tests/ -q` passes.
- Pre-commit hook runs `validate_config()` cleanly with the new YAML.
- `python run_dashboard.py --no-cache --no-alerts --quiet` succeeds and
  renders the news brief section with at least one source label visible
  (look for "Fed", "Reuters", "AP", or one of the configured names).
- `data/alert_log.jsonl` has at most a small number of `news_feed_failure`
  entries (some feeds will inevitably 404 — that's expected and is the
  signal value of having the audit log).
- Manually inspect Haiku output: at least one bullet should reference
  content from an official-tier source over the next ~5 dashboard runs
  if there's relevant Fed/BLS/Treasury activity.
- Total feeds in active rotation: ≥ 8 (vs current 4). If fewer than 8
  validate live, halt and surface failures rather than ship a stub.

**Non-goals:**

- **Article body fetching of any kind.** This brief is headlines + dek
  only. No scraping, no readability extraction.
- **Paywall bypass tooling** (12ft.io, BPC techniques). Explicitly
  rejected in the design conversation that produced this brief —
  legal/operational risk exceeds marginal signal value vs free wires.
- **Per-source signal weighting** in scoring or alerts. Tempting but
  needs weeks of empirical tuning data; revisit only if a real episode
  shows the breadth expansion isn't enough.
- **Email-based ingestion** of Ian's WSJ/FT subscriptions (the original
  "Brief B" alternative). Not declined permanently — just deferred until
  Brief 20 ships and we see whether the breadth expansion alone is
  sufficient.
- **Async/parallel feed fetching.** ~10s sync round-trip is well within
  budget for a 7:30 AM run.
- **A new dashboard section.** Brief 20 enriches the existing news brief
  in place; no new card.

---

## Brief 21 — Codebase optimization pass

**Dependencies:** None. All items below are surgical and independent — Sonnet
can ship them in any order, or split into multiple commits.

**Problem:** The codebase has accumulated real cruft and structural drift over
the past months as Briefs 1–17 + 10A/B/C + 16 layered features on. This pass
is the prioritized punch list of items worth fixing *before* the next round of
features (Phase G remainder, Briefs 19/20, plus future briefs). The findings
below are ranked by risk/correctness × value/effort. P0 items have observable
correctness or observability gaps; P1 are DRY/structural improvements that
compound over future work; P2 are small wins.

Each item is self-contained — Sonnet should commit them individually with
the brief number suffix (e.g. `Brief 21A — backtest indicator gap`).

---

### P0 — Correctness / observability gaps

#### 21A — Backtest is missing six active production indicators

**File:** `src/backtest.py` (specifically `_IND_TO_SERIES` lines 144–164,
plus `_fetch_raw` and `_build_derived`)

**Diagnosis:** The backtest engine maps only 19 indicators to derived series.
The following live production indicators are silently absent from the
backtest output and therefore from `recalibrate.py`'s IC measurements:

- `vix_term_structure` (Brief 16, shipped)
- `move_index`
- `cnn_fear_greed` (CNN F&G launch)
- `treasury_auction_stress`
- `sector_breadth`
- `spx_200dma_distance`

Effect: when `recalibrate.py` calls `_indicator_ic_series` on the backtest
CSVs, these indicators have no `__score` column → `ic_recent` and `ic_hist`
are NaN → the recalibrator falls into the "keep (no recent/hist data)"
silent-pass branch (lines 191–196). They never get IC validated, never get
weight-adjusted, and we have no quantitative evidence whether they're
helping or hurting the composite.

**Fix:** Add point-in-time fetch + derivation for each missing indicator:

- `vix_term_structure`: needs `^VIX3M` fetched (≥18 years available); ratio
  `vix / vix3m`. Add to `_IND_TO_SERIES`. New entry `_AVAIL["vix_term_structure"] = "2008-04-01"` (VIX3M start).
- `move_index`: yfinance ticker `^MOVE`. Add directly.
- `cnn_fear_greed`: no historical series available outside the live cache
  (CNN does not expose pre-2022 data via API). Mark as `_MANUAL`-equivalent
  in backtest — set raw=50, pct=50, score=50 for all dates (i.e. neutral).
  Document this in a comment so the IC table is not misleading.
- `treasury_auction_stress`: TreasuryDirect search API does provide
  historical auctions, but reliably only back to ~2008. Add `_AVAIL = "2008-01-01"`. Reuse `_compute_auction_stress` from `scoring.py`.
- `sector_breadth`: 11 sector ETFs, all on yfinance. XLY/XLE/XLI/XLF/XLB
  start ~1998; XLRE starts 2015 (handle by skipping it before that date in
  the breadth calculation, not by setting `_AVAIL` — the indicator is
  meaningful with 10/11 sectors). Reuse `_compute_sector_breadth` logic.
- `spx_200dma_distance`: derive from existing `^GSPC` series. Add to
  `_build_derived` as `(price - price.rolling(200).mean()) / rolling_mean * 100`.

**Tests to add:** One test per new indicator confirming `_indicator_pit`
returns a numeric value at a representative date when the indicator is
available, and `(None, None, None)` before its `_AVAIL` date.

**Effort:** ~60–90 min. Must re-run both backtests after change
(`python -m src.backtest`) and inspect `output/backtest_full.csv` for new
columns.

---

#### 21B — `_band_from_score` is duplicated four times with three implementations

**Files:**
- `src/scoring.py:241` (`_band_from_score`) — canonical
- `src/triggers.py:30` (`_score_band`) — identical body, used in
  `annotate_results`
- `src/dashboard.py:771` (inline `_band_fn` lambda inside `write_dashboard`)
- `src/backtest_report.py:317` (inline `band = "red" if score_at >= 70 else ...`
  inside `_section_events`)

**Diagnosis:** Every band-from-score derivation is copy-pasted with the same
30/50/70 thresholds. If thresholds ever change (or someone wants to test a
sensitivity), they have to find and update all four. Two of the four are
hidden inside other functions (lambda + inline ternary) — easy to miss.

**Fix:**
1. Move the canonical implementation to `src/indicators.py` as
   `band_from_score(score: float) -> str` (public name).
2. Add `BAND_THRESHOLDS = {"yellow": 30, "orange": 50, "red": 70}` constant
   alongside it.
3. Update the three duplicates to import and call it. In `triggers.py`,
   delete `_score_band` and import `band_from_score`. In `dashboard.py`,
   delete the `_band_fn` lambda. In `backtest_report.py`, replace the
   inline ternary.
4. `scoring.py` already exports `_band_from_score` (used by `dashboard.py`);
   keep it as a re-export from indicators or just have everything import
   from indicators.

**Tests:** Existing tests on `_band_from_score` (search `tests/` for it)
should keep passing; add one assertion that `band_from_score(70.0) == "red"`
boundary case.

**Effort:** ~20 min.

---

#### 21C — Band color palette diverges between dashboard and backtest report

**Files:**
- `src/dashboard.py:22` `_BAND_COLOR = {"green": "#22cc44", "yellow": "#ffcc00", "orange": "#ff8800", "red": "#ff4444"}`
- `src/history.py:17` — same palette as dashboard (good)
- `src/indicator_detail.py:9` `_THRESH_COLOR` and line 121 `band_colors` —
  same as dashboard (good)
- `src/backtest_report.py:46` `.pos {color:#3fb950} .neg {color:#f85149} .neu {color:#8b949e} .warn {color:#d29922}`
- `src/backtest_report.py:322` `badge_color = {"red": "#f85149", "orange": "#d29922", "yellow": "#e3b341", "green": "#3fb950"}`

**Diagnosis:** The dashboard uses one set of greens/reds/oranges; the
backtest report uses different hex values for the same semantic bands
(`#ff4444` vs `#f85149` for red, `#22cc44` vs `#3fb950` for green). When a
user clicks "View full backtest report →" from the dashboard, the visual
language shifts — same word "red" maps to two different visible reds. Minor
but easy to fix.

**Fix:** Decide which palette is canonical (recommend dashboard's because
it's already used by 3+ files vs backtest_report's 1). Move `_BAND_COLOR`
and `_BAND_BG` to a new file `src/colors.py` (or append to `indicators.py`).
Update both dashboard.py and backtest_report.py to import from there.
Replace the divergent hex values in backtest_report.py CSS and
`badge_color` dict.

**Effort:** ~15 min. Visual regression check: open dashboard then backtest
report in browser, confirm reds/greens/oranges match.

---

### P1 — DRY / structural improvements

#### 21D — Live and backtest fetch implementations duplicate 80% of their logic

**Files:** `src/fetch.py` (live, with retry + stale-cache fallback) vs
`src/backtest.py:_bt_fred / _bt_yf` (lines 68–117, no retry, no fallback)

**Diagnosis:** `_bt_fred` and `_bt_yf` are near-copies of `fetch_fred_series`
and `fetch_yfinance_series` with three differences: (a) different cache
directory (`data/cache/backtest/`), (b) different default years (26 vs 10),
(c) no retry / stale-cache logic. The duplication exists because the
backtest needs longer history and a separate cache so 26-year fetches don't
overwrite the live 10-year cache. But that's parameterizable, not
duplication-worthy.

**Fix:** Refactor `fetch.py` to expose:

```python
def fetch_fred_series(series_id: str, env: dict, years: int = 10,
                     cache_subdir: str = "") -> pd.Series:
    ...
def fetch_yfinance_series(ticker: str, env: dict, years: int = 10,
                          cache_subdir: str = "") -> pd.Series:
    ...
```

`cache_subdir` defaults to `""` (live cache root). Backtest passes
`cache_subdir="backtest"`. Existing live callers don't change. Delete
`_bt_fred` and `_bt_yf` from `backtest.py`; replace with calls to
`fetch.fetch_fred_series(..., years=FETCH_YEARS, cache_subdir="backtest")`.

The retry/stale-cache logic now applies to backtest too — pure win, since
backtest currently fails hard on transient network errors mid-2-hour run.

**Tests:** Existing fetch tests must still pass. Add a test that
`cache_subdir="backtest"` writes to `data/cache/backtest/` and doesn't
collide with the live cache.

**Effort:** ~45 min. Risk: low — additive parameter, defaults preserve
existing behavior.

---

#### 21E — Six near-identical YAML loader functions in `dashboard.py`

**File:** `src/dashboard.py`, functions: `_load_events`, `_load_review_prompts`,
`_load_tooltips`, `_load_thresholds`, `_load_ind_weights`,
`_load_escalation_paths` (lines 128–250 of dashboard.py)

**Diagnosis:** Each is ~10 lines doing the same thing: check path exists,
`yaml.safe_load`, optionally extract a sub-key, fallback to `{}` on error.
Six near-identical bodies in one file.

**Fix:** Add a single helper at the top of `dashboard.py`:

```python
def _load_yaml(path: str, key: str | None = None, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return data.get(key, default if default is not None else {}) if key else data
    except Exception:
        return default if default is not None else {}
```

Then collapse the six callers:
- `_load_events()` → `_load_yaml("config/events.yaml", "events", [])`
- `_load_review_prompts()` → `_load_yaml("config/review_prompts.yaml", "bands")`
- `_load_tooltips()` → `_load_yaml("config/tooltips.yaml")`
- `_load_thresholds()` → `_load_yaml("config/thresholds.yaml", "indicators")`
- `_load_escalation_paths()` → `_load_yaml("config/escalation_paths.yaml", "buckets")`
- `_load_ind_weights()` is slightly more complex (nested transformation);
  leave as-is or refactor with a helper call + comprehension.

**Effort:** ~30 min. Net: ~50 lines deleted.

---

#### 21F — `compute_composite` special-cases VIX series capture by string match

**File:** `src/scoring.py`, `compute_composite` lines 364–365:

```python
if bkey == "equity_volatility" and ikey == "vix" and series is not None:
    _vix_series_for_regime = series
```

**Diagnosis:** The VIX series is captured for downstream regime
classification (line 442) by hardcoded string match on the bucket+indicator
keys. If `weights.yaml` ever renames `equity_volatility` → `volatility`, or
`vix` → `vix_index`, regime classification silently breaks. This is the
exact failure mode `validate_config()` was built to prevent — but here the
keys are hardcoded *outside* the validation surface.

**Fix:** Two options, pick one:

(a) **Re-fetch VIX inside `classify_vix_regime` rather than threading it
through.** Cheap because the series is cached anyway. Removes the cross-
function coupling entirely. Recommended.

(b) **Add a `regime_input: vix` flag to the indicator's config** in
weights.yaml; have `_fetch_indicator` annotate the result with this flag;
let `compute_composite` collect any `regime_input`-flagged series. More
flexible but more machinery.

Go with (a). In `compute_composite`, delete the special-case capture.
After the bucket loop, before regime classification:

```python
try:
    vix_series = fetch.fetch_yfinance_series("^VIX", env, years=int(env.get("HISTORY_YEARS", 10)))
    regime_info = classify_vix_regime(vix_series, _load_prev_regime())
except Exception as exc:
    errors.append(f"vix_regime: {exc}")
    regime_info = {}
```

**Tests:** Existing scoring tests should pass. Verify the regime block in
the dashboard still renders (`scoring["regime"]` populated).

**Effort:** ~20 min.

---

#### 21G — Top-level deferred imports for no apparent reason

**Files:**
- `src/scoring.py:440` — `from src.history import classify_vix_regime`
  inside `compute_composite`
- `src/alerts.py:318` — `from src.history import compute_composite_momentum, ...`
  inside `send_alerts`
- `src/alerts.py:488` — `from src.history import classify_shock_type` inside
  `send_alerts`
- `src/backtest_report.py` — `from src.evaluation import ...` repeated 3+
  times inside functions

**Diagnosis:** These imports are at function scope, suggesting a circular
dependency was historically there and worked-around. Verify there's no
cycle today — `history.py` does not import from `scoring`, `alerts`, or
`backtest_report`. The deferred imports are unnecessary cargo cult.

**Fix:** Move all four to module-level imports. If a cycle is discovered,
restore the deferred import with a one-line comment explaining the cycle.

**Tests:** All tests must pass. If imports succeed at module load, no
runtime change.

**Effort:** ~10 min.

---

### P2 — Small wins

#### 21H — Dead string in `backtest._MANUAL`

**File:** `src/backtest.py:141` —
`_MANUAL = {"repo_stress", "aaii_bull_bear", "iran_trigger"}`

**Diagnosis:** `aaii_bull_bear` is not in `KNOWN_INDICATOR_KEYS`,
`weights.yaml`, or any handler. It's a leftover from an earlier draft. The
string sits dormant; no current effect, but it's misleading documentation.

**Fix:** Delete `"aaii_bull_bear"` from the set. One-character commit.

**Effort:** ~1 min.

---

#### 21I — Duplicate "not in model" badge in `dashboard._calendar_indicator_badge`

**File:** `src/dashboard.py:282–291`

**Diagnosis:** Lines 282–286 and 287–291 produce the same fallback HTML
(`"not in model"` badge). The for-loop's `else` branch is identical to the
post-loop fallback. One can be removed.

**Fix:** Delete lines 287–291 (the post-loop fallback) and let the function
fall through cleanly, OR collapse the conditional inside the loop. Trivial.

**Effort:** ~5 min.

---

### Summary table

| ID | Item | Priority | Effort |
|----|------|----------|--------|
| 21A | Add 6 missing indicators to backtest | P0 | 60–90 min |
| 21B | Consolidate `_band_from_score` (4 → 1) | P0 | 20 min |
| 21C | Unify band color palette across reports | P0 | 15 min |
| 21D | Parameterize fetch (live + backtest in one impl) | P1 | 45 min |
| 21E | Generic `_load_yaml` helper in dashboard | P1 | 30 min |
| 21F | Remove VIX series string-match special case | P1 | 20 min |
| 21G | Lift deferred imports to module level | P1 | 10 min |
| 21H | Delete dead `aaii_bull_bear` string | P2 | 1 min |
| 21I | Remove duplicate calendar-badge fallback | P2 | 5 min |

**Total effort estimate:** ~3.5–4 hours for everything. Recommended order:
21A → 21B → 21C → 21D → 21F → 21G → 21E → 21H → 21I. Run full test suite
after each commit. **Do not bundle into one mega-commit** — keep the
21A/21B/21C/... split so any single revert is surgical.

**Non-goals (deliberately not included):**

- Splitting `dashboard.py` into multiple files. The 1100-line size is
  uncomfortable but the file is mostly HTML strings; splitting now would
  scatter related templates without enabling anything. Revisit only if a
  Phase G UX brief makes part of it genuinely reusable.
- Replacing `recalibrate._patch_weights_file` with `ruamel.yaml` for proper
  comment-preserving round-trip. Real concern but adds a dependency for
  marginal benefit; manual review of recalibration output is the existing
  safety net. Track separately.
- Vectorizing `evaluation.build_forward_drawdown` (currently O(n²)). At
  6500 backtest dates the runtime is ~30s on cold cache — acceptable for
  a function that runs once per recalibration cycle. Don't optimize until
  it's actually a bottleneck.
- Type-hinting alert state with a TypedDict / dataclass. Worth doing; not
  worth the refactor cost right now. Add when next state-key is added.
- Splitting `compute_composite` into smaller functions. Real complexity
  but the function is well-tested and the splits aren't obvious. Defer.

---

## Brief 22 — Backtest model explainer (expert + plain-English)

**Dependencies:** None. Pure content addition to `output/backtest_report.html`.

**Problem:** The backtest report currently presents IC values, confidence
intervals, ROC curves, regime-stratified metrics, and event case studies —
all without context for *what any of it means*. A reader who isn't already
fluent in time-series statistics + market microstructure has no way to read
the report. Specifically:

1. **What is "IC"?** Spearman vs Pearson, what counts as good (0.05 vs 0.15),
   why it's the right metric for a stress signal.
2. **Why "forward SPX drawdown" as the target?** Other choices exist
   (forward HY widening, forward stress index) — why is this the headline?
3. **What does regime stratification tell you that the headline doesn't?**
   A composite IC of 0.12 averaged across regimes might hide that the
   model is strong in stress regimes and noise in calm regimes.
4. **Known limitations** — look-ahead bias, survivorship in indicator
   selection, regime change risk, out-of-sample = "out of training" not
   "out of fitting" because there was no training (the model is rules-based).

**Design decisions — locked:**

1. **Two collapsible `<details>` sections at the top of the report**, above
   the headline IC table. Both default to collapsed (so the report still
   opens cleanly to numbers for return readers); the summaries on the
   `<summary>` line make the value of opening obvious.
2. **"Expert view"** — for someone fluent in stats but new to *this*
   project. Methodology + caveats. Roughly 350–500 words.
3. **"Plain-English view"** — for an intelligent generalist (lawyer,
   doctor, retired professional, family member) with no stats / no finance
   background. Answers: what is this report? What does the model do? Why
   should I care? What can it predict, and what can't it? Roughly 350–500
   words. No jargon, no acronyms used without expansion.
4. **Same visual style** as the rest of the report (dark theme, existing
   `.card` and `.note` classes). New section gets a subtle blue
   left-border to differentiate it from data sections.
5. **Wired in via a new `_section_explainer()` function** in
   `backtest_report.py`, called from `generate_report` *before* the first
   `_run_and_render` call. Function is content-only — paste the prose
   below into it as raw HTML strings.

**Files to change:**

1. **`src/backtest_report.py`** — add `_section_explainer()` function
   (content provided in full below). Insert call in `generate_report()`
   immediately after the `<div class="ts">...</div>` line and before the
   first `sections.append(...)` call.

2. **No new dependencies, no schema changes, no test additions.** Visual
   smoke test only: regenerate report with `python -m src.backtest_report`
   and confirm both expandable sections render at the top.

**The two sections — paste this prose verbatim into `_section_explainer()`:**

```python
def _section_explainer() -> str:
    """Two collapsible sections explaining the report. Insert above headline table."""
    return """
<div class="card" style="border-left:3px solid #58a6ff;background:#0d1f2e">
<details>
<summary style="cursor:pointer;font-size:1rem;font-weight:600;color:#e6edf3">
Methodology and caveats — for finance / stats readers
<span style="color:#8b949e;font-size:.85rem;font-weight:400;margin-left:8px">click to expand</span>
</summary>
<div style="margin-top:14px;line-height:1.65;font-size:.92rem">

<p><b>What this report measures.</b> Each row is a Spearman rank correlation
(IC) between the model's composite stress score on date T and a
forward-looking outcome over the subsequent 1–6 months — primarily peak
S&amp;P 500 drawdown, secondarily HY OAS widening and a multi-asset stress
index. Spearman is preferred over Pearson because the composite is bounded
[0, 100] and outcome distributions are heavy-tailed; rank correlation is
robust to both.</p>

<p><b>Reading the IC table.</b> An IC of <b>0.15+</b> is considered strong
for a daily-frequency macro stress signal — it is the threshold above
which institutional risk teams typically take a signal seriously. <b>0.05
to 0.15</b> is detectable signal that's worth keeping but not strong on
its own. <b>Below 0.05</b> is statistically indistinguishable from noise
at this sample size, even if the headline number is positive. The 95%
confidence intervals are computed via block bootstrap with quarterly
blocks (63 business days) to preserve autocorrelation — they will be
substantially wider than naive bootstrap CIs and that is correct. If a CI
crosses zero, the IC is not significantly different from random.</p>

<p><b>Why these specific targets.</b> Forward SPX drawdown is the headline
because it is what the user actually cares about — capital preservation —
and because drawdown distributions are non-Gaussian in ways that the
composite is designed to anticipate. HY widening and the multi-asset
stress index are sanity checks: a real stress signal should predict all
three, not just one. If the composite hits SPX drawdowns but misses HY
widening, that's a hint the signal is overfit to equity vol. The
benchmark columns (VIX alone, HY OAS alone, NFCI, 3-factor average) test
whether the composite adds anything over its own components — if VIX
alone matches the composite, the other 25 indicators are dead weight.</p>

<p><b>Regime stratification.</b> The single-number IC averages across
calm and stress periods, which can hide regime-dependent performance. The
regime-stratified table breaks IC out by VIX tercile (bottom third =
calm, top third = stress). A model with strong stress-regime IC and weak
calm-regime IC is *better* than one with uniform mediocre IC — calm-period
noise is harmless because the user does nothing on calm days. Conversely,
strong calm-regime IC and weak stress-regime IC is the worst pattern: the
model is most confident exactly when it shouldn't be.</p>

<p><b>Known limitations.</b> (1) <b>No look-ahead bias is structural</b> —
each date T uses only data from [T−10y, T] for percentile computation —
but indicator <i>selection</i> is post-hoc, chosen with the benefit of
knowing 2008 / 2020 / 2022 happened. The 2000–2017 subset model exists
specifically to test out-of-sample. (2) <b>Survivorship</b> — indicators
in the current model are ones that survived discretionary review. Failed
prior candidates are not preserved, so the headline IC is biased upward.
(3) <b>Manual indicators</b> (`repo_stress`, `iran_trigger`) are always
zero historically because no historical series exists; this slightly
deflates pre-2018 composite levels. (4) <b>FRED licensing</b> — ICE BofA
OAS series are limited to ~3 years on the FRED API regardless of
requested start date; the engine handles this by skipping unavailable
indicators and renormalizing bucket weights, so the pre-2018 subset model
is structurally smaller than the post-2018 full model.</p>

<p><b>Recalibration cycle.</b> Bucket weights and indicator weights are
re-tuned via <code>src/recalibrate.py</code>, which applies a 2×2 matrix
on each indicator's pre-2016 and post-2016 IC. Strong/strong → keep;
strong/weak → reduce 4×; weak/strong → keep (new signal); weak/weak →
drop. Re-running this requires both backtest CSVs to be fresh. The
checkpoint cadence is documented in the project TODO.</p>

</div>
</details>
</div>

<div class="card" style="border-left:3px solid #58a6ff;background:#0d1f2e">
<details>
<summary style="cursor:pointer;font-size:1rem;font-weight:600;color:#e6edf3">
What does this report actually mean? — for non-specialists
<span style="color:#8b949e;font-size:.85rem;font-weight:400;margin-left:8px">click to expand</span>
</summary>
<div style="margin-top:14px;line-height:1.65;font-size:.92rem">

<p><b>The big picture.</b> The dashboard you saw is a kind of weather
station for financial markets. It reads 26 different gauges every day —
stock-market jumpiness, the cost of borrowing for risky companies, how
worried investors are, what the Federal Reserve is signaling, oil prices,
unemployment numbers, and so on — and combines them into one summary
number from 0 to 100. Higher means more market stress; lower means
calmer. This report is the answer to a fair question: "is that summary
number actually any good?"</p>

<p><b>The way we test it.</b> We replay history. Imagine pretending it's
March 1, 2008. We compute the dashboard's stress score using <i>only</i>
the data that existed on that date — no peeking ahead. Then we look at
what the stock market actually did over the following weeks and months
and ask: when the score was high back then, did bad things tend to
follow? When the score was low, did the market mostly behave? We do this
every business day going back to 2000 (for the older subset) and 2018
(for the newer full model), and we measure how reliably high scores
preceded losses. That measurement — the "IC" you see throughout the
report — is essentially "how often was the dashboard right, on a scale
where 0 means useless and higher means more useful."</p>

<p><b>What counts as good.</b> Forecasting markets is hard, and you
should be deeply skeptical of anyone who claims a perfect score. For
this kind of broad early-warning gauge, an IC above 0.15 is genuinely
good news — it means the signal is meaningfully better than guessing,
even if it's far from a crystal ball. Between 0.05 and 0.15 is "real but
modest" — useful in combination with other information, not on its own.
Below 0.05 is essentially noise. The colored badges next to each row in
the IC tables tell you which bucket each row falls into.</p>

<p><b>Why it's not a crystal ball.</b> Three honest limits to bear in
mind. <b>First</b>, the model was built knowing what crises happened
between 2008 and today, so it's been quietly tuned in hindsight to catch
those events. The 2000–2017 subset is included specifically to check
that the model still works on a period the designers didn't optimize for
— but even there, the choice of which gauges to include benefits from
hindsight. <b>Second</b>, future crises will not look exactly like past
ones. The 2008 crisis and the 2020 COVID crash and the 2022 inflation
shock all triggered different gauges in different orders. A new kind of
crisis — say, an AI-driven flash crash, or a sovereign-debt episode in a
country we don't track — could move markets without our gauges seeing it.
<b>Third</b>, the dashboard tells you when stress is rising. It does not
tell you what to do about it. A high score is a prompt to think
carefully about your situation, not an instruction to sell.</p>

<p><b>Reading the rest of this report.</b> The "headline" table at the
top shows the model's score against three different definitions of "bad
outcome" — biggest stock drop, biggest credit-market widening, and an
overall stress index. The tables further down break performance out by
indicator (which gauges are pulling weight, which aren't), by VIX tercile
(does the model work better when markets are already nervous, or when
they're calm?), and by year (was 2017 a fluke or representative?). The
ROC curves are a different way of asking the same question — they show
how often the model gives a true alarm vs a false alarm at different
sensitivity settings. The event case studies pick specific historical
crises and show what the model said in advance and during them.</p>

<p><b>The bottom line.</b> If you take only one thing away: this report
exists so the model is not a black box. It tells you, with numbers and
caveats, where the model is reliable and where it isn't. The dashboard's
job is to help its user think more carefully about market risk, not to
replace that thinking — and this report is the receipts.</p>

</div>
</details>
</div>
"""
```

**Wiring it in:** In `generate_report` (around line 478), add one line:

```python
sections.append(_section_explainer())
sections.append(html_full)
```

That's the entire change. The two new collapsible cards render at the top
of the report, both default-collapsed.

**Success criteria:**

- `python -m src.backtest_report` regenerates `output/backtest_report.html`
  without error.
- Both new sections appear at the top, default-collapsed; expanding each
  shows the full prose with proper paragraph breaks.
- Existing sections (headline table, per-indicator IC, ROC curves, regime,
  events) render unchanged below.
- Visual: blue left-border on the explainer cards distinguishes them from
  data cards.

**Non-goals:**

- Inline tooltips on individual metrics. The two top-of-report sections
  are the right level of detail; sprinkling per-cell tooltips would clutter
  the data tables and duplicate explanation across many sites.
- Auto-generated commentary on the actual numbers ("the model's IC this
  cycle is X, which means…"). Tempting, but writing it requires either
  hardcoded ranges or LLM synthesis — both add fragility for marginal
  user value. The reader can interpret the badges + their own knowledge.
- A third "investor view" register. Two registers cover the realistic
  audience (Ian himself, plus anyone he might show this to). More
  registers = more drift over time as the report's content evolves.

---

## Brief 23 — G3: Layman narrative suggests household action

**Dependencies:** None. All wiring already exists.

**State of the world before this brief:** A surprisingly large fraction
of G3 is already shipped. `src/narrative.py` already (a) generates both
expert and layman registers in a single Haiku call, (b) parses them from a
JSON schema, (c) caches them together to `data/cache/narrative.json`, and
(d) returns both as a tuple. `src/dashboard.py:1034–1058` already renders
the AI Narrative Summary card with a "Plain English" toggle button, both
text blocks (expert visible, layman `display:none`), and a working
`toggleNarrative()` JS function (line 1113). `tests/test_narrative.py`
already exercises both registers through cache + Haiku-call paths.

**The actual gap.** Three small things, only one of which is a real
design call:

1. **Tone of the layman register is wrong for what Ian wants.** The
   current `_SYSTEM` prompt (`narrative.py:76–86`) explicitly forbids
   action: *"what (if anything) a cautious non-expert should be aware of
   — not what to do"* and *"No investment advice in either version."*
   Ian's call (2026-05-01): the layman register should suggest action.
   The expert register stays observational.

2. **Toggle resets on page reload.** No localStorage persistence — every
   refresh sends Ian back to expert view even if he last selected layman.

3. **Footer disclaimer needs nuance.** Currently *"AI-generated summary
   (Claude) · not financial advice."* That phrasing is fine but the
   layman block specifically now contains action prompts; the disclaimer
   should be visible in *both* views, not just under the expert block,
   and should be a hair stronger.

**Design decisions — locked:**

1. **Action level is household financial behavior, never specific
   securities.** Examples of acceptable action language: *"some people
   in this situation might review their emergency cash buffer," "a
   cautious household might delay large new financial commitments this
   week," "no action is typically warranted at this level — file it
   away."* Examples of unacceptable: *"consider trimming equity
   exposure to 50%," "rotate into defensive sectors," "buy gold."*

   **Rationale:** the dashboard publishes to GitHub Pages, technically
   public. Asset-allocation specificity invites investment-advice
   regulatory questions and trips the "AI told me to" failure mode that
   the disclaimer can't really cover. Household-behavior level is
   semantically what Ian wants ("what should a normal person do about
   this?") and stays clear of that line.

2. **Action language is band-calibrated.** Different bands warrant
   different intensities. Haiku gets four explicit examples in the
   prompt (one per band) so the layman text varies appropriately rather
   than always sounding the same alarm. See prompt below.

3. **Frame action as conditional, not imperative.** *"Some people might
   consider X"* / *"a cautious household might X"* — never *"you
   should X"* or *"do X."* This matches the existing dashboard tone
   ("help me think") without abandoning Ian's call.

4. **Expert register stays observational.** Ian himself reads the expert
   block and CLAUDE.md's locked rule applies: help-me-think, never
   tell-me-what-to-do. Only the layman register changes.

   > **Note for future models:** this asymmetry is intentional. The
   > "never tell me what to do" rule from CLAUDE.md applies to the
   > *expert* register (which Ian reads) and the dashboard's overall
   > stance. The *layman* register is for over-the-shoulder readers and
   > Ian's own occasional "step back" use; for that audience he has
   > explicitly authorized prescriptive endings, household-level only.
   > Don't quietly revert this prompt to "no advice in either version"
   > on a future cleanup pass — that would re-create the gap this brief
   > closed.

5. **localStorage key is `dashboardNarrativeRegister`** with values
   `'expert'` (default) or `'layman'`. Read on page load, write on
   toggle. Namespaced so it doesn't collide with anything Ian might add
   later.

6. **No new tests for the prompt content itself.** The system prompt is
   instruction text, not assertable behavior; testing it would mean
   asserting against Haiku output, which is brittle. The existing
   integration tests already cover both-register parsing. *Do* add one
   small test that the localStorage init JS is present in rendered HTML.

**Files to change:**

1. **`src/narrative.py`** — replace the `_SYSTEM` constant with the
   prompt below.

2. **`src/dashboard.py`** — three small edits:

   (a) Update `toggleNarrative()` to write to localStorage on switch.

   (b) Add an init block in the existing `(function(){...})()` IIFE near
       line 1128 that reads `dashboardNarrativeRegister` and applies the
       saved choice on load.

   (c) Move the disclaimer from inside the narrative card to render once
       below *both* blocks (it currently sits after the expert div but is
       outside the toggle, so it's already visible in both views — but
       update its wording per the new prompt below).

3. **`tests/test_dashboard.py`** (or wherever the dashboard render
   tests live — Sonnet pick the right file) — one test that the
   rendered HTML contains the literal string `'dashboardNarrativeRegister'`
   so the persistence wiring can't silently get deleted.

**The new `_SYSTEM` constant — paste verbatim:**

```python
_SYSTEM = (
    "You are writing a daily market stress narrative in two registers. "
    "Respond ONLY with valid JSON matching this schema exactly: "
    "{\"expert\": \"...\", \"layman\": \"...\"}. "
    "\n\n"
    "EXPERT REGISTER (2–4 sentences): for a finance professional. Cover "
    "composite level, key drivers, momentum direction. Use jargon directly "
    "(OAS, basis points, percentile, regime, etc.). Tone: precise, neutral, "
    "observational. NO recommendations, NO suggestions of what to do. "
    "Describe the situation; do not prescribe action."
    "\n\n"
    "LAYMAN REGISTER (3–5 sentences): for an intelligent generalist with no "
    "finance background. Plain English only — no jargon, no acronyms, no "
    "ticker symbols. Three parts in order: (1) what the score means in "
    "everyday terms, (2) which areas of the market are under stress and why "
    "that might matter to a household, (3) ONE concrete household-level "
    "action a cautious non-expert might consider given the current band. "
    "\n\n"
    "Action language must be CONDITIONAL ('some people might consider', "
    "'a cautious household might', 'no action is typically warranted') — "
    "NEVER imperative ('you should', 'do X', 'sell'). Action must be at "
    "the household financial behavior level (cash buffer, emergency fund, "
    "timing of large purchases, news attentiveness). NEVER suggest specific "
    "securities, sectors, asset allocations, percentages, or portfolio "
    "moves. NEVER mention buying or selling stocks, bonds, gold, or any "
    "named instrument."
    "\n\n"
    "Calibrate the action to the band:\n"
    "- green (composite < 30): 'no action typically warranted at this "
    "level — markets are calm; this is normal background weather.'\n"
    "- yellow (30–50): 'some people might choose to read more market news "
    "this week than usual — stress is elevated but not alarming.'\n"
    "- orange (50–70): 'a cautious household might review their emergency "
    "cash buffer and hold off on major new financial commitments until "
    "the picture clarifies.'\n"
    "- red (≥70): 'this is a moment when many cautious households tighten "
    "their belts — keep cash on hand, defer large discretionary spending, "
    "and stay informed.' "
)
```

**localStorage JS — paste verbatim into `dashboard.py`:**

Replace the existing `toggleNarrative()` function with:

```javascript
function toggleNarrative() {
  var expert = document.getElementById('narr-expert');
  var layman = document.getElementById('narr-layman');
  var btn = document.getElementById('narr-toggle');
  if (!expert || !layman || !btn) return;
  var nowLayman = (layman.style.display === 'none');
  if (nowLayman) {
    expert.style.display = 'none';
    layman.style.display = '';
    btn.textContent = 'Expert ▾';
    try { localStorage.setItem('dashboardNarrativeRegister', 'layman'); } catch (e) {}
  } else {
    expert.style.display = '';
    layman.style.display = 'none';
    btn.textContent = 'Plain English ▾';
    try { localStorage.setItem('dashboardNarrativeRegister', 'expert'); } catch (e) {}
  }
}
```

Add this to the existing IIFE (the `(function() { ... })();` block that
already handles the automation banner near line 1128):

```javascript
try {
  var saved = localStorage.getItem('dashboardNarrativeRegister');
  if (saved === 'layman') {
    var expert = document.getElementById('narr-expert');
    var layman = document.getElementById('narr-layman');
    var btn = document.getElementById('narr-toggle');
    if (expert && layman && btn) {
      expert.style.display = 'none';
      layman.style.display = '';
      btn.textContent = 'Expert ▾';
    }
  }
} catch (e) {}
```

**Disclaimer wording update:**

Replace the existing footer line in the narrative card from:

```
AI-generated summary (Claude) · not financial advice
```

to:

```
AI-generated · for orientation only · not financial advice · not a substitute for your own judgment
```

**Edge cases:**

1. **Cache invalidation.** Existing caches (`data/cache/narrative.json`)
   on disk will contain the old observational layman text. Solution:
   bump `_CACHE_HOURS` *briefly is wrong* — just delete the file once
   when this ships. Sonnet should add a one-liner near top of
   `_read_cache()` that returns empty if the cached layman text starts
   with the literal phrase `"What this means"` or any of the old
   observational lead-ins — actually, simplest: add a `_CACHE_VERSION`
   sentinel field to the cache JSON (`{"v": 2, "narrative": ..., ...}`)
   and treat any cache without `v: 2` as invalid. This survives future
   prompt revisions cleanly.

2. **Haiku returns malformed JSON.** Existing fallback (`narrative.py:122`)
   sets `expert = raw, layman = ""`. With layman empty, the existing
   render-path at `dashboard.py:1039` already hides the toggle button.
   No new handling needed.

3. **Haiku ignores band-calibration and writes generic action.** This
   is a prompt-quality risk, not a code risk. Acceptable on first ship;
   if Ian sees mis-calibrated layman text in real bands, iterate the
   prompt then.

4. **localStorage unavailable** (private mode, old browser). Wrapped in
   `try/catch`; toggle still works in-session, just doesn't persist.

**Success criteria:**

- `python run_dashboard.py --no-cache --no-alerts --quiet` runs, loads
  the dashboard, both registers appear, toggle works.
- Toggling to "Plain English" then refreshing the page leaves the layman
  view active.
- Layman text on a current run includes a household-level action prompt
  (visual check; not asserted in tests).
- All 219 tests still pass; new test for `dashboardNarrativeRegister`
  presence in rendered HTML passes.
- `data/cache/narrative.json` is regenerated cleanly after the cache
  versioning change (delete-once or auto-invalidated).

**Non-goals:**

- Asset-allocation suggestions in the layman register. Hard line.
- A third "intermediate" register (informed-but-not-pro). Two is enough.
- Per-bucket plain-English narratives. Out of scope; would balloon
  Haiku token use and create N×2 prompts to maintain.
- Server-side rendering of the user's last choice. localStorage is
  sufficient for a single-user dashboard; the dashboard is rebuilt fresh
  every morning anyway.

---

## Brief 24 — JSON sidecar for downstream consumers

**Dependencies:** None. Touches `run_dashboard.py` after the existing
`write_dashboard()` call; no scoring / alerts / config changes.

**Problem:** The full scoring dict — composite, bands, all 11 buckets, all
26 indicators with raw/score/percentile/band, regime, shock_type, stale
list, provenance — is computed every run and lives in memory inside
`run_dashboard.py:main`. The only persisted outputs today are
`dashboard.html` (not machine-parseable) and `data/history.csv` (composite
+ bucket scores only — no per-indicator detail, no stale list, no
shock_type, no regime-adjusted composite). The sibling repo
`tactical_markets_trading` needs to consume the regime / health view to
modulate position sizing. With no JSON contract, it would have to either
reverse-engineer `history.csv` (loses indicator detail) or import
`src.scoring` and re-fetch (couples the bot's cadence to the dashboard's
and double-pays for FRED/yfinance). Neither is acceptable long-term.

**Design decision:** Emit `data/latest.json` once per run, after
`write_dashboard()` returns and after the dashboard-specific augmentations
to `scoring` (composite_regime_adj, composite_regime_adj_label) have been
applied. Strip the `_series` blobs (UI-only; large; the bot has no use for
them). Stamp with `schema_version: 1`, `weights_hash`, and `code_sha` so
the bot can refuse to trade on an unrecognised hash. Do not couple to
GitHub Pages publish — the sidecar lives at `data/latest.json` in the
working dir, same place as `history.csv` and `alert_state.json`. The bot
reads from there via shared filesystem (both repos live under
`c:\Users\rekwa\ian_projects\`).

This is intentionally a one-way contract: the dashboard writes, the bot
reads. The dashboard does NOT need to know the bot exists. No HTTP, no
queue, no DB — a single JSON file on disk is the simplest thing that
works and makes failures obvious (stale mtime = automation broken).

**Files to change:**

1. **`src/history.py`** — add a sidecar writer next to `log_run`:
   ```python
   SIDECAR_FILE = DATA_DIR / "latest.json"
   SIDECAR_SCHEMA_VERSION = 1

   def write_latest_sidecar(scoring: dict, shock_type: str | None = None) -> None:
       """
       Emit a machine-readable snapshot of the latest run for downstream
       consumers (e.g. tactical_markets_trading). Strips _series blobs.
       """
       import json
       payload = {
           "schema_version": SIDECAR_SCHEMA_VERSION,
           "run_timestamp": scoring["run_timestamp"],
           "composite": scoring["composite"],
           "composite_naive": scoring.get("composite_naive"),
           "composite_regime_weighted": scoring.get("composite_regime_weighted"),
           "regime_weights_applied": scoring.get("regime_weights_applied", False),
           "composite_band": scoring["composite_band"],
           "composite_short": scoring.get("composite_short"),
           "composite_short_band": scoring.get("composite_short_band"),
           "composite_regime_adj": scoring.get("composite_regime_adj"),
           "composite_regime_adj_label": scoring.get("composite_regime_adj_label"),
           "regime": scoring.get("regime"),
           "shock_type": shock_type,
           "red_count": scoring["red_count"],
           "orange_count": scoring["orange_count"],
           "yellow_count": scoring["yellow_count"],
           "stale_indicators": scoring.get("stale_indicators", []),
           "errors": scoring.get("errors", []),
           "buckets": _strip_series(scoring["buckets"]),
           "weights_hash": _weights_hash(),
           "code_sha": _code_sha(),
       }
       DATA_DIR.mkdir(parents=True, exist_ok=True)
       tmp = SIDECAR_FILE.with_suffix(".json.tmp")
       tmp.write_text(json.dumps(payload, indent=2, default=str))
       tmp.replace(SIDECAR_FILE)  # atomic rename so readers never see a half-written file

   def _strip_series(buckets: dict) -> dict:
       out = {}
       for bkey, b in buckets.items():
           out[bkey] = {
               "label": b["label"], "weight": b["weight"],
               "score": b["score"], "score_short": b.get("score_short"),
               "band": b["band"],
               "indicators": {
                   ikey: {k: v for k, v in i.items() if k != "_series"}
                   for ikey, i in b["indicators"].items()
               },
           }
       return out
   ```

2. **`run_dashboard.py`** — one call, after `write_dashboard()` returns and
   after `scoring["composite_regime_adj*"]` are set (so the sidecar sees
   the same scoring dict the dashboard rendered):
   ```python
   from src.history import write_latest_sidecar
   ...
   output_path = write_dashboard(...)
   write_latest_sidecar(scoring, shock_type=shock_type)
   ```
   Place the call *before* `_publish_to_github`, so a sidecar exists even
   if publish fails. Place it *after* the `composite_regime_adj` lines
   (~line 225 today) so those keys are populated.

3. **`tests/test_sidecar.py`** — new test file:
   - Build a minimal valid `scoring` dict (1 bucket, 1 indicator,
     include `_series`). Call `write_latest_sidecar`. Assert:
     - file exists at `data/latest.json`
     - `json.loads` succeeds
     - `schema_version == 1`
     - `weights_hash` is an 8-char hex string (or empty if no weights.yaml in test cwd — handle both)
     - `_series` keys are absent from indicators
     - All top-level required keys present (use a constant list).
   - Run the writer twice in a row and assert the second call doesn't crash and produces a valid file (atomic-rename behavior).

**Edge cases:**

- **Missing optional keys.** `compute_composite` sets all the fields the
  payload references; the `.get()` calls are belt-and-braces for older
  scoring dicts in tests. Don't introduce defaults that mask real bugs in
  the producer.
- **Partial runs.** If `compute_composite` raised mid-run, `main` would
  exit before reaching the sidecar — that's correct, we want absence-on-
  failure so a stale `mtime` signals trouble. Don't add a try/except
  around the writer call.
- **Concurrent reads.** The atomic `tmp → replace` rename means a reader
  either sees the old file or the new file, never a half-written one.
  This is the *only* concurrency guarantee — readers must still tolerate
  the file being briefly absent (during the rename window, `replace` is
  atomic on Windows NTFS for same-volume operations).
- **`_series` blob size.** Indicators with 10y daily history have ~2,500
  date+value pairs each × 26 indicators ≈ ~150KB extra if left in. Cheap
  to strip; expensive for the bot to parse and ignore. Strip them.
- **`shock_type` parameter.** Currently computed inside `run_dashboard.py`
  via `classify_shock_type(history, scoring)`. Pass it in rather than
  re-computing inside the writer — keeps the writer pure and avoids
  loading history twice.

**Success criteria:**

- `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  runs cleanly and produces `data/latest.json`.
- `python -c "import json; print(sorted(json.load(open('data/latest.json')).keys()))"`
  shows all top-level keys.
- `data/latest.json` is < 50KB (sanity check that `_series` stripping
  worked).
- `tests/test_sidecar.py` passes; full suite stays green (195/195+).
- Manual: open `data/latest.json` in an editor, eyeball that bucket /
  indicator structure matches the in-memory shape documented in
  `_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md`.

**Non-goals:**

- Multiple-run history sidecar (history.csv already does this).
- HTTP / pubsub / queue. File-on-disk is the contract.
- Bumping schema_version. Only do that when an existing field's meaning
  changes or a required field is dropped. Adding new optional fields
  does NOT require a version bump; the bot reads defensively.
- Documenting the contract in `dashboard.html`. The contract lives in
  the integration brief and (eventually) a `CHANGELOG.md` section if
  schema_version ever moves.

**Downstream coordination (out of scope for Sonnet to implement, but
worth flagging):**

- `tactical_markets_trading` should read `data/latest.json` via an
  absolute path it knows about, validate `schema_version == 1`,
  `weights_hash` is in its known-good set, `run_timestamp` < 26h old,
  `errors` is empty, then act. That code lives in the other repo.

---

## Brief 25 — Phase H: Phone-triggered dashboard refresh via GitHub Actions

**Dependencies:** None. Net-new infrastructure; the existing morning
automation continues unchanged.

**Problem:** Ian wants to refresh the published dashboard from his phone
without waiting for the 7:30 AM scheduled run. Use case is mid-day
curiosity ("what does the composite look like *now*?"), not crisis
response. Current state: only the 7:30 AM Task Scheduler run publishes —
the rest of the day Ian sees stale data on the phone-accessed GitHub
Pages URL.

**Design decision — locked: GitHub Actions `workflow_dispatch` triggered
from an iOS Shortcut via the GitHub API.** No laptop dependency, no home
network dependency, runs from cellular trivially, free for this public
repo, and the existing `.github/workflows/tests.yml` already proves the
Python runtime works in CI without modification.

The four alternatives Ian's TODO entry listed, and why each loses:

1. **Pushover callback URL → local HTTP listener.** Pushover doesn't
   have a meaningful callback feature for this — the "supplementary URL"
   is just a clickable link in the notification, and the Open Client API
   needs a persistent connection from a running listener. Requires the
   laptop awake and reachable from cellular (ngrok tunnel or port
   forward). Solves zero of the wake/network problems.

2. **iOS Shortcut → SSH into laptop.** Requires laptop awake, sshd
   running, and either port-forwarded SSH from cellular or a relay
   (Tailscale/ZeroTier). Still doesn't solve the wake problem — Wake-on-
   LAN over the internet is fragile and needs router-side magic-packet
   forwarding. Most failure modes of any option.

3. **GitHub Actions `workflow_dispatch`.** ✓ Picked. Detailed below.

4. **ntfy.sh / pub-sub listener.** Same wake problem as options 1 and 2:
   the laptop must be awake to receive. ntfy itself is fine; the
   laptop-side dependency isn't.

The wake-on-command problem is the load-bearing constraint. Only option
3 sidesteps it entirely by not involving the laptop at all.

**Why this is safe additive infrastructure:**

The on-demand workflow only *publishes the dashboard* (and writes
`data/latest.json`) — it does NOT mutate the canonical state files
(`history.csv`, `alert_state.json`, `alert_log.jsonl`). The morning
7:30 AM laptop run remains the single owner of history and alert state.
On-demand runs are read-only-with-respect-to-history.

**Files to change:**

1. **New `.github/workflows/on-demand-dashboard.yml`:**

   ```yaml
   name: on-demand-dashboard
   on:
     workflow_dispatch:
   permissions:
     contents: write
   jobs:
     run:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
         - run: pip install -r market_dashboard/requirements.txt
         - name: Run dashboard (ondemand mode)
           env:
             FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
             ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
           run: |
             cd market_dashboard
             python run_dashboard.py --ondemand --no-alerts --quiet
         - name: Commit and push refreshed dashboard
           run: |
             git config user.name "github-actions[bot]"
             git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
             cp market_dashboard/output/dashboard.html docs/index.html
             if [ -f market_dashboard/output/backtest_report.html ]; then
               cp market_dashboard/output/backtest_report.html docs/backtest_report.html
             fi
             git add docs/index.html docs/backtest_report.html
             if git diff --cached --quiet; then
               echo "No dashboard changes to publish."
               exit 0
             fi
             git commit -m "On-demand dashboard refresh $(date -u +%Y-%m-%dT%H:%M:%SZ)"
             git push origin main
   ```

   Note: the workflow does the publish step itself rather than calling
   `_publish_to_github()`. The existing function assumes a local
   `_genai_tmp/` clone; in CI we're already inside the checked-out repo,
   so directly copying + committing is simpler. Don't try to make
   `_publish_to_github()` "smart" about both contexts — that's the
   abstraction trap CLAUDE.md warns about.

2. **`run_dashboard.py` — new `--ondemand` flag.**

   Add to the argparse block:
   ```python
   parser.add_argument("--ondemand", action="store_true",
       help="On-demand refresh: skip history/alert state mutations. "
            "Use for CI-triggered runs that should not pollute the "
            "morning automation's canonical state files.")
   ```

   In `main()`, gate the state-mutating steps on `not args.ondemand`:

   - **Skip `log_run(scoring)` and `prune_history()`** at lines 182–183.
   - **Skip `send_alerts(scoring, env, history)`** at line 205 (also
     skip `score_past_alerts(history)` at 196 since alert_log.jsonl
     won't exist in CI — and even if we mounted it, on-demand runs
     shouldn't re-score alerts).
   - **Skip `send_weekly_digest`** at line 248.
   - **Skip `send_heartbeat`** at line 252.

   Keep running: `compute_composite`, `annotate_results`, remediation,
   news, narrative, `write_dashboard`, `write_latest_sidecar`.

   When `--ondemand` is set, `load_history(days=90)` will load an empty
   DataFrame in CI (no history.csv). The dashboard already handles
   empty-history gracefully (momentum returns all-None, shock_type
   returns "insufficient", trend chart shows the day-1 placeholder).
   This is acceptable — the on-demand view is a *current snapshot*, not
   a historical view. If Ian wants the trend chart populated, he checks
   in the morning after the 7:30 AM run.

   The `--ondemand` flag implies `--no-alerts` semantically, but the
   workflow above passes `--no-alerts` explicitly for clarity in CI
   logs. Don't make `--ondemand` automatically set `--no-alerts` in
   argparse — keep flags orthogonal.

3. **`tests/test_ondemand.py` (new file)** — one test that with
   `args.ondemand = True`:
   - `log_run` is not called
   - `send_alerts` is not called
   - `write_dashboard` IS called
   - `write_latest_sidecar` IS called

   Use `unittest.mock.patch` to spy on each. Run `main()` in a tmp_path
   chdir with mocked `compute_composite` returning a minimal valid
   scoring dict so the orchestration runs end-to-end without network
   calls. Pattern: see `tests/test_remediation.py` for a similar
   end-to-end harness shape.

**Secrets to add in GitHub repo Settings → Secrets and variables → Actions:**

- `FRED_API_KEY` — required; without it most indicators fall back to
  cached or empty data.
- `ANTHROPIC_API_KEY` — for the Haiku narrative call. Without it the
  narrative card renders empty (existing fallback at
  `narrative.py:99`). Acceptable degradation.

Not needed: `PUSHOVER_*`, Twilio, `GMAIL_APP_PASSWORD` — those are
alert-only and on-demand mode skips alerts.

**iOS Shortcut setup (Ian one-time, document only — no code):**

1. Create a GitHub Personal Access Token (fine-scoped):
   - Repo: `IanRekward/GenAI_Messing`
   - Permissions: `Actions: Read and write`, `Contents: Read-only`.
   - Expiration: 1 year (the longest fine-scoped tokens allow). Calendar
     a renewal.

2. iOS Shortcut steps:
   - **Get contents of URL**:
     - URL: `https://api.github.com/repos/IanRekward/GenAI_Messing/actions/workflows/on-demand-dashboard.yml/dispatches`
     - Method: POST
     - Headers: `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`
     - Request body (JSON): `{"ref": "main"}`
   - **Show notification**: "Dashboard refresh queued — ~3 min."
   - **Wait 180 seconds** (optional; GH Actions cold start ~30s + run
     ~2 min).
   - **Open URL**: the GitHub Pages dashboard URL.

   Latency from tap to refreshed page: ~3–4 minutes worst case. That's
   fine for the stated use case (curiosity, not crisis).

**Edge cases:**

1. **Concurrent run with morning automation.** If Ian taps at 7:31 AM
   while the laptop's morning run is still in flight, both runs try to
   push to `docs/index.html`. The CI push will either race-win or get
   rejected by GitHub on push (non-fast-forward). Two acceptable
   behaviors:
   - Let the CI push retry-on-conflict (3 attempts with backoff) using
     `git pull --rebase` between tries.
   - Or just let it fail and Ian re-taps. Failure mode is benign.

   Pick the retry approach — adds ~6 lines to the workflow YAML and
   makes morning-window taps reliable:
   ```yaml
   for i in 1 2 3; do
     git push origin main && break
     git pull --rebase origin main
   done
   ```

2. **PAT expires / revoked.** Shortcut returns 401. Ian sees no refresh
   and no push notification. Acceptable — annoying but not silent
   wrong-data. Add a Shortcut step that checks the HTTP response status
   and shows a different notification on failure.

3. **GH Actions outage.** Tap does nothing. No fallback. The morning
   automation still runs locally on its own track, so the dashboard
   isn't lost — it's just stale until 7:30 AM next day. Acceptable for
   a low-priority feature.

4. **FRED/yfinance rate-limiting from CI IPs.** GitHub Actions runs from
   AWS IP ranges that some upstream APIs throttle aggressively. FRED in
   particular has been documented to throttle GH Actions runners. If
   this bites, the symptom is a dashboard with many indicators in
   "stale" state. Mitigation if it happens: cache the indicator-fetch
   layer in a GitHub Actions cache keyed by date, so repeated on-demand
   taps within a day reuse the morning run's data. Don't pre-emptively
   build this — wait to see if it's a real problem.

5. **`data/latest.json` written by CI is ephemeral.** It's not pushed
   back to the repo (only `docs/index.html` is committed), so the
   trading bot's local `data/latest.json` is unchanged. That's correct:
   the bot's signal cadence is daily, owned by morning automation. If a
   future use case requires on-demand sidecar updates for the bot,
   that's a separate brief.

6. **Empty trend chart on day-1 / empty-history runs.** Dashboard
   already handles this. Visual check during first deploy.

**Success criteria:**

- `on-demand-dashboard.yml` workflow visible in the repo's Actions tab.
- Manually triggering it from the GitHub UI runs to completion in
  under 4 minutes.
- A commit appears on `main` titled "On-demand dashboard refresh ...".
- The GitHub Pages URL reflects the refresh (new timestamp on the
  rendered page).
- The iOS Shortcut, on tap, returns HTTP 204 from the API and the
  refresh completes.
- After the on-demand run, the morning automation runs normally the
  next day (verify by checking `data/history.csv` mtime advances on
  the next 7:30 AM run and contains no gaps caused by the on-demand
  run).
- `tests/test_ondemand.py` passes; full suite stays green.

**Non-goals:**

- Migrating the morning automation to CI. See "Future consideration"
  below — that's a separate decision Ian should make explicitly, not
  smuggle in as part of Phase H.
- Authentication beyond a PAT in iOS Shortcuts. A real auth layer (e.g.
  a thin Cloudflare Worker that exchanges a passphrase for a GH API
  call) is overkill for a single-user tool.
- Real-time dashboard refresh. The 3–4 minute cycle is fine; trying to
  optimise further means caching FRED responses in the workflow, which
  is its own brief.
- An Android Tasker equivalent. Ian's on iOS; cross-platform isn't a
  goal here.
- Removing the local Task Scheduler entries. They keep working in
  parallel; Phase H is additive.

**Future consideration (separate brief, not part of this one):**

Once Phase H is validated for ~2 weeks, the natural next step is to
*also* migrate the morning 7:30 AM run to GH Actions (cron schedule),
retiring the laptop-side Task Scheduler entirely. That addresses TODO
"Issue 1" (the 9:30 AM misfire from 2026-04-29) at the root —
laptop-wake fragility goes away when no laptop is involved. The
migration requires solving the canonical-state question: where does
`history.csv` live if not on Ian's laptop? Options: commit it back to
the repo from CI (simple, public — fine since the dashboard is public
anyway), or move to a small Postgres/Supabase instance (more work, no
clear benefit at single-user scale). Recommended path when ready:
commit back to repo, .gitignore the cache files, accept the public
history as a feature not a bug. Defer this decision until Phase H is
proven reliable.

---

## Brief 26 — Regime-weights review (5/30) + W1 paired-commit protocol

Produced by Opus 4.7 on 2026-05-15. Two deliverables, intentionally bundled:
(1) the 5/30 regime-weights review decision, (2) a reusable W1 protocol for
any future `weights_hash` change. The W1 half is generic — copy/paste for
any subsequent recalibration; the 5/30 half is the first invocation.

### Why bundle them

The 5/30 checkpoint is the first event that exercises the W1 contract with
the trading bot. Working out the protocol mid-decision is the wrong time;
locking it in *before* the data review removes one source of pressure on the
day. The W1 half outlives 5/30 — it's the playbook for every recalibration.

### Locked decisions (do not relitigate on 5/30)

- **Allow-list update lives in the bot repo, not MACRO.** MACRO ships the
  weights change; the bot's `data/macro_weights_allowlist.json` records the
  human review. This matches the bot's AR12 ("forces human review when MACRO
  recalibrates"). MACRO does not modify the bot's allow-list — it provides
  the hash and the diff summary; Ian (or whoever runs the review) edits the
  bot file.
- **Paired commits, not atomic.** The two repos are siblings, not a
  monorepo. The protocol sequences the commits so the window where MACRO has
  shipped a new hash but the bot hasn't allow-listed it is minimized — but
  it is non-zero. The bot is designed to block-not-crash in that window,
  which is the correct failure mode.
- **No automation of the bot allow-list.** The human review is the point.
  Don't script around it.
- **`weights_hash` is MD5 of the file bytes, first 8 hex chars.** Defined in
  `src/history.py:_weights_hash()`. Any byte change to `config/weights.yaml`
  produces a new hash — including whitespace and comments. Treat YAML
  comment edits as a hash-changing operation.

### Part A — The 5/30 regime-weights review decision

**Trigger:** the 2026-05-30 entry in TODO.md Phase E.

**Steps:**

1. Catch up: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -10`.
2. Run the report: `python -m src.recalibrate --regime`. This prints a
   proposed `regime_weights:` YAML block to stdout. Do **not** write it
   anywhere yet.
3. Inspect `data/history.csv` for regime distribution since 2026-04-25
   (when Brief 10A landed). Specifically:
   - `regime` column populated on every row (sanity check)
   - At least one stretch where `regime=high` (otherwise we have no
     evidence the regime layer would have done anything different)
   - `composite_regime_weighted` vs `composite_naive` divergence on those
     high-regime rows: is the divergence small (<3 points) and in a
     defensible direction?
4. Inspect `output/backtest_report.html` per-regime IC table (Brief 10B
   wired it). Look for: rates_curve and inflation IC positive in high
   regime; no bucket flipping sign across regimes (a sign-flip suggests
   the regime layer is amplifying noise, not signal).
5. **Decision gate — flip `regime_weights.enabled: true` only if ALL of:**
   - (a) ≥1 high-regime episode with sensible divergence direction
   - (b) per-regime IC table shows rates_curve and inflation positive in
     high regime
   - (c) `regime` column doesn't flap (≤3 transitions across the May
     review window — Brief 10A applied 5-day smoothing + 1.0 VIX
     hysteresis specifically to prevent flapping; if it's still flapping,
     the classifier needs tightening, not the multipliers)
6. **If the gate fails:** leave `enabled: false`, note the failing
   criterion in TODO.md, schedule a re-review (suggest +30 days). No bot
   coordination needed — hash unchanged.
7. **If the gate passes:** proceed to Part B (the W1 protocol below) using
   the proposed YAML block from step 2.

### Part B — W1 paired-commit protocol (reusable for any hash-changing weights edit)

This is the playbook. Save this section; reuse for any future change to
`config/weights.yaml`. Steps assume you're starting from a clean tree on
both repos.

1. **Edit `config/weights.yaml` in the primary dir** (`market_dashboard/`).
   Apply the change. Do not commit yet.
2. **Compute the new hash** before doing anything else:
   ```bash
   cd /c/Users/rekwa/ian_projects/market_dashboard && \
     python -c "import hashlib; print(hashlib.md5(open('config/weights.yaml','rb').read()).hexdigest()[:8])"
   ```
   Save the 8-char string. Call it `NEW_HASH`.
3. **Capture a one-line diff summary** for the bot's allow-list record.
   Example: `"5/30 regime review: enabled flipped true; high-regime
   multipliers unchanged from Option A"`. Keep it under ~100 chars.
4. **Update the bot's allow-list** at
   `tactical_markets_trading/data/macro_weights_allowlist.json`. Append
   `NEW_HASH` to `allowed_hashes[]` and add a sibling structured record
   keyed by hash. Use this shape (the existing file's `_bootstrap_*`
   keys are the precedent):
   ```json
   {
     "_comment": "...",
     "_bootstrap_date": "2026-05-13",
     "_bootstrap_source": "...",
     "allowed_hashes": ["2532e380", "<NEW_HASH>"],
     "review_log": {
       "<NEW_HASH>": {
         "added_date": "<YYYY-MM-DD>",
         "added_by": "<reviewer>",
         "macro_commit_preview": "<short SHA if known, else 'pending'>",
         "summary": "<one-line diff summary from step 3>"
       }
     }
   }
   ```
   First invocation creates the `review_log` block; subsequent invocations
   add a new key under it. The bot reads only `allowed_hashes[]` — the
   `review_log` is human audit context. Do not remove old hashes; the bot
   may see them in historical `latest.json` files referenced in
   `trades.jsonl`.
5. **Sync MACRO changes to `_genai_tmp/`** per CLAUDE.md two-repo workflow:
   ```bash
   cp market_dashboard/config/weights.yaml \
      _genai_tmp/market_dashboard/config/weights.yaml
   ```
6. **Run MACRO dry-run** to verify the new hash is what shows up in
   `latest.json`:
   ```bash
   cd /c/Users/rekwa/ian_projects/market_dashboard && \
     python run_dashboard.py --no-cache --no-news --no-alerts --quiet && \
     python -c "import json; d=json.load(open('data/latest.json')); print(d['weights_hash'])"
   ```
   The printed hash must equal `NEW_HASH`. If not, stop and diagnose
   before committing anything.
7. **Commit MACRO first** (the producer of the new hash):
   ```bash
   cd /c/Users/rekwa/ian_projects/_genai_tmp && \
     git add market_dashboard/config/weights.yaml && \
     git commit -m "market_dashboard: <change description> (weights_hash NEW_HASH)" && \
     git push origin main
   ```
   Including `NEW_HASH` in the commit subject lets the bot allow-list
   record reference back to the producing commit.
8. **Commit the bot allow-list second**, immediately:
   ```bash
   cd /c/Users/rekwa/ian_projects/_genai_tmp && \
     git add tactical_markets_trading/data/macro_weights_allowlist.json && \
     git commit -m "tactical_markets_trading: allow-list weights_hash NEW_HASH (<one-line summary>)" && \
     git push origin main
   ```
9. **Verify the bot won't block.** From the bot side:
   ```bash
   cd /c/Users/rekwa/ian_projects/tactical_markets_trading && \
     python -c "import json; print('<NEW_HASH>' in json.load(open('data/macro_weights_allowlist.json'))['allowed_hashes'])"
   ```
   Expected: `True`.

### Skipping the protocol — when NOT to invoke

Not every YAML edit needs the bot dance. Skip the protocol when:

- The change is to a non-weights YAML (thresholds, tooltips, events). The
  hash MD5s only `config/weights.yaml`.
- A purely-formatting edit was reverted before commit (hash didn't actually
  change on disk).

Invoke the protocol when:

- Any byte of `config/weights.yaml` changes (including whitespace or YAML
  comments — they affect MD5).
- A new indicator/bucket is added, removed, or reweighted.
- `regime_weights.enabled` is flipped or any multiplier changes.

### Edge cases

- **Bot hasn't wired MACRO consumption yet (today's state).** Per
  bot-integration-asks.md, `macro_consumer.py` is committed but not yet
  in the entry flow. The allow-list update is still required — the bot's
  Phase 2 wiring will read it the moment it ships. Don't defer.
- **Two recalibrations in one day.** Run the protocol twice; allow-list
  accumulates both new hashes. Avoid this if possible by batching.
- **Hash collision with a prior recalibration** (extremely unlikely with
  MD5/8 hex). If `NEW_HASH` is already in `allowed_hashes[]`, you've
  somehow produced byte-identical YAML to a prior version — investigate
  before pushing. Either you reverted by accident, or there's a real
  collision to investigate.
- **CI/laptop drift on hash.** `_weights_hash()` reads the file from the
  process cwd, so different machines will produce the same hash for the
  same file bytes. Windows line endings have not been an issue (git's
  `core.autocrlf` keeps `\n` in the working tree on this repo) — but if
  a future `latest.json` shows an unexpected hash, check
  `git diff config/weights.yaml` first.

### Files touched (5/30 invocation, if gate passes)

- `config/weights.yaml` — flip `regime_weights.enabled: true`, possibly
  refresh multipliers from `recalibrate --regime` output
- `tactical_markets_trading/data/macro_weights_allowlist.json` — new
  hash + review_log entry
- `TODO.md` — mark 5/30 checkpoint complete; link to commit SHA

### Success criteria

- 5/30 review decision recorded in TODO.md (flipped or deferred — both
  are valid outcomes, the gate is what matters)
- If flipped: bot allow-list contains the new hash before the next bot
  run; `latest.json` `weights_hash` matches; no `MacroValidationError`
  in bot logs on next consumption
- Protocol section above is reusable verbatim for the next recalibration
  (no Brief-26-specific assumptions baked in)

---

## Brief 27 — Parallel indicator fetch via ThreadPoolExecutor

**Status: shipped 2026-05-27. 250/250 tests.**

**Problem:** `compute_composite()` in `src/scoring.py` fetches ~26
indicators serially via `_fetch_indicator()`. Each indicator is I/O-bound
(FRED, yfinance, TreasuryDirect). On cold-cache daily runs the wall time
is dominated by sequential network round-trips. Parallelizing the top-level
fetch is the single biggest user-visible win still on the table from the
2026-05-27 simplify pass.

**Out of scope:** `backtest.py:_fetch_raw` is left serial. Backtest
parallelization is a separate brief if ever needed — the daily run is the
hot path.

### Design decisions — LOCKED

1. **Default worker count: 8.** Override via `MAX_FETCH_WORKERS` env var.
   FRED rate limit is 120 req/min; Yahoo Finance soft limit unreached at
   this scale. 8 workers ≈ 2 "waves" across the 26 indicators.

2. **Serial fallback escape hatch.** `MAX_FETCH_WORKERS=1` MUST use a
   plain `for`-loop, not `ThreadPoolExecutor(max_workers=1)`. This is
   the production-safety lever: if a future change in yfinance breaks
   concurrent fetches, set the env var and revert to deterministic
   serial execution without code changes.

3. **Computed handlers run serially within their worker.** Handlers
   like `_handler_treasury_auction_stress`, `_handler_vix_term_structure`,
   `_handler_copper_gold_ratio` etc. internally call
   `fetch.fetch_yfinance_series()` 2–3 times. Those inner calls stay
   serial — they do NOT submit back to the pool. This avoids nested-
   submission deadlock and keeps reasoning simple. Parallelism is only
   across the ~26 top-level indicators.

4. **VIX regime fetch joins the plan.** The inline `fetch.fetch_yfinance_series("^VIX", ...)`
   at `src/scoring.py:469` (used for `classify_vix_regime`) gets a
   virtual indicator slot in the fetch phase so it parallelizes with
   the others. It dedupes with the existing `vix` indicator fetch via
   the shared cache layer — same ticker, same cache file.

5. **Three-phase refactor in `compute_composite`:**
   - **Plan** — flatten weights into a list of `(bkey, ikey, icfg)`
     triplets plus the VIX regime fetch.
   - **Fetch** — dispatch through `_fetch_indicators_parallel`. Each
     completed future is caught individually for `StaleCacheFallback`
     and `Exception`. Results collected into a `{ikey: FetchOutcome}`
     dict where `FetchOutcome` is a 4-tuple `(status, raw, series, msg)`:
       - `"ok"`: `(raw: float, series: pd.Series, None)`
       - `"stale"`: `(raw: float, series: pd.Series, msg: str)` — used the
         stale cache; warning string set
       - `"error"`: `(None, None, msg: str)` — hard fail
   - **Score** — iterate buckets, read from results map, branch on
     status. This phase has zero I/O — pure CPU. Easier to test.

6. **Deterministic output.** Parallel execution produces non-deterministic
   completion order, which currently bleeds into `errors`, `warnings`,
   and `stale_indicators` lists in scoring output. Sort all three
   alphabetically at the end of `compute_composite` so downstream
   consumers (sidecar, history.csv, the bot) see stable diffs.
   Grep confirmed no test asserts list ordering — only `any()` checks
   and empty-list assertions.

7. **Test mocking still works unchanged.** All scoring tests patch
   `src.scoring._fetch_indicator` via `monkeypatch.setattr`, which
   substitutes the module attribute. The patched function is visible
   from all worker threads (Python GIL + thread-safe attribute lookup).
   Confirmed against `tests/test_scoring.py`, `tests/test_remediation.py`,
   `tests/test_alert_controls.py`.

8. **No timeout added.** Today's code has no per-call timeout on
   `yf.download`. Parallel doesn't make this worse. Existing
   retry/backoff in `fetch.fetch_yfinance_series` bounds total wait
   to ~21s per ticker via `_RETRY_DELAYS = [1, 4, 16]`. Out of scope
   to add timeouts.

9. **No rate limiting.** 8 concurrent requests across mixed endpoints
   (FRED + yfinance + TreasuryDirect) is well under any documented or
   observed limit. Re-evaluate if a real rate-limit error is seen.

### Implementation spec for Sonnet

**File: `src/scoring.py`**

Add a new private function above `compute_composite`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# FetchOutcome = (status, raw, series, msg) where status ∈ {"ok", "stale", "error"}
FetchOutcome = tuple  # (str, float | None, pd.Series | None, str | None)


def _fetch_indicators_parallel(
    specs: list[tuple[str, dict]],
    env: dict,
    manual: dict,
) -> dict[str, FetchOutcome]:
    """Fetch every indicator in `specs` and return {ikey: (status, raw, series, msg)}.

    status="ok"     → fetch succeeded (raw, series, None)
    status="stale"  → live fetch failed, used cache (raw, series, warning_msg)
    status="error"  → hard failure (None, None, error_msg)

    Serial when MAX_FETCH_WORKERS=1; otherwise threaded across `specs`.
    """
    workers = int(env.get("MAX_FETCH_WORKERS", 8))

    def _run_one(ikey: str, icfg: dict) -> FetchOutcome:
        try:
            raw, series = _fetch_indicator(ikey, icfg, env, manual)
            return ("ok", raw, series, None)
        except StaleCacheFallback as stale:
            return ("stale", float(stale.series.iloc[-1]), stale.series,
                    f"STALE CACHE: {ikey} — {stale}")
        except Exception as exc:
            return ("error", None, None, str(exc))

    if workers <= 1:
        return {ikey: _run_one(ikey, icfg) for ikey, icfg in specs}

    out: dict[str, FetchOutcome] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(_run_one, ikey, icfg): ikey
                      for ikey, icfg in specs}
        for fut in as_completed(future_map):
            out[future_map[fut]] = fut.result()
    return out
```

Then refactor `compute_composite`:

```python
def compute_composite(weights, env, manual) -> dict:
    cadence_cfg = fetch.load_cadence_config()
    short_years = int(env.get("HISTORY_YEARS_SHORT", 3))
    short_cutoff = pd.Timestamp.now() - pd.DateOffset(years=short_years)

    # Phase 1: plan
    specs: list[tuple[str, dict]] = [
        (ikey, icfg)
        for bcfg in weights["buckets"].values()
        for ikey, icfg in bcfg["indicators"].items()
    ]
    # Add VIX regime fetch as a virtual indicator (no bucket, no scoring)
    vix_regime_spec = ("__vix_regime__", {
        "source": {"type": "yfinance", "ticker": "^VIX"},
        "label": "VIX (regime)", "weight": 0,
    })

    # Phase 2: fetch (parallel)
    fetched = _fetch_indicators_parallel(specs + [vix_regime_spec], env, manual)

    # Phase 3: score (CPU-only)
    bucket_results: dict = {}
    errors: list[str] = []
    warnings: list[str] = []
    stale_indicators: list[str] = []

    for bkey, bcfg in weights["buckets"].items():
        # ... existing per-bucket scoring loop, but instead of calling
        # _fetch_indicator inline, consume fetched[ikey]:
        for ikey, icfg in bcfg["indicators"].items():
            iweight = float(icfg["weight"])
            invert = bool(icfg.get("invert", False))
            status, raw, series, msg = fetched[ikey]

            if status == "error":
                errors.append(f"{ikey}: {msg}")
                # ... same error-path _build_ind_record as today
                continue
            if status == "stale":
                warnings.append(msg)
            # ... rest of success path unchanged (staleness check, percentile, score)

    # VIX regime classification (consume fetched[__vix_regime__])
    regime_info: dict = {}
    vix_status, _, vix_series, _ = fetched["__vix_regime__"]
    if vix_status in ("ok", "stale") and vix_series is not None:
        try:
            regime_info = classify_vix_regime(vix_series, _load_prev_regime())
        except Exception as exc:
            errors.append(f"vix_regime: {exc}")
    elif vix_status == "error":
        errors.append(f"vix_regime: {fetched['__vix_regime__'][3]}")

    # ... rest of compute_composite (regime weights, composite calc) unchanged

    # Determinism: sort for stable output
    errors.sort()
    warnings.sort()
    stale_indicators.sort()

    result = { ... }
    return result
```

**File: `tests/test_parallel_fetch.py`** (new)

Three tests are sufficient:

```python
def test_parallel_serial_fallback_matches(monkeypatch):
    """MAX_FETCH_WORKERS=1 (serial) and =8 (parallel) produce identical results."""
    # Patch _fetch_indicator with a known-good function, run both modes,
    # assert composite scores are equal.

def test_parallel_isolates_per_indicator_failures(monkeypatch):
    """A single-indicator exception does not short-circuit the others."""
    # Patch _fetch_indicator: half the keys succeed, half raise. Assert all
    # successful keys score normally, all failures appear in errors[],
    # and `errors` is sorted alphabetically.

def test_parallel_handles_stale_cache_fallback(monkeypatch):
    """StaleCacheFallback from one indicator is recorded as a warning,
    not an error, and the stale series is used for scoring."""
    # Patch _fetch_indicator: one key raises StaleCacheFallback(series=...).
    # Assert that key has a non-50 score derived from the stale series,
    # and a STALE CACHE: warning appears in warnings[].
```

**File: `CLAUDE.md`**

Add a new bullet under "Technical gotchas":

> - **Parallel indicator fetch via `MAX_FETCH_WORKERS`.** `compute_composite`
>   parallelizes the ~26 top-level indicator fetches across 8 workers by
>   default. Set `MAX_FETCH_WORKERS=1` in `.env` or shell to force serial
>   execution (escape hatch for concurrency-related issues). Computed
>   handlers' nested `fetch.fetch_yfinance_series` calls stay serial —
>   no nested pool submissions.

### Acceptance criteria

- All 247 existing tests pass without modification.
- Three new tests in `tests/test_parallel_fetch.py` (above).
- `errors`, `warnings`, `stale_indicators` are sorted alphabetically at
  end of `compute_composite`.
- `MAX_FETCH_WORKERS` documented in CLAUDE.md.
- Manual smoke: `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  completes ≥30% faster than serial baseline (collect baseline time first).
- Manual smoke #2: `MAX_FETCH_WORKERS=1 python run_dashboard.py ...` produces
  byte-identical `data/latest.json` to the parallel run (modulo `run_timestamp`).

### Estimated effort

Sonnet execution: ~2 hours including the three new tests and the manual
smoke runs. The refactor itself is mechanical given the spec above;
most of the time is in the manual verification.

---

## Brief 28 — Run reliability hardening: close the silent-gap failure modes

**Status: implemented 2026-06-03 (Opus). This brief is the design record.**

### Problem

The dashboard did not run for ~59 hours over the 2026-05-24/25 Memorial Day
weekend (`history.csv`: 05-23 07:30 → 05-26 18:25, recovered by a manual
off-schedule run). Diagnosis surfaced **four** distinct reliability gaps, only
one of which the prior battery-flag fix addressed:

1. **No off-machine liveness check.** Every liveness signal — the heartbeat and
   `_check_dashboard_freshness()` — runs *inside* the pipeline on Ian's machine.
   A watchdog that lives inside the thing it watches cannot detect its own
   non-execution. When the machine is simply off (holiday, travel), nothing
   fires until it comes back. The Memorial Day gap was exactly this.
2. **A single hung fetch can silently eat up to 3 days of runs.** `yf.download`
   had no timeout (every `requests.get` already has `timeout=20`). The scheduled
   task had `ExecutionTimeLimit: PT72H` and `MultipleInstances: IgnoreNew`, so a
   hung yfinance call keeps the instance "running" for up to 72h, during which
   the next day's trigger is skipped — and `LastTaskResult` stays `0` the whole
   time, so nothing looks wrong.
3. **No run logging.** The task runs `--quiet` with no stdout/stderr capture, so
   a crash leaves no traceback anywhere — you can see *that* it failed but never
   *why*.
4. **Staleness thresholds too tight → daily cry-wolf.** Confirmed via live probe,
   not a fetch failure: FRED dates monthly series to the period *start*, so a
   fresh CPI/UNRATE print legitimately reaches a 63–71d gap right before the next
   release, tripping the 60d monthly threshold every month. Weekly series hit
   11–13d against a 10d threshold. The morning Pushover became a rotating
   staleness nag that masks genuine stress alerts.

### Design decisions — LOCKED

- **The watchdog runs on GitHub Actions, not the local machine.** This is the
  whole point: it must survive the machine being off. Free, always-on, and it
  already has repo secrets + a publish history to key off.
- **Liveness signal = git commit time of `docs/index.html`.** That file is the
  published GitHub Pages dashboard; its last commit is an unambiguous "last
  successful publish" timestamp, independent of the local clock. We do NOT parse
  the HTML (fragile) or rely on file mtime (checkout resets it).
- **Watchdog threshold = 28h, check at 20:00 UTC daily.** The run publishes
  ~12:30 UTC (07:30 CT). Checking at 20:00 UTC (~7.5h later) with a 28h threshold
  catches a *fully-missed* day the same evening — e.g. on the Memorial Day
  scenario, last publish Fri 12:30 → Sat 20:00 check sees a 31.5h gap → alert
  Saturday evening — while still tolerating a catch-up run that fires up to ~7h
  late. Runs daily incl. weekends (the local job runs weekends too). (Caveat: `_publish_to_github` skips the
  commit when the dashboard is byte-identical to the prior day. In practice the
  HTML changes daily — scores, AI narrative, news — so a daily commit is
  reliable; `git log` confirms an unbroken daily-commit cadence. If a content-
  identical day ever occurs, the watchdog would false-positive once; accepted.)
- **Watchdog alerts via Pushover** using repo secrets `PUSHOVER_APP_TOKEN` and
  `PUSHOVER_USER_KEY` (same names as `.env`). ← **MANUAL STEP for Ian: add these
  two as GitHub repo secrets.** Until then the workflow runs but the send is a
  no-op (it logs and exits 0 if secrets are absent — no hard failure).
- **yfinance timeout = 20s**, matching the existing `requests` convention.
  yfinance 1.3.0 supports the `timeout=` kwarg (verified).
- **`ExecutionTimeLimit` = PT20M** on both scheduled tasks. The pipeline finishes
  in ~1 min; 20 min is generous headroom while guaranteeing a hung run
  self-terminates so the next day starts clean.
- **Run logging is in-process** (a `RotatingFileHandler` in `run_dashboard.py`),
  NOT a task-action change. Re-pointing the scheduled task to a launcher script
  is higher-risk to the daily automation; in-process logging captures every
  start/finish and full exception traceback regardless of `--quiet`, with zero
  change to the task action. (Trade-off: it cannot capture a pre-interpreter
  failure like a missing python.exe — that surfaces in Task Scheduler's
  `LastTaskResult`, and the external watchdog catches its downstream effect.)
- **Staleness thresholds:** weekly 10→15, monthly 60→75, daily unchanged at 5.
  Reasoning is documented inline in `config/series_cadence.yaml`.

### Files changed

- `config/series_cadence.yaml` — recalibrated weekly/monthly thresholds + rationale.
- `src/fetch.py` — `yf.download(..., timeout=20)`.
- `run_dashboard.py` — extracted `_verify_dashboard_written()` (testable seam);
  added `_setup_run_logging()` + try/except traceback capture in `__main__`.
- `setup_task.ps1` — `ExecutionTimeLimit` on both tasks; also applied live via
  `Set-ScheduledTask`.
- `.github/workflows/dashboard-watchdog.yml` — NEW external dead-man's-switch.
- `tests/test_calendar.py`, `tests/test_ondemand.py` — fixed pre-existing red
  tests (clock injection for ISM; mock the new `_verify_dashboard_written` seam).
- `tests/test_run_logging.py` — NEW: traceback capture + verify-guard behavior.

### Edge cases

- Watchdog can't `git log` the file (first run, shallow checkout) → fetch full
  history (`fetch-depth: 0`); if the file is missing entirely, alert (that itself
  is a failure state).
- Pushover secrets absent → log a warning and exit 0 (don't fail the workflow and
  spam Ian with red-X emails before he's added the secrets).
- yfinance timeout fires → existing retry/backoff + `StaleCacheFallback` path
  already handles it; the timeout just bounds each attempt.

### Success criteria

- Full suite green (was 7 pre-existing failures; fixed as part of this pass).
- New tests prove: an exception in `main()` writes a traceback to the log and
  re-raises; `_verify_dashboard_written` raises on a missing/stale file and
  passes on a fresh one.
- Live: `(Get-ScheduledTask 'Market Stress Dashboard').Settings.ExecutionTimeLimit`
  returns `PT20M`.
- Watchdog workflow validates (YAML) and the freshness logic returns "fresh" for
  the current `docs/index.html`.
