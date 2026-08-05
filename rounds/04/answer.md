# Round 4 — Strategy Specification

Same market as Round 3, so [`rounds/03/answer.md`](../03/answer.md) applies in full:
$\theta = 0$ everywhere, $F = S - K$ for the deep in-the-money vouchers, the one-tick spread
guard, delta hedged in `VELVETFRUIT_EXTRACT`, effort ordered
PACK > FRUIT > `VEV_4000` > the rest.

This document records only what the new information changes. **The answer is: nothing.**

Derivation: [`research/round4.ipynb`](../../research/round4.ipynb).

---

## 1. What was re-verified

| Round 3 rule | still supported? |
|---|---|
| $\theta = 0$ on both spot products | ✅ VR(50) 0.881–1.030, slope ≈ −0.002 |
| $F = S - K$ at strikes 4000, 4500 | ✅ basis mean +0.00…+0.02, sd 0.77–0.91, VR(200) 0.0049 |
| Effort ordered PACK > FRUIT > `VEV_4000` | ✅ flow 677 / 1,128 / 138 lots per day |
| One-tick spread guard | ✅ unchanged |

No revision required.

---

## 2. Order-book imbalance: do not add it

Rounds 1–2 measured depth imbalance leading the outer fair with a coefficient near 2.5 and
$t$ near 40. Here:

| | coefficient at $h{=}1$ | $t$ |
|---|---:|---:|
| `HYDROGEL_PACK` | −0.91 | −1.3 |
| `VELVETFRUIT_EXTRACT` | −0.21 | −0.7 |

**No signal**, on the pre-round days or the scored day. The imbalance term belongs to the
Rounds 1–2 market and must not be carried across.

---

## 3. Counterparty names: do not use them

### 3.1 The measurement

For each name, sign every trade it took part in by its own direction and average the mid-price
change over the next 50 ticks. **Per day. Never pooled.**

| | d1 | d2 | d3 | scored |
|---|---:|---:|---:|---:|
| FRUIT · Mark 14 | −0.77 (t −1.6) | −0.72 (t −1.9) | −0.56 (t −1.2) | **−2.70 (t −4.9)** |
| PACK · Mark 14 | +1.31 (t +1.9) | +0.70 (t +1.0) | +0.56 (t +0.7) | **−4.20 (t −4.5)** |

One held. One reversed. **Before the scored day they are indistinguishable**: both consistent
in sign across three days, neither significant on any single day.

### 3.2 Why no admission rule fixes this

Any threshold is applied to the pre-round evidence, and the pre-round evidence is the same for
both. A rule admitting FRUIT · Mark 14 admits PACK · Mark 14.

- *Require sign consistency across days?* Both pass.
- *Require significance on each day?* Both fail.
- *Require a pooled $t$ above some bar?* This is what created the illusion — pooling three
  insignificant days produced $t = -2.70$ for one of them and hid that its twin was equally
  consistent.

**Three days is not enough evidence to separate a counterparty signal from noise here.**

### 3.3 Independent confirmation

A team finishing 64th on the algorithmic leaderboard fitted per-counterparty weights on this
same data with leave-one-out validation, and reported that the weights did not generalise;
disabling them recovered about \$15.8k of held-out PnL.

Two methods, same conclusion.

### 3.4 Specification

```
counterparty names: recorded, not traded on
```

**If a future round supplies more days**, the admission rule is: significant on each day
individually, same sign on every day, and validated on a day held out of estimation. Not a
pooled statistic.

---

## 4. Time to expiry: not a sensitivity

| `DAYS_LEFT` | 4 | 3 | 2 | 1 |
|---|---:|---:|---:|---:|
| total | 43,940 | 43,848 | 43,167 | 42,410 |

3.5% across the whole range, and PACK identical throughout. The vouchers that trade are the
deep in-the-money pair, priced by identity. **No expiry input is required for this book**, which
is a restatement of Round 3 §2.2 rather than a new finding.

---

## 5. Evidence

| Rule | Evidence |
|---|---|
| Round 3's specification reused unchanged | all three findings reproduce on this round's data |
| No imbalance term | coefficient −0.91 / −0.21, $\|t\| \le 1.3$, pre-round and scored |
| No counterparty term | same counterparty holds on one product and reverses on the other; pre-round evidence identical for both |
| Pooled statistics rejected as a validation | pooling three insignificant days produced the apparent signal |
| No expiry input | 3.5% spread across all values of `DAYS_LEFT`; deep-ITM value is $S-K$ |

---

## 6. What this round is worth as a lesson

The market was unchanged and the submission was already close to right. The examinable content
is entirely in the validation:

> **A signal that is consistent across three days, and significant on none of them, is not a
> signal. Pooling the days manufactures the significance.**

The counterfactual is concrete. Adopting FRUIT · Mark 14 on that evidence means adopting
PACK · Mark 14 on identical evidence — and that one reversed, hard, on the day that counted.
