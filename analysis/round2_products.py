"""Round 2 — figures for rounds/02/3-what-the-market-is.md.

The question is not what these products are (round 1 established that) but whether
round 1's conclusions still hold. One does; one does not.
"""
import sys; sys.path.insert(0, "../tools")
import numpy as np, pandas as pd, product_props as pp, prosperity_review as pr

DATA, RND, DAYS = "../data/round2", 2, [-1, 0, 1]
ROOT, ASH = "INTARIAN_PEPPER_ROOT", "ASH_COATED_OSMIUM"
pd.set_option("display.width", 200)

print("§1  ROOT on the pre-round days — the intercept sequence")
print(pp.drift_check(DATA, RND, DAYS, ROOT).to_string(index=False))

print("\n§2  ASH on the pre-round days — indistinguishable from round 1")
print(pp.ou_check(DATA, RND, DAYS, ASH).to_string(index=False))

print("\n§1-2  The scored day, recovered from the exchange log")
log = pr.load_log("../submissions/round2.log")
a = log.activities
for prod in (ROOT, ASH):
    g = a[a["product"] == prod].reset_index(drop=True)
    f = pp.largest_level_mid(g).to_numpy()
    if prod == ROOT:
        b, c = np.polyfit(g["timestamp"], f, 1)
        res = f - (c + b * g["timestamp"])
        print(f"   ROOT  slope={b:.6f}  intercept={c:.1f}  "
              f"R2={1-res.var()/f.var():.6f}  sd(resid)={res.std():.2f}")
    else:
        ac = [np.corrcoef(f[:-k], f[k:])[0, 1] for k in range(1, 2000)]
        hl = next((k for k, v in enumerate(ac, 1) if v < 0.5), ">2000")
        q = len(f) // 4
        print(f"   ASH   mean={f.mean():.2f}  sd={f.std():.2f}  "
              f"half-life={hl}  VR(200)={pp.vr(f,200):.3f}")
        print("         quartile means: " + " -> ".join(f"{f[i*q:(i+1)*q].mean():.1f}" for i in range(4)))

print("\n§3  Was the regime break detectable intraday? Rolling VR(200) on ASH")
print(f"   {'day':>8s} {'median':>8s} {'90th pct':>10s} {'share > 0.15':>14s}")
for d in DAYS:
    p, _ = pp.load(DATA, RND, d)
    v = pp.rolling_vr(pp.largest_level_mid(p[p["product"] == ASH].reset_index(drop=True)).to_numpy())
    print(f"   {d:>8d} {np.median(v):>8.3f} {np.percentile(v,90):>10.3f} {(v>0.15).mean():>13.1%}")
g = a[a["product"] == ASH].reset_index(drop=True)
v = pp.rolling_vr(pp.largest_level_mid(g).to_numpy())
print(f"   {'scored':>8s} {np.median(v):>8.3f} {np.percentile(v,90):>10.3f} {(v>0.15).mean():>13.1%}  <-")
