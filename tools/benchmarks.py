"""
benchmarks.py — a perfect-foresight upper bound, and the flow decomposition it rests on.

**What the bound is for.** A post-mortem asks "how far short did I fall", so the yardstick
has to be something that could in principle be pursued. This module computes the opposite:
what a trader who knew the entire session's book in advance could have earned. That figure
is *not* a target — it is unreachable by construction. Its only use is as a ceiling: the
gap between it and an achievable policy measures what foresight alone is worth.

**Three defects in a naive version of this calculation**, each of which can be switched back
on here to reproduce the old number and price the correction:

  Defect 1 — counting the same flow on both sides.
    Treating `v = trades.groupby(timestamp).quantity.sum()` as simultaneously "the size
    willing to sell to me at the bid" and "the size willing to buy from me at the offer".
    A trade has one aggressor; it cannot be both. Classifying round 1's three days by
    aggressor gives 0.489 / 0.511 — an even split — so each side was inflated roughly
    twofold. Switch: `split_direction=False`.

  Defect 2 — forbidding two-sided execution within a tick.
    Allowing only a net buy or a net sell per tick removes the principal source of
    market-making revenue: buying at the bid and selling at the offer in the same instant.
    Combined with defect 1 the result overstates in one place and understates in another,
    **so the sign of the error is unknown — and a bound whose direction is unknown is not a
    bound.** Switch: `allow_both_sides=False`.

  Defect 3 — marking with a different yardstick than the exchange.
    Marking terminal inventory at `nanmean(bid1, ask1)` degenerates to a one-sided price
    when the book is one-sided. Switch: `mark="mid"` reproduces it; `mark="fair"` uses the
    largest-size level midpoint.

**The two-sided treatment is exact, not an approximation.** With `a` units available to buy
and `b` to sell in a tick, `k = min(a, b)` paired executions leave inventory unchanged and
each earn `ask1 - bid1 >= 0`, so taking all `k` is always weakly optimal and can be added as
a constant. The residual `|a - b|` can only sit on one side, and the dynamic program decides
how much of it to take.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NEG = -1e18


# --------------------------------------------------------------------------
# Aggressor classification: who crossed the spread
# --------------------------------------------------------------------------
def split_flow_by_aggressor(prices: pd.DataFrame, trades: pd.DataFrame,
                            product: str) -> pd.DataFrame:
    """
    Split each timestamp's traded volume by which side crossed:

      price >= ask1  ->  buyer-initiated; this flow can only lift **my offer**
      price <= bid1  ->  seller-initiated; it can only hit **my bid**
      bid1 < price < ask1  ->  an inside-the-spread print whose aggressor cannot be
                               determined from price; excluded from both sides

    Returns a frame indexed by timestamp with columns to_my_bid / to_my_ask / total.

    Price is the classifier because it needs no further assumption: a print at the offer
    means the buyer accepted the seller's quote. Inside prints admit no such inference, so
    they are dropped rather than assigned to a side — assigning them would be inventing
    data.

    The scored-day log adds a case: some prints are mine. A passive fill of my bid at
    bid1+1 lands inside the spread and would be discarded by the price rule — yet that is
    precisely the flow I intercepted. Where a `side` flag is present (+1 I bought,
    -1 I sold, 0 bot-to-bot), it takes precedence:

      I bought below the offer  ->  I was passive, a bot sold into me  ->  to_my_bid
      I sold above the bid      ->  I was passive, a bot lifted me     ->  to_my_ask
      I crossed the spread      ->  I consumed resting size, which is ladder liquidity
                                    rather than flow arriving at my quotes; excluded
    """
    book = prices[prices["product"] == product].set_index("timestamp")
    tr = trades[trades["symbol"] == product].copy()
    tr = tr.join(book[["bid_price_1", "ask_price_1"]], on="timestamp")

    agg_buy = tr["price"] >= tr["ask_price_1"]     # can lift my offer
    agg_sell = tr["price"] <= tr["bid_price_1"]    # can hit my bid

    if "side" in tr.columns:
        mine = tr["side"] != 0
        my_passive_buy = mine & (tr["side"] == 1) & (tr["price"] < tr["ask_price_1"])
        my_passive_sell = mine & (tr["side"] == -1) & (tr["price"] > tr["bid_price_1"])
        # remove my own prints from the price rule, then reassign by passive/aggressive
        agg_buy = (agg_buy & ~mine) | my_passive_sell
        agg_sell = (agg_sell & ~mine) | my_passive_buy

    out = pd.DataFrame({
        "to_my_ask": tr.loc[agg_buy].groupby("timestamp")["quantity"].sum(),
        "to_my_bid": tr.loc[agg_sell].groupby("timestamp")["quantity"].sum(),
        "total": tr.groupby("timestamp")["quantity"].sum(),
    }).fillna(0.0)
    return out


# --------------------------------------------------------------------------
# book access and marking
# --------------------------------------------------------------------------
def _ladder(row, side: str):
    """The three (price, size) levels of one side, ordered most favourable first."""
    out = []
    for i in (1, 2, 3):
        p, v = row.get(f"{side}_price_{i}"), row.get(f"{side}_volume_{i}")
        if pd.notna(p) and pd.notna(v) and v != 0:
            out.append((float(p), int(abs(v))))
    out.sort(reverse=(side == "bid"))   # cheapest first to buy; richest first to sell
    return out


def _marks(df: pd.DataFrame, mode: str) -> np.ndarray:
    """
    The yardstick for marking terminal inventory.
      mid   nanmean(bid1, ask1) — the naive version; degenerates on one-sided books
      fair  midpoint of the largest-size level on each side
    """
    if mode == "mid":
        m = df[["bid_price_1", "ask_price_1"]].mean(axis=1, skipna=True)
        return m.ffill().bfill().to_numpy()

    if mode == "fair":
        vals = []
        for _, r in df.iterrows():
            bids, asks = _ladder(r, "bid"), _ladder(r, "ask")
            bb = max(bids, key=lambda x: x[1])[0] if bids else np.nan
            ba = max(asks, key=lambda x: x[1])[0] if asks else np.nan
            vals.append(np.nanmean([bb, ba]))
        return pd.Series(vals).ffill().bfill().to_numpy()

    raise ValueError(f"unknown mark mode: {mode}")


def _expand(tiers, cap: int) -> list[float]:
    """Expand (price, size) levels into per-lot marginal prices, up to `cap` lots."""
    out = []
    for pr, vol in tiers:
        take = min(int(vol), cap - len(out))
        if take > 0:
            out.extend([pr] * take)
        if len(out) >= cap:
            break
    return out


# --------------------------------------------------------------------------
# B2
# --------------------------------------------------------------------------
def b2_ceiling(prices: pd.DataFrame, trades: pd.DataFrame, product: str,
               limit: int = 80, *,
               split_direction: bool = True,
               allow_both_sides: bool = True,
               mark: str = "fair") -> dict:
    """
    Perfect-foresight upper bound. Turning all three switches off reproduces the naive
    figure described in the module docstring.

    Dynamic program over net inventory p in [-L, L], recursed backwards from the close:
    V[p] is the most that can be earned from this tick onward — cash plus terminal mark —
    holding p right now.
    """
    df = (prices[prices["product"] == product]
          .sort_values("timestamp").reset_index(drop=True))
    flow = split_flow_by_aggressor(prices, trades, product)

    L = limit
    n_states = 2 * L + 1
    positions = np.arange(-L, L + 1)

    marks = _marks(df, mark)
    buy_cums, sell_cums, paired = [], [], []

    for _, r in df.iterrows():
        t = r["timestamp"]
        bid1, ask1 = r.get("bid_price_1"), r.get("ask_price_1")
        f = flow.loc[t] if t in flow.index else None

        if f is None:
            v_bid = v_ask = 0.0
        elif split_direction:
            v_bid, v_ask = float(f["to_my_bid"]), float(f["to_my_ask"])
        else:
            v_bid = v_ask = float(f["total"])       # naive: the whole of v on both sides

        pair_profit = 0.0
        if allow_both_sides and pd.notna(bid1) and pd.notna(ask1):
            k = min(v_bid, v_ask)
            pair_profit = k * (float(ask1) - float(bid1))
            v_bid -= k
            v_ask -= k                              # the residual can only sit on one side

        buy_tiers = ([(float(bid1), int(v_bid))] if pd.notna(bid1) and v_bid > 0 else []) \
            + _ladder(r, "ask")
        buy_tiers.sort()
        sell_tiers = ([(float(ask1), int(v_ask))] if pd.notna(ask1) and v_ask > 0 else []) \
            + _ladder(r, "bid")
        sell_tiers.sort(reverse=True)

        bm = _expand(buy_tiers, 2 * L)
        sm = _expand(sell_tiers, 2 * L)
        buy_cums.append(np.concatenate([[0.0], -np.cumsum(bm)]) if bm else np.array([0.0]))
        sell_cums.append(np.concatenate([[0.0], np.cumsum(sm)]) if sm else np.array([0.0]))
        paired.append(pair_profit)

    V = positions * marks[-1]
    pi = np.arange(n_states)

    for t in range(len(df) - 1, -1, -1):
        buy_cum, sell_cum = buy_cums[t], sell_cums[t]
        max_buy, max_sell = len(buy_cum) - 1, len(sell_cum) - 1

        # buy db lots: pos+db <= L  <=>  pi+db <= 2L
        db = np.arange(max_buy + 1)
        idx = pi[:, None] + db[None, :]
        ok = idx <= 2 * L
        cand_b = np.where(ok, buy_cum[None, :] + V[np.clip(idx, 0, 2 * L)], NEG)

        # sell ds lots: pos-ds >= -L  <=>  pi-ds >= 0
        ds = np.arange(1, max_sell + 1)
        if ds.size:
            jdx = pi[:, None] - ds[None, :]
            ok2 = jdx >= 0
            cand_s = np.where(ok2, sell_cum[ds][None, :] + V[np.clip(jdx, 0, 2 * L)], NEG)
            V = np.maximum(cand_b.max(axis=1), cand_s.max(axis=1))
        else:
            V = cand_b.max(axis=1)
        V = V + paired[t]

    return {
        "product": product,
        "ceiling": float(V[L]),
        "split_direction": split_direction,
        "allow_both_sides": allow_both_sides,
        "mark": mark,
    }


def b2_defect_attribution(prices, trades, product, limit=80) -> pd.DataFrame:
    """
    Enable the three corrections one at a time to price each defect.
    V0 naive; V1 adds aggressor classification; V2 adds two-sided execution; V3 changes the
    marking yardstick.
    """
    cfgs = [
        ("V0 naive",              dict(split_direction=False, allow_both_sides=False, mark="mid")),
        ("V1 +aggressor split",   dict(split_direction=True,  allow_both_sides=False, mark="mid")),
        ("V2 +two-sided tick",    dict(split_direction=True,  allow_both_sides=True,  mark="mid")),
        ("V3 +largest-level mark",dict(split_direction=True,  allow_both_sides=True,  mark="fair")),
    ]
    rows, prev = [], None
    for name, kw in cfgs:
        c = b2_ceiling(prices, trades, product, limit, **kw)["ceiling"]
        rows.append({"config": name, "ceiling": round(c), "delta": "" if prev is None else f"{c - prev:+,.0f}"})
        prev = c
    return pd.DataFrame(rows)
