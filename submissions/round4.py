from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import numpy as np
import math
from statistics import NormalDist

_N = NormalDist()

# ── CHANGE BEFORE EACH SUBMISSION ─────────────────────────────────────────
# Round 4: Day1=4, Day2=3, Day3=2, Day4=1
DAYS_LEFT = 4
# ──────────────────────────────────────────────────────────────────────────

DAYS_PER_YEAR      = 365
TIMESTAMPS_PER_DAY = 1_000_000

# ── Hydrogel ───────────────────────────────────────────────────────────────
HP = {
    "adverse_volume":      10,
    "reversion_beta":      -0.13,
    "take_width":          2,
    "clear_width":         0,
    "disregard_edge":      1,
    "join_edge":           2,
    "default_edge":        8,
    "soft_position_limit": 50,
    "position_limit":      200,
    "global_mean":         9994.70,
    "global_std":          32.84,
    "extreme_zscore":      2.5,
    "volatile_std":        25,
    "velocity_window":     15,
    "zscore_skew_factor":  2.0,
    "velocity_skew_cap":   2,
    "max_quote_skew":      4,
}

# ── Velvet ─────────────────────────────────────────────────────────────────
VP = {
    "adverse_volume":      10,
    "reversion_beta":      -0.15,
    "take_width":          1,
    "clear_width":         0,
    "disregard_edge":      1,
    "join_edge":           2,
    "default_edge":        5,
    "soft_position_limit": 60,
    "position_limit":      200,
    "global_mean":         5248.0,
    "global_std":          17.27,
    "extreme_zscore":      2.2,
    "volatile_std":        14.0,
    "velocity_window":     15,
    "zscore_skew_factor":  2.0,
    "velocity_skew_cap":   2,
    "max_quote_skew":      3,
}

# ── VEV ────────────────────────────────────────────────────────────────────
VEV_LIMIT            = 300
VEV_SOFT             = 100
VEV_DELTA_SKEW_SCALE = 60
VEV_IV_WINDOW        = 20
VEV_IV_FALLBACK      = 0.24
VEV_MAKE_EDGE_SIGMA  = 1.0
VEV_MAKE_EDGE_MIN: Dict[str, float] = {
    "VEV_4000": 6.0, "VEV_4500": 6.0,
    "VEV_5000": 3.0, "VEV_5100": 3.0,
    "VEV_5200": 3.0, "VEV_5300": 3.0,
    "VEV_5400": 2.0, "VEV_5500": 2.0,
    "VEV_6000": 0.0, "VEV_6500": 0.0,
}
VEV_BASE_TAKE_EDGE: Dict[str, float] = {
    "VEV_4000": 2.0, "VEV_4500": 2.0,
    "VEV_5000": 1.5, "VEV_5100": 1.5,
    "VEV_5200": 1.5, "VEV_5300": 1.5,
    "VEV_5400": 1.0, "VEV_5500": 1.0,
    "VEV_6000": 0.0, "VEV_6500": 0.0,
}
VEV_STRIKES: Dict[str, int] = {
    "VEV_4000": 4000, "VEV_4500": 4500,
    "VEV_5000": 5000, "VEV_5100": 5100,
    "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500,
    "VEV_6000": 6000, "VEV_6500": 6500,
}

BOT_ACTIVE_WINDOW = 5000


def bs_call(S: float, K: int, T: float, sigma: float):
    if T <= 1e-9:
        price = max(float(S - K), 0.0)
        return price, (1.0 if S > K else 0.0)
    sqT = math.sqrt(T)
    d1  = (math.log(S / K) + 0.5 * sigma ** 2 * T) / (sigma * sqT)
    d2  = d1 - sigma * sqT
    return S * _N.cdf(d1) - K * _N.cdf(d2), _N.cdf(d1)


