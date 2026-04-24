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

### Brief 10 — Regime-aware weighting
Run two sets of bucket weights based on VIX tercile (low/mid/high).
Precomputed during backtest. At score time, pick the weight set matching
current VIX regime. Big lift — touches scoring, backtest, recalibrate.

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
