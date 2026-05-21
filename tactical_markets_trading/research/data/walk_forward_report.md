# Walk-Forward (Out-of-Sample) Validation

Generated: 2026-05-21 10:55

**TRAIN window:** 2014-01-01 to 2019-12-31 (in-sample, ~6 years)
**TEST window:** 2020-01-01 to today (out-of-sample, ~6+ years, includes COVID crash + 2022 bear)

## Question

Are the in-sample sensitivity-best sector-rotation parameters likely to keep working out-of-sample, or are they overfit to the 2014-2026 window the sweep was originally run on?

## Method

1. Run the same 288-combo sensitivity sweep, but only on the TRAIN window.
2. Identify the top-10 combos by Sharpe AND the top-10 by CAGR from TRAIN.
3. Apply each of those param sets to the TEST window without re-tuning.
4. Compare to the current LIVE params (pos=0.10, max=5, hold=5, spread=0.015) and BUY-HOLD-SPY benchmark, both applied to the same TEST window.

## TRAIN summary (in-sample, for reference)

### Top 10 by Sharpe — TRAIN

|   position_size |   max_positions |   hold_days |   spread_threshold |   final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |   years |
|----------------:|----------------:|------------:|-------------------:|------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|--------:|
|            0.1  |              10 |          21 |              0.015 |      131177 |       4.63 |      4.87 |     0.96 |              -6.42 |     0.72 |                   69   |       6 |
|            0.05 |              10 |          21 |              0.015 |      115588 |       2.45 |      2.57 |     0.95 |              -3.55 |     0.69 |                   69   |       6 |
|            0.2  |              10 |          21 |              0.015 |      155882 |       7.69 |      8.44 |     0.92 |             -11.63 |     0.66 |                   67.6 |       6 |
|            0.05 |              10 |          21 |              0.005 |      115010 |       2.36 |      2.61 |     0.91 |              -3.96 |     0.6  |                   67.6 |       6 |
|            0.1  |              10 |          21 |              0.005 |      130020 |       4.48 |      4.96 |     0.91 |              -7.69 |     0.58 |                   67.6 |       6 |
|            0.15 |              10 |          21 |              0.015 |      144295 |       6.31 |      7.01 |     0.91 |              -9.7  |     0.65 |                   69   |       6 |
|            0.2  |              10 |          21 |              0.005 |      155560 |       7.65 |      8.54 |     0.91 |             -11.3  |     0.68 |                   69   |       6 |
|            0.05 |               3 |          21 |              0.03  |      108751 |       1.41 |      1.61 |     0.88 |              -2.32 |     0.61 |                   63.4 |       6 |
|            0.1  |               3 |          21 |              0.03  |      117502 |       2.73 |      3.13 |     0.88 |              -4.38 |     0.62 |                   63.4 |       6 |
|            0.15 |               3 |          21 |              0.03  |      126253 |       3.97 |      4.56 |     0.88 |              -6.21 |     0.64 |                   63.4 |       6 |

### Top 10 by CAGR — TRAIN

|   position_size |   max_positions |   hold_days |   spread_threshold |   final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |   years |
|----------------:|----------------:|------------:|-------------------:|------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|--------:|
|            0.2  |              10 |          21 |              0.015 |      155882 |       7.69 |      8.44 |     0.92 |             -11.63 |     0.66 |                   67.6 |       6 |
|            0.2  |              10 |          21 |              0.005 |      155560 |       7.65 |      8.54 |     0.91 |             -11.3  |     0.68 |                   69   |       6 |
|            0.3  |               3 |          21 |              0.03  |      152507 |       7.3  |      8.5  |     0.87 |             -10.69 |     0.68 |                   63.4 |       6 |
|            0.25 |               5 |          21 |              0.03  |      148665 |       6.84 |      8.58 |     0.81 |             -13.27 |     0.52 |                   62   |       6 |
|            0.25 |              10 |          21 |              0.03  |      148665 |       6.84 |      8.58 |     0.81 |             -13.27 |     0.52 |                   62   |       6 |
|            0.3  |               5 |          21 |              0.03  |      146268 |       6.55 |      9.26 |     0.73 |             -16.02 |     0.41 |                   60.6 |       6 |
|            0.3  |              10 |          21 |              0.03  |      146268 |       6.55 |      9.26 |     0.73 |             -16.02 |     0.41 |                   60.6 |       6 |
|            0.25 |               5 |          21 |              0.015 |      145418 |       6.45 |      9.67 |     0.69 |             -15.2  |     0.42 |                   63.4 |       6 |
|            0.25 |              10 |          21 |              0.015 |      145418 |       6.45 |      9.67 |     0.69 |             -15.2  |     0.42 |                   63.4 |       6 |
|            0.2  |               5 |          21 |              0.015 |      144978 |       6.39 |      8.17 |     0.8  |             -12.17 |     0.53 |                   64.8 |       6 |

## TEST results (out-of-sample)

These are the same TRAIN-best params **applied to the TEST window without re-tuning**. If params hold up here, they have real out-of-sample edge.

### Top-10-by-Sharpe-on-TRAIN, evaluated on TEST

