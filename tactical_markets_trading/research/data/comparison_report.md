# Strategy Comparison Report

Generated: 2026-05-08 13:36
Backtest window: 2014-01-02 to 2026-05-08

## Summary metrics

| strategy                           |   years |        final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |
|:-----------------------------------|--------:|-----------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|
| buy_hold_spy                       |    12.3 | 496385           |      13.86 |     17.25 |     0.84 |             -33.72 |     0.41 |                   69.6 |
| trend_following_spy                |    12.3 | 326745           |      10.07 |     11.37 |     0.9  |             -19.81 |     0.51 |                   59.5 |
| vix_overlay_spy_30                 |    12.3 | 335188           |      10.29 |     13.84 |     0.78 |             -29.22 |     0.35 |                   68.9 |
| vix_overlay_spy_25                 |    12.3 | 319318           |       9.86 |     12.01 |     0.85 |             -21.92 |     0.45 |                   66.9 |
| sixty_forty                        |    12.3 | 306005           |       9.48 |     10.89 |     0.89 |             -27.24 |     0.35 |                   65.5 |
| dual_momentum                      |    12.3 | 250854           |       7.73 |     15.01 |     0.57 |             -33.72 |     0.23 |                   64.2 |
| sector_momentum_top3_monthly       |    12.3 | 393825           |      11.74 |     17.02 |     0.74 |             -31.38 |     0.37 |                   63.5 |
| sector_rotation_5d_live            |    12.3 | 122909           |       1.68 |      2.88 |     0.6  |              -5.1  |     0.33 |                   61.5 |
| sector_rotation_5d_trend_filter    |    12.3 | 113645           |       1.04 |      2.55 |     0.42 |              -5.31 |     0.2  |                   50.7 |
| sector_rotation_5d_vix_filter      |    12.3 | 116515           |       1.25 |      2.58 |     0.49 |              -5.23 |     0.24 |                   56.8 |
| sector_rotation_monthly_match_live |    12.3 | 124705           |       1.8  |      3.36 |     0.55 |              -6.95 |     0.26 |                   61.5 |
| buy_hold_btc                       |    11.6 |      1.75375e+07 |      55.88 |     55.53 |     0.83 |             -83.4  |     0.67 |                   56.4 |
| btc_stress_overlay                 |    11.6 |      5.71209e+07 |      72.53 |     56.74 |     1.24 |             -69.11 |     1.05 |                   50   |

## Performance during stress periods

Total return and max drawdown for each strategy *within the window*. Helps see who's robust under fire.

### 2018 Q4 Selloff (2018-10-01 → 2018-12-24)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -19.2  |       -19.2  |
| trend_following_spy                |       -10.35 |       -10.35 |
| vix_overlay_spy_30                 |       -17    |       -17.01 |
| vix_overlay_spy_25                 |       -14.06 |       -14.1  |
| sixty_forty                        |       -10.02 |       -10.21 |
| dual_momentum                      |       -19.2  |       -19.2  |
| sector_momentum_top3_monthly       |       -12.86 |       -12.86 |
| sector_rotation_5d_live            |        -3.13 |        -3.13 |
| sector_rotation_5d_trend_filter    |        -2.3  |        -2.48 |
| sector_rotation_5d_vix_filter      |        -3.17 |        -3.17 |
| sector_rotation_monthly_match_live |        -1.8  |        -2.26 |
| buy_hold_btc                       |       -38.11 |       -51.34 |
| btc_stress_overlay                 |        -4.35 |        -6.75 |

### COVID Crash (2020-02-19 → 2020-03-23)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -33.72 |       -33.72 |
| trend_following_spy                |       -17.42 |       -17.42 |
| vix_overlay_spy_30                 |       -11.89 |       -12.08 |
| vix_overlay_spy_25                 |        -4.47 |        -4.71 |
| sixty_forty                        |       -16.26 |       -17.76 |
| dual_momentum                      |       -33.72 |       -33.72 |
| sector_momentum_top3_monthly       |       -31.38 |       -31.38 |
| sector_rotation_5d_live            |        -2.73 |        -2.73 |
| sector_rotation_5d_trend_filter    |        -2.89 |        -2.89 |
| sector_rotation_5d_vix_filter      |        -2.77 |        -2.77 |
| sector_rotation_monthly_match_live |        -6.23 |        -6.23 |
| buy_hold_btc                       |       -33.4  |       -49.91 |
| btc_stress_overlay                 |        -6.32 |       -10.15 |

