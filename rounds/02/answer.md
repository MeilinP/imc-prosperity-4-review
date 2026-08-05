# Round 2 — Strategy Specification

Same products and limits as Round 1. The framework in
[`rounds/01/answer.md`](../01/answer.md) is unchanged: state $(i,q)$, value function
$V_i(q)$, reservation prices $\Delta V_{i+1}(q+1)$ to buy and $\Delta V_{i+1}(q)$ to sell.

This document specifies only what changes, and why.

Derivation: [`research/round2.ipynb`](../../research/round2.ipynb).

---

## 1. What changes, and what does not

| Round 1 conclusion | status on the scored day | consequence |
|---|---|---|
| A · ROOT is a line; the intercept is an arithmetic sequence | **held exactly** (14,000, residual sd 0.21) | reuse unchanged; seed the intercept |
| B · ASH mean-reverts, half-life ≈ 130 | **failed** (half-life 625, VR(200) 0.339) | gate the reversion term |
| C · depth imbalance leads the outer fair, $\beta \approx 2.5$ | **failed** (0.3 – 0.7, from 2.4 – 2.9) | gate the imbalance lean |
| D · flow ≈ 1,000 lots/day, spread 13 – 16 | held | unchanged |

A is a structural identity. B and C are statistical estimates. **Both estimates failed, on
the same day; the identity did not.**

---

## 2. ROOT — unchanged, with the intercept seeded

$$F_i = c + \mu\Delta i, \qquad \mu = 0.001 \ \text{per timestamp}$$

```
c_0 <- previous session's intercept + 1000        # 10,000 -> 11,000 -> 12,000 -> 13,000 -> 14,000
c   <- running mean of (m_t - mu*t), initialised at c_0
```

Accumulation, reserve and replenishment as in Round 1 §3. Nothing about ROOT requires
revision.

**Why seeding matters here specifically.** The whole position is built inside the first few
hundred ticks ([Round 1 §3.3](../01/answer.md)), which is exactly when a cold-started running
mean is least settled. Seeding removes the error at the only moment it is expensive.

---

## 3. ASH — a validity condition on the reversion term

### 3.1 The problem, stated in the framework

$$\Delta V_i(q) = \bar P + (\hat F_i - \bar P)\,e^{-\theta(M-i)} - \Lambda_i(q)$$

Two inputs, $\bar P$ and $\theta$, are estimates. On the scored day $\bar P$ moved 18 points
and $\ln 2/\theta$ stretched from ~130 ticks to 625.

Stale values do not merely shrink the edge — **they invert the sizing logic.** The policy
takes a position expecting resolution within ~130 ticks and carries it five times as long.

### 3.2 Estimate $\bar P$ within the session

$\bar P$ must not be a constant in the source.

With half-life $h \approx 130$ ticks, a 10,000-tick session holds roughly $M/2h \approx 40$
independent observations, so

$$\mathrm{se}(\hat{\bar P}) \approx \frac{\sigma_{\text{stat}}}{\sqrt{40}} \approx \frac{5.3}{6.3} \approx 0.84$$

against a **between-day shift of 18.5**. The prior is worth less than a single session of
data.

```
mu_hat <- running mean of F_hat over the current session
if samples < N_warmup:  no directional term; quote only
```

### 3.3 Gate both estimated terms on a live persistence test

$\theta$ cannot be repaired by re-estimating a level — the reversion assumption itself fails.
The gate tests that assumption directly:

```
every 10 ticks:
    append F_hat to window W                       # keep the last 200 samples ~ 2,000 ticks
    if |W| = 200:
        VR <- Var(W[k:] - W[:-k]) / (k * Var(diff W))        # k = 20

if VR >= VR_GATE:                                  # VR_GATE in [0.15, 0.40]
    theta_effective <- 0                           # reversion term off
    beta_effective  <- 0                           # imbalance lean off
```

With both off, $\Delta V_i(q) = \hat F_i - \Lambda_i(q)$: **pure spread capture.** That is the
correct fallback, because spread capture does not rest on either assumption while both gated
terms rest on them entirely.

**Threshold.** Pre-round days sit at 0.09 with the 90th percentile ≤ 0.137; the broken day
sits at 0.579 with 100% of the session above 0.15. Any value in [0.15, 0.40] separates them.

**Why the same gate covers the imbalance lean.** The two signals were measured independently
and failed together on the scored day (README §3). One statistic flags the regime in which
neither is reliable.

### 3.4 Keep the module — do not delete it

| lean strength | 0 | 0.5 | 1.0 |
|---|---:|---:|---:|
| ASH, mean of the eight available days | 17,754 | **18,969** | 19,056 |

Seven of eight days favour leaning. **Removing the term because of one day is the
result-driven error**, and costs about 1,200 a day.

---

## 4. Evidence

| Rule | Evidence |
|---|---|
| ROOT reused unchanged | scored day intercept 14,000 exactly, $R^2 = 0.999999$, residual sd 0.21 |
| Intercept seeded from the sequence | 10,000 / 11,000 / 12,000 / 13,000 / 14,000, four days, zero error |
| Seeding matters at the open specifically | the whole position is built in the first few hundred ticks |
| $\bar P$ estimated within the session | 18.5-point between-day shift against 0.84 estimation error |
| Warm-up before any directional term | standard error scales as $\sigma/\sqrt{M/2h}$ |
| Reversion term gated on rolling VR | half-life 625 vs 54–213; VR(200) 0.339 vs 0.009–0.011 |
| The same gate covers the imbalance lean | both signals failed on the same day, measured independently |
| Fallback is spread capture, not flat | spread capture is independent of both gated assumptions |
| Threshold in [0.15, 0.40] | pre-round 90th pct ≤ 0.137; scored day 100% above 0.15 |
| Directional module retained | 7 of 8 days favour leaning, ≈1,200/day |

Every rule rests on a measurement. **One item is not validated and is marked as such below.**

---

## 5. Not validated

**The gate's implementation does not yet produce a net gain.**

A first implementation recovered **+1,399** on the scored day and lost more, in small amounts,
across the seven normal days — **about −900 net over the eight days**.

Cause, identified: the offline diagnostic computes VR on a **gap-filled** price series
(one-sided books carry the previous value forward) while the in-algorithm version **skips**
those ticks. The two series have different spacing, so the VR baseline differs and the
threshold measured offline does not transfer.

The repair is to make the in-algorithm series match the offline one, then re-verify both that
the separation survives and that the eight-day total improves.

**The threshold was not tuned to make the number look better.** Searching it over the same
eight days would produce a figure fitted to those eight days — the same error this round is
about.
