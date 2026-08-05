# Round 5 — Strategy Specification

Fifty products, position limit **10 each**. The framework from
[`rounds/01/answer.md`](../01/answer.md) applies to every one of them: state $(i,q)$, value
function $V_i(q)$, reservation prices $\Delta V_{i+1}(q+1)$ to buy and $\Delta V_{i+1}(q)$ to
sell.

Fifty instances of one problem. Only the reference price differs, and only for five products.

Derivation: [`research/round5.ipynb`](../../research/round5.ipynb).

---

## 1. The organising fact

Ten groups of five. **One group's prices sum to an exact constant; the other nine do not.**

| | sd of the five-price sum |
|---|---:|
| PEBBLES | **2.8** |
| the other nine groups | 124 – 1,540 |

The examinable skill is separating structure from noise across fifty products — **not finding
as many plausible relationships as possible.** A fitted $\beta$ relates any two series; the
test is whether the resulting spread reverts.

---

## 2. Reference prices

### 2.1 The PEBBLES group — the identity

$$F^{(j)}_i = 50{,}000 - \sum_{k \in \text{PEBBLES},\, k \neq j} P^{(k)}_i$$

Each member's fair value is pinned by the other four to within ±3, against spreads of 12–17.
No estimation, no fitting.

**Do not trade the basket.** Deviation sd 2.82 against a five-leg cost of 65 — the whole
distribution sits inside the cost. The identity is a pricing input, not a trade.

**Overturned if** the sd of the five-sum rises materially above 3.

### 2.2 Four products with persistent short-horizon reversion

| product | d2 | d3 | d4 |
|---|---:|---:|---:|
| `OXYGEN_SHAKE_EVENING_BREATH` | −0.174 | −0.094 | −0.077 |
| `ROBOT_IRONING` | −0.162 | −0.077 | −0.114 |
| `OXYGEN_SHAKE_CHOCOLATE` | −0.121 | −0.007 | −0.111 |
| `ROBOT_DISHES` | −0.001 | −0.004 | −0.290 |

Lag-1 autocorrelation of returns; the other forty-six never exceed 0.024 on any day.

**Enters as a lean on the quoting centre, never as a reason to cross:**

$$F_i \leftarrow F_i - \gamma\,\rho\,r_{i-1}, \qquad \rho = \text{that product's autocorrelation}$$

**Why quoting and not taking.** The predicted move is $|\rho| \times \mathbb{E}|r|$, which is
0.55–2.48. Crossing costs 3.0–6.5. **Not one of the four clears its own spread**, including
`ROBOT_DISHES` on its strongest day. A resting order earns the spread instead of paying it, so
the same signal is usable there and not here.

**Size the first three, not the fourth.** `ROBOT_DISHES` is the loudest single number and the
least consistent — near zero on two days out of three. The other three are weaker and present
every day. This is [Round 4's standard](../04/answer.md): consistency across days, not one
striking value.

### 2.3 The remaining forty-five

$$F_i = \text{smoothed mid}, \qquad \theta = 0$$

No group identity, no persistent autocorrelation. Pure quoting.

---

## 3. Policy

```
for each of the fifty products P:
    F <- 50000 - sum(other four)          if P in PEBBLES
         smoothed mid                     otherwise
    F <- F - gamma * rho_P * last_return  if P in the four reverting products

    r_buy  <- ΔV[i+1][q+1]                # = F - Λ(q+1)
    r_sell <- ΔV[i+1][q]                  # = F - Λ(q)

    for p ascending  in offers:  if p < r_buy:  BUY  min(size, 10-q) @ p
    for p descending in bids:    if p > r_sell: SELL min(size, 10+q) @ p

    bid_px <- best_bid + 1  if spread > 1  else best_bid       # Round 3 §3.2
    ask_px <- best_ask - 1  if spread > 1  else best_ask
    POST BUY  min(10-q, S) @ min(bid_px, floor(r_buy))
    POST SELL min(10+q, S) @ max(ask_px, ceil(r_sell))
```

**Quote all fifty.** Capacity is about 70,000 a day and the top ten are only a third of it;
with a 10-lot limit there is no way to concentrate even if one wanted to. **Breadth is the
design, not a compromise.**

---

## 4. Two modules to remove

**The five pairs.** VR(50) between 0.908 and 0.993 — random walks. Against 0.020 for the
PEBBLES sum and 0.025 for Round 1's ASH, a factor of fifty. Trading them cost −13,518.

> **General rule: before trading any spread on the expectation of reversion, compute its
> variance ratio.** Above ~0.5, do not trade it. The in-sample fit of $\beta$ says nothing
> about this.

**The six fixed directional bets.** Pre-round agreement is two days out of three for five of
the six — the modal outcome under no signal. Sixty lots decided the round, in either direction.

> Neither module is removed because it lost money on the scored day. **Each is removed because
> the property it assumes was measured to be absent beforehand.** Contrast
> [Round 2](../02/answer.md), where the directional module lost on the scored day but was
> profitable on seven of eight days and should be *gated*, not deleted.

---

## 5. Evidence

| Rule | Evidence |
|---|---|
| $F = 50{,}000 - \sum$(other four) for PEBBLES | five-sum sd 2.76–2.82, relative error $5.6\times10^{-5}$, three days |
| Identity for pricing, never as a basket trade | deviation sd 2.82 against a five-leg cost of 65 |
| $\theta = 0$ for the other forty-five | every other group's sum drifts (sd 124–1,540, means unstable between days) |
| Reversion lean on four products | lag-1 autocorrelation −0.077 to −0.290, the other forty-six ≤ 0.024 |
| Lean, never cross | predicted move 0.55–2.48 against a crossing cost of 3.0–6.5 |
| Size the three consistent ones over `ROBOT_DISHES` | that one is near zero on two of three days |
| Remove the five pairs | VR(50) 0.908–0.993 against 0.020 for the PEBBLES sum |
| Remove the six bets | two-of-three agreement for five of six — the modal coin-flip outcome |
| Quote all fifty | capacity ~70,000/day, top ten only a third |
| One-tick spread guard | carried from [Round 3](../03/answer.md) |

Every rule rests on a measurement.

---

## 6. Recorded, not adopted

**The 389,000 attributed to `ROBOT_DISHES`.** A public write-up reports that figure on the
product's strong day. It is not reproducible here, and two independent bounds contradict it:

- market-making capacity on that product is **849 a day**
- the position limit is 10 lots and the full daily range is 1,302, so **perfect foresight with
  the position flipped at every turning point caps out near 13,000**

The signal also cannot be crossed on — 2.48 predicted against a 4.0 half-spread. Neither
mechanism available under these rules reaches that figure.

The specification uses the autocorrelation at the size the measurements support: a quoting
lean worth a few hundred to about 1,600 a day per product.