def implied_vol(market_price: float, S: float, K: int, T: float) -> float:
    intrinsic = max(S - K, 0.0)
    if market_price <= intrinsic + 1e-6 or T <= 1e-9:
        return VEV_IV_FALLBACK
    lo, hi = 1e-4, 5.0
    for _ in range(100):
        mid = (lo + hi) / 2
        price, _ = bs_call(S, K, T, mid)
        if abs(price - market_price) < 1e-6:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def get_tte(days_left: int, timestamp: int) -> float:
    return max(days_left / DAYS_PER_YEAR - timestamp / (TIMESTAMPS_PER_DAY * DAYS_PER_YEAR), 1e-9)


class Trader:

    def run(self, state: TradingState):
        data   = json.loads(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}

        self._update_bot_signals(state, data)

        S = self._get_mid(state.order_depths.get("VELVETFRUIT_EXTRACT"))
        T = get_tte(DAYS_LEFT, state.timestamp)

        if S is not None:
            self._update_iv(state, data, S, T)

        net_delta = 0.0
        if S is not None:
            for sym, K in VEV_STRIKES.items():
                pos = state.position.get(sym, 0)
                if pos != 0:
                    iv       = self._get_iv(data, sym)
                    _, delta = bs_call(S, K, T, iv)
                    net_delta += pos * delta

        result["HYDROGEL_PACK"] = self._trade_hydrogel(state, data)

        if S is not None and state.order_depths.get("VELVETFRUIT_EXTRACT"):
            result["VELVETFRUIT_EXTRACT"] = self._trade_velvet(state, data, net_delta)

        if S is not None:
            for sym, K in VEV_STRIKES.items():
                if sym in state.order_depths:
                    take_edge = self._get_take_edge(sym, data, state.timestamp)
                    result[sym] = self._trade_vev(state, sym, K, S, T, net_delta, take_edge, data)

        return result, 0, json.dumps(data)

    # ── Rolling IV ───────────────────────────────────────────────────────

    def _update_iv(self, state: TradingState, data: dict, S: float, T: float):
        for sym, K in VEV_STRIKES.items():
            od = state.order_depths.get(sym)
            if not od or not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2
            if mid <= 0:
                continue
            iv   = implied_vol(mid, S, K, T)
            key  = f"iv_{sym}"
            hist = data.setdefault(key, [])
            hist.append(iv)
            if len(hist) > VEV_IV_WINDOW:
                data[key] = hist[-VEV_IV_WINDOW:]

    def _get_iv(self, data: dict, sym: str) -> float:
        hist = data.get(f"iv_{sym}", [])
        return float(np.mean(hist)) if hist else VEV_IV_FALLBACK

    def _get_iv_std(self, data: dict, sym: str) -> float:
        hist = data.get(f"iv_{sym}", [])
        return float(np.std(hist)) if len(hist) >= 5 else 0.0

    # ── Bot signal tracking ──────────────────────────────────────────────

    def _update_bot_signals(self, state: TradingState, data: dict):
        ts = state.timestamp
        for sym, trades in state.market_trades.items():
            for t in trades:
                if sym == "HYDROGEL_PACK":
                    if t.buyer == "Mark 38" or t.seller == "Mark 38":
                        data["h_m38_last_ts"] = ts
                    if t.buyer == "Mark 14" or t.seller == "Mark 14":
                        data["h_m14_last_ts"] = ts
                if sym == "VELVETFRUIT_EXTRACT" and t.buyer == "Mark 67":
                    data["m67_last_buy_ts"] = ts
                if sym in ("VEV_4000", "VEV_4500"):
                    if t.buyer == "Mark 38" or t.seller == "Mark 38":
                        data["m38_last_active_ts"] = ts
                    if t.buyer == "Mark 14":
                        data["m14_beat_count"] = data.get("m14_beat_count", 0) + 1
                if sym.startswith("VEV_") and t.seller == "Mark 22":
                    data[f"m22_last_sell_{sym}_ts"] = ts

    def _get_take_edge(self, sym: str, data: dict, ts: int) -> float:
        base = VEV_BASE_TAKE_EDGE[sym]
        if sym in ("VEV_4000", "VEV_4500"):
            if ts - data.get("m38_last_active_ts", -999999) < BOT_ACTIVE_WINDOW:
                return 1.5
        if sym in ("VEV_5400", "VEV_5500"):
            if ts - data.get(f"m22_last_sell_{sym}_ts", -999999) < BOT_ACTIVE_WINDOW:
                return 0.5
        return base

    # ── Shared helpers ───────────────────────────────────────────────────

    def _get_mid(self, od):
        if od and od.buy_orders and od.sell_orders:
            return (max(od.buy_orders) + min(od.sell_orders)) / 2
        return None

    def _compute_velocity(self, history: list, window: int) -> float:
        if len(history) < window:
            return 0.0
        recent = history[-window:]
        return float(np.polyfit(np.arange(window), recent, 1)[0])

    def _fair_value(self, od: OrderDepth, data: dict, prefix: str, params: dict) -> float:
        adv  = params["adverse_volume"]
        fb   = {p: v for p, v in od.buy_orders.items() if v >= adv}
        fa   = {p: v for p, v in od.sell_orders.items() if abs(v) >= adv}
        mm   = (max(fb) + min(fa)) / 2 if fb and fa else (max(od.buy_orders) + min(od.sell_orders)) / 2
        last = data.get(f"{prefix}_mid", mm)
        fair = mm + (mm - last) * params["reversion_beta"]
        data[f"{prefix}_mid"] = mm
        return fair

    def _take(self, od, fair, pos, bv, sv, orders, sym, params):
        lim, tw, adv = params["position_limit"], params["take_width"], params["adverse_volume"]
        if od.sell_orders:
            ba  = min(od.sell_orders)
            qty = abs(od.sell_orders[ba])
            if qty <= adv and ba <= fair - tw:
                qty = min(qty, lim - pos - bv)
                if qty > 0:
                    orders.append(Order(sym, ba, qty)); bv += qty
        if od.buy_orders:
            bb  = max(od.buy_orders)
            qty = od.buy_orders[bb]
            if qty <= adv and bb >= fair + tw:
                qty = min(qty, lim + pos - sv)
                if qty > 0:
                    orders.append(Order(sym, bb, -qty)); sv += qty
        return bv, sv

    def _clear(self, od, fair, pos, bv, sv, orders, sym, params):
        lim = params["position_limit"]
        pa  = pos + bv - sv
        fb, fa = round(fair - params["clear_width"]), round(fair + params["clear_width"])
        if pa > 0:
            clr  = min(sum(v for p, v in od.buy_orders.items() if p >= fa), pa)
            send = min(lim + pos - sv, clr)
            if send > 0:
                orders.append(Order(sym, fa, -send)); sv += send
        if pa < 0:
            clr  = min(sum(abs(v) for p, v in od.sell_orders.items() if p <= fb), abs(pa))
            send = min(lim - pos - bv, clr)
            if send > 0:
                orders.append(Order(sym, fb, send)); bv += send
        return bv, sv

    def _extreme(self, od, zscore, rolling_std, pos, bv, sv, orders, data, sym, params, el_key, es_key):
        lim = params["position_limit"]
        if not (rolling_std > params["volatile_std"] or abs(zscore) > params["extreme_zscore"]):
            return bv, sv
        if zscore < -params["extreme_zscore"] and od.sell_orders:
            ba  = min(od.sell_orders)
            qty = min(abs(od.sell_orders[ba]), lim - pos - bv)
            if qty > 0:
                orders.append(Order(sym, ba, qty))
                bv += qty; data[el_key] = data.get(el_key, 0) + qty
        elif zscore > params["extreme_zscore"] and od.buy_orders:
            bb  = max(od.buy_orders)
            qty = min(od.buy_orders[bb], lim + pos - sv)
            if qty > 0:
                orders.append(Order(sym, bb, -qty))
                sv += qty; data[es_key] = data.get(es_key, 0) + qty
        return bv, sv

    def _clear_extreme(self, od, zscore, pos, bv, sv, orders, data, sym, params, el_key, es_key):
        lim = params["position_limit"]
        if abs(zscore) > 0.3:
            return bv, sv
        el, es = data.get(el_key, 0), data.get(es_key, 0)
        if el > 0 and od.buy_orders:
            bb  = max(od.buy_orders)
            qty = min(el, od.buy_orders[bb], lim + pos - sv)
            if qty > 0:
                orders.append(Order(sym, bb, -qty))
                sv += qty; data[el_key] = max(0, el - qty)
        if es > 0 and od.sell_orders:
            ba  = min(od.sell_orders)
            qty = min(es, abs(od.sell_orders[ba]), lim - pos - bv)
            if qty > 0:
                orders.append(Order(sym, ba, qty))
                bv += qty; data[es_key] = max(0, es - qty)
        return bv, sv

    def _make(self, od, fair, pos, bv, sv, orders, sym, params, zscore, velocity, extra_skew=0):
        lim, soft = params["position_limit"], params["soft_position_limit"]

        asks_above = [p for p in od.sell_orders if p > fair + params["disregard_edge"]]
        bids_below = [p for p in od.buy_orders  if p < fair - params["disregard_edge"]]

        ask = round(fair + params["default_edge"])
        if asks_above:
            baa = min(asks_above)
            ask = baa if abs(baa - fair) <= params["join_edge"] else baa - 1

        bid = round(fair - params["default_edge"])
        if bids_below:
            bbb = max(bids_below)
            bid = bbb if abs(fair - bbb) <= params["join_edge"] else bbb + 1

        v_skew     = np.sign(velocity) * min(abs(velocity) * 20.0, params["velocity_skew_cap"])
        quote_skew = int(np.clip(
            zscore * params["zscore_skew_factor"] + v_skew + extra_skew,
            -params["max_quote_skew"], params["max_quote_skew"]
        ))
        ask -= quote_skew
        bid -= quote_skew

        if pos > soft:    ask -= 1
        elif pos < -soft: bid += 1

        ask = max(ask, round(fair) + 1)
        bid = min(bid, round(fair) - 1)

        if lim - pos - bv > 0:
            orders.append(Order(sym, bid,  lim - pos - bv))
        if lim + pos - sv > 0:
            orders.append(Order(sym, ask, -(lim + pos - sv)))

    # ── Hydrogel ─────────────────────────────────────────────────────────

    def _trade_hydrogel(self, state: TradingState, data: dict) -> List[Order]:
        od = state.order_depths.get("HYDROGEL_PACK")
        if not od or not od.buy_orders or not od.sell_orders:
            return []

        sym = "HYDROGEL_PACK"
        pos = state.position.get(sym, 0)
        orders: List[Order] = []
        bv = sv = 0

        fair = self._fair_value(od, data, "h", HP)

        hist = data.setdefault("h_hist", [])
        hist.append(fair)
        if len(hist) > 500:
            data["h_hist"] = hist[-500:]
            hist = data["h_hist"]

        rolling_std = float(np.std(hist)) if len(hist) >= 50 else HP["global_std"]
        zscore      = (fair - HP["global_mean"]) / HP["global_std"]
        velocity    = self._compute_velocity(hist, HP["velocity_window"])

        # Mark 38 active → undercut Mark 14 by 1 tick to capture its flow
        ts = state.timestamp
        m38_active = ts - data.get("h_m38_last_ts", -999999) < BOT_ACTIVE_WINDOW
        hp = {**HP, "default_edge": 7 if m38_active else 8}

        bv, sv = self._take(od, fair, pos, bv, sv, orders, sym, hp)
        bv, sv = self._clear_extreme(od, zscore, pos, bv, sv, orders, data, sym, hp, "h_el", "h_es")
        bv, sv = self._clear(od, fair, pos, bv, sv, orders, sym, hp)
        bv, sv = self._extreme(od, zscore, rolling_std, pos, bv, sv, orders, data, sym, hp, "h_el", "h_es")
        self._make(od, fair, pos, bv, sv, orders, sym, hp, zscore, velocity)

        return orders

    # ── Velvet ───────────────────────────────────────────────────────────

    def _trade_velvet(self, state: TradingState, data: dict, net_delta: float) -> List[Order]:
        od  = state.order_depths["VELVETFRUIT_EXTRACT"]
        sym = "VELVETFRUIT_EXTRACT"
        pos = state.position.get(sym, 0)
        orders: List[Order] = []
        bv = sv = 0

        fair = self._fair_value(od, data, "v", VP)

        hist = data.setdefault("v_hist", [])
        hist.append(fair)
        if len(hist) > 500:
            data["v_hist"] = hist[-500:]
            hist = data["v_hist"]

        rolling_std = float(np.std(hist)) if len(hist) >= 50 else VP["global_std"]
        zscore      = (fair - VP["global_mean"]) / VP["global_std"]
        velocity    = self._compute_velocity(hist, VP["velocity_window"])

        m67_bias   = 0.5 if state.timestamp - data.get("m67_last_buy_ts", -999999) < BOT_ACTIVE_WINDOW else 0
        delta_skew = float(np.clip(net_delta / 150, -1, 1))
        extra_skew = delta_skew - m67_bias

        bv, sv = self._take(od, fair, pos, bv, sv, orders, sym, VP)
        bv, sv = self._clear_extreme(od, zscore, pos, bv, sv, orders, data, sym, VP, "v_el", "v_es")
        bv, sv = self._clear(od, fair, pos, bv, sv, orders, sym, VP)
        bv, sv = self._extreme(od, zscore, rolling_std, pos, bv, sv, orders, data, sym, VP, "v_el", "v_es")
        self._make(od, fair, pos, bv, sv, orders, sym, VP, zscore, velocity, extra_skew)

        return orders

    # ── VEV Options ──────────────────────────────────────────────────────

    def _trade_vev(
        self, state: TradingState, sym: str, K: int,
        S: float, T: float, net_delta: float, take_edge: float, data: dict
    ) -> List[Order]:
        od  = state.order_depths[sym]
        pos = state.position.get(sym, 0)
        orders: List[Order] = []
        bv = sv = 0

        iv          = self._get_iv(data, sym)
        iv_std      = self._get_iv_std(data, sym)
        fair, _     = bs_call(S, K, T, iv)
        min_edge    = VEV_MAKE_EDGE_MIN[sym]

        # Deep OTM: bid 1 only
        if min_edge == 0.0:
            if VEV_LIMIT - pos > 0:
                orders.append(Order(sym, 1, VEV_LIMIT - pos))
            return orders

        # make_edge = vega * iv_std, floored at min_edge
        sqT      = math.sqrt(T)
        d1       = (math.log(S / K) + 0.5 * iv ** 2 * T) / (iv * sqT) if iv > 0 else 0.0
        vega     = _N.pdf(d1) * S * sqT
        make_edge = max(min_edge, VEV_MAKE_EDGE_SIGMA * vega * iv_std)

        # Take phase
        if take_edge > 0:
            for ask_p in sorted(od.sell_orders):
                if ask_p > fair - take_edge:
                    break
                qty = min(abs(od.sell_orders[ask_p]), VEV_LIMIT - pos - bv)
                if qty > 0:
                    orders.append(Order(sym, ask_p, qty)); bv += qty

            for bid_p in sorted(od.buy_orders, reverse=True):
                if bid_p < fair + take_edge:
                    break
                qty = min(od.buy_orders[bid_p], VEV_LIMIT + pos - sv)
                if qty > 0:
                    orders.append(Order(sym, bid_p, -qty)); sv += qty

        # Make phase
        delta_skew = int(np.clip(net_delta / VEV_DELTA_SKEW_SCALE, -2, 2))
        pos_skew   = -1 if pos > VEV_SOFT else (1 if pos < -VEV_SOFT else 0)

        bid_p = max(1,               round(fair - make_edge) - delta_skew + pos_skew)
        ask_p = max(round(fair) + 1, round(fair + make_edge) - delta_skew)

        if bid_p >= ask_p:
            ask_p = bid_p + 1

        if VEV_LIMIT - pos - bv > 0:
            orders.append(Order(sym, bid_p,  VEV_LIMIT - pos - bv))
        if VEV_LIMIT + pos - sv > 0:
            orders.append(Order(sym, ask_p, -(VEV_LIMIT + pos - sv)))

        return orders