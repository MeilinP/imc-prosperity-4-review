"""Round 1 — every figure quoted in rounds/01/3-what-the-market-is.md."""
import sys; sys.path.insert(0, "../tools")
import numpy as np, pandas as pd, product_props as pp

DATA, RND, DAYS = "../data/round1", 1, [-2, -1, 0]
ROOT, ASH = "INTARIAN_PEPPER_ROOT", "ASH_COATED_OSMIUM"
pd.set_option("display.width", 200)

print("§1  ROOT: deterministic line, or random walk with drift?")
print("    A random walk's residual grows with sqrt(t); a deterministic line's does not.")
print(pp.drift_check(DATA, RND, DAYS, ROOT).to_string(index=False))

print("\n§2  ASH: mean reverting, random walk, or trending?")
print("    beta<0 and VR<<1 rule out both alternatives.")
print("    Note the two half-life columns — see §2 of the document.")
print(pp.ou_check(DATA, RND, DAYS, ASH).to_string(index=False))

print("\n§2  Attenuation bias, demonstrated on synthetic data")
print("    True half-life 138; observation noise is added and both estimators re-run.")
rng = np.random.default_rng(0)
n, phi = 10000, 0.995
x = np.zeros(n)
for i in range(1, n):
    x[i] = phi * x[i - 1] + rng.normal(0, 1)
print(f"    {'noise sd':>10s} {'AR(1) half-life':>17s} {'empirical half-life':>21s}")
for noise in (0, 1, 3, 5):
    y = x + rng.normal(0, noise, n)
    b = np.polyfit(y[:-1], y[1:], 1)[0]
    hl = np.log(2) / -np.log(b) if 0 < b < 1 else np.nan
    ac = [np.corrcoef(y[:-k], y[k:])[0, 1] for k in range(1, 900)]
    print(f"    {noise:>10d} {hl:>17.1f} {next((k for k,v in enumerate(ac,1) if v<0.5), 900):>21d}")

print("\n§3  Is the book two-layered?")
print(pp.layer_check(DATA, RND, DAYS, [ASH, ROOT]).to_string(index=False))
print("    Structure is real — but §1's table shows the largest-level mid is the *worse*")
print("    fair-price estimator on ROOT, where the truth is known.")

print("\n§4  Interceptable flow and the market-making ceiling")
print(pp.flow_check(DATA, RND, DAYS, [ASH, ROOT]).to_string(index=False))
