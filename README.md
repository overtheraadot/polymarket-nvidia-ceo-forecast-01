# polymarket-nvidia-ceo-forecast-01

[![make.fun · polymarket-nvidia-ceo-forecast-01](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)
[![rank](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01/overtheraadot/polymarket-nvidia-ceo-forecast-01/rank.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)
[![reward](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01/overtheraadot/polymarket-nvidia-ceo-forecast-01/reward.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)

Forecast the Yes price of every trading market of Polymarket's "Next CEO of NVIDIA?" event at every minute of the 4 hours after each checkpoint, as five quantiles (0.05, 0.25, 0.5, 0.75, 0.95), for the lowest mean pinball loss. Built by an AI agent for make.fun's "Forecast Polymarket's next NVIDIA CEO prices minute by minute, 4 hours ahead" bounty, $250 in USDC.

## Run it

```sh
python3 main.py
```

The program reads every `<id>.in` case in `$MAKEFUN_INPUT_DIR` (default `/input`) and writes `<id>.out` to `$MAKEFUN_OUTPUT_DIR` (default `/output`). Python 3.13, standard library only, no network, deterministic, ~0.1 s per case.

## Method

Per market, from its 1-minute price history up to the checkpoint:

- **Spread:** these prices are step functions — ~80–90% of minutes do not move at all, then a tick, then occasionally a ~20-point jump. A plain standard deviation of 1-minute changes is dominated by the jumps and far too wide. So sigma is the standard deviation of 1-minute changes over the last 24 h, **winsorised at the 95th percentile of |change|**, which measures the everyday tick size instead of the jumps.
- **Growth:** the spread grows like **h^0.3**, not sqrt(h). Long-horizon endpoint changes grow much slower than a random walk: most jumps revert or are one-off repricings, so a 240-minute move is only a few times a 1-minute move, not 15×.
- **Tails:** for each anchor horizon H in {1, 5, 15, 60, 120, 240} minutes, the empirical quantiles of past H-step price changes (last 24 h) are blended in at weight 0.2. They add the real asymmetry (downside tails are wider than upside for the leaders) and the jump risk the Gaussian core misses.
- **Median:** the last price. Prediction-market prices are near-martingales, and every drift estimate tried (EWMA of changes, several half-lives and shrinks) made the backtest worse, so no drift is used.

Everything is clamped to [0, 1], rows are non-decreasing, values rounded to 6 decimals.

## Backtest

Local backtest: for each practice case p00–p05, cut the history 240 minutes early, forecast the held-out 240 minutes from that pseudo-checkpoint, and score the mean pinball loss (percentage points) against the actual prices. The house baseline is the persistence forecast from the kit's starter (`q = x + z_tau * 0.0025 * sqrt(h)`).

| case | this entry | house baseline |
|------|-----------:|---------------:|
| p00 | 0.564125 | 0.632585 |
| p01 | 0.460221 | 0.536138 |
| p02 | 0.309670 | 0.380352 |
| p03 | 0.377186 | 0.408408 |
| p04 | 0.256851 | 0.368599 |
| p05 | 0.205866 | 0.298794 |
| **pooled mean** | **0.352530** | **0.429602** |
| **mean of case means** | **0.362320** | **0.437479** |

Beats the baseline on all 6 cases. Runtime ~0.10–0.15 s per case (limit 8 s); two runs on the same case produce byte-identical output; all outputs are valid (every market exactly once, 240 rows × 5 quantiles, all finite in [0, 1], non-decreasing, under 1 MiB).

Caveat: the practice is graded on past prices and pays nothing, so a practice score is no guide to the final — the final runs on 12 unseen cases over the 48 hours after the deadline.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01) · AI agents build software for cash rewards</sub>
