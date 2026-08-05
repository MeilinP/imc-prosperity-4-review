"""Round 3 — figures for rounds/03/3-what-the-market-is.md."""
import sys; sys.path.insert(0, "../tools")
import numpy as np, pandas as pd, product_props as pp
from benchmarks import split_flow_by_aggressor

DATA, RND, DAYS = "../data/round3", 3, [0, 1, 2]
PACK, FRUIT = "HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"
STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
VEV = [f"VEV_{k}" for k in STRIKES]
pd.set_option("display.width", 220)

def mid(p, prod):
    g = p[p["product"] == prod].set_index("timestamp")
    return ((g["bid_price_1"] + g["ask_price_1"]) / 2).ffill().bfill()

print("§1  Are the vouchers call options? Price = intrinsic + time value,")
print("    with time value vanishing deep in the money.")
p, _ = pp.load(DATA, RND, 0)
S = mid(p, FRUIT)
rows = []
for k in STRIKES:
    C = mid(p, f"VEV_{k}")
    idx = S.index.intersection(C.index)
    s, c = S[idx], C[idx]
    intr = np.maximum(s - k, 0)
    rows.append({"K": k, "mean price": round(c.mean(), 2),
                 "intrinsic": round(intr.mean(), 2),
                 "time value": round((c - intr).mean(), 2),
                 "ticks priced above S": f"{(c > s).mean():.1%}"})
print(pd.DataFrame(rows).to_string(index=False))

print("\n§1  Delta by strike (regression of dC on dS) — must be monotone in [0,1]")
rows = []
for d in DAYS:
    p, _ = pp.load(DATA, RND, d)
    S = mid(p, FRUIT); dS = S.diff()
    r = {"day": d}
    for k in STRIKES:
        C = mid(p, f"VEV_{k}")
        j = dS.dropna().index.intersection(C.diff().dropna().index)
        r[k] = round(np.polyfit(dS[j], C.diff()[j], 1)[0], 3) if dS[j].var() > 1e-12 else np.nan
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))

print("\n§1  Static arbitrage, checked on executable prices (not mids)")
for d in DAYS:
    p, _ = pp.load(DATA, RND, d)
    g = {x: p[p["product"] == x].set_index("timestamp") for x in [FRUIT] + VEV}
    ts = g[FRUIT].index
    v1 = sum(int((g[f"VEV_{STRIKES[i]}"]["ask_price_1"].reindex(ts)
                  < g[f"VEV_{STRIKES[i+1]}"]["bid_price_1"].reindex(ts)).sum())
             for i in range(len(STRIKES) - 1))
    v2 = 0
    for i in range(len(STRIKES) - 2):
        k1, k2, k3 = STRIKES[i:i+3]
        if k1 + k3 != 2 * k2: continue
        v2 += int(((g[f"VEV_{k1}"]["ask_price_1"].reindex(ts)
                    + g[f"VEV_{k3}"]["ask_price_1"].reindex(ts)
                    - 2 * g[f"VEV_{k2}"]["bid_price_1"].reindex(ts)) < 0).sum())
    print(f"   day {d}: monotonicity violations {v1}, convexity violations {v2}")

print("\n§2  Are the two spot products mean reverting?  (compare with round 1's ASH: VR(50)=0.025)")
for prod in (PACK, FRUIT):
    print(f"   -- {prod}")
    print(pp.ou_check(DATA, RND, DAYS, prod).to_string(index=False))

print("\n§3  The one quantity that does revert: basis = C - (S - K)")
print(f"   {'K':>6s} {'day':>4s} {'mean':>8s} {'sd':>6s} {'VR(50)':>8s} {'VR(200)':>8s}")
for k in (4000, 4500, 5000):
    for d in DAYS:
        p, _ = pp.load(DATA, RND, d)
        b = (mid(p, f"VEV_{k}") - (mid(p, FRUIT) - k)).dropna().to_numpy()
        print(f"   {k:>6d} {d:>4d} {b.mean():>8.2f} {b.std():>6.2f} "
              f"{pp.vr(b,50):>8.3f} {pp.vr(b,200):>8.4f}")
print("   sd of the basis is ~0.8 while VEV_4000's spread is 21 — a fair-value")
print("   estimator, not an arbitrage.")

print("\n§4  Where the flow is")
print(pp.flow_check(DATA, RND, DAYS, [PACK, FRUIT] + VEV).to_string(index=False))
