"""
product_props.py — statistical tests shared by all five rounds.

Every figure quoted in the round documents is produced here or by a script in
`analysis/`, so the estimator is identical across rounds and the numbers are directly
comparable.

Design principle: each test is chosen so that it *rules out* a specific alternative,
and so that a stated falsification condition can be checked against its output.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from benchmarks import _ladder, split_flow_by_aggressor


# ---------------------------------------------------------------------------
# loading and price construction
# ---------------------------------------------------------------------------
def load(data_dir: str, rnd: int, day: int):
    """Official semicolon-delimited prices and trades for one round-day."""
    return (pd.read_csv(f"{data_dir}/prices_round_{rnd}_day_{day}.csv", sep=";"),
            pd.read_csv(f"{data_dir}/trades_round_{rnd}_day_{day}.csv", sep=";"))


def best_mid(g: pd.DataFrame) -> pd.Series:
    """Midpoint of the best bid and offer."""
    return g[["bid_price_1", "ask_price_1"]].mean(axis=1, skipna=True).ffill().bfill()


def largest_level_mid(g: pd.DataFrame) -> pd.Series:
    """
    Midpoint of the largest-size level on each side.

    The book is visibly two-layered — large orders outside, small ones interleaved
    inside — which suggests the outer levels define the fair price. Round 1 tests that
    against ROOT's known straight line and finds it *worse* than `best_mid`; see
    `rounds/01/3-what-the-market-is.md` §3.
    """
    out = []
    for _, r in g.iterrows():
        b, a = _ladder(r, "bid"), _ladder(r, "ask")
        bb = max(b, key=lambda x: x[1])[0] if b else np.nan
        ba = max(a, key=lambda x: x[1])[0] if a else np.nan
        out.append(np.nanmean([bb, ba]) if (b or a) else np.nan)
    return pd.Series(out).ffill().bfill()


# ---------------------------------------------------------------------------
# the central statistic
# ---------------------------------------------------------------------------
def vr(x, k: int) -> float:
    """
    Variance ratio.

        VR(k) = Var(x[t+k] - x[t]) / (k * Var(x[t+1] - x[t]))

    Random walk => 1. Mean reverting => below 1. Trending => above 1.

    Nothing to choose but the horizon k, which is why the same estimator is applied to
    every product in every round and the results are comparable across the repository.
    """
    x = np.asarray(x, dtype=float)
    return float(np.var(x[k:] - x[:-k]) / (k * np.var(np.diff(x))))


# ---------------------------------------------------------------------------
# hypothesis tests
# ---------------------------------------------------------------------------
def drift_check(data_dir, rnd, days, product) -> pd.DataFrame:
    """
    Deterministic line, or random walk with drift?

    Both fit a line with high R-squared, so R-squared cannot separate them. What does:
    under a random walk the residual dispersion grows with the square root of time;
    under a deterministic line plus observation noise it stays constant.
    """
    rows = []
    for d in days:
        p, _ = load(data_dir, rnd, d)
        g = p[p["product"] == product].reset_index(drop=True)
        for name, f in [("best mid", best_mid(g)),
                        ("largest-level mid", largest_level_mid(g))]:
            b, a = np.polyfit(g["timestamp"], f, 1)
            res = f - (a + b * g["timestamp"])
            h = len(res) // 2
            rows.append({"day": d, "fair": name, "slope": round(b, 6),
                         "intercept": round(a, 2),
                         "R2": round(1 - res.var() / f.var(), 6),
                         "sd(resid)": round(res.std(), 3),
                         "1st half": round(res[:h].std(), 2),
                         "2nd half": round(res[h:].std(), 2),
                         "VR200(resid)": round(vr(res.to_numpy(), 200), 3)})
    return pd.DataFrame(rows)


def ou_check(data_dir, rnd, days, product) -> pd.DataFrame:
    """
    Mean reverting, random walk, or trending? Three independent angles:

      beta                 regression of the next increment on the current deviation;
                           negative under mean reversion, zero under a random walk
      VR(50), VR(200)      variance ratio at two horizons
      half-life            reported twice. The AR(1) figure is what discretising an OU
                           process gives; the empirical figure is the lag at which the
                           autocorrelation crosses 0.5. On noisy series they differ by
                           two orders of magnitude (attenuation bias) — rounds/01 §2.
    """
    rows = []
    for d in days:
        p, _ = load(data_dir, rnd, d)
        g = p[p["product"] == product].reset_index(drop=True)
        f = largest_level_mid(g).to_numpy()
        mu = f.mean()
        beta = np.polyfit(f[:-1] - mu, np.diff(f), 1)[0]
        ac = [np.corrcoef(f[:-k], f[k:])[0, 1] for k in range(1, 900)]
        hl_emp = next((k for k, v in enumerate(ac, 1) if v < 0.5), None)
        phi = np.polyfit(f[:-1] - mu, f[1:] - mu, 1)[0]
        rows.append({"day": d, "mean": round(mu, 2), "sd": round(f.std(), 2),
                     "beta": round(beta, 4),
                     "VR(50)": round(vr(f, 50), 3), "VR(200)": round(vr(f, 200), 3),
                     "AR(1) half-life": round(np.log(2) / -np.log(phi), 1) if 0 < phi < 1 else np.nan,
                     "empirical half-life": hl_emp})
    return pd.DataFrame(rows)


def layer_check(data_dir, rnd, days, products, big: int = 15) -> pd.DataFrame:
    """Is the book two-layered? Distance of resting orders from fair, split by size."""
    rows = []
    for prod in products:
        big_d, small_d = [], []
        for d in days:
            p, _ = load(data_dir, rnd, d)
            g = p[p["product"] == prod].reset_index(drop=True)
            f = largest_level_mid(g).to_numpy()
            for i, (_, r) in enumerate(g.iterrows()):
                for side in ("bid", "ask"):
                    for px, v in _ladder(r, side):
                        (big_d if v >= big else small_d).append(abs(px - f[i]))
        for name, arr in [(f"large (>={big})", np.array(big_d)),
                          (f"small (<{big})", np.array(small_d))]:
            rows.append({"product": prod, "group": name, "n": len(arr),
                         "median |price-fair|": round(float(np.median(arr)), 1),
                         "Q1": round(float(np.percentile(arr, 25)), 1),
                         "Q3": round(float(np.percentile(arr, 75)), 1)})
    return pd.DataFrame(rows)


def flow_check(data_dir, rnd, days, products) -> pd.DataFrame:
    """
    Interceptable flow and the gross market-making ceiling it implies.

    A trade printing at or above the offer was buyer-initiated and can only lift my
    offer; at or below the bid, seller-initiated and can only hit my bid. Round-trip
    capacity is therefore the smaller of the two sides:

        ceiling = min(to_my_bid, to_my_ask) * (spread - 2) / 2

    An upper bound on the market-making component alone. It assumes every interceptable
    lot is captured one tick inside the touch, and ignores the position limit.
    """
    rows = []
    for prod in products:
        tb = ta = 0.0
        spreads = []
        for d in days:
            p, tr = load(data_dir, rnd, d)
            f = split_flow_by_aggressor(p, tr, prod)
            tb += f["to_my_bid"].sum()
            ta += f["to_my_ask"].sum()
            g = p[p["product"] == prod]
            spreads.append((g["ask_price_1"] - g["bid_price_1"]).median())
        sp = float(np.nanmedian(spreads))
        n = len(days)
        rows.append({"product": prod, "flow/day": int(min(tb, ta) / n),
                     "median spread": sp,
                     "MM ceiling/day": int(min(tb, ta) / n * max(sp - 2, 0) / 2)})
    return pd.DataFrame(rows)


def rolling_vr(x, sub: int = 10, win: int = 200, k: int = 20) -> np.ndarray:
    """
    Variance ratio on a rolling window — an intraday regime test.

    Sampled every `sub` ticks, `win` samples deep, so the window spans sub*win ticks and
    lag k corresponds to sub*k ticks on the original series. Round 2 uses it to show the
    regime break was detectable while it was happening.
    """
    x = np.asarray(x, dtype=float)[::sub]
    out = []
    for i in range(win, len(x)):
        s = x[i - win:i]
        d1 = np.diff(s)
        out.append(float(np.var(s[k:] - s[:-k]) / (k * np.var(d1))) if d1.var() > 1e-12 else 1.0)
    return np.array(out)
