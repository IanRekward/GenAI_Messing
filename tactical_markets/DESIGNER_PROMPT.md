# Designer Prompt — tactical_markets

Use this prompt at the start of any session that's about to make a design or scoping call in this project. It's calibrated to counter the over-engineering tendency that the existing ROADMAP and RESEARCH_SUMMARY can pull a model into.

**Recommended model:** Opus 4.7+ for design sessions; switch to Sonnet 4.6+ once the design is locked and execution begins.

---

## The prompt

> You're designing the next implementation step in `tactical_markets/` (or `tactical_markets_trading/`). Read the ROADMAP and RESEARCH_SUMMARY, then **treat them as brainstorming output, not a contract** — be willing to propose deleting half of it.
>
> Before suggesting any code or architecture, answer these in order:
> 1. **What's the smallest end-to-end slice that produces real evidence about whether the core idea works?** "End-to-end" means a thesis lands in front of Ian, not a passing unit test.
> 2. **What's the fastest path to get that slice in front of Ian — one human investor, one machine — within a week?** Minutes-of-his-attention is the binding constraint.
> 3. **What in the existing ROADMAP can be deferred or deleted without blocking the core test?** Default: cut. Don't carry scope on faith.
>
> Constraints to internalize:
> - This is a personal decision-support tool, not a product. No generality, no abstractions for hypothetical second users.
> - "Edge documented in 2000–2026 research" ≠ "edge for me right now." Treat published numbers as starting hypotheses, never as truth.
> - Backtested confidence numbers are dressed-up guesses until they survive contact with reality. Don't build precision into things that don't deserve it.
> - The dashboard exists to help Ian think. It never tells him what to do. A thesis is a candidate, not an instruction.
> - Three similar lines beats a premature helper. No shared `core/` library across the three projects — files-on-disk contracts only.
>
> Give one opinionated recommendation, defend it, name the trade-off you're accepting. Don't offer a menu.

---

## What this prompt is doing

- **Authorizes deletion** of existing scope explicitly. Without that, the model inherits and extends the ROADMAP rather than questioning it.
- **Anchors progress on evidence-in-front-of-Ian**, not lines-of-code or tests-passing. That's what kills over-engineering.
- **Names the precision trap.** The ROADMAP has confidence formulas and slippage models that imply more rigor than the data supports. The prompt calls that out so the model won't add more of it.

## When to NOT use this prompt

- Routine execution of an already-locked design — Sonnet doesn't need design framing, just the brief.
- Bug fixes, test additions, mechanical refactors. The prompt's "delete half the scope" instruction is wrong for those.
