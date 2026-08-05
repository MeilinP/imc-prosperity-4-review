"""Round 5 — figures for rounds/05/3-what-the-market-is.md."""
import sys; sys.path.insert(0, "../tools")
import numpy as np, pandas as pd, product_props as pp
from benchmarks import split_flow_by_aggressor

DATA, RND, DAYS = "../data/round5", 5, [2, 3, 4]
GROUPS = ["GALAXY_SOUNDS", "MICROCHIP", "OXYGEN_SHAKE", "PANEL", "PEBBLES",
          "ROBOT", "SLEEP_POD", "SNACKPACK", "TRANSLATOR", "UV_VISOR"]
PAIRS = [("TRANSLATOR_ECLIPSE_CHARCOAL", "TRANSLATOR_VOID_BLUE", 0.500071),
         ("PANEL_2X2", "PANEL_4X4", -0.778745),
         ("SNACKPACK_PISTACHIO", "SNACKPACK_STRAWBERRY", -0.163593),
         ("GALAXY_SOUNDS_DARK_MATTER", "GALAXY_SOUNDS_BLACK_HOLES", 0.443447),
         ("MICROCHIP_OVAL", "MICROCHIP_RECTANGLE", 0.848069)]
TREND = {"PEBBLES_XL": 1, "OXYGEN_SHAKE_GARLIC": 1, "TRANSLATOR_SPACE_GRAY": -1,
         "MICROCHIP_TRIANGLE": -1, "GALAXY_SOUNDS_SOLAR_FLAMES": 1,
         "GALAXY_SOUNDS_PLANETARY_RINGS": 1}
pd.set_option("display.width", 200)

def mids(p):
    return {x: ((p[p["product"] == x].set_index("timestamp")["bid_price_1"]
                 + p[p["product"] == x].set_index("timestamp")["ask_price_1"]) / 2).ffill().bfill()
            for x in p["product"].unique()}

print("§1  Does any group's five prices sum to a constant?")
for d in DAYS:
    p, _ = pp.load(DATA, RND, d)
    m = mids(p)
    print(f"   day {d}  " + "  ".join(
        f"{g[:9]}:{sum(v for k, v in m.items() if k.startswith(g)).std():7.1f}" for g in GROUPS))
print("   Only PEBBLES is pinned. Its five prices sum to 50,000.")

print("\n§2  Can the identity be arbitraged?")
p, _ = pp.load(DATA, RND, 2)
m = mids(p)
pb = [x for x in m if x.startswith("PEBBLES")]
s = sum(m[x] for x in pb)
cost = sum((p[p["product"] == x]["ask_price_1"] - p[p["product"] == x]["bid_price_1"]).median()
           for x in pb)
print(f"   deviation sd = {s.std():.2f},  90th pct of |deviation| = {np.percentile(abs(s-50000),90):.2f}")
print(f"   cost of executing all five legs  = {cost:.0f}")
print("   Cost exceeds the deviation twentyfold: a fair-value estimator, not a trade.")

print("\n§3  The five spreads that were traded: log(A) - beta*log(B). Do they revert?")
print(f"   {'pair':<52s} {'VR(50)':>8s} {'VR(200)':>8s}")
for A, B, beta in PAIRS:
    v = []
    for d in DAYS:
        p, _ = pp.load(DATA, RND, d)
        m = mids(p)
        if A in m and B in m:
            sp = np.log(m[A]) - beta * np.log(m[B])
            v.append((pp.vr(sp, 50), pp.vr(sp, 200)))
    print(f"   {A[:24]:<24s} / {B[:24]:<24s} {np.mean([x[0] for x in v]):>8.3f} "
          f"{np.mean([x[1] for x in v]):>8.3f}")
print("\n   For scale, the PEBBLES five-sum:")
for d in DAYS:
    p, _ = pp.load(DATA, RND, d)
    s = sum(v for k, v in mids(p).items() if k.startswith("PEBBLES"))
    print(f"   day {d}: VR(50)={pp.vr(s,50):.4f}  VR(200)={pp.vr(s,200):.4f}")

print("\n§4  Did the six fixed directions have any pre-round basis?")
print(f"   {'product':<32s} {'bet':>4s}  " + " ".join(f"{'day'+str(d):>9s}" for d in DAYS) + "  agree")
for prod, dirn in TREND.items():
    moves, agree = [], 0
    for d in DAYS:
        p, _ = pp.load(DATA, RND, d)
        m = mids(p)
        mv = m[prod].iloc[-1] - m[prod].iloc[0] if prod in m else np.nan
        moves.append(mv)
        agree += int(np.sign(mv) == dirn)
    print(f"   {prod:<32s} {dirn:>+4d}  " + " ".join(f"{x:>+9.0f}" for x in moves) + f"  {agree}/3")
print("   2 of 3 is the modal outcome of three coin flips.")

print("\n§5  Where the flow is (top 12 of 50)")
t = pp.flow_check(DATA, RND, DAYS, sorted(p["product"].unique()))
t = t.sort_values("MM ceiling/day", ascending=False)
print(t.head(12).to_string(index=False))
print(f"\n   all fifty products: {t['MM ceiling/day'].sum():,}/day")
print(f"   top ten as a share: {100*t.head(10)['MM ceiling/day'].sum()/t['MM ceiling/day'].sum():.0f}%")
