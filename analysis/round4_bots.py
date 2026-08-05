"""Round 4 — which counterparties are informed. Figures for rounds/04/3-what-the-market-is.md.

Test: an informed counterparty's purchases precede price rises. For each name, sign every
trade it participated in by its own direction and average the mid-price change over the
following h ticks, with standard errors.

Not its P&L: that is dominated by entry timing and position management, and measured across
all names it is indistinguishable from zero. Forward price change measures information
content directly.

Estimated on the pre-round days, validated on the scored day. Estimating on the scored day
would be circular.
"""
import sys; sys.path.insert(0, "../tools")
import numpy as np, pandas as pd, product_props as pp, prosperity_review as pr

DATA, RND, DAYS = "../data/round4", 4, [1, 2, 3]
SPOT = ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]
H = 50

def edges(prices, trades, product, h=H):
    g = prices[prices["product"] == product].set_index("timestamp")
    m = ((g["bid_price_1"] + g["ask_price_1"]) / 2).ffill().bfill()
    ts = m.index.to_numpy(); pos = {t: i for i, t in enumerate(ts)}
    out = {}
    for _, r in trades[trades["symbol"] == product].iterrows():
        for name, side in ((r["buyer"], 1), (r["seller"], -1)):
            if not isinstance(name, str) or name in ("", "SUBMISSION"): continue
            i = pos.get(int(r["timestamp"]))
            if i is None or i + h >= len(ts): continue
            out.setdefault(name, []).append(side * (m.iloc[i + h] - m.iloc[i]))
    return out

def report(e, label):
    print(f"  {label}")
    rows = []
    for k, v in e.items():
        v = np.asarray(v)
        if len(v) < 50: continue
        se = v.std(ddof=1) / np.sqrt(len(v))
        rows.append((k, len(v), v.mean(), se, v.mean() / se))
    for k, n, mu, se, t in sorted(rows, key=lambda x: -x[4]):
        flag = "***" if abs(t) > 3 else ("**" if abs(t) > 2 else "")
        print(f"    {k:<10s} n={n:<6d} {mu:+7.3f} +/- {se:5.3f}   t={t:+6.2f} {flag}")

print("Round 3's conclusions, re-checked on this round's pre-round days")
for prod in SPOT:
    t = pp.ou_check(DATA, RND, DAYS, prod)
    print(f"  {prod}: VR(50) = " + " / ".join(f"{v:.3f}" for v in t["VR(50)"]))

print(f"\nCounterparty information content, h = {H} ticks")
print("(positive: it buys and price rises. |t| > 2 marked **, > 3 marked ***)")
for prod in SPOT:
    acc = {}
    for d in DAYS:
        p, tr = pp.load(DATA, RND, d)
        for k, v in edges(p, tr, prod).items():
            acc.setdefault(k, []).extend(v)
    report(acc, f"{prod} — pre-round days")

log = pr.load_log("../submissions/round4.log")
for prod in SPOT:
    report(edges(log.activities, log.trades, prod), f"{prod} — scored day (out of sample)")
