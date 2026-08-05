# IMC Prosperity 4 — A Post-Mortem

**Rank 572 / 18,803.** This is not a highlight reel. It is a review of five submissions I got
wrong, and what the right answers were.

Prosperity runs like an exam: five rounds, five markets, each testing something specific. Each
round here gets the same treatment — what I submitted, what it did, what the market actually
was, and the strategy the evidence supports.

| | | |
|---|---|---|
| **[Round 1](rounds/01/)** | one trending and one mean-reverting instrument | [notebook](research/round1.ipynb) · [specification](rounds/01/answer.md) |
| **[Round 2](rounds/02/)** | the same two, a new day — do the parameters still hold? | [notebook](research/round2.ipynb) · [specification](rounds/02/answer.md) |
| **[Round 3](rounds/03/)** | spot plus ten option strikes | [notebook](research/round3.ipynb) · [specification](rounds/03/answer.md) |
| **[Round 4](rounds/04/)** | the same market, counterparty names revealed | [notebook](research/round4.ipynb) · [specification](rounds/04/answer.md) |
| **[Round 5](rounds/05/)** | fifty products in ten groups | [notebook](research/round5.ipynb) · [specification](rounds/05/answer.md) |

Each round also shipped a one-shot manual puzzle, scored separately:
**[the manual track](manual/)**. In Round 3 it scored **70,444 at rank 442** against the
algorithm's 5,841 at rank 2,093 — twelve times the contribution and five times the rank. That
record is incomplete, since the exchange returns a log for the algorithm and nothing but a
number for the puzzle, and the gaps are stated rather than filled.

---

## What each round was testing, and what I answered

| | the question | the answer | what I submitted |
|---|---|---|---|
| **1** | Identify each price process and trade it accordingly | ROOT is a deterministic line; ASH is mean-reverting with a ~130-tick half-life | traded the trend correctly but wrote **no sell branch at all**; never used ASH's reversion — session mark-to-market on inventory was **+101** |
| **2** | Do last round's conclusions still hold? | one parameter is a structural identity and extrapolates exactly; the other is an estimate and **had already broken** | re-verified neither |
| **3** | Where does an option's fair value come from? | from an **identity** where time value vanishes; the spot products are random walks; `HYDROGEL_PACK` alone outweighs all ten vouchers | Black-Scholes with a fitted smile, a mean-reversion rule on two random walks, and the effort spent on the vouchers |
| **4** | Is the new information a signal? | **no** — three days cannot separate it from noise | didn't use it (correct, by accident) |
| **5** | Which of fifty products' relationships are real? | exactly one — a five-product basket summing to a constant | traded five fitted pairs, **all random walks**; the whole score came from **six bets on sixty lots** |

---

## Four findings

**A bug that saved money.** In Round 3 a threshold sat 47% above its signal's all-time maximum,
so ten of twelve products never traded — apparently the reason the round scored badly.
Reopening the gate, changing one constant, makes it *worse*: the suppressed strategy was itself
unprofitable. The bug concealed a design error rather than causing one, and the obvious fix
would have cost money. [→](rounds/03/README.md)

**Pooling manufactured a signal.** In Round 4 a counterparty's trades appeared to predict
prices on one product — $t = -2.70$ across the pre-round days. Reported *per day* the estimate
is significant on none of them, and the same counterparty is equally consistent on a second
product where it reverses sharply on the day that counted. **Nothing in the pre-round data
separates the two.** A team finishing 64th reached the same conclusion by a different route and
recovered \$15.8k by switching their version off. [→](rounds/04/README.md)

**Structure exists; arbitrage does not.** Two rounds contain exact identities — deep
in-the-money options at $S-K$ to within 0.01, and a five-product basket summing to 50,000.
Neither can be traded: the deviations (0.8 and 2.8) sit entirely inside the cost of executing
them (21 and 65). Both are worth having anyway, as fair-value estimators no fitting can match.
[→](rounds/03/README.md) · [→](rounds/05/README.md)

**Winning and being right are different.** Round 2's outperformance came from carrying
inventory on a day that drifted up — correlation between position held and the next tick's move
was **+0.024**. Round 5's entire score came from sixty lots while four thousand lots lost money.
Round 1's much larger directional profit, by contrast, is 96% of what the optimal policy
achieves. [→](rounds/02/README.md)

