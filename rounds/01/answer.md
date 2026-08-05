# Round 1 — Strategy Specification

`INTARIAN_PEPPER_ROOT` (ROOT) and `ASH_COATED_OSMIUM` (ASH), position limit ±80 each.

Every rule below is either forced by the exchange mechanics or measured from the pre-round
data. §6 lists each rule against its evidence, and marks the one quantity that is a stated
preference rather than a measurement.

Derivation: [`research/round1.ipynb`](../../research/round1.ipynb).

---

## 1. Notation

| | |
|---|---|
| $i$ | tick index, $0 \le i \le M$, $M = 10{,}000$ |
| $\Delta$ | timestamps per tick, $\Delta = 100$ |
| $q$ | inventory, $\lvert q \rvert \le L = 80$ |
| $F_i$ | reference price (product-specific, §3–§4) |
| $\phi_i$ | depth imbalance, $\dfrac{\sum \text{bid sizes} - \sum \text{ask sizes}}{\sum \text{bid sizes} + \sum \text{ask sizes}}$ over three levels |
| $V_i(q)$ | value function: max expected terminal cash plus inventory marked at $F_M$ |
| $\Delta V_i(q)$ | $V_i(q) - V_i(q-1)$ |

---

## 2. The common problem

Both products pose the same decision at every tick: holding $q$ with $M-i$ ticks left, where
to quote and what to lift. Only the law of $F_i$ differs.

$$V_M(q) = q\,F_M$$

Buying one lot at $p$ costs $p$ and delivers a lot worth $\Delta V_{i+1}(q+1)$. Therefore

$$\boxed{\ \text{buy iff } p < \Delta V_{i+1}(q+1) \qquad \text{sell iff } p > \Delta V_{i+1}(q)\ }$$

$\Delta V$ is the reservation price. $V$ is concave in $q$ because the limit binds, so
$\Delta V$ declines as inventory builds and **inventory control needs no separate skew term**.

```
TRADE(i, q, book):
    r_buy  <- ΔV[i+1][q+1]        if q <  L  else -inf
    r_sell <- ΔV[i+1][q]          if q > -L  else +inf

    for p ascending  in offers:  if p < r_buy:  BUY  min(size, L-q) @ p
    for p descending in bids:    if p > r_sell: SELL min(size, L+q) @ p

    POST BUY  min(L-q, S) @ min(best_bid + 1, floor(r_buy))
    POST SELL min(L+q, S) @ max(best_ask - 1, ceil(r_sell))
```

**Quote size $S = 10$.** Arriving flow has a median of 5 lots and a maximum of 13; quoting
10 captures **99.8%** of it and quoting 80 captures 100%. Size above ~10 is immaterial.

**Quotes are clipped to the reservation price, never skipped.** Posting one tick inside the
touch is free optionality whenever that price is on the profitable side of $\Delta V$.

---

## 3. ROOT — deterministic drift

### 3.1 Reference price

$$F_i = c + \mu\,\Delta\,i, \qquad \mu = 0.001 \ \text{per timestamp}$$

$c$ is estimated as the running mean of $(m_t - \mu t)$, and may be seeded from the previous
day's value plus 1,000.

> $\mu$ is per *timestamp*. One tick spans 100 of them and a session spans 1,000,000 — a move
> of 1,000. Reading $\mu$ as per-tick understates the drift a hundredfold and inverts §3.3.

### 3.2 Value function

Holding one lot through a tick earns $\mu\Delta$ with certainty:

$$\Delta V_i(q) = F_i + \underbrace{\mu\Delta(M-i)}_{\text{drift remaining}} - \underbrace{\Lambda_i(q)}_{\text{shadow price of capacity}}$$

$\Lambda_i(q)$ rises with $q$ and falls with $i$: the $q$-th lot consumes capacity that could
otherwise absorb a cheap offer later, and that option is worth less as the session runs out.

### 3.3 Accumulation — lift, do not wait

| | cost per lot |
|---|---:|
| resting passively: 75 lots take until timestamp 86,800, so the average lot arrives ~43,400 late | **43.4** |
| lifting the offer instead | **8.1** |

Waiting is five times more expensive, because the position is absent while the drift accrues.
Offers never sit worse than ~10 above fair, so in practice the rule lifts the whole ladder.

### 3.4 Reserve

$\Delta V$ falls as $q \to L$, so the policy stops accumulating before the limit binds and
keeps a reserve to sell into strength and re-buy. Each reserved lot forgoes 1,000 of drift and
earns roughly 59 of spread, so **the reserve is a few lots, not tens**.

### 3.5 Replenishment

After a passive sale, $\Delta V_{i+1}(q+1)$ jumps back and the aggressive branch fires at once.
Resting instead leaves the position below target while the drift accrues regardless.

---

## 4. ASH — mean reversion

### 4.1 Reference price

$$\hat F_i = \alpha\,m_i + (1-\alpha)\hat F_{i-1}, \qquad \alpha \sim \mathcal{O}(1/h),\quad h \approx 130 \text{ ticks}$$

$h$ is the **empirical** half-life — the lag at which the autocorrelation crosses 0.5. The
AR(1) estimate is 1.6–2.9 ticks and is wrong: observation noise biases $\hat\phi$ toward zero.

