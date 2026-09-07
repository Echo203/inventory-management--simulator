# Multi-Policy Inventory Managment Simulation Engine

## The business problem

Every inventory planner has to answer the same question for every SKU:
**when do we reorder, and how much?** Get it wrong in one direction and you
tie up cash in excess stock and warehouse space. Get it wrong the other way
and you stock out, lose sales, and frustrate customers.

There's no single right answer — the best policy depends on how a SKU
behaves. A steady, high-volume "runner" product can be managed leanly with
tight reorder points. A spiky, unpredictable "erratic" product needs more
safety stock or a more responsive policy, or you'll stock out constantly.

This project builds a simulation engine that tests three real-world
inventory policies against a year of daily demand for a 30-SKU portfolio,
and measures which policy actually performs best — on cost **and** service
level — for each type of SKU. It's the same kind of analysis an inventory
or supply planning team would run before choosing a replenishment policy
for a product category.

## The three policies tested

| Policy | How it works | Best suited for |
|---|---|---|
| **Fixed Reorder Point (Q,R)** | Continuously watch stock; order a fixed quantity Q the moment stock hits reorder point R | Stable, high-volume SKUs |
| **Periodic Review (s,S)** | Only check stock on a schedule (e.g. weekly); order up to target level S if below s | Suppliers with fixed order windows, or teams reviewing inventory on a cadence |
| **Min-Max** | Continuous review; order up to Max whenever stock drops below Min, with order size scaling to the shortfall | Erratic, spiky-demand SKUs |

Reorder points, safety stock, and order quantities are calculated using
standard supply chain formulas (EOQ, lead-time demand, service-level-based
safety stock) — not arbitrary numbers.

## What the simulation tracks

For every SKU, under every policy, day by day:
- Stock on hand, on order, and units short
- Service level (fill rate)
- Holding cost, ordering cost, and stockout cost
- Inventory turns

## Data

Demand is synthetically generated to mirror a realistic SKU portfolio: a
mix of steady "runner" SKUs, seasonal SKUs, and erratic low-volume SKUs,
each with different cost, lead time, and demand variability — because a
real inventory analysis is only meaningful if the underlying demand mix
looks like a real business, not uniform random noise. Swap in real demand
history by replacing `data_generator.py`'s output with your own
`(date, sku_id, demand)` table — the rest of the pipeline is unchanged.

## Key finding (from a sample run)

Periodic Review tends to carry more safety stock and hits close to 100%
service level, at a higher holding cost. Fixed Reorder Point runs leaner
but takes on more stockout risk for erratic SKUs. Min-Max often lands
between the two — the dashboard's "Recommended Policy by SKU" view shows
exactly which policy wins for which SKU profile, which is the actual
decision this tool is meant to support.

## Project structure

```
inventory_sim/
├── data_generator.py   # synthetic SKU + demand data
├── policies.py         # 3 inventory policy classes + EOQ/safety-stock math
├── simulation.py       # day-by-day simulation engine + metrics
├── app.py              # Streamlit dashboard
├── test_run.py         # quick CLI smoke test (no dashboard needed)
└── requirements.txt
```

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Or run the simulation from the command line without the dashboard:

```bash
python test_run.py
```

## Possible extensions

- Plug in a real dataset (sales data from Kaggle)
- Add a forecasting layer so reorder points adapt to a rolling forecast instead of historical averages
- Add supplier lead-time variability (not just demand variability) to stress-test service levels
