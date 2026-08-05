# Round 3 — Strategy Specification

Twelve products. The framework from [`rounds/01/answer.md`](../01/answer.md) applies to each
of them unchanged: state $(i,q)$, value function $V_i(q)$, reservation prices
$\Delta V_{i+1}(q+1)$ to buy and $\Delta V_{i+1}(q)$ to sell.

**Only the reference price $F_i$ differs between products, and for two of them it comes from
an identity rather than a model.**

Derivation: [`research/round3.ipynb`](../../research/round3.ipynb).

---

## 1. The organising fact

Two measurements point in opposite directions:

| | |
|---|---|
| The instruments have no exploitable dynamics | `HYDROGEL_PACK` VR(50) = 0.845–0.961, `VELVETFRUIT_EXTRACT` 0.809–1.030 |
| The relationship between them is exact | deep-ITM basis: mean 0.01, sd 0.82, **VR(200) = 0.005** |

Therefore, throughout this round:

$$\theta = 0 \quad \text{for every product}$$

No directional term anywhere. The only structure enters through $F_i$ for the deep in-the-money
vouchers, where it is supplied by an identity.

**This round examines whether structure and noise can be told apart.**

---

## 2. Reference prices

### 2.1 `HYDROGEL_PACK`, `VELVETFRUIT_EXTRACT`

$$F_i = \text{smoothed mid}, \qquad \theta = 0$$

$\Delta V_i(q) = F_i - \Lambda_i(q)$ — reference price adjusted for inventory only. Quoting is
symmetric.

> A non-zero $\theta$ here is exactly the submitted `UNDERLYING_MR_THR = 15`. The variance
> ratios rule it out.

### 2.2 `VEV_4000`, `VEV_4500` — identity

$$\boxed{\ F_i = S_i - K\ }$$

No volatility. No time to expiry. No smile.

Time value is 0.01 and the basis has sd 0.82 with VR(200) = 0.005. **Any Black-Scholes
valuation must first estimate $\sigma$, and the estimation error alone exceeds 0.82** — the
identity is strictly more accurate than any model requiring a fit.

**Overturned if** $S$ approaches $K$, where time value ceases to be negligible. Monitor
$S - K$.

### 2.3 `VEV_5000` … `VEV_5500`

Time value here is genuine (5–51), so pricing requires a volatility model. **Interceptable
flow at 5000, 5100 and 5200 is zero**, so that modelling cost buys no business at those
strikes.

At 5300–5500 there is one-sided seller flow (138–312 lots/day) across a 1–2 tick spread,
worth 2–143 a day. Quote them at the touch (§3.2); do not build a volatility model for them.

### 2.4 `VEV_6000`, `VEV_6500`

Pinned at bid 0 / ask 1 all session, delta 0.000. **334 lots a day of sellers, at +0.50 of
edge per lot — the largest one-sided flow in the chain.** Worth 167 a day each.

---

## 3. Policy

```
for each product P:
    F      <- reference price of P per §2
    r_buy  <- ΔV[i+1][q+1]                        # = F - Λ(q+1)
    r_sell <- ΔV[i+1][q]                          # = F - Λ(q)

    for p ascending  in offers:  if p < r_buy:  BUY  min(size, limit-q) @ p
    for p descending in bids:    if p > r_sell: SELL min(size, limit+q) @ p

    # quoting — see §3.2 for the spread guard
    bid_px <- best_bid + 1  if spread > 1  else best_bid
    ask_px <- best_ask - 1  if spread > 1  else best_ask
    POST BUY  min(limit-q, S) @ min(bid_px, floor(r_buy))
    POST SELL min(limit+q, S) @ max(ask_px, ceil(r_sell))

# delta hedge, since voucher flow is one-sided
hedge <- - Σ_k  δ_k · q_k                          # δ from §5 of the notebook
steer VELVETFRUIT_EXTRACT's reservation prices toward `hedge`
```

### 3.1 Effort allocation

$$\text{PACK }(4{,}573) \;>\; \text{FRUIT }(1{,}672) \;>\; \text{VEV\_4000 }(1{,}528) \;>\; \text{the other nine }(576 \text{ combined})$$

**All ten vouchers together are worth less than half of `HYDROGEL_PACK` alone.** The
submission's attention ran in the reverse order.

### 3.2 The one-tick spread guard

Where the spread is 1 there is no inside to quote: posting at `best_bid + 1` *is* the offer.
On `VEV_5400`–`VEV_6500` that would mean paying 1 for something worth 0.5, turning +0.50 of
edge per lot into −0.50. **Quote the touch instead.**

### 3.3 Hedging

Voucher flow runs one way — participants sell, nobody buys — so a voucher book accumulates a
long position that cannot be unwound in the same instrument. The delta is carried in
`VELVETFRUIT_EXTRACT`, which has 1,114 lots a day of two-sided flow. Deltas: 0.745 at 4000,
0.055 at 5500, 0.000 at 6000 and above.

---

## 4. A required pre-submission check

The failure in this round was operational, not a modelling error, and warrants a rule:

```
before submitting:
    run the strategy over every pre-round day
    print the order count per product
    if any product shows zero orders on any day -> do not submit
```

Under a minute to run. It would have caught this round's ten silent products on all three
pre-round days.

**More generally: any rule of the form "act only when signal > threshold" must have the
signal's realised distribution checked against the threshold before submission.** Here the
threshold sat 47% above the signal's all-time maximum.

Related: replace `except: pass` with logging. It swallowed nothing here — the replay proves
the gate was reached on 9,990 of 10,000 ticks — but establishing that required reconstructing
the run, because from the log alone "silent" and "crashed" are the same thing.

---

## 5. Evidence

| Rule | Evidence |
|---|---|
| $\theta = 0$ on both spot products | VR(50) 0.845–1.030; reversion slope ≈ −0.002 |
| $F = S - K$ at strikes 4000 and 4500 | time value 0.01; basis sd 0.82, VR(200) 0.005 |
| No volatility model for those strikes | $\sigma$ estimation error exceeds the 0.82 residual it would model |
| Basis used for quoting, never as an arbitrage | sd 0.82 against a 21-tick spread |
| No arbitrage across strikes | monotonicity, convexity, bounds: zero violations, three days, executable prices |
| Skip 5000–5200 | genuine time value; zero interceptable flow |
| Quote 5300–6500 at the touch | one-sided flow 138–334 lots/day at +0.37 to +0.50 per lot |
| One-tick spread guard | posting inside a 1-tick spread inverts the edge from +0.50 to −0.50 |
| Hedge the delta in FRUIT | voucher flow is one-sided; FRUIT carries 1,114 lots/day two-sided |
| Effort ordered PACK > FRUIT > VEV_4000 | 4,573 / 1,672 / 1,528 against 576 for the rest |
| Zero-order check before submitting | zero voucher orders on all three pre-round days |

Every rule rests on a measurement.

---

## 6. Open

**Whether the at-the-money vouchers' resting quotes are mispriced against a volatility
surface.** A rank-64 team reports the at-the-money cluster carrying the bulk of their voucher
PnL, which cannot come from intercepting flow — there is none at 5000 and 5100. It would have
to come from lifting mispriced resting size, which requires a volatility model to identify.

Not tested here. If it holds, §2.3 changes and the effort allocation in §3.1 changes with it.
