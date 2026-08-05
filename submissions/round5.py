from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import numpy as np

# ── Strategy parameters ────────────────────────────────────────────────────────
POSITION_LIMIT = 10
WINDOW         = 500
ENTRY_K        = 2.0
MM_EDGE        = 2      # quote this many ticks inside fair value each side

PAIRS = [
    ("TRANSLATOR_ECLIPSE_CHARCOAL", "TRANSLATOR_VOID_BLUE",       0.500071),
    ("PANEL_2X2",                   "PANEL_4X4",                  -0.778745),
    ("SNACKPACK_PISTACHIO",         "SNACKPACK_STRAWBERRY",       -0.163593),
    ("GALAXY_SOUNDS_DARK_MATTER",   "GALAXY_SOUNDS_BLACK_HOLES",   0.443447),
    ("MICROCHIP_OVAL",              "MICROCHIP_RECTANGLE",         0.848069),
]

TREND = {
    "PEBBLES_XL":            1,
    "OXYGEN_SHAKE_GARLIC":   1,
    "TRANSLATOR_SPACE_GRAY": -1,
    "MICROCHIP_TRIANGLE":    -1,
    "GALAXY_SOUNDS_SOLAR_FLAMES":    1,
    "GALAXY_SOUNDS_PLANETARY_RINGS": 1,
}

MM_PRODUCTS = [
    "SNACKPACK_RASPBERRY",
    "SNACKPACK_VANILLA",
    "SNACKPACK_CHOCOLATE",
    "MICROCHIP_CIRCLE",
]


class Trader:

    def run(self, state: TradingState):
        data   = json.loads(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}

        for A, B, beta in PAIRS:
            orders_a, orders_b = self._trade_pair(state, data, A, B, beta)
            if orders_a: result[A] = orders_a
            if orders_b: result[B] = orders_b

        for product, direction in TREND.items():
            orders = self._trade_trend(state, product, direction)
            if orders: result[product] = orders

        for product in MM_PRODUCTS:
            orders = self._trade_mm(state, data, product)
            if orders: result[product] = orders

        return result, 0, json.dumps(data)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _mid(self, od: OrderDepth):
        if od and od.buy_orders and od.sell_orders:
            return (max(od.buy_orders) + min(od.sell_orders)) / 2
        return None

    def _clamp_qty(self, qty: int, pos: int, limit: int) -> int:
        """Clamp buy qty so position stays within [-limit, limit]."""
        if qty > 0:
            return min(qty, limit - pos)
        return max(qty, -limit - pos)

    # ── Pairs trading ─────────────────────────────────────────────────────────

    def _trade_pair(self, state, data, A, B, beta):
        od_a = state.order_depths.get(A)
        od_b = state.order_depths.get(B)
        mid_a, mid_b = self._mid(od_a), self._mid(od_b)
        if mid_a is None or mid_b is None:
            return [], []

        spread = np.log(mid_a) - beta * np.log(mid_b)

        key = f"spread_{A}_{B}"
        hist = data.setdefault(key, [])
        hist.append(float(spread))
        if len(hist) > WINDOW:
            data[key] = hist[-WINDOW:]
            hist = data[key]

        if len(hist) < WINDOW:
            return [], []

        mu, sigma = float(np.mean(hist)), float(np.std(hist))
        if sigma < 1e-8:
            return [], []

        z       = (spread - mu) / sigma
        pos_a   = state.position.get(A, 0)
        pos_b   = state.position.get(B, 0)
        sig_key = f"sig_{A}_{B}"
        sig     = data.get(sig_key, 0)

        if sig == 0:
            if z > ENTRY_K:
                sig = -1
            elif z < -ENTRY_K:
                sig = 1
        elif sig == 1 and z >= 0:
            sig = 0
        elif sig == -1 and z <= 0:
            sig = 0
        data[sig_key] = sig

        orders_a, orders_b = [], []
        if sig == 0:
            return orders_a, orders_b

        # sig=1: long spread → buy A, sell B
        # sig=-1: short spread → sell A, buy B
        q_a = int(min(POSITION_LIMIT, np.floor(POSITION_LIMIT / max(abs(beta), 1e-8))))

        if sig == 1:
            qty_a = self._clamp_qty(q_a, pos_a, POSITION_LIMIT)
            qty_b = self._clamp_qty(-int(round(q_a * abs(beta))), pos_b, POSITION_LIMIT)
        else:
            qty_a = self._clamp_qty(-q_a, pos_a, POSITION_LIMIT)
            qty_b = self._clamp_qty(int(round(q_a * abs(beta))), pos_b, POSITION_LIMIT)

        if qty_a != 0 and od_a.sell_orders and od_a.buy_orders:
            price = min(od_a.sell_orders) if qty_a > 0 else max(od_a.buy_orders)
            orders_a.append(Order(A, price, qty_a))

        if qty_b != 0 and od_b.sell_orders and od_b.buy_orders:
            price = min(od_b.sell_orders) if qty_b > 0 else max(od_b.buy_orders)
            orders_b.append(Order(B, price, qty_b))

        return orders_a, orders_b

    # ── Trend following ───────────────────────────────────────────────────────

    def _trade_trend(self, state, product, direction):
        od  = state.order_depths.get(product)
        pos = state.position.get(product, 0)
        if od is None:
            return []

        target = direction * POSITION_LIMIT
        delta  = target - pos
        if delta == 0:
            return []

        orders = []
        if delta > 0 and od.sell_orders:
            price = min(od.sell_orders)
            orders.append(Order(product, price, delta))
        elif delta < 0 and od.buy_orders:
            price = max(od.buy_orders)
            orders.append(Order(product, price, delta))

        return orders

    # ── Market making ─────────────────────────────────────────────────────────

    def _trade_mm(self, state, data, product):
        od  = state.order_depths.get(product)
        pos = state.position.get(product, 0)
        mid = self._mid(od)
        if od is None or mid is None:
            return []

        fair = round(mid)
        bid  = fair - MM_EDGE
        ask  = fair + MM_EDGE

        buy_qty  = self._clamp_qty(POSITION_LIMIT - pos, pos, POSITION_LIMIT)
        sell_qty = self._clamp_qty(-(POSITION_LIMIT + pos), pos, POSITION_LIMIT)

        orders = []
        if buy_qty  > 0: orders.append(Order(product, bid,  buy_qty))
        if sell_qty < 0: orders.append(Order(product, ask, sell_qty))

        return orders