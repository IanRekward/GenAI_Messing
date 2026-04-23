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

Briefs 1–5 are written in full below. Briefs 6–13 are sketched and can be
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