### 4.2 The signal, measured

Bucketing by deviation from the mean and measuring the realised move over the next 130 ticks:

| deviation | subsequent move | $t$ |
|---:|---:|---:|
| below −12 | **+7.31** | 2.4 |
| −12 … −9 | +4.98 | 2.5 |
| −9 … −6 | +3.50 | 3.0 |
| −3 … −1 | +0.89 | 1.3 |
| −1 … +1 | +0.09 | 0.1 |
| +3 … +6 | −1.62 | −2.1 |
| +9 … +12 | −5.22 | −3.0 |
| above +12 | **−8.75** | −2.8 |

Monotone across eleven buckets, crossing zero at zero deviation, and **linear**:

$$\mathbb{E}\big[F_{i+h} - F_i\big] \approx -0.5\,(F_i - \bar P)$$

Half the deviation reverts within $h$ — which is what a half-life of $h$ means. The two
measurements were taken independently and agree.

### 4.3 Value function

$$\Delta V_i(q) = \bar P + (\hat F_i - \bar P)e^{-\theta(M-i)} - \Lambda_i(q)$$

Below $\bar P$ the reservation prices rise above the market, so the policy bids more and
offers less. **The directional view and the quoting centre are one object.**

Target inventory is linear in deviation and saturates at the limit:

$$q^\star(F) = -L\cdot\mathrm{clip}\!\left(\frac{F - \bar P}{K},\ -1,\ 1\right)$$

The **linear shape is measured** (§4.2). $K$ — the deviation at which the position saturates
— is **not derivable from the data**: it trades expected return against inventory risk and
against capacity reserved for quoting, and that trade-off requires a stated risk preference.
It is the only free quantity in this specification.

---

## 5. Depth imbalance — a quote lean, not a trade

Measured against the **outer** (largest-level) fair price, which inner-order churn does not
contaminate:

| | coefficient | $r$ | $t$ at $h{=}1$ | $t$ at $h{=}50$ |
|---|---:|---:|---:|---:|
| ASH, three-level depth | **+2.43** | 0.219 | 37.3 | 4.3 |
| ROOT, three-level depth | **+2.56** | 0.260 | 44.8 | 6.6 |
| best-level only | +0.58 / +0.62 | 0.04 | 7.5 | ~1 |

Depth-weighted imbalance predicts the outer fair and the effect persists to 50 ticks.
Best-level imbalance alone is far weaker.

**It cannot be crossed on.** Full imbalance predicts a move of about 4.9 while crossing the
spread costs 8. It enters as a shift of the quoting centre:

$$F_i \leftarrow F_i + \beta\,\phi_i, \qquad \beta \approx 2.5$$

> Measuring this against the best-level midpoint instead reverses the ranking of the two
> imbalance definitions — inner orders move the touch and the touch-based size simultaneously.
> The outer fair is the correct target.

---

## 6. Evidence

| Rule | Evidence |
|---|---|
| ROOT fair $= c + \mu\Delta i$ | residual sd constant across the session (2.01/2.00/2.02); VR(200) = 0.005 |
| $c$ seeded from the previous day | intercepts 10,000 / 11,000 / 12,000 exactly; 13,000 realised |
| Lift rather than rest | 43.4 forgone against 8.1 paid |
| Small reserve | 1,000 of drift against 59 of spread per lot |
| Replenish aggressively | drift is continuous; time below target is a direct cost |
| ASH fair = smoothed mid | AR(1) vs empirical half-life diverge under noise (simulation) |
| $h \approx 130$ ticks | autocorrelation crosses 0.5 at 76–213 |
| $q^\star$ linear in deviation | eleven monotone buckets; coefficient −0.5 |
| Reversion coefficient −0.5 over $h$ | agrees with the independently measured half-life |
| Quote size 10 | flow median 5, max 13; 10 captures 99.8% |
| Quotes clipped, not skipped | posting inside the touch is free when on the right side of $\Delta V$ |
| Imbalance lean $\beta \approx 2.5$ | coefficient +2.43 / +2.56 against the outer fair, $t = 37$ / 45, persisting to $h{=}50$ |
| Imbalance not crossable | predicts 4.9 against a crossing cost of 8 |
| Fair from best mid, not largest level | largest-level midpoint has higher residual sd against ROOT's known line |
| **$K$ (saturation deviation)** | **not measurable — a stated risk preference** |

Fifteen rules. Fourteen rest on a measurement or on the exchange mechanics; one is a
preference, and is labelled.

---

## 7. What the submission did instead

| | specified above | submitted |
|---|---|---|
| ROOT sell side | reserve a few lots and quote them; replenish aggressively | **no sell branch exists** |
| ROOT entry | lift the ladder | lifts the ladder ✓ |
| ASH inventory | target linear in deviation from $\bar P$ | inventory independent of price; session mark-to-market **+101** |
| ASH quoting | clip to the reservation price | skips the quote when the touch is unattractive |
| Imbalance | quoting centre leans with depth | not used |
| Quote size | 10 | 10 (the adaptive rule sits at its floor) ✓ |
