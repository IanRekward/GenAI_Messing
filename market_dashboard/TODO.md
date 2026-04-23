# Market Dashboard — To-Do / Project Plan

## Pending

- [ ] **Backtesting & performance evaluation mechanism**
  Build a system to evaluate how well the composite stress score and individual indicators
  predicted actual market stress events historically and over live use.
  Suggested approach: use Opus 4.7 to design the evaluation framework first, then
  implement with Sonnet. Key questions to answer:
  - How well did score spikes precede drawdowns in S&P 500, credit, etc.?
  - Which indicators have the most predictive signal vs noise?
  - How does the model perform in live use over time vs backtested history?
  - What's the right lag/lead window to measure predictive value?

- [ ] **Project optimization, documentation & feature roadmap**
  Use Opus 4.7 to: review current architecture for improvements, write thorough
  documentation, and generate a prioritized feature enhancement roadmap.

- [ ] **Mobile access for dashboard**
  Enable viewing the full HTML dashboard from phone, not just Pushover alerts.
  Leading option: auto-publish `output/dashboard.html` to GitHub Pages after each run.
  See conversation notes — Options 2 (local server) and 3 (hosting) discussed.

## Completed

- [x] Build all 8 source modules (`fetch`, `indicators`, `scoring`, `triggers`, `history`, `alerts`, `news`, `dashboard`)
- [x] Config files (`weights.yaml`, `thresholds.yaml`)
- [x] Push to GitHub (IanRekward/GenAI_Messing → `market_dashboard/`)
- [x] Configure all API keys (FRED, EIA, Anthropic, Pushover)
- [x] Test Pushover alerts