### 2022 Bear Market (2022-01-04 → 2022-10-12)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -24.47 |       -24.47 |
| trend_following_spy                |       -13.08 |       -13.08 |
| vix_overlay_spy_30                 |       -28.72 |       -28.73 |
| vix_overlay_spy_25                 |       -17.79 |       -19.97 |
| sixty_forty                        |       -25.69 |       -25.69 |
| dual_momentum                      |       -12.78 |       -18.19 |
| sector_momentum_top3_monthly       |        -9.88 |       -16.27 |
| sector_rotation_5d_live            |        -1.53 |        -3.42 |
| sector_rotation_5d_trend_filter    |        -0.11 |        -1.42 |
| sector_rotation_5d_vix_filter      |        -1.23 |        -2.72 |
| sector_rotation_monthly_match_live |         0.41 |        -2.46 |
| buy_hold_btc                       |       -58.26 |       -60.92 |
| btc_stress_overlay                 |       -24.49 |       -24.49 |

## NAV at key dates

| strategy                           |   2016-12 |         2018-12 |          2020-12 |          2022-12 |          2024-12 |           latest |
|:-----------------------------------|----------:|----------------:|-----------------:|-----------------:|-----------------:|-----------------:|
| buy_hold_spy                       |    129890 | 150861          | 234256           | 246746           | 388813           | 496385           |
| trend_following_spy                |    114892 | 138840          | 177932           | 194955           | 280950           | 326745           |
| vix_overlay_spy_30                 |    121195 | 132045          | 189612           | 175804           | 274555           | 335188           |
| vix_overlay_spy_25                 |    121041 | 139230          | 202290           | 184598           | 272024           | 319318           |
| sixty_forty                        |    130646 | 148218          | 224726           | 199008           | 257999           | 306005           |
| dual_momentum                      |     96613 | 107455          | 124930           | 142157           | 194489           | 250854           |
| sector_momentum_top3_monthly       |    112929 | 137051          | 217496           | 286383           | 411050           | 393825           |
| sector_rotation_5d_live            |    103716 | 103456          | 109773           | 116750           | 119222           | 122909           |
| sector_rotation_5d_trend_filter    |     98356 |  99104          | 101563           | 108268           | 110336           | 113645           |
| sector_rotation_5d_vix_filter      |    102455 | 102195          | 104883           | 109134           | 111953           | 116515           |
| sector_rotation_monthly_match_live |    102087 | 102616          | 107293           | 114001           | 123613           | 124705           |
| buy_hold_btc                       |    210731 | 818374          |      6.34148e+06 |      3.61825e+06 |      2.04291e+07 |      1.75375e+07 |
| btc_stress_overlay                 |    349983 |      2.2949e+06 |      2.03439e+07 |      2.40839e+07 |      8.84585e+07 |      5.71209e+07 |

## Diagnostics: dual_momentum regime analysis

Dual momentum's 7.74% CAGR (Sharpe 0.57) sits well below Antonacci's published 1974-2014 results (~17% CAGR). This is **regime-dependent, not a bug** — the implementation matches Antonacci's GEM rule (compare SPY 12-mo to T-bills; if SPY wins, hold max of SPY/VEU; else hold cash).

**Decision history (149 months):** {'SPY': 91, 'VEU': 26, 'BIL_riskoff': 20, 'BIL_warmup': 12}.

**Regime transitions and whipsaws:**

| Date | Transition | Prev regime months |
|---|---|---|
| 2015-01-31 | CASH → EQUITY | ~12 |
| 2015-09-30 | EQUITY → CASH | ~8 |
| 2015-10-31 | CASH → EQUITY | ~1 |
| 2016-01-31 | EQUITY → CASH | ~3 |
| 2016-03-31 | CASH → EQUITY | ~2 |
| 2018-12-31 | EQUITY → CASH | ~33 |
| 2019-02-28 | CASH → EQUITY | ~1 |
| 2020-03-31 | EQUITY → CASH | ~13 |
| 2020-05-31 | CASH → EQUITY | ~2 |
| 2022-05-31 | EQUITY → CASH | ~24 |
| 2023-06-30 | CASH → EQUITY | ~13 |

**Key whipsaws in this window:**
- **2018-12-31:** exited to cash at the bottom of the Q4 selloff; re-entered 2 months later after SPY had already rebounded ~10%. Classic 12-month-lookback V-shape penalty.
- **2020-03-31:** exited at COVID bottom; re-entered 2 months later after SPY rallied ~30%. Catastrophic whipsaw.
- **2022-05-31:** correctly anticipated the bear market; stayed in cash 13 months. Strategy working as designed.

**Implication for Phase 2:** dual momentum requires extended drawdowns (1+ year regime transitions) to capture its edge. In our 2014-2026 window, two of three SPY drawdowns were V-shaped, neutralizing the strategy. Antonacci's 1974-2014 backtest included the 2000-2002 dot-com bust and 2007-2009 GFC — both 12+ month drawdowns. Don't read this window as evidence the strategy is broken; read it as evidence the strategy is *regime-conditional*.

Full decision history: [dual_momentum_decisions.csv](dual_momentum_decisions.csv)
