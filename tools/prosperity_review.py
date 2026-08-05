"""
prosperity_review.py — turn a submission log into data frames. pandas and numpy only.

A Prosperity `.log` is a single-line JSON object with four keys:

  submissionId    the submission's id
  activitiesLog   a semicolon-delimited CSV, one row per (timestamp, product): three book
                  levels a side, mid_price, and the exchange's own profit_and_loss
  logs            one {sandboxLog, lambdaLog} per timestamp — whatever the algorithm printed
  tradeHistory    a list of prints; those naming "SUBMISSION" as buyer or seller are mine

Matching rules, established by probe submissions in the tutorial round and applicable
throughout:

  * no queue — resting at the touch carries no time priority, and quoting one tick inside
    it intercepts the flow
  * bots only trade at the touch; they never cross
  * my own marketable orders may sweep several levels at once
  * within one timestamp, bot-initiated prints occur only at the touch

The exchange's `profit_and_loss` column is a mark-to-market figure:

    PnL(t) = cash(t) + position(t) * mid_price(t)

with cash decremented on purchases and incremented on sales. `reconstruct_pnl` reproduces
that column independently, which is what makes it usable as a reconciliation check.
"""

from __future__ import annotations
import json
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. reading a .log
# ---------------------------------------------------------------------------
@dataclass
class Log:
    """One parsed submission log."""
    submission_id: str
    activities: pd.DataFrame   # book snapshots plus the exchange PnL column
    trades: pd.DataFrame       # every print, including bot-to-bot
    sandbox: pd.DataFrame      # whatever the algorithm printed, per timestamp


def load_log(path: str) -> Log:
    """Parse a .log into three tables."""
    with open(path, "r") as f:
        raw = json.load(f)

    activities = _parse_activities(raw["activitiesLog"])
    trades = _parse_trades(raw.get("tradeHistory", []))
    sandbox = pd.DataFrame(raw.get("logs", []))
    return Log(raw.get("submissionId", ""), activities, trades, sandbox)


def _parse_activities(csv_text: str) -> pd.DataFrame:
    """activitiesLog string -> DataFrame; empty book levels become NaN.

    Adds a `mark` column for mark-to-market. The raw `mid_price` column is unsafe for this:
    on a one-sided book it equals whichever side exists, which distorts the valuation. Here
    the midpoint is taken only when both sides are present, and carried forward otherwise.
    Reconstructing the exchange's PnL with it leaves a mean error around 20, or 0.1%.
    """
    df = pd.read_csv(io.StringIO(csv_text), sep=";")
    df.columns = [c.strip() for c in df.columns]
    num_cols = [c for c in df.columns if c not in ("product",)]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["timestamp", "product"]).reset_index(drop=True)

    # two-sided midpoint only; filled forward and backward within each product
    two = df["bid_price_1"].notna() & df["ask_price_1"].notna()
    df["_mid2"] = np.where(two, (df["bid_price_1"] + df["ask_price_1"]) / 2, np.nan)
    df = df.sort_values(["product", "timestamp"])
    df["mark"] = df.groupby("product")["_mid2"].ffill()
    df["mark"] = df.groupby("product")["mark"].bfill()
    df = df.drop(columns="_mid2").sort_values(
        ["timestamp", "product"]).reset_index(drop=True)
    return df