|   rank_in_train_by_sharpe |   position_size |   max_positions |   hold_days |   spread_threshold |   final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |   years |
|--------------------------:|----------------:|----------------:|------------:|-------------------:|------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|--------:|
|                         1 |            0.1  |              10 |          21 |              0.015 |      139134 |       5.31 |      8.14 |     0.68 |             -12.44 |     0.43 |                   60.5 |     6.4 |
|                         2 |            0.05 |              10 |          21 |              0.015 |      119357 |       2.81 |      4.22 |     0.68 |              -6.24 |     0.45 |                   60.5 |     6.4 |
|                         3 |            0.2  |              10 |          21 |              0.015 |      166319 |       8.3  |     13.4  |     0.66 |             -24.74 |     0.34 |                   60.5 |     6.4 |
|                         4 |            0.05 |              10 |          21 |              0.005 |      119357 |       2.81 |      4.22 |     0.68 |              -6.24 |     0.45 |                   60.5 |     6.4 |
|                         5 |            0.1  |              10 |          21 |              0.005 |      139134 |       5.31 |      8.14 |     0.68 |             -12.44 |     0.43 |                   60.5 |     6.4 |
|                         6 |            0.15 |              10 |          21 |              0.015 |      155987 |       7.21 |     11.09 |     0.69 |             -18.61 |     0.39 |                   59.2 |     6.4 |
|                         7 |            0.2  |              10 |          21 |              0.005 |      166319 |       8.3  |     13.4  |     0.66 |             -24.74 |     0.34 |                   60.5 |     6.4 |
|                         8 |            0.05 |               3 |          21 |              0.03  |      114005 |       2.08 |      2.55 |     0.82 |              -5.31 |     0.39 |                   65.8 |     6.4 |
|                         9 |            0.1  |               3 |          21 |              0.03  |      128011 |       3.95 |      4.9  |     0.82 |              -9.75 |     0.4  |                   65.8 |     6.4 |
|                        10 |            0.15 |               3 |          21 |              0.03  |      142016 |       5.65 |      7.09 |     0.81 |             -13.52 |     0.42 |                   65.8 |     6.4 |

### Top-10-by-CAGR-on-TRAIN, evaluated on TEST

|   rank_in_train_by_cagr |   position_size |   max_positions |   hold_days |   spread_threshold |   final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |   years |
|------------------------:|----------------:|----------------:|------------:|-------------------:|------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|--------:|
|                       1 |            0.2  |              10 |          21 |              0.015 |      166319 |       8.3  |     13.4  |     0.66 |             -24.74 |     0.34 |                   60.5 |     6.4 |
|                       2 |            0.2  |              10 |          21 |              0.005 |      166319 |       8.3  |     13.4  |     0.66 |             -24.74 |     0.34 |                   60.5 |     6.4 |
|                       3 |            0.3  |               3 |          21 |              0.03  |      169804 |       8.65 |     13.7  |     0.68 |             -24.21 |     0.36 |                   63.2 |     6.4 |
|                       4 |            0.25 |               5 |          21 |              0.03  |      177820 |       9.44 |     14.17 |     0.71 |             -23.8  |     0.4  |                   63.2 |     6.4 |
|                       5 |            0.25 |              10 |          21 |              0.03  |      179434 |       9.59 |     14.19 |     0.72 |             -23.8  |     0.4  |                   63.2 |     6.4 |
|                       6 |            0.3  |               5 |          21 |              0.03  |      188435 |      10.44 |     14.64 |     0.75 |             -28.34 |     0.37 |                   60.5 |     6.4 |
|                       7 |            0.3  |              10 |          21 |              0.03  |      188435 |      10.44 |     14.64 |     0.75 |             -28.34 |     0.37 |                   60.5 |     6.4 |
|                       8 |            0.25 |               5 |          21 |              0.015 |      177705 |       9.43 |     14.26 |     0.7  |             -23.28 |     0.4  |                   61.8 |     6.4 |
|                       9 |            0.25 |              10 |          21 |              0.015 |      179131 |       9.56 |     14.28 |     0.71 |             -23.28 |     0.41 |                   61.8 |     6.4 |
|                      10 |            0.2  |               5 |          21 |              0.015 |      163067 |       7.96 |     13.16 |     0.65 |             -24.74 |     0.32 |                   60.5 |     6.4 |

### Benchmark comparisons on TEST

- **CURRENT LIVE params** (pos=0.10, max=5, hold=5, spread=0.015): CAGR 2.28%, Sharpe 0.66, MaxDD -5.16%, Calmar 0.44
- **BUY-HOLD-SPY**: CAGR 15.38%, Sharpe 0.81, MaxDD -33.72%, Calmar 0.46

## Verdict

**Sensitivity-best params do NOT survive out-of-sample.** Best TRAIN-top achieves only 10.44% CAGR on TEST vs buy-hold-SPY 15.38%. In-sample sweep was overfit to the 2014-2019 regime. Re-paramming will NOT fix the strategy. The 5-day sector rotation signal itself is the bottleneck; switching to a different signal (monthly momentum, dual momentum, 60/40, trend-following SPY) is the only defensible path forward.

## What this means for Option B vs C vs new-signal

- **Option B (re-param to TRAIN-best 21d-style params):** OOS evidence says this is unlikely to help.
- **Option C (parallel A/B paper):** OOS evidence says low expected value — both variants will likely underperform.
- **Switch signal entirely:** look at compare_strategies.py — trend_following_spy (10.07% CAGR, Sharpe 0.90), sixty_forty (9.48%, 0.89), and sector_momentum_top3_monthly (11.74%, 0.74) all dominated sector_rotation_5d_live in-sample. The btc_stress_overlay (72.53% CAGR, Sharpe 1.24) is the outlier but carries high vol and crypto correlation; consider only if risk preferences allow.
