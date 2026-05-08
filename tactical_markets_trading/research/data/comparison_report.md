# Strategy Comparison Report

Generated: 2026-05-08 13:12
Backtest window: 2014-01-02 to 2026-05-08

## Summary metrics

| strategy                           |   years |        final_nav |   cagr_pct |   vol_pct |   sharpe |   max_drawdown_pct |   calmar |   monthly_win_rate_pct |
|:-----------------------------------|--------:|-----------------:|-----------:|----------:|---------:|-------------------:|---------:|-----------------------:|
| buy_hold_spy                       |    12.3 | 496419           |      13.86 |     17.25 |     0.84 |             -33.72 |     0.41 |                   69.6 |
| trend_following_spy                |    12.3 | 326767           |      10.07 |     11.37 |     0.9  |             -19.81 |     0.51 |                   59.5 |
| sixty_forty                        |    12.3 | 306053           |       9.48 |     10.89 |     0.89 |             -27.24 |     0.35 |                   65.5 |
| dual_momentum                      |    12.3 | 250914           |       7.74 |     15.01 |     0.57 |             -33.72 |     0.23 |                   65.5 |
| sector_momentum_top3_monthly       |    12.3 | 394105           |      11.75 |     17.02 |     0.74 |             -31.38 |     0.37 |                   63.5 |
| sector_rotation_5d_live            |    12.3 | 122911           |       1.69 |      2.88 |     0.6  |              -5.1  |     0.33 |                   61.5 |
| sector_rotation_5d_trend_filter    |    12.3 | 113647           |       1.04 |      2.55 |     0.42 |              -5.31 |     0.2  |                   50.7 |
| sector_rotation_monthly_match_live |    12.3 | 124730           |       1.81 |      3.36 |     0.55 |              -6.95 |     0.26 |                   61.5 |
| buy_hold_btc                       |    11.6 |      1.75341e+07 |      55.88 |     55.53 |     0.83 |             -83.4  |     0.67 |                   56.4 |
| btc_stress_overlay                 |    11.6 |      5.71098e+07 |      72.53 |     56.74 |     1.24 |             -69.11 |     1.05 |                   50   |

## Performance during stress periods

Total return and max drawdown for each strategy *within the window*. Helps see who's robust under fire.

### 2018 Q4 Selloff (2018-10-01 → 2018-12-24)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -19.2  |       -19.2  |
| trend_following_spy                |       -10.35 |       -10.35 |
| sixty_forty                        |       -10.02 |       -10.21 |
| dual_momentum                      |       -19.2  |       -19.2  |
| sector_momentum_top3_monthly       |       -12.86 |       -12.86 |
| sector_rotation_5d_live            |        -3.13 |        -3.13 |
| sector_rotation_5d_trend_filter    |        -2.3  |        -2.48 |
| sector_rotation_monthly_match_live |        -1.8  |        -2.26 |
| buy_hold_btc                       |       -38.11 |       -51.34 |
| btc_stress_overlay                 |        -4.35 |        -6.75 |

### COVID Crash (2020-02-19 → 2020-03-23)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -33.72 |       -33.72 |
| trend_following_spy                |       -17.42 |       -17.42 |
| sixty_forty                        |       -16.26 |       -17.76 |
| dual_momentum                      |       -33.72 |       -33.72 |
| sector_momentum_top3_monthly       |       -31.38 |       -31.38 |
| sector_rotation_5d_live            |        -2.73 |        -2.73 |
| sector_rotation_5d_trend_filter    |        -2.89 |        -2.89 |
| sector_rotation_monthly_match_live |        -6.23 |        -6.23 |
| buy_hold_btc                       |       -33.4  |       -49.91 |
| btc_stress_overlay                 |        -6.32 |       -10.15 |

### 2022 Bear Market (2022-01-04 → 2022-10-12)

| strategy                           |   return_pct |   max_dd_pct |
|:-----------------------------------|-------------:|-------------:|
| buy_hold_spy                       |       -24.47 |       -24.47 |
| trend_following_spy                |       -13.08 |       -13.08 |
| sixty_forty                        |       -25.69 |       -25.69 |
| dual_momentum                      |       -12.78 |       -18.19 |
| sector_momentum_top3_monthly       |        -9.88 |       -16.27 |
| sector_rotation_5d_live            |        -1.53 |        -3.42 |
| sector_rotation_5d_trend_filter    |        -0.11 |        -1.42 |
| sector_rotation_monthly_match_live |         0.41 |        -2.46 |
| buy_hold_btc                       |       -58.26 |       -60.92 |
| btc_stress_overlay                 |       -24.49 |       -24.49 |

## NAV at key dates

| strategy                           |   2016-12 |         2018-12 |          2020-12 |          2022-12 |          2024-12 |           latest |
|:-----------------------------------|----------:|----------------:|-----------------:|-----------------:|-----------------:|-----------------:|
| buy_hold_spy                       |    129890 | 150861          | 234256           | 246746           | 388813           | 496419           |
| trend_following_spy                |    114892 | 138840          | 177932           | 194955           | 280949           | 326767           |
| sixty_forty                        |    130646 | 148218          | 224726           | 199008           | 257999           | 306053           |
| dual_momentum                      |     96613 | 107455          | 124930           | 142157           | 194488           | 250914           |
| sector_momentum_top3_monthly       |    112929 | 137051          | 217497           | 286383           | 411050           | 394105           |
| sector_rotation_5d_live            |    103716 | 103456          | 109773           | 116750           | 119222           | 122911           |
| sector_rotation_5d_trend_filter    |     98356 |  99104          | 101563           | 108268           | 110336           | 113647           |
| sector_rotation_monthly_match_live |    102087 | 102616          | 107293           | 114001           | 123613           | 124730           |
| buy_hold_btc                       |    210731 | 818374          |      6.34148e+06 |      3.61825e+06 |      2.04291e+07 |      1.75341e+07 |
| btc_stress_overlay                 |    349983 |      2.2949e+06 |      2.03439e+07 |      2.40839e+07 |      8.84585e+07 |      5.71098e+07 |
