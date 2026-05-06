# tactical_markets — TODO

Companion to the strategic [market_dashboard](../market_dashboard/) early-warning system. Focuses on shorter-term tactical signals (overnight repricing, sector rotation, premarket positioning).

## Status

**Planning, in hopper.** Specs are locked in and research-backed; no code yet. Holds until Market Stress Dashboard is shipped and Phase G items are complete. Earliest start: after the 2026-05-30 regime-weights review checkpoint.

## Source documents

- [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) — full implementation brief: overnight repricing + sector rotation dashboard, 6:30 AM premarket signals
- [RESEARCH_SUMMARY.md](RESEARCH_SUMMARY.md) — empirical findings (2000–2026) that grounded the signal design
- [README.md](README.md) — project framing and design principles

## Next concrete step (when the hopper opens)

Brief 1 in [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) — stand up the signal-generation skeleton. Specifically: pick the data layer (yfinance + FRED is the working assumption), wire one overnight-repricing indicator end-to-end, and produce a static HTML output before adding a second signal.

## Integration with the other two projects

- **Strategic dashboard** (`market_dashboard/`) — eventually consume its composite score / band as a tactical-context input.
- **Trading layer** (`tactical_markets_trading/`) — emit theses as structured records (e.g. JSON) for the Alpaca executor to consume. Keep the contract explicit — no shared imports across projects.

Three-way integration is on the long-term roadmap, not now.
