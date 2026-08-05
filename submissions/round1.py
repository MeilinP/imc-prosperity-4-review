from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json


class Trader:
    LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }
    PEPPER_SLOPE = 0.001
    PEPPER_BUY_BUFFER = 10

    def run(self, state: TradingState):
        data: dict = json.loads(state.traderData) if state.traderData else {}
        orders: Dict[str, List[Order]] = {}

        pepper_fair = self._update_pepper_fair(state, data)
        ash_fair = self._update_ash_fair(state, data)

        for product, od in state.order_depths.items():
            pos = state.position.get(product, 0)
            lim = self.LIMITS.get(product, 80)

            if product == "INTARIAN_PEPPER_ROOT":
                orders[product] = self._pepper_orders(od, pos, lim, pepper_fair)
            elif product == "ASH_COATED_OSMIUM":
                orders[product] = self._ash_orders(od, pos, lim, ash_fair)

        return orders, 0, json.dumps(data)

    def _update_pepper_fair(self, state: TradingState, data: dict) -> float:
        od = state.order_depths.get("INTARIAN_PEPPER_ROOT")
        if od and od.buy_orders and od.sell_orders:
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2
            implied_intercept = mid - self.PEPPER_SLOPE * state.timestamp
            if "pepper_intercept" not in data:
                data["pepper_intercept"] = implied_intercept
            else:
                data["pepper_intercept"] = (
                    0.02 * implied_intercept + 0.98 * data["pepper_intercept"]
                )
        return data.get("pepper_intercept", 10000) + self.PEPPER_SLOPE * state.timestamp

    def _update_ash_fair(self, state: TradingState, data: dict) -> float:
        od = state.order_depths.get("ASH_COATED_OSMIUM")
        if od and od.buy_orders and od.sell_orders:
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2
            if "ash_fair" not in data:
                data["ash_fair"] = mid
            else:
                deviation = abs(mid - data["ash_fair"])
                alpha = 0.05 + 0.05 * min(deviation / 5, 1.0)
                data["ash_fair"] = alpha * mid + (1 - alpha) * data["ash_fair"]
        return data.get("ash_fair", 10000)

    def _pepper_orders(self, od: OrderDepth, pos: int, lim: int, fair: float) -> List[Order]:
        orders: List[Order] = []
        buy_cap = lim - pos

        for price in sorted(od.sell_orders):
            if buy_cap <= 0:
                break
            if price <= fair + self.PEPPER_BUY_BUFFER:
                qty = min(-od.sell_orders[price], buy_cap)
                orders.append(Order("INTARIAN_PEPPER_ROOT", price, qty))
                buy_cap -= qty

        if buy_cap > 0 and od.buy_orders:
            rest_bid = min(max(od.buy_orders) + 1, int(fair))
            orders.append(Order("INTARIAN_PEPPER_ROOT", rest_bid, buy_cap))

        return orders

    def _ash_orders(self, od: OrderDepth, pos: int, lim: int, fair: float) -> List[Order]:
        orders: List[Order] = []
        buy_cap = lim - pos
        sell_cap = lim + pos

        spread = min(od.sell_orders) - max(od.buy_orders) if od.sell_orders and od.buy_orders else 16
        skew_k = spread * 0.3
        fair_skewed = fair - skew_k * (pos / lim)

        avg_bot_size = (
            sum(od.buy_orders.values()) + sum(abs(v) for v in od.sell_orders.values())
        ) / max(len(od.buy_orders) + len(od.sell_orders), 1)
        passive_cap = max(10, min(30, int(avg_bot_size * 0.6)))

        for price in sorted(od.sell_orders):
            if price >= fair_skewed or buy_cap <= 0:
                break
            qty = min(-od.sell_orders[price], buy_cap)
            orders.append(Order("ASH_COATED_OSMIUM", price, qty))
            buy_cap -= qty

        for price in sorted(od.buy_orders, reverse=True):
            if price <= fair_skewed or sell_cap <= 0:
                break
            qty = min(od.buy_orders[price], sell_cap)
            orders.append(Order("ASH_COATED_OSMIUM", price, -qty))
            sell_cap -= qty

        if od.buy_orders and buy_cap > 0:
            mm_bid = max(od.buy_orders) + 1
            if mm_bid < int(fair_skewed):
                orders.append(Order("ASH_COATED_OSMIUM", mm_bid, min(buy_cap, passive_cap)))

        if od.sell_orders and sell_cap > 0:
            mm_ask = min(od.sell_orders) - 1
            if mm_ask > int(fair_skewed):
                orders.append(Order("ASH_COATED_OSMIUM", mm_ask, -min(sell_cap, passive_cap)))

        return orders