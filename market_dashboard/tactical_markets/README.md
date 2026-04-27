# Tactical Markets Dashboard (In Development)

Companion tool to the strategic early-warning dashboard. Focuses on **shorter-term tactical signals** (hours–days) to support entry/exit decisions and position sizing.

## Purpose

- Early-warning dashboard: *Is the system in stress?* (strategic, 10y+ context, 11 buckets)
- Tactical tool: *What's moving right now, and why?* (tactical, 24–48h context, news + microstructure)

## Signal categories (ideation)

- **News & events**: Recency, directional consensus, calendar catalysts
- **Market microstructure**: VIX slope, sector flows, order imbalances, vol term structure
- **Real-time repricing**: Treasury curve moves, credit spread moves in last 4h
- **Consensus formation**: What's the market actually pricing in?

## Design principles

- Shorter data window (4h–48h) vs strategic percentiles (10y)
- Accepts interpretation/subjectivity (unlike strategic composite)
- Never predicts; surfaces "market is pricing X, you decide"
- Feeds tactical decisions, not strategic positioning

## Status

Early-stage ideation. TBD: architecture, data sources, update cadence, display format.
