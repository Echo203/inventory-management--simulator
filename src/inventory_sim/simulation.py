"""
simulation.py
-------------
The core engine: runs a day-by-day simulation of one SKU under one policy
across a full demand history, tracking stock levels, orders, stockouts,
and costs. This is what turns static formulas (EOQ, ROP) into an actual
test of how a policy performs against real (simulated) demand variability.

Mechanics per day:
  1. Receive any shipment whose lead time has elapsed today
  2. Demand arrives; fulfill from on-hand stock (fill what you can)
  3. If demand exceeds stock -> record a stockout (lost/backordered units)
  4. Policy checks inventory position (on-hand + on-order) and may place
     a new order, which will arrive after the SKU's lead time
  5. Sum holding cost on end-of-day on-hand stock
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SimulationResult:
    sku_id: str
    policy_name: str
    daily_log: pd.DataFrame
    total_demand: int
    total_units_short: int
    stockout_days: int
    num_orders: int
    holding_cost: float
    ordering_cost_total: float
    stockout_cost: float

    @property
    def service_level(self) -> float:
        """Fill rate: % of demand units satisfied directly from stock."""
        fulfilled = self.total_demand - self.total_units_short
        # Make sure we don't divide by 0
        return 100 * fulfilled / self.total_demand if self.total_demand else 100.0

    @property
    def total_cost(self) -> float:
        return self.holding_cost + self.ordering_cost_total + self.stockout_cost

    @property
    # How many times do we go over our stock
    def inventory_turns(self) -> float:
        avg_on_hand = self.daily_log["on_hand"].mean()
        return self.total_demand / avg_on_hand if avg_on_hand > 0 else 0.0


# When reading this remember:
# This function runs for ONE sku and ONE policy at the time
def run_simulation(
    sku_row, demand_series: np.ndarray, policy, starting_stock=None
) -> SimulationResult:
    # Sku_row - data about sku
    # Demand series - everyday of demand as a list
    # Policy - single policy class object

    # Get all the data we need, for easier access
    days = len(demand_series)
    lead_time = int(sku_row["lead_time_days"])
    unit_cost = sku_row["unit_cost"]
    # Get holding cost per day (easier math later)
    daily_holding_cost_rate = sku_row["holding_cost_rate"] / 365
    ordering_cost = sku_row["ordering_cost"]
    stockout_penalty = sku_row["stockout_penalty"]

    # If we dont provide starting inventory levels
    # Order is 1.5 * lead time * mean avg of demand
    on_hand = (
        starting_stock
        if starting_stock is not None
        else demand_series.mean() * lead_time * 1.5
    )

    # Tracker of orders coming in
    pending_orders = {}  # arrival_day -> quantity

    # Build a table with python
    # We will be adding a row (one value for each column) for each day in sim
    # to create a log book in a form of a table
    log = {
        "day": [],
        "on_hand": [],
        "demand": [],
        "shipped": [],
        "short": [],
        "order_placed": [],
        "on_order": [],
    }

    # All stats to collect through out the simulation
    total_short = 0  # ammount of items short
    stockout_days = 0
    num_orders = 0
    holding_cost_total = 0.0
    ordering_cost_total = 0.0

    # Actuall simulation
    # We will go thorugh every day in the timeline we provided

    for day in range(days):
        # 1. receive shipments
        # we check if there's shipment coming in for current day
        # if so we add the ammount of items coming to our stock
        if day in pending_orders:
            on_hand += pending_orders.pop(day)

        # 2. demand arrives, fulfill what we can
        demand_today = demand_series[day]
        # Check if the demand doesn't exceed our current stock
        # if so we only ship what we have
        shipped = min(on_hand, demand_today)
        on_hand -= shipped

        # Difference between demand for today and ammount we shipped
        short = demand_today - shipped

        # If the difference is positive we went out of stock
        if short > 0:
            total_short += short
            stockout_days += 1

        # 3. policy decision (inventory position = on-hand + on-order)
        # Calculate inventory on-site + shipments coming in
        on_order_qty = sum(pending_orders.values())
        inventory_position = on_hand + on_order_qty
        # .decide_order return a number
        # 0 means no order
        # Anything above is an ammount to place an order for
        order_qty = policy.decide_order(inventory_position, day)

        order_placed = 0
        if order_qty > 0:
            arrival_day = day + lead_time
            # Sum delivery coming in if there's another one scheduled for that day
            # If not just add the record
            pending_orders[arrival_day] = pending_orders.get(arrival_day, 0) + order_qty
            ordering_cost_total += ordering_cost
            num_orders += 1
            order_placed = order_qty

        # 4. holding cost on end-of-day stock
        #    calculated via daily rate of holding, times unit price
        holding_cost_total += on_hand * unit_cost * daily_holding_cost_rate

        # Log everything that happened on this day
        log["day"].append(day)
        log["on_hand"].append(on_hand)
        log["demand"].append(demand_today)
        log["shipped"].append(shipped)
        log["short"].append(short)
        log["order_placed"].append(order_placed)
        log["on_order"].append(sum(pending_orders.values()))

    daily_log = pd.DataFrame(log)
    stockout_cost = total_short * stockout_penalty

    # Wrap everything up into SimulationResult class object
    return SimulationResult(
        sku_id=sku_row["sku_id"],
        policy_name=policy.name,
        daily_log=daily_log,
        total_demand=int(demand_series.sum()),
        total_units_short=int(total_short),
        stockout_days=stockout_days,
        num_orders=num_orders,
        holding_cost=holding_cost_total,
        ordering_cost_total=ordering_cost_total,
        stockout_cost=stockout_cost,
    )


def summarize_results(results: list) -> pd.DataFrame:
    """Flatten a list of SimulationResult into a comparison DataFrame."""
    # All SKUs with all policies
    rows = []
    for r in results:
        rows.append(
            {
                "sku_id": r.sku_id,
                "policy": r.policy_name,
                "total_demand": r.total_demand,
                "units_short": r.total_units_short,
                "service_level_pct": round(r.service_level, 2),
                "stockout_days": r.stockout_days,
                "num_orders": r.num_orders,
                "holding_cost": round(r.holding_cost, 2),
                "ordering_cost": round(r.ordering_cost_total, 2),
                "stockout_cost": round(r.stockout_cost, 2),
                "total_cost": round(r.total_cost, 2),
                "inventory_turns": round(r.inventory_turns, 2),
            }
        )
    return pd.DataFrame(rows)
