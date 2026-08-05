from datamodel import OrderDepth, TradingState, Order
import json
import math


HYDROGEL_SYMBOL = 'HYDROGEL_PACK'
VEV_SYMBOL = 'VELVETFRUIT_EXTRACT'
OPTION_SYMBOLS = [
    'VEV_5000', 'VEV_5100', 'VEV_5200',
    'VEV_5300', 'VEV_5400', 'VEV_5500',
]

POS_LIMITS = {
    HYDROGEL_SYMBOL: 200,
    VEV_SYMBOL: 200,
    **{s: 300 for s in OPTION_SYMBOLS},
    **{s: 300 for s in ['VEV_4000', 'VEV_4500', 'VEV_6000', 'VEV_6500']},
}
DAY = 3
DAYS_PER_YEAR = 365
IV_SMILE_COEFFS = [0.034, 0.0015, 0.2315]
THR_OPEN = 0.5     
THR_CLOSE = 0       
LOW_VEGA_THR_ADJ = 0.5
THEO_NORM_WINDOW = 20
IV_SCALPING_WINDOW = 100
IV_SCALPING_THR = 0.7 
UNDERLYING_MR_WINDOW = 10
UNDERLYING_MR_THR = 15

LONG, NEUTRAL, SHORT = 1, 0, -1


class ProductTrader:

    def __init__(self, name, state, prints, new_trader_data, product_group=None):
        self.orders = []
        self.name = name
        self.state = state
        self.prints = prints
        self.new_trader_data = new_trader_data
        self.product_group = name if product_group is None else product_group

        self.last_traderData = self._load_trader_data()

        self.position_limit = POS_LIMITS.get(self.name, 0)
        self.initial_position = self.state.position.get(self.name, 0)
        self.expected_position = self.initial_position

        self.mkt_buy_orders, self.mkt_sell_orders = self._get_order_depth()
        self.bid_wall, self.wall_mid, self.ask_wall = self._get_walls()
        self.best_bid, self.best_ask = self._get_best_bid_ask()
        self.max_allowed_buy_volume, self.max_allowed_sell_volume = self._get_max_volume()
        self.total_mkt_buy_volume, self.total_mkt_sell_volume = self._get_total_market_volume()

    def _load_trader_data(self):
        try:
            if self.state.traderData != '':
                return json.loads(self.state.traderData)
        except:
            pass
        return {}

    def _get_order_depth(self):
        buy_orders, sell_orders = {}, {}
        try:
            od: OrderDepth = self.state.order_depths[self.name]
            buy_orders = {p: abs(v) for p, v in sorted(od.buy_orders.items(), key=lambda x: x[0], reverse=True)}
            sell_orders = {p: abs(v) for p, v in sorted(od.sell_orders.items(), key=lambda x: x[0])}
        except:
            pass
        return buy_orders, sell_orders

    def _get_walls(self):
        bid_wall = ask_wall = wall_mid = None
        try: bid_wall = min(self.mkt_buy_orders.keys())
        except: pass
        try: ask_wall = max(self.mkt_sell_orders.keys())
        except: pass
        try: wall_mid = (bid_wall + ask_wall) / 2
        except: pass
        return bid_wall, wall_mid, ask_wall

    def _get_best_bid_ask(self):
        best_bid = best_ask = None
        try:
            if self.mkt_buy_orders: best_bid = max(self.mkt_buy_orders.keys())
            if self.mkt_sell_orders: best_ask = min(self.mkt_sell_orders.keys())
        except:
            pass
        return best_bid, best_ask

    def _get_max_volume(self):
        return (self.position_limit - self.initial_position,
                self.position_limit + self.initial_position)

    def _get_total_market_volume(self):
        buy_vol = sell_vol = 0
        try:
            buy_vol = sum(self.mkt_buy_orders.values())
            sell_vol = sum(self.mkt_sell_orders.values())
        except:
            pass
        return buy_vol, sell_vol

    def bid(self, price, volume, logging=True):
        vol = min(abs(int(volume)), self.max_allowed_buy_volume)
        if vol <= 0: return
        order = Order(self.name, int(price), vol)
        if logging: self.log("BUYO", {"p": price, "v": vol}, product_group='ORDERS')
        self.max_allowed_buy_volume -= vol
        self.orders.append(order)

    def ask(self, price, volume, logging=True):
        vol = min(abs(int(volume)), self.max_allowed_sell_volume)
        if vol <= 0: return
        order = Order(self.name, int(price), -vol)
        if logging: self.log("SELLO", {"p": price, "v": vol}, product_group='ORDERS')
        self.max_allowed_sell_volume -= vol
        self.orders.append(order)

    def log(self, kind, message, product_group=None):
        if product_group is None: product_group = self.product_group
        if product_group == 'ORDERS':
            group = self.prints.get(product_group, [])
            group.append({kind: message})
        else:
            group = self.prints.get(product_group, {})
            group[kind] = message
        self.prints[product_group] = group

    def get_orders(self):
        return {}



class HydrogelTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(HYDROGEL_SYMBOL, state, prints, new_trader_data)

    def get_orders(self):
        if self.wall_mid is None:
            return {self.name: self.orders}
        for sp, sv in self.mkt_sell_orders.items():
            if sp <= self.wall_mid - 1:
                self.bid(sp, sv, logging=False)
            elif sp <= self.wall_mid and self.initial_position < 0:
                self.bid(sp, min(sv, abs(self.initial_position)), logging=False)

        for bp, bv in self.mkt_buy_orders.items():
            if bp >= self.wall_mid + 1:
                self.ask(bp, bv, logging=False)
            elif bp >= self.wall_mid and self.initial_position > 0:
                self.ask(bp, min(bv, self.initial_position), logging=False)

        bid_price = int(self.bid_wall + 1)
        ask_price = int(self.ask_wall - 1)

        for bp, bv in self.mkt_buy_orders.items():
            overbid = bp + 1
            if bv > 1 and overbid < self.wall_mid:
                bid_price = max(bid_price, overbid)
                break
            elif bp < self.wall_mid:
                bid_price = max(bid_price, bp)
                break

        for sp, sv in self.mkt_sell_orders.items():
            underask = sp - 1
            if sv > 1 and underask > self.wall_mid:
                ask_price = min(ask_price, underask)
                break
            elif sp > self.wall_mid:
                ask_price = min(ask_price, sp)
                break

        self.bid(bid_price, self.max_allowed_buy_volume)
        self.ask(ask_price, self.max_allowed_sell_volume)

        return {self.name: self.orders}


class VelvetfruitTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(VEV_SYMBOL, state, prints, new_trader_data)

    def get_orders(self):
        if self.wall_mid is None:
            return {self.name: self.orders}

        for sp, sv in self.mkt_sell_orders.items():
            if sp <= self.wall_mid - 1:
                self.bid(sp, sv, logging=False)
            elif sp <= self.wall_mid and self.initial_position < 0:
                self.bid(sp, min(sv, abs(self.initial_position)), logging=False)

        for bp, bv in self.mkt_buy_orders.items():
            if bp >= self.wall_mid + 1:
                self.ask(bp, bv, logging=False)
            elif bp >= self.wall_mid and self.initial_position > 0:
                self.ask(bp, min(bv, self.initial_position), logging=False)

        bid_price = int(self.bid_wall + 1)
        ask_price = int(self.ask_wall - 1)

        for bp, bv in self.mkt_buy_orders.items():
            overbid = bp + 1
            if bv > 1 and overbid < self.wall_mid:
                bid_price = max(bid_price, overbid)
                break
            elif bp < self.wall_mid:
                bid_price = max(bid_price, bp)
                break

        for sp, sv in self.mkt_sell_orders.items():
            underask = sp - 1
            if sv > 1 and underask > self.wall_mid:
                ask_price = min(ask_price, underask)
                break
            elif sp > self.wall_mid:
                ask_price = min(ask_price, sp)
                break

        self.bid(bid_price, self.max_allowed_buy_volume)
        self.ask(ask_price, self.max_allowed_sell_volume)

        return {self.name: self.orders}