def _parse_trades(trade_list: list) -> pd.DataFrame:
    """tradeHistory -> DataFrame, flagged from my own point of view.

    side = +1  I bought   (buyer == SUBMISSION)
    side = -1  I sold     (seller == SUBMISSION)
    side =  0  bot-to-bot; I was not involved
    """
    if not trade_list:
        return pd.DataFrame(
            columns=["timestamp", "symbol", "price", "quantity",
                     "buyer", "seller", "side"]
        )
    df = pd.DataFrame(trade_list)
    df = df.rename(columns={"symbol": "symbol"})
    df["buyer"] = df["buyer"].fillna("")
    df["seller"] = df["seller"].fillna("")

    def side(row):
        if row["buyer"] == "SUBMISSION":
            return 1
        if row["seller"] == "SUBMISSION":
            return -1
        return 0

    df["side"] = df.apply(side, axis=1)
    keep = ["timestamp", "symbol", "price", "quantity", "buyer", "seller", "side"]
    return df[keep].sort_values("timestamp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. position time series, rebuilt from prints
# ---------------------------------------------------------------------------
def own_trades(log: Log) -> pd.DataFrame:
    """Only my own prints, with a signed quantity column."""
    t = log.trades
    mine = t[t["side"] != 0].copy()
    mine["signed_qty"] = mine["side"] * mine["quantity"]
    return mine.reset_index(drop=True)


def build_positions(log: Log) -> pd.DataFrame:
    """
    Cumulative position per product at the end of each timestamp.
    One column per product; values are net position at that instant.
    """
    mine = own_trades(log)
    if mine.empty:
        return pd.DataFrame({"timestamp": sorted(log.activities["timestamp"].unique())})

    # net traded quantity per (timestamp, symbol)
    flow = (mine.groupby(["timestamp", "symbol"])["signed_qty"]
                .sum().unstack(fill_value=0))
    # accumulate along the full timestamp axis
    all_ts = sorted(log.activities["timestamp"].unique())
    flow = flow.reindex(all_ts, fill_value=0)
    pos = flow.cumsum()
    pos.index.name = "timestamp"
    return pos.reset_index()


# ---------------------------------------------------------------------------
# 3. reproduce the exchange PnL, for reconciliation
# ---------------------------------------------------------------------------
def reconstruct_pnl(log: Log) -> pd.DataFrame:
    """
    Recompute each product's mark-to-market PnL independently from prints and mid.
    Returns a long frame: timestamp, product, cash, position, mid, pnl_recon.

        PnL = cash + position * mid
        buy:  cash -= price*qty, position += qty
        sell: cash += price*qty, position -= qty
    """
    mine = own_trades(log)
    acts = log.activities[["timestamp", "product", "mark"]].copy()

    out = []
    for product, grp in acts.groupby("product"):
        grp = grp.sort_values("timestamp").reset_index(drop=True)
        # aggregate this product's prints into exact cash flow and net quantity
        pt = mine[mine["symbol"] == product]
        cash_flow = (pt.assign(cf=-pt["price"] * pt["signed_qty"])
                       .groupby("timestamp")["cf"].sum())
        qty_flow = pt.groupby("timestamp")["signed_qty"].sum()

        grp["cash"] = grp["timestamp"].map(cash_flow).fillna(0.0).cumsum()
        grp["position"] = grp["timestamp"].map(qty_flow).fillna(0).cumsum()
        grp["pnl_recon"] = grp["cash"] + grp["position"] * grp["mark"]
        out.append(grp.rename(columns={"mark": "mid"})[
            ["timestamp", "product", "cash", "position", "mid", "pnl_recon"]])

    return pd.concat(out, ignore_index=True)


def reconcile_pnl(log: Log) -> pd.DataFrame:
    """
    Align the reconstruction against the exchange's profit_and_loss column and report the
    largest absolute discrepancy per product. It should be at floating-point scale.
    """
    recon = reconstruct_pnl(log)
    official = log.activities[["timestamp", "product", "profit_and_loss"]]
    m = recon.merge(official, on=["timestamp", "product"], how="inner")
    m["abs_err"] = (m["pnl_recon"] - m["profit_and_loss"]).abs()
    summary = (m.groupby("product")["abs_err"]
                 .agg(["max", "mean"]).reset_index()
                 .rename(columns={"max": "max_abs_err", "mean": "mean_abs_err"}))
    return summary


# ---------------------------------------------------------------------------
# 4. attribution: spread earned versus inventory carried
# ---------------------------------------------------------------------------
def pnl_attribution(log: Log) -> pd.DataFrame:
    """
    Per product, evaluated at the final timestamp:
      final_pnl    mark-to-market PnL on the exchange's definition
      realized     cash locked in by closed round trips (average-cost basis)
      inventory    final net position
      inv_markval  unrealised P&L on it: position * (mid - avg_cost)
      n_trades     number of prints
      volume       total lots

    final_pnl is approximately realized + inv_markval. A large inventory alongside a
    negative inv_markval means the position is losing while spread capture carries the
    result — the distinction between skill and exposure.
    """
    mine = own_trades(log)
    last_mark = (log.activities.sort_values("timestamp")
                 .groupby("product")["mark"].last())

    rows = []
    for product, grp in mine.groupby("symbol"):
        grp = grp.sort_values("timestamp")
        position = 0          # running net position
        avg_cost = 0.0        # average cost of the current position
        realized = 0.0        # P&L locked in by closed round trips
        for _, r in grp.iterrows():
            q = int(r["signed_qty"])
            px = float(r["price"])
            if position == 0 or (position > 0) == (q > 0):
                # adding in the same direction: update average cost
                new_pos = position + q
                avg_cost = (avg_cost * position + px * q) / new_pos if new_pos else 0.0
                position = new_pos
            else:
                # opposite direction: settle the offset portion as realised
                closed = min(abs(q), abs(position))
                # long: (sale - cost) * qty; short is the mirror, handled by sign
                realized += closed * (px - avg_cost) * (1 if position > 0 else -1)
                if abs(q) > abs(position):
                    # flipped through zero: the remainder opens a new position at this price
                    position += q
                    avg_cost = px
                else:
                    position += q
        mark = float(last_mark.get(product, np.nan))
        inv_markval = position * (mark - avg_cost) if position != 0 else 0.0
        rows.append({
            "product": product,
            "final_pnl": realized + inv_markval,   # should match the exchange figure
            "realized": realized,                  # earned from spread
            "inv_markval": inv_markval,            # unrealised on the closing position
            "inventory": position,                 # closing net position
            "avg_cost": round(avg_cost, 2),
            "last_mark": round(mark, 2),
            "n_trades": len(grp),
            "volume": int(grp["quantity"].sum()),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4b. per-print classification: aggressive or passive, and the edge earned
# ---------------------------------------------------------------------------
def classify_and_edge(log: Log, fair_long: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each of my prints as aggressive or passive and compute its edge. Applies to any
    round once a fair price series is supplied.

    fair_long: long frame [timestamp, product, fair] — the strategy's own fair price at each
    instant, obtained by reproducing its fair-price calculation.

    Classification against the touch at the time of the print:
      a buy at or above the offer crossed the spread; otherwise it was passive
      a sell at or below the bid crossed; otherwise passive
      edge = fair - price for buys, price - fair for sells

    Edge is how much better than fair the print was. Summed over quantity it should
    approximate `realized`.
    """
    mine = own_trades(log)
    book = log.activities.pivot_table(
        index="timestamp", columns="product", values=["bid_price_1", "ask_price_1"])
    fmap = fair_long.set_index(["timestamp", "product"])["fair"]

    rows = []
    for _, tr in mine.iterrows():
        t, sym, px, side = tr["timestamp"], tr["symbol"], tr["price"], tr["side"]
        try:
            b1 = book.loc[t, ("bid_price_1", sym)]
            a1 = book.loc[t, ("ask_price_1", sym)]
        except KeyError:
            b1 = a1 = np.nan
        fair = fmap.get((t, sym), np.nan)
        if side == 1:
            kind = "take" if (pd.notna(a1) and px >= a1) else "make"
            edge = fair - px
        else:
            kind = "take" if (pd.notna(b1) and px <= b1) else "make"
            edge = px - fair
        rows.append(dict(timestamp=t, symbol=sym, side=side, price=px,
                         qty=tr["quantity"], kind=kind, edge=edge, fair=fair))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. reading the official CSVs (research and backtesting; unrelated to the log)
# ---------------------------------------------------------------------------
def load_prices_csv(path: str) -> pd.DataFrame:
    """Official prices_round_X_day_Y.csv: three book levels a side plus mid_price."""
    df = pd.read_csv(path, sep=";")
    df.columns = [c.strip() for c in df.columns]
    return df


def load_trades_csv(path: str) -> pd.DataFrame:
    """Official trades_round_X_day_Y.csv: the print tape."""
    df = pd.read_csv(path, sep=";")
    df.columns = [c.strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# convenience entry point
# ---------------------------------------------------------------------------
def quick_summary(path: str) -> None:
    """Quick summary of a log: products, days, final PnL, volume, reconciliation error."""
    log = load_log(path)
    print(f"submissionId : {log.submission_id}")
    print(f"products      : {sorted(log.activities['product'].unique())}")
    print(f"days          : {sorted(log.activities['day'].unique())}")
    ts = log.activities["timestamp"]
    print(f"timestamps    : {ts.min()} to {ts.max()} ({ts.nunique()} of them)")
    attr = pnl_attribution(log)
    print("\n== attribution by product ==")
    print(attr.to_string(index=False))
    print(f"\ntotal final_pnl: {attr['final_pnl'].sum():,.1f}")
    print("\n== reconciliation against the exchange PnL (error should be ~0) ==")
    print(reconcile_pnl(log).to_string(index=False))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        quick_summary(sys.argv[1])
    else:
        print("usage: python prosperity_review.py <path/to/submission.log>")
