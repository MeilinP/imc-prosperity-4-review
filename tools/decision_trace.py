"""
decision_trace.py — recover, timestamp by timestamp, what a submitted algorithm decided.

**The problem.** The exchange log records the order book at every one of the 10,000
timestamps and every fill, but nothing about the algorithm's internal state: the
submissions printed nothing, so all 10,000 `lambdaLog` entries are empty. What the
algorithm was *doing* at a given instant does not exist in the raw data and has to be
reconstructed.

Three design decisions, each with a reason it could not be made the other way.

**1. Execute the unmodified submitted source, not a re-implementation.**
A re-implementation drifts the moment a line is changed for clarity, and the resulting
account then describes the paraphrase rather than the code that traded. `sys.settrace`
captures every executed line and every scalar local from the original file, so what is
reported is the code's own behaviour.

**2. Do not simulate matching.**
The book, the trades and the position at each timestamp all come from the exchange record.
Only the algorithm's internal state is recomputed. Its decision at time *t* is a
deterministic function of (internal state, book, position); all three are available, so the
reconstruction is exact rather than approximate.

**3. `verify_trace` is a precondition, not an extra.**
Internal state cannot be observed directly, so the only falsifiable interface is whether
the orders the replay emits can account for the fills the exchange actually awarded:

    a buy fill at price p  =>  the replay must emit a buy order at price >= p that tick
    a sell fill at price p =>  the replay must emit a sell order at price <= p
    and the filled quantity must not exceed the quantity ordered on that side

**A match rate below 100% means the reconstruction is wrong**, and every statement it
supports about *why* something happened must be discarded. An account that cannot state
this condition is not evidence.

Round 3 admits a second, independent check: that submission printed its orders every tick,
so the replay's orders can be compared directly against what was sent.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# 1. Rebuild the exact TradingState at every timestamp
# ---------------------------------------------------------------------------
def _load_datamodel(datamodel_path: str):
    spec = importlib.util.spec_from_file_location("datamodel", datamodel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["datamodel"] = mod
    spec.loader.exec_module(mod)
    return mod


def rebuild_states(log, datamodel_path: str, tick: int = 100):
    """
    activitiesLog + tradeHistory -> one TradingState per timestamp.

    Alignment convention — getting this backwards makes `verify_trace` fail everywhere:
      * orders sent at t are matched at t, and the resulting trades are also stamped t
      * therefore state(t).own_trades carries the fills from **t - tick**, and
        state(t).position is the cumulative position from everything strictly before t
    """
    dm = _load_datamodel(datamodel_path)
    act, tr = log.activities, log.trades

    depths_by_t: dict[int, dict[str, object]] = {}
    for t, g in act.groupby("timestamp"):
        d = {}
        for _, r in g.iterrows():
            od = dm.OrderDepth()
            for i in (1, 2, 3):
                p, v = r.get(f"bid_price_{i}"), r.get(f"bid_volume_{i}")
                if pd.notna(p) and pd.notna(v) and v != 0:
                    od.buy_orders[int(p)] = int(abs(v))
                p, v = r.get(f"ask_price_{i}"), r.get(f"ask_volume_{i}")
                if pd.notna(p) and pd.notna(v) and v != 0:
                    od.sell_orders[int(p)] = -int(abs(v))
            d[r["product"]] = od
        depths_by_t[int(t)] = d

    own = tr[tr["side"] != 0]
    mkt = tr[tr["side"] == 0]
    own_by_t = {int(t): g for t, g in own.groupby("timestamp")}
    mkt_by_t = {int(t): g for t, g in mkt.groupby("timestamp")}

    pos_running: dict[str, int] = {}
    states = []
    for t in sorted(depths_by_t):
        prev = t - tick
        ot: dict[str, list] = {}
        if prev in own_by_t:
            for _, r in own_by_t[prev].iterrows():
                sym, qty = r["symbol"], int(r["quantity"]) * int(r["side"])
                pos_running[sym] = pos_running.get(sym, 0) + qty
                ot.setdefault(sym, []).append(
                    dm.Trade(sym, int(r["price"]), abs(int(r["quantity"])),
                             r["buyer"], r["seller"], prev))
        mt: dict[str, list] = {}
        if prev in mkt_by_t:
            for _, r in mkt_by_t[prev].iterrows():
                mt.setdefault(r["symbol"], []).append(
                    dm.Trade(r["symbol"], int(r["price"]), abs(int(r["quantity"])),
                             r["buyer"], r["seller"], prev))

        states.append(dm.TradingState(
            traderData="", timestamp=t, listings={},
            order_depths=depths_by_t[t],
            own_trades=ot, market_trades=mt,
            position=dict(pos_running),
            observations=dm.Observation({}, {}),
        ))
    return states, dm


def rebuild_states_from_csv(prices_csv: str, trades_csv: str, datamodel_path: str,
                            tick: int = 100):
    """
    Build TradingState objects from the **pre-round** CSVs (no own trades; position is 0).

    Why this exists: the log only covers the scored day. Answering "was this bug
    discoverable before submitting?" requires running the same source over the data that
    was already in hand. It is the only hard evidence for prior discoverability — without
    it one can merely assert that a plot would have shown it.
    """
    dm = _load_datamodel(datamodel_path)
    px = pd.read_csv(prices_csv, sep=";")
    tr = pd.read_csv(trades_csv, sep=";")

    depths: dict[int, dict] = {}
    for t, g in px.groupby("timestamp"):
        d = {}
        for _, r in g.iterrows():
            od = dm.OrderDepth()
            for i in (1, 2, 3):
                p, v = r.get(f"bid_price_{i}"), r.get(f"bid_volume_{i}")
                if pd.notna(p) and pd.notna(v) and v != 0:
                    od.buy_orders[int(p)] = int(abs(v))
                p, v = r.get(f"ask_price_{i}"), r.get(f"ask_volume_{i}")
                if pd.notna(p) and pd.notna(v) and v != 0:
                    od.sell_orders[int(p)] = -int(abs(v))
            d[r["product"]] = od
        depths[int(t)] = d

    mkt = {int(t): g for t, g in tr.groupby("timestamp")}
    states = []
    for t in sorted(depths):
        mt: dict[str, list] = {}
        for _, r in mkt.get(t - tick, pd.DataFrame()).iterrows():
            mt.setdefault(r["symbol"], []).append(
                dm.Trade(r["symbol"], int(r["price"]), abs(int(r["quantity"])),
                         r.get("buyer", ""), r.get("seller", ""), t - tick))
        states.append(dm.TradingState(
            traderData="", timestamp=t, listings={}, order_depths=depths[t],
            own_trades={}, market_trades=mt, position={},
            observations=dm.Observation({}, {})))
    return states, dm


# ---------------------------------------------------------------------------
# 2. Run the original source and capture every line
# ---------------------------------------------------------------------------
@dataclass
class TickTrace:
    timestamp: int
    lines: list = field(default_factory=list)     # [(lineno, {name: value})]
    orders: dict = field(default_factory=dict)    # {symbol: [(price, qty)]}


def trace(submission_path: str, states, dm, capture=(int, float, bool)) -> list[TickTrace]:
    """
    Record every executed line of the **unmodified submitted source** via `sys.settrace`.

    Only scalar locals are captured. That is sufficient — every branch condition in these
    submissions is a scalar comparison — and it keeps memory bounded across 10,000 ticks.

    Note that `frame.f_locals` at a `line` event is the state **before** that line runs, so
    a value assigned on line N first appears in the record for the next executed line.
    `_last_snap` reads with that offset in mind.
    """
    spec = importlib.util.spec_from_file_location("submitted_trader", submission_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["submitted_trader"] = mod
    spec.loader.exec_module(mod)
    trader = mod.Trader()

    target = spec.origin
    out: list[TickTrace] = []
    cur: TickTrace | None = None

    def local_tracer(frame, event, arg):
        if event == "line" and cur is not None:
            snap = {k: v for k, v in frame.f_locals.items()
                    if isinstance(v, capture) and not k.startswith("__")}
            cur.lines.append((frame.f_lineno, snap))
        return local_tracer

    def global_tracer(frame, event, arg):
        if event == "call" and frame.f_code.co_filename == target:
            return local_tracer
        return None

    trader_data = ""
    for st in states:
        st.traderData = trader_data
        cur = TickTrace(timestamp=st.timestamp)
        sys.settrace(global_tracer)
        try:
            res = trader.run(st)
        finally:
            sys.settrace(None)
        orders = res[0] if isinstance(res, tuple) else res
        trader_data = res[2] if isinstance(res, tuple) and len(res) > 2 else ""
        cur.orders = {sym: [(o.price, o.quantity) for o in lst]
                      for sym, lst in (orders or {}).items()}
        out.append(cur)
        cur = None
    return out


# ---------------------------------------------------------------------------
# 3. The falsification test
# ---------------------------------------------------------------------------
def verify_trace(traces: list[TickTrace], log) -> pd.DataFrame:
    """
    For every fill the exchange awarded, check that the replay emitted an order at the same
    timestamp that could account for it:

        buy fill at p  -> a buy order at price >= p, with enough quantity on that side
        sell fill at p -> a sell order at price <= p

    Returns one row per fill. **The match rate must be 100%**; below that, the
    reconstruction is not usable.
    """
    by_t = {tr.timestamp: tr for tr in traces}
    own = log.trades[log.trades["side"] != 0]
    rows = []
    for _, r in own.iterrows():
        t, sym = int(r["timestamp"]), r["symbol"]
        px, qty, side = float(r["price"]), int(r["quantity"]), int(r["side"])
        placed = by_t.get(t).orders.get(sym, []) if t in by_t else []
        if side > 0:
            cand = [(p, q) for p, q in placed if q > 0 and p >= px]
        else:
            cand = [(p, q) for p, q in placed if q < 0 and p <= px]
        cap = sum(abs(q) for _, q in cand)
        rows.append({"timestamp": t, "symbol": sym, "price": px,
                     "qty": qty, "side": side,
                     "matched": bool(cand) and cap >= qty,
                     "order_qty": cap})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Helpers used by replay_player to turn line traces into annotations
# ---------------------------------------------------------------------------
def _last_snap(tt: TickTrace, lo: int, hi: int) -> dict:
    """
    The last locals snapshot recorded within line range [lo, hi] for this tick.

    The last one is wanted because `f_locals` at a `line` event precedes that line's
    execution, so the final snapshot of a routine holds the settled values of everything
    assigned within it.
    """
    snap = {}
    for ln, s in tt.lines:
        if lo <= ln <= hi:
            snap = s
    return snap


def _fired(tt: TickTrace, lines: set[int]) -> bool:
    """Whether any of the given lines executed — branch detection by line number rather
    than inference."""
    return any(ln in lines for ln, _ in tt.lines)