class VEVOptionTrader:

    def __init__(self, state, prints, new_trader_data):
        self.options = [
            ProductTrader(s, state, prints, new_trader_data, product_group='OPTION')
            for s in OPTION_SYMBOLS
        ]
        self.underlying = ProductTrader(VEV_SYMBOL, state, prints, new_trader_data, product_group='OPTION')

        self.state = state
        self.last_traderData = self.underlying.last_traderData
        self.new_trader_data = new_trader_data

        self.indicators = self._calculate_indicators()


    def _compute_tte(self):
        return 1.0 - (DAYS_PER_YEAR - 8 + DAY + self.state.timestamp // 100 / 10_000) / DAYS_PER_YEAR

    def _get_iv(self, S, K, TTE):
        if TTE <= 0: return 0.001
        m = math.log(K / S) / math.sqrt(TTE)
        c2, c1, c0 = IV_SMILE_COEFFS
        iv = c2 * m * m + c1 * m + c0
        return max(iv, 0.005)

    def _bs_price_delta_vega(self, S, K, TTE, sigma):
        if TTE <= 1e-9:
            return max(S - K, 0.0), 1.0 if S > K else 0.0, 0.0
        
        sqrt_TTE = math.sqrt(TTE)
        sigma_sqrt_TTE = sigma * sqrt_TTE
        d1 = (math.log(S / K) + 0.5 * sigma**2 * TTE) / sigma_sqrt_TTE
        d2 = d1 - sigma_sqrt_TTE
        
        cdf_d1 = 0.5 * (1.0 + math.erf(d1 / 1.4142135623730951))
        cdf_d2 = 0.5 * (1.0 + math.erf(d2 / 1.4142135623730951))
        pdf_d1 = 0.3989422804014327 * math.exp(-0.5 * d1 * d1)
        
        price = S * cdf_d1 - K * cdf_d2
        delta = cdf_d1
        vega = S * pdf_d1 * sqrt_TTE
        return price, delta, vega

    def _get_option_values(self, S, K, TTE):
        iv = self._get_iv(S, K, TTE)
        return self._bs_price_delta_vega(S, K, TTE, iv)


    def _ema(self, td_key, window, value):
        old = self.last_traderData.get(td_key, value)  
        alpha = 2.0 / (window + 1)
        new = alpha * value + (1 - alpha) * old
        self.new_trader_data[td_key] = new
        return new


    def _calculate_indicators(self):
        indicators = {
            'ema_u_dev': None,
            'ema_o_dev': None,
            'mean_theo_diffs': {},
            'current_theo_diffs': {},
            'switch_means': {},
            'deltas': {},
            'vegas': {},
        }

        if self.underlying.wall_mid is None:
            return indicators

        tte = self._compute_tte()

        ema_u = self._ema('ema_u', UNDERLYING_MR_WINDOW, self.underlying.wall_mid)
        indicators['ema_u_dev'] = self.underlying.wall_mid - ema_u

        ema_o = self._ema('ema_o', IV_SCALPING_WINDOW, self.underlying.wall_mid)
        indicators['ema_o_dev'] = self.underlying.wall_mid - ema_o

        S = None
        if self.underlying.best_bid is not None and self.underlying.best_ask is not None:
            S = 0.5 * (self.underlying.best_bid + self.underlying.best_ask)
        elif self.underlying.wall_mid is not None:
            S = self.underlying.wall_mid

        if S is None or tte <= 0:
            return indicators

        for option in self.options:
            K = int(option.name.split('_')[-1])

            if option.wall_mid is None:
                if option.ask_wall is not None:
                    option.wall_mid = option.ask_wall - 0.5
                    option.bid_wall = option.ask_wall - 1
                    option.best_bid = option.ask_wall - 1
                elif option.bid_wall is not None:
                    option.wall_mid = option.bid_wall + 0.5
                    option.ask_wall = option.bid_wall + 1
                    option.best_ask = option.bid_wall + 1

            if option.wall_mid is None:
                continue

            theo, delta, vega = self._get_option_values(S, K, tte)
            theo_diff = option.wall_mid - theo

            indicators['current_theo_diffs'][option.name] = theo_diff
            indicators['deltas'][option.name] = delta
            indicators['vegas'][option.name] = vega

            mean_diff = self._ema(f'{option.name}_td', THEO_NORM_WINDOW, theo_diff)
            indicators['mean_theo_diffs'][option.name] = mean_diff

            avg_abs_dev = self._ema(f'{option.name}_aad', IV_SCALPING_WINDOW, abs(theo_diff - mean_diff))
            indicators['switch_means'][option.name] = avg_abs_dev

        return indicators


    def _get_iv_scalping_orders(self, options):
        out = {}
        for option in options:
            name = option.name
            if (name not in self.indicators['mean_theo_diffs']
                    or name not in self.indicators['current_theo_diffs']
                    or name not in self.indicators['switch_means']):
                continue

            avg_abs_dev = self.indicators['switch_means'][name]
            if avg_abs_dev < IV_SCALPING_THR:
                continue

            current_diff = self.indicators['current_theo_diffs'][name]
            mean_diff = self.indicators['mean_theo_diffs'][name]

            low_vega_adj = LOW_VEGA_THR_ADJ if self.indicators['vegas'].get(name, 1) <= 1 else 0

            dev_at_bid = current_diff - option.wall_mid + option.best_bid - mean_diff
            dev_at_ask = current_diff - option.wall_mid + option.best_ask - mean_diff

            if dev_at_bid >= (THR_OPEN + low_vega_adj) and option.max_allowed_sell_volume > 0:
                option.ask(option.best_bid, option.max_allowed_sell_volume)

            if dev_at_bid >= THR_CLOSE and option.initial_position > 0:
                option.ask(option.best_bid, option.initial_position)

            elif dev_at_ask <= -(THR_OPEN + low_vega_adj) and option.max_allowed_buy_volume > 0:
                option.bid(option.best_ask, option.max_allowed_buy_volume)

            if dev_at_ask <= -THR_CLOSE and option.initial_position < 0:
                option.bid(option.best_ask, -option.initial_position)

            out[name] = option.orders

        return out

    def _get_underlying_orders(self):
        if self.underlying.wall_mid is None:
            return {}

        dev = self.indicators.get('ema_u_dev')
        mr_fired = False

        if dev is not None and self.state.timestamp / 100 >= UNDERLYING_MR_WINDOW:
            if dev > UNDERLYING_MR_THR and self.underlying.max_allowed_sell_volume > 0:
                self.underlying.ask(self.underlying.bid_wall + 1, self.underlying.max_allowed_sell_volume)
                mr_fired = True
            elif dev < -UNDERLYING_MR_THR and self.underlying.max_allowed_buy_volume > 0:
                self.underlying.bid(self.underlying.ask_wall - 1, self.underlying.max_allowed_buy_volume)
                mr_fired = True

        if not mr_fired:
            u = self.underlying
            bid_price = int(u.bid_wall + 1)
            ask_price = int(u.ask_wall - 1)

            for bp, bv in u.mkt_buy_orders.items():
                overbid = bp + 1
                if bv > 1 and overbid < u.wall_mid:
                    bid_price = max(bid_price, overbid); break
                elif bp < u.wall_mid:
                    bid_price = max(bid_price, bp); break

            for sp, sv in u.mkt_sell_orders.items():
                underask = sp - 1
                if sv > 1 and underask > u.wall_mid:
                    ask_price = min(ask_price, underask); break
                elif sp > u.wall_mid:
                    ask_price = min(ask_price, sp); break

            u.bid(bid_price, u.max_allowed_buy_volume)
            u.ask(ask_price, u.max_allowed_sell_volume)

        return {self.underlying.name: self.underlying.orders}

    def get_orders(self):
        out = self._get_underlying_orders()
        if self.state.timestamp / 100 >= min(THEO_NORM_WINDOW, UNDERLYING_MR_WINDOW):
            out.update(self._get_iv_scalping_orders(self.options))
        return out


class Trader:

    def run(self, state: TradingState):
        new_trader_data = {}
        prints = {"GENERAL": {"TS": state.timestamp, "POS": state.position}}

        def export(p):
            try: print(json.dumps(p))
            except: pass

        result = {}

        if HYDROGEL_SYMBOL in state.order_depths:
            try:
                t = HydrogelTrader(state, prints, new_trader_data)
                result.update(t.get_orders())
            except: pass

        if VEV_SYMBOL in state.order_depths:
            try:
                opt_trader = VEVOptionTrader(state, prints, new_trader_data)
                result.update(opt_trader.get_orders())
            except: pass

        try: final_trader_data = json.dumps(new_trader_data)
        except: final_trader_data = ''

        export(prints)
        return result, 0, final_trader_data