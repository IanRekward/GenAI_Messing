# DEEP_ASSESSMENT_PROMPT — keep / repair / gut / rebuild, then a dev plan

Reusable prompt for a full project deep-dive. Born from the tactical_markets 2026-08/09 pass
(`fable_plan.md` → `REDESIGN_2026-08-31.md` → `DEV_PLAN.md`). Paste everything below the line
into a fresh session in the target project, fill the header, run with the strongest model available.

---

## Target

- **Project:** `<path>` — `<one line on what it claims to be>`
- **Sibling systems it reads/writes:** `<paths, or "none">`
- **Docs to trust for conventions:** CLAUDE.md, TODO.md `<adjust>`
- **Invocation:** Assess this project end to end: keep what works, repair what's salvageable, gut and rebuild the rest. Then refine the result into a dev plan you can execute later. Code execution will wait for my explicit go — plan docs commit freely.

## Rules of engagement

1. **Recompute, never quote.** Any number, claim, or status in the docs gets re-derived from primary evidence (logs, data files, git history, scheduler state, live API/file contracts) before you repeat it. The docs describe intent; only the evidence describes the project.
2. **Read-only investigation is autonomous; decisions are surfaced.** Chase every diagnostic thread yourself — logs in sibling repos, task scheduler history, whatever it takes. But anything that changes behavior or scope waits for sign-off.
3. **Correct the record inline.** When evidence contradicts a doc claim — including a claim you made earlier in the session — fix it where it lives with a dated bracketed note, and propagate to every doc that carried it. Numbers travel with their effective sample size and provenance or not at all.
4. **Every phase commits.** Follow the project's commit conventions. The session must survive a crash at any point.
5. **End each review with a default action and a deadline.** Stalled decisions are the documented disease; never produce "options A–D awaiting sign-off" without "default = X on date Y."

## Phase 1 — Ground truth

- Read the founding docs AND all production code (code is usually smaller than the docs). Build the timeline of what actually shipped vs. what was planned, from git log.
- **Score the output against reality.** Whatever the project produces (signals, alerts, reports), compute its actual performance/precision from logged history vs. ground truth. De-overlap before believing any statistic: report effective n, try alternative conventions (does the sign survive?), and say plainly when no cut of the data has power to support a direction.
- **Reliability audit:** missed runs (count them against the calendar), silent failures, retries absent at flaky boundaries, watchdogs that share fate with what they watch, alerts that can't fire when the machine is dark.
- **Verify every external contract against live files** — exact field names, timezones, staleness at read time, update cadence. Sketches from memory are how translation errors are born.
- **Broken figuratively, not just literally:** who consumes each output *today*? When did a human last act on one? Are there decisions that have sat unanswered — for how long? Did the original purpose quietly move?

## Phase 2 — Provenance and methodology autopsy

- Trace every imported parameter/threshold/citation to its source: universe, period, cadence, direction, costs — and the delta to this implementation. Look hard for the founding-inversion class of error: header says one thing, mechanics say another, and no stage ever reconciled them.
- Did the project expensively re-derive something its own founding docs already contained?
- Do gates ship with historical firing rates? Are confidence numbers calibrated against outcomes, or decoration? Does every published output have a scorer (one command from log to outcome)? If not, that's a finding.
- **Instrument match:** is the feedback loop the project relies on actually powerful enough to answer the question it's trusted with? Estimate the noise floor vs. the plausible effect. Lived exposure calibrates UX; only statistics calibrate edges.
- Write the transferable methodology rules the autopsy implies, numbered, so the rebuild can cite them.

## Phase 3 — Keep / Repair / Gut / Rebuild

- **KEEP** names the proven pieces verbatim so nothing working gets gutted by accident. **REPAIR** items come with size estimates. **GUT** states what leaves the production path and when (retirement lands the same commit its replacement ships — no gap in delivery). **REBUILD** answers the thesis question first: *what is the binding constraint now?* It has usually moved since founding.
- Apply "**who acts on this?**" to every proposed feature. Delta-first for anything a human reads daily (lead with what changed; unchanged state compresses to one calm line). Any state requiring a human decision becomes a queue entry that reappears with its age.
- **Rejected on principle** list — kill dead options explicitly; dead options invite re-litigation. Include guard rails: the gravitational pulls this project's history proves it is prone to.
- **Sequencing:** live risk first (a Phase −1 outside nominal scope if something adjacent is on fire). Thin v1 to the lowest-dependency core; flaky dependencies ship best-effort in a later pass where a failure drops the line, never the product.
- **Kill criteria for the rebuild itself,** defaulted up front: what happens after the first review window if nobody acts on it.

## Phase 4 — Second-thoughts self-audit (do not skip; this caught real errors every time)

- Audit your own Phase-1 numbers the way you audited the project's: recompute under different conventions, de-overlap, check effective n. Retract in writing what doesn't survive.
- Re-derive any date or duration you quoted from a label in the data ("last X" fields rarely date what you think they date — find the actual event in the primary log).
- Re-check priority ordering against live risk, thin v1 further if you can, and re-test each plan element against the methodology rules you just wrote.
- **Doc hygiene:** SUPERSEDED banners on stale specs so no future session re-imports them as live truth; ONE canonical execution doc; the session record frozen separately; no dual maintenance.

## Phase 5 — Dev plan (the executable refinement)

- A separate DEV_PLAN doc: scope stays in the execution doc (it wins conflicts); this adds only the how.
- Pin the **verified contracts** with exact field names and the corrections you found. File-by-file changes per phase with line estimates. Smoke tests per phase (including: corrupt a contract file copy and prove degradation, run against live sibling data and state what the output must show today). Commit points named.
- **Hunt for swap-time gaps** the design doc missed: watchdogs/consumers pointed at the old output path, schedulers, log readers — anything that false-alarms or breaks the moment the new thing replaces the old.
- A "deliberately not doing" list at implementation altitude (abstractions not built, versioning skipped, and why).
- **Gate audit:** list every step that needs the human, then dissolve every gate that existing infrastructure, credentials, or read-only work can cover (verify creds/scopes actually exist — check, don't assume). What remains should be only genuine decisions, ideally one word each. If a credential-handling step gets permission-blocked, don't work around it — record it as a one-approval step.
- **End state: ready-for-dev, holding.** Production code waits for the explicit go. Update project memory with the corrected facts and the hold state.

## Deliverables

1. Session record doc (full assessment + autopsy + self-audit — the reasoning survives even if only the plan executes).
2. Canonical execution doc (keep/repair/gut/rebuild + sequencing + rejected list).
3. DEV_PLAN doc (contracts, file-by-file, smoke tests, gates).
4. Inline record corrections in any doc that carried a disproven claim.
5. Commits at each stage; memory updated; a closing summary that leads with what changed about your understanding, not what you wrote.
