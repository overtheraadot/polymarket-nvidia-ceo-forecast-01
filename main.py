"""polymarket-nvidia-ceo-forecast-01 entry (Python 3.13, stdlib only).

Forecasts the Yes price of every market of Polymarket's "Next CEO of NVIDIA?"
event at every minute of the 240 minutes after a checkpoint, as five
quantiles (0.05, 0.25, 0.5, 0.75, 0.95).

Method
------
Per market, from its 1-minute price history up to the checkpoint:

* Spread: these prices are step functions -- ~80-90% of minutes do not
  move at all, then a tick, then occasionally a ~20-point jump. A plain
  standard deviation of 1-minute changes is dominated by the jumps and
  is far too wide. So sigma is the standard deviation of 1-minute
  changes over the last 24h, winsorised at the 95th percentile of |change|,
  which measures the everyday tick size instead of the jumps.
* Growth: the spread grows like h**0.3, not sqrt(h). Long-horizon
  endpoint changes grow much slower than a random walk: most jumps
  revert or are one-off repricings, so a 240-minute move is only a few
  times a 1-minute move, not 15x. (Fitted on the six practice cases;
  alpha 0.25-0.35 all beat the baseline, 0.3 is the middle.)
* Tails: for each anchor horizon H in {1, 5, 15, 60, 120, 240} minutes,
  the empirical quantiles of past H-step price changes (last 24h) are
  blended in at weight 0.2. They add the real asymmetry (downside tails
  are wider than upside for the leaders) and the jump risk the Gaussian
  core misses. Quantiles for other horizons interpolate in h**0.3.
* Median: the last price. Prediction-market prices are near-martingales
  and every drift estimate tried (EWMA of changes, several half-lives
  and shrinks) made the practice backtest worse, so no drift is used.
* Everything is clamped to [0, 1], rows are non-decreasing, values are
  rounded to 6 decimals. Deterministic: no randomness, no time, no I/O
  beyond reading the case files.

Local backtest (cut each practice case 240 minutes early and forecast
the held-out window): mean pinball 0.3525 vs the house baseline's
0.4296, beating it on all six cases. See README.md.

Runs offline, stdlib only, ~0.1 s per case, well under the 8 s cap.
"""

import json
import math
import os

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

TAUS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.644854, -0.674490, 0.0, 0.674490, 1.644854)
ANCHORS = (1, 5, 15, 60, 120, 240)

# Tuned on the six practice cases (see README); middle values of the
# flat region that beat the baseline, not a sharp optimum.
ALPHA = 0.3           # spread grows like h**ALPHA
EMP_W = 0.2           # weight on empirical quantiles vs Gaussian spread
WINSOR_Q = 0.95       # winsorise 1-min |changes| at this quantile
SIGMA_WINDOW = 1440   # minutes of history for sigma
SIGMA_FLOOR = 0.0004  # per-unit spread floor
SIGMA_CAP = 0.02      # per-unit spread cap
SIGMA_BASE = 0.0025   # house baseline sigma, fallback for tiny histories
EMP_LOOKBACK = 1440   # minutes of history for empirical changes
MIN_EMP_SAMPLES = 30


def _quantile(sorted_vals, tau):
    """Linear-interpolation quantile of an already-sorted list."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _clamp6(x):
    v = round(min(1.0, max(0.0, x)) * 1e6) / 1e6
    return v + 0.0  # avoid -0.0


def _sigma(prices):
    """Winsorised std of 1-minute changes over the last 24h."""
    n = len(prices)
    if n < 3:
        return SIGMA_BASE
    start = max(0, n - 1 - SIGMA_WINDOW)
    diffs = [prices[i + 1] - prices[i] for i in range(start, n - 1)]
    if not diffs:
        return SIGMA_BASE
    abs_sorted = sorted(abs(d) for d in diffs)
    cap = abs_sorted[min(len(abs_sorted) - 1, int(WINSOR_Q * len(abs_sorted)))]
    # Note: cap may be 0 for a market that barely moves (95% of minutes
    # flat); winsorising to 0 then gives sigma = the floor, which is the
    # intended behaviour -- do not skip it.
    diffs = [max(-cap, min(cap, d)) for d in diffs]
    mean = sum(diffs) / len(diffs)
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    return min(SIGMA_CAP, max(SIGMA_FLOOR, math.sqrt(var)))


def _empirical_quantiles(prices):
    """{anchor H: [q_tau for tau in TAUS]} of past H-step changes."""
    n = len(prices)
    out = {}
    for h in ANCHORS:
        t_max = n - 1 - h
        t_min = max(0, t_max - EMP_LOOKBACK)
        if t_max - t_min + 1 < MIN_EMP_SAMPLES:
            continue
        changes = sorted(prices[t + h] - prices[t] for t in range(t_min, t_max + 1))
        out[h] = [_quantile(changes, tau) for tau in TAUS]
    return out


def _interp_emp(emp, h):
    """Empirical quantiles at horizon h, interpolated in h**ALPHA."""
    if not emp:
        return None
    hs = sorted(emp)
    if h <= hs[0]:
        lo = hi = hs[0]
    elif h >= hs[-1]:
        lo = hi = hs[-1]
    else:
        lo = max(a for a in hs if a <= h)
        hi = min(a for a in hs if a >= h)
    if lo == hi:
        return list(emp[lo])
    gh, glo, ghi = h ** ALPHA, lo ** ALPHA, hi ** ALPHA
    f = (gh - glo) / (ghi - glo)
    return [emp[lo][j] * (1.0 - f) + emp[hi][j] * f for j in range(len(TAUS))]


def forecast_market(prices, horizon):
    """Return `horizon` rows of five quantiles for one market."""
    n = len(prices)
    if n == 0:
        raise ValueError("market has no prices")
    x = prices[-1]
    sigma = _sigma(prices)
    emp = _empirical_quantiles(prices)

    rows = []
    for h in range(1, horizon + 1):
        g = h ** ALPHA
        emp_q = _interp_emp(emp, h)
        row = []
        for j in range(len(TAUS)):
            gauss = x + Z[j] * sigma * g
            if emp_q is not None:
                # Empirical quantiles are changes from x; re-centre them on
                # the median (x) so the median stays the last price.
                emp_abs = x + emp_q[j] - emp_q[2]
                q = EMP_W * emp_abs + (1.0 - EMP_W) * gauss
            else:
                q = gauss
            row.append(q)
        row = [_clamp6(v) for v in row]
        for j in range(1, len(row)):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for fname in inputs:
        case_id = fname[: -len(".in")]
        with open(os.path.join(INPUT_DIR, fname), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        horizon = int(case["horizon_minutes"])
        forecasts = []
        for m in case["markets"]:
            q = forecast_market([float(p) for p in m["prices"]], horizon)
            forecasts.append({"id": m["id"], "q": q})
        out_path = os.path.join(OUTPUT_DIR, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"forecasts": forecasts}, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
