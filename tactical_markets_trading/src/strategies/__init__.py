"""Phase 3 strategy components for the multi-strategy ensemble.

Each strategy is a self-contained module with a uniform `Strategy` interface.
The ensemble orchestrator (`run_ensemble.py`) asks each active strategy to
`decide()` based on current state, then executes the resulting decisions.

Phase 3.1: only `leveraged_trend` is built.
Phase 3.2 will add `sector_momentum_monthly` and `spy_trend`.
"""
