# Data

The organisers' market data is not committed here — the five rounds total roughly 400 MB.

## What is needed

Per round, three pre-round days of order-book snapshots and trade records:

```
data/round1/prices_round_1_day_{-2,-1,0}.csv
data/round1/trades_round_1_day_{-2,-1,0}.csv
data/round2/…                      days -1, 0, 1
data/round3/…                      days  0, 1, 2
data/round4/…                      days  1, 2, 3
data/round5/…                      days  2, 3, 4
```

Semicolon-delimited. Prices carry three levels per side plus `mid_price` and
`profit_and_loss`; trades carry `timestamp;buyer;seller;symbol;currency;price;quantity`.

Available from the IMC Prosperity 4 wiki:
<https://imc-prosperity.notion.site/prosperity-4-wiki>

## The scored days

Each round's scored day is not distributed as a CSV. It is contained in the submission log
returned by the exchange, which holds the full order book for all 10,000 timestamps plus
every one of my fills.

`tools/decision_trace.py` reads those logs directly. To run a *backtest* on a scored day,
export it first:

```python
import prosperity_review as pr
log = pr.load_log("submissions/round1.log")
log.activities.to_csv("prices_round_1_day_1.csv", sep=";", index=False)
```

## Position limits

| Round | Limits |
|---|---|
| 1–2 | `ASH_COATED_OSMIUM` 80, `INTARIAN_PEPPER_ROOT` 80 |
| 3–4 | `HYDROGEL_PACK` 200, `VELVETFRUIT_EXTRACT` 200, each `VEV_*` 300 |
| 5 | 10 per product, all fifty |