---

## The battery

The same tests run on every product in every round. Five notebooks, one procedure — the point
being that the conclusions come out of a fixed process rather than being assembled per round.

| | what it separates |
|---|---|
| variance ratio | trending / mean-reverting / random walk |
| autocorrelation decay | slow reversion from instantaneous noise — **the variance ratio cannot** |
| depth imbalance vs the outer fair | short-horizon predictability |
| group sums and fitted spreads | identities from curve fits |
| flow by aggressor × spread | what is actually available to earn |
| forward move after each counterparty | information content, per day, never pooled |

Two results this produced that a per-round approach would miss:

**Depth imbalance is a property of one market, not of the exchange.** Coefficient +2.4 to +2.6
with $t \approx 40$ in Rounds 1–2, and nothing at all ($|t| \le 1.3$) in Rounds 3–4. Carrying it
across would have added a term with no support.

**The variance ratio has a blind spot.** Round 1's ROOT residual has VR(200) = 0.005 — lower
than ASH's 0.011 — yet it is untradeable white noise, gone by the next tick. Only the
autocorrelation decay separates them: ASH stays above 0.5 for 76–213 lags, ROOT's residual for
two.

---

## How the reconstruction works

The exchange returns the order book for all 10,000 timestamps and every fill, but nothing about
the algorithm's internal state — the submissions printed nothing, so all 10,000 log entries are
empty. Explaining *why* a decision was taken requires recovering that state.

**Method.** The unmodified submission source is executed under `sys.settrace`, one timestamp at
a time, against `TradingState` objects rebuilt from the log. Matching is not simulated: the book
and the fills are the real ones. Running the original source rather than a re-implementation is
deliberate — a re-implementation drifts, and the account then describes a paraphrase.

**It is only usable if it is falsifiable**, so it is checked against the fills the exchange
actually awarded: every own trade must be explained by an order the replay emits at that
timestamp, on the right side, at a compatible price.

| Round | own trades | explained |
|---|---:|---:|
| 1 | 763 | **100%** |
| 2 | 632 | **100%** |
| 3 | 740 | **100%** |
| 4 | 1,272 | 99.84% |

Round 3 allows a second, independent check: that submission printed its orders every tick, so
the replay can be compared directly against what was sent — **9,986 of 10,000 timestamps
identical**.

**Open in a browser and drag the timeline:**
[R1 · ASH](rounds/01/replay/ash.html) · [R1 · ROOT](rounds/01/replay/root.html) ·
[R2 · ASH](rounds/02/replay/ash.html) · [R2 · ROOT](rounds/02/replay/root.html)

Every frame shows the book, my own resting quotes, the fair price, and a line-by-line account of
that instant's decision — which branches fired, both sides of every comparison, and why the
alternative was not taken.

---

## On the numbers

What my submissions scored comes from the exchange log and is exact.

What a *different* strategy would have scored comes from a simulator replaying a fixed recording
of the book and the tape. **That recording already contains the effect of the algorithm that
traded that day and cannot react to a different one.** Such figures support comparisons between
strategies on the same recording; they do not establish what a strategy would have scored live.

Simulator error against the exchange, running my own submissions: **0.13%** (R1), **0.02%**
(R2), **−1,733 on one product** (R3), **+9.8%** (R4 — fails calibration, and that round's
conclusions are drawn without it).

Each specification ends with an evidence table mapping every rule to the measurement behind it.
Three items are marked as not measurable and are labelled rather than dressed up:

- Round 1's saturation deviation $K$ — a risk preference, not an estimate
- Round 2's regime gate — the diagnosis holds, the implementation is not yet net-positive, and
  the reason is stated instead of tuned away
- Round 5's reported 389,000 on one product — not reproducible here, and bounded above by
  ~13,000 under a 10-lot limit; recorded, not adopted

---

## Layout

```
rounds/01..05/     one README and one specification per round, plus replays
research/          the derivation for each round: load, plot, test, conclude
submissions/       the five algorithms as submitted, unmodified
tools/             replay engine, the test battery, benchmarks
assets/            figures, generated by the notebooks
data/              how to obtain the market data
```
