# fable_plan.md — Full session record, 2026-08-31

**What this is:** the complete assessment + plan + methodology findings from the 2026-08-31 deep-dive session (Claude Fable 5, at Ian's request: "keep what works, repair what's salvageable, gut and rebuild the rest"). The execution-facing subset is locked in [REDESIGN_2026-08-31.md](REDESIGN_2026-08-31.md) (committed `f650684`). This document is the fuller record — including the performance analysis and methodology autopsy — so the reasoning survives even if only the redesign doc gets executed. Not the whole plan; a checkpoint to come back to.

---

## Part I — Assessment

### What the project is

A deliberately minimal daily signal generator: rank 12 ETFs (9 SPDR sectors + IWM/QQQ/SPY) by 5-day return, pair top vs bottom greedily, publish if spread ≥ 1.5% and buy-leg above its 20d MA, deliver one Pushover at 6:30 ET, log every run to `data/theses.jsonl`. ~200 lines of production Python (`run_tactical.py`, `src/sector_rotation.py`, `src/pushover.py`, `watch_tactical.py`) on Windows Task Scheduler. Designed as a rule-based heuristic calibrated by lived exposure (Ian reading it on his phone), not by backtests.

### Live performance (scored 2026-08-31, market-neutral 5d pairs vs actual prices)

| Slice | n | Win | Mean/trade | Sharpe/trade |
|---|---|---|---|---|
| All pairs, full period (5/6–8/31) | 210 | 43% | −0.82% | −0.20 |
| Pre-review (≤ 6/12) | 69 | 32% | −2.29% | −0.52 |
| Post-review (> 6/12) | 141 | 48% | −0.11% | −0.03 |
| Post-review, top pair/day | 39 | 54% | **+0.58%** | +0.14 |

Monthly top-pair: May −3.20%/trade, June −2.23%, July +0.53%, Aug +0.11%. The sign flipped **again** after the June review — a June flip to reversion (options A/B) would have lost money since. Three independent analyses now agree (live record, 2-yr production-replica backtest, bot's 33-yr backtest at Sharpe 0.19): **no stable edge in either direction at this horizon.**

*[Corrected same session — see Part IV: the post-review directional claims above rest on overlapping trades (effective n≈9) and don't survive de-overlapping. The retire conclusion is unaffected and strengthened.]*

Two more empirical nails:
- **Confidence field is anti-predictive:** corr(spread, fwd 5d return) = −0.14 over 210 live trades; high-spread half −1.09%/trade vs low-spread half −0.56%.
- **The 1.5% publish gate never fired:** 0 no-signal days in 75 run-days (~3.1 theses pushed per morning). The "binary publish/don't publish" design is de facto "always publish."

### What works (operationally)

Scheduler stack (main 5:30 CT + wake 5:20 + watchdog 7:00, `-WakeToRun`, battery flags), NYSE holiday calendar, ET date handling, Pushover delivery (100% success on signal days), log-every-run JSONL discipline, two-repo git flow. All four scheduled tasks green as of 8/31. The ops layer matured into something solid.

### What's broken — literally

1. **8 of 81 trading days missing entirely** (6/17, 6/18, 6/22, 7/6–7/8, 7/13, 7/15 — ~10% silent-miss rate). The watchdog shares the machine: asleep at 5:30 means asleep at 7:00 → **shared-fate design flaw**, no alert ever fired.
2. **4 days lost to yfinance empty responses** ("Only 0 rows") — no retry logic.
3. **Repo drift:** June's TODO.md review-DONE edit never reached `_genai_tmp` (fixed in `f650684`); `theses.jsonl` was untracked until then.
4. **Adjacent (bot repo):** as of 8/31 — Tactical Trading Watchdog LastResult=1, `last_successful_run.json` stale since 8/28, and **the kill switch has entries blocked** ("5 losses in a row, last winner 2026-06-05"). Needs its own session.

### What's broken — figuratively

- **The decision loop:** the June 12 review produced options A–D "awaiting Ian sign-off" — nothing was decided for 11 weeks. The system ran on option D by inaction, publishing a signal its own research called value-destructive.
- **The purpose:** the bot pivoted away 2026-05-21; MICRO's only consumer became Ian's phone, and the stalled A–D loop suggests the phone reads stopped mattering too. A well-engineered pipeline pushing a no-edge signal to a disengaged reader.
- **The live question moved past A–D** to: does this clear the bar to publish at all? (Answered by Part II: no — repurpose the pipeline.)

---

## Part II — The plan (execution copy: [REDESIGN_2026-08-31.md](REDESIGN_2026-08-31.md))

Resolves 2026-06-12 A–D with **option E: retire the signal, rebuild MICRO as the premarket briefing layer.**

### KEEP
Scheduler stack, holiday calendar + ET dates, Pushover client + 6:30 ET slot, JSONL logging discipline, two-repo flow, CLAUDE.md conventions, the ≥30-labeled-trades ML gate (bot's `trades.jsonl` is now the label source), and the 4 months of `theses.jsonl` history (now git-tracked).

### REPAIR
1. yfinance retry ×3 with 60s backoff (~10 lines).
2. External dead-man's switch: `run_tactical.py` pings healthchecks.io on success; service alerts if no ping by ~7:15 ET. Fixes the shared-fate flaw — machine-off finally alerts. Local watchdog stays as second layer (~5 lines + free account).
3. Repo hygiene (done in `f650684`).
4. Bot repo watchdog/kill-switch investigation (separate session, out of MICRO scope).

### GUT
The 5d momentum signal, "rotate 5–10%" advice, confidence field, spread gate, 20d MA filter. `sector_rotation.py` leaves the production path; backtests stay in `research/`. Supersedes the CLAUDE.md locked-scope row "Week 1 signal: sector rotation only" upon Ian's go. Gut lands the same commit briefing v1 ships — no gap in the 6:30 push.

### REBUILD — Premarket Briefing v1 (~3–4 days, ~150–200 lines)
MICRO's new job: **the 6:30 ET human window into the systems that do have edge.** Read-only, files-on-disk, no cross-project imports. One Pushover, ~8 lines:

1. **Regime** — `market_dashboard/data/latest.json`: composite + band, regime, shock type; staleness flag >36h.
2. **Bot health** — `tactical_markets_trading/data/last_successful_run.json` + `account_state.json`: last-success freshness, `entry_ok` + gate reason, open positions, equity vs peak. (On 8/31 it would have read: *"⚠ bot: entries blocked (kill_switch 5 consecutive losses), last success 8/28."* Nothing currently tells Ian this.)
3. **Positions & flip proximity** — `strategy_state_*.json` + live quotes: TQQQ distance to trailing stop (off `position_peak_price`), SPY distance to 200d/50d MA router levels; ⚠ prefix within ~2%.
4. **Overnight tape** — SPY/QQQ premarket gap (flag ≥1%), VIX level + 5d change.

Entrypoint stays `run_tactical.py` (scheduler untouched); `src/briefing.py` replaces `sector_rotation.py` in the call path; log to `data/briefings.jsonl` (`signal_type: "premarket_briefing"`). Then a **two-week read** with the week-1 failure-mode trick: (a) acted on a ⚠ → tune/expand; (b) all noise → alert-only mode; (c) never read it → format wrong.

### Backlog (pick after the read)
1. **Trade postmortems** — bot close since yesterday → realized P&L line; builds the labeled-trade corpus toward the ML gate.
2. **Event awareness** — hardcoded FOMC/CPI/NFP dates (NYSE_HOLIDAYS pattern) → "FOMC today" line.
3. **VIX term structure** — ^VIX vs ^VIX3M, flag backwardation flips.
4. **Priority escalation** — high-priority Pushover only for acute states (stop within 1%, kill switch newly tripped).
5. **Weekly digest** (Sunday PM) — equity vs SPY, regime-day counts, gate trips.
6. **Shadow-vs-live divergence line** — bot already writes `drift_log.jsonl` / `shadow_book.jsonl`; surface backtest-vs-live drift daily (see Part III — this is the methodological payoff).
7. **Sector dispersion line** — widest 5d spread, no direction claimed. Recommendation: skip; the question is answered.

**Rejected on principle:** reversion flip (no stable edge), adaptive switch (parameter luck; doubles parameter surface), ML confidence (gate unmet), HTML output, intraday polling.

### Sequencing
- **Phase 0 — done (`f650684`):** plan docs + TODO sync + data tracked. No behavior change.
- **Phase 1 (day 1):** repairs (retry + heartbeat). Ships independently; old signal keeps running.
- **Phase 2 (days 2–4):** briefing v1, smoke-tested against live sibling files, swapped in; momentum retires same commit.
- **Phase 3:** two-week read → pick from backlog.
- **Code execution awaits Ian's explicit go** (locked-design rule).

---

## Part III — Methodology autopsy

### The headline: the signal was inverted at birth

The project's own founding documents contain the June review's "discovery":

- [RESEARCH_SUMMARY.md line 11](RESEARCH_SUMMARY.md#L11): the Sharpe 0.92 citation is **quarterly mean reversion on the TSX 60** (2000–2025).
- [Line 165](RESEARCH_SUMMARY.md#L165): "**Mean reversion: 2–10 days optimal**; **Momentum: 3 weeks to 3 months optimal**."
- [Line 185](RESEARCH_SUMMARY.md#L185): design basis restated as "mean reversion, quarterly."

[ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md), written the same evening (2026-04-27), titles the signal "Quarterly Mean Reversion" ([line 25](ROADMAP_SIGNAL_GENERATION.md#L25)) and seven lines later operationalizes it as *rank by 5-day momentum, rotate into the top* — **buy the recent winner**. Header says fade; mechanics say chase; at the 5-day horizon the compiled research assigns the edge to fading. That single-document translation error was carried by every downstream stage — the May 5 design pass locked "5d momentum + 1.5% spread" as a unit, the implementation coded it faithfully, and the June review recommended reversion *as a new empirical finding* without noticing it was line 165 of the founding doc. **Four months of live collection and two backtests expensively re-derived a fact the repo already contained.**

Provenance hygiene failed more broadly than the sign: a quarterly-rebalance Sharpe from Canadian large caps became the "starting hypothesis" for a daily-cadence, 5-day-hold strategy on US sector ETFs. Different universe, horizon, and direction — nothing survived translation except the number 0.92.

### The instrument mismatch

The freeze-and-read loop is excellent for delivery/UX questions and had ~zero power for the edge question it was implicitly trusted with. From live data: per-trade σ ≈ 4.1%. A two-week read = ~2 independent 5d windows → noise floor ±2.9% vs a plausible edge of ±0.5% (noise 6× effect). Detecting 0.5%/trade at conventional confidence needs ~500 independent trades ≈ **10 years of live collection at this cadence**. Meanwhile the instrument that *could* answer it (a production-replica backtest) was explicitly deferred — and took one session to build when finally attempted. **Rule: UX earns iteration through use; signals earn deployment by surviving cheap falsification first.** The project applied software-shipping methodology to a statistics problem.

### Smaller breaks, same family

- **Thresholds without base rates:** the 1.5% gate shipped without checking how often 12 tickers' top-bottom spread exceeds it (always). Any gate should ship with its historical firing rate.
- **Confidence without calibration:** the research summary defined confidence as belief-the-edge-is-real with a 70% publish bar; M2 shipped `sigmoid((spread−1.5)/2)` — calibrated to nothing, empirically anti-predictive. A confidence number never scored against outcomes is decoration.
- **Prescribed guardrails not built:** the summary's own rolling-Sharpe monitor with edge-decay flag (<0.5 for 4 weeks) never existed; theses were logged but unscoreable until June. **A signal ships with its scorer** — one command from log to win-rate.
- **Decisions without decay:** A–D hung 11 weeks. Every review should end with a default action and a deadline.

### What the methodology got right

Thin-slice shipping; log-everything-from-day-1 (the only reason the 8/31 re-scoring was possible); the scope table; docs-as-mail between the three projects (the pivot-note pattern worked); and the June review itself — non-overlapping cuts, mirror test, oracle bound, parameter-sensitivity as an overfitting detector, honest autocorrelation-artifact diagnosis. The self-correction machinery worked; it was just slow and never consulted its own founding evidence.

### The ecosystem inherits the mirror-image risk

MICRO under-trusted backtests; the bot risks over-trusting them. It scanned "every retail-accessible strategy over 33 years" and picked the best (TQQQ + 50d MA + 5% trail, Sharpe 1.86) — selection over many variants quietly burns the walk-forward test; synthetic leveraged-ETF history flatters; the research summary's own heuristic puts real retail edge at 0.75–1.0 after friction. Live evidence already speaking: five consecutive losses since June 5, kill switch tripped. Same root error in both directions: **treating a backtest number as the object rather than a hypothesis with an error bar.** The briefing pivot is the methodological response — it moves MICRO to a domain with fast feedback (alert precision measurable in days) and makes it the daily surface where live-vs-backtest divergence becomes visible (backlog item 6).

### Proposed methodology rules (adopt with the rebuild)

1. **Provenance diff:** any imported parameter/result records the source's universe, period, cadence, direction, and costs — plus the delta to our implementation.
2. **Falsify before publish:** no signal goes live without a production-replica backtest attempt, however crude.
3. **Gates ship with firing rates;** confidence numbers ship with a calibration check.
4. **Signals ship with scorers:** if it publishes daily, it's scoreable in one command.
5. **Decisions decay to defaults:** every review names a default action and a deadline.
6. **Match instrument to question:** lived exposure for UX; statistics for edge; know the power of each before trusting it.
7. **De-overlap before you believe:** added in Part IV after the same-session audit caught this plan's own author committing the error.

---

## Part IV — Second thoughts (same session, on Ian's "anything you'd add/change/delete?")

### Corrections to my own analysis first

Audited my own scoring the way I audited the project's. Two results:

1. **Entry convention doesn't matter.** Close→close vs open→open (the actionable moment after a 6:30 push) give near-identical numbers across every slice. The headline figures are robust to that choice.
2. **De-overlapping demolishes my directional claims.** Non-overlapping top-pair, full period: n=15, +0.29%/trade close-entry but **−0.27% open-entry** — the sign flips with the convention, t≈±0.2. Post-review non-overlapping: n=9, t≈1.0–1.4, not significant. My Part I claim that "the sign flipped post-review; a June flip to reversion would have lost money" was built on overlapping trades (effective n≈9) — **the same class of error as the project's founding one: reading direction from an underpowered sample.** Even the full-record t=−2.89 on 210 trades is overlap-inflated (~40 independent windows). Honest restatement: *no cut of the live data, properly de-overlapped, ever had the power to establish any direction.* The only adequately powered estimate remains the 33-year backtest: Sharpe 0.19 ≈ nothing after costs. This strengthens the retire decision — there is nothing to flip to — while weakening the drama of every live-performance number quoted along the way, the June review's included (it flagged this itself: "effective independent sample ≈ 12–15"; the caveat kept getting dropped as numbers were carried forward).

→ **Methodology rule 7: de-overlap before you believe.** Any statistic on overlapping windows reports its effective n; directional claims come only from non-overlapping cuts. This failure mode bit three times in one project (the founding live read, the review's autocorrelation artifact, and my own post-review claim) — it is sticky.

### Changes to the plan

1. **Reprioritize: bot health is Phase −1, ahead of everything here.** The kill switch has blocked entries since ~June 5, the bot's own watchdog is exiting 1, state is stale since 8/28, and five positions are open on ~$102.7k equity (near Alpaca's $100k paper default, so presumably paper — **verify**). The briefing is polish; that is live risk. It was buried as "adjacent" — wrong altitude.
2. **Thin briefing v1 further.** Core = sections 1–2 only (regime + bot health): pure file reads, zero market-data dependency, shippable in ~1–2 days and immune to the yfinance flakiness that cost 4 days. Sections 3–4 (stop proximity, overnight tape) need premarket quotes — the flakiest dependency (yfinance premarket is unreliable; VIX has no premarket) — so they ship best-effort in a 2b pass: a failed quote drops the line, never the briefing.
3. **Why observability lives in MICRO, not the bot — now a principled answer, not opportunism:** an observer inside the observed system cannot report its own death, and today's evidence is exactly that (the bot's watchdog is the failing component). MICRO is a separate process in a separate repo on a different schedule slot — a genuinely independent observer. This also re-justifies the healthchecks.io heartbeat: for a signal generator, missed days were trivia; for the observability layer over a live-money bot, silent darkness is a real risk.
4. **Contract fragility:** the three bot JSON files carry no schema version (M5 was deferred). Defensive reads (missing key → "unknown" in the briefing line, never a crash) plus a one-line schema-drift warning when expected keys vanish. No formal versioning — one consumer, overkill.
5. **Backlog item 4 (priority escalation) was incoherent as written** — MICRO runs once daily and cannot detect intraday acute states. Reduced to: the single 6:30 push uses Pushover high priority when it contains a ⚠ line, nothing more.
6. **Backlog item 7 (sector dispersion line): deleted outright** rather than "recommend skip" — dead options invite re-litigation.
7. **Kill criteria for the briefing itself (rule 5 applied to my own plan):** after the two-week read, default = alert-only mode unless Ian affirmatively opts into the daily push; after 8 weeks with zero acted-on ⚠ lines, default = park the project. The predecessor died of decision-stall; this one ships with its own sunset defaults.
8. **The briefing's scorer, defined before it exists (rule 4 applied):** every ⚠ line logs its trigger values to `briefings.jsonl`; the scorer computes warning **precision** (⚠ followed within 3 days by the flagged event — stop hit, MA cross, gate change) and **recall** (events that occurred with no prior-day ⚠), one command, from bot logs + prices. Unlike edge detection, this feedback loop is fast — weeks, not decades.
9. **Doc hygiene:** SUPERSEDED banners added to ROADMAP_SIGNAL_GENERATION.md and RESEARCH_SUMMARY.md so no future session re-imports the Sharpe 0.92 or the 5d-momentum spec as live truth — the founding inversion survived partly because stale docs read as current specs. REDESIGN_2026-08-31.md stays the single canonical execution doc; this file is the frozen session record (avoid dual maintenance — the disease that hit TODO.md in June).

### Considered and rejected

Keeping Pushover-only, once-daily cadence, the closed ML gate, and files-on-disk contracts — all re-examined, all stand. And the retire decision itself: every audit pass this session made it stronger.

---

## Part V — Thesis review (same session, on Ian's "is the overall thesis sound? should there be more?")

### Verdict: sound, with one sharpening

The ecosystem's binding constraint is no longer signal generation — the bot took that over with better-researched strategies. The binding constraint is **oversight**: an autonomous bot trading (presumably paper, eventually maybe real) money, watched by a human who checks in sporadically. The proof case is already on the record: the kill switch tripped ~June 5 and was discovered August 31 — **an 87-day detection latency on the single most important state change in the system.** A tool that allocates Ian's scarcest resource (attention) to the system's scarcest input (timely human awareness) is the right thesis. The feedback loop is fast, the contracts exist, the delivery slot precedes the bot's 14:45 entry window by 8 hours.

The sharpening: **the product is a health-and-pending-decisions console, not a market briefing.** Apply the "who acts on this line?" test to each planned section: a stop-proximity line is *interesting* but the bot handles it — no human action. A gap/VIX line is garnish. The lines that pass the test are: the machine is broken (bot can't act), a human decision is pending (kill-switch reset), data is drifting, a run went missing. Market context earns its place only after those. Two design consequences:

1. **Delta-first.** A daily push that mostly restates yesterday trains the reader to ignore it — alert fatigue is the classic observability failure, and mode (c) is this project's documented risk. The briefing keeps a tiny snapshot of yesterday's state and leads with *what changed*: kill switch newly tripped/cleared, regime flipped, position opened/closed/stopped, drawdown threshold crossed, run missed. Unchanged state compresses to one calm line. What Ian needed on June 5 was not a summary — it was one line saying "kill switch tripped *today*."
2. **A pending-decisions queue, with age.** The system's documented disease is decision-stall (A–D sat 11 weeks; the kill-switch reset has sat ~12). Any state requiring a human decision becomes a queue entry that reappears daily with its age: *"⚠ pending 87d: kill-switch reset (bot trades nothing until resolved)."* Escalating staleness is the anti-stall mechanism the ecosystem has been missing — it converts silence from the default into a visible cost.

### Should there be more? Two additions

1. **Morning intent preview — the windshield, not the rear-view.** The bot's actions are deterministic and computable read-only: MA distances, the monthly rebalance calendar, stop levels. The briefing can say *"today the bot will likely: exit XLV (fell out of top-3 at Friday's close); no other triggers within 1%."* This is simultaneously better oversight (a veto window — 6:30 push, 14:45 execution) and the legitimate heir to the dead discretionary layer: tactical awareness derived from rules that earned their place, not from a re-invented signal. An actual veto mechanism needs a bot-side contract (e.g., a hold-file the bot checks before entries) — bot project's call, backlog until then; the read-only preview needs nothing.
2. **Promote the weekly digest.** The daily briefing serves the operate loop; the actual top-level decision — *keep running this ensemble or kill it* — is made from equity vs SPY over months. That loop currently has no delivery mechanism at all (report_card.html requires opening a file on the machine). A Sunday push with equity curve vs benchmarks, regime-day counts, and gate trips serves the more consequential decision and is compatible with alert-only mode if the daily read fails.

### What must NOT be added — guard rails

- **No new signals, ever, without passing rules 1–7.** The gravitational pull back toward "MICRO generates trade ideas" is the failure mode this whole record documents. The intent preview is the permitted substitute: it surfaces the *bot's* decided rules, it doesn't invent edges.
- **No LLM-generated market commentary/news digest.** Tempting, cheap to bolt on, unfalsifiable, violates the rule-based charter, and adds a flaky dependency to the reliability layer.
- **No second trading brain.** MICRO observes and previews; it never overrides. The moment a MICRO line says "consider overriding the bot," the independent-observer rationale collapses.
- **No intraday expansion.** Once-daily reconciliation + the bot's own immediate alerts (fixed in Phase −1) is the division of labor; defense in depth, not duplication.

### Net effect on the thesis statement

Old: "the 6:30 ET human window into the systems that do have edge."
Refined: **"the daily reconciler and pending-decisions console for the trading system, delta-first, with a preview of the machine's intent — plus a weekly verdict on whether the machine deserves to keep running."**

---

## Related documents

- [REDESIGN_2026-08-31.md](REDESIGN_2026-08-31.md) — execution plan (keep/repair/gut/rebuild), the doc awaiting Ian's go.
- [research/2026-06-10_review_findings.md](research/2026-06-10_review_findings.md) — June review + backtests.
- [RESEARCH_SUMMARY.md](RESEARCH_SUMMARY.md) / [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) — founding docs (see Part III for the inversion).
- [TODO.md](TODO.md) — status pointer, source of truth for what's being built.
