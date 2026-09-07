"""
policies.py
-----------
Three inventory reorder policies, implemented as classes so the simulation
engine can swap between them with identical interfaces. Each policy answers
one question every simulated day: "should we place an order today, and
for how much?"

1. Fixed Reorder Point (Q, R) - continuous review
   At or less than R order Q.
   Classic textbook EOQ-driven policy. Watch stock every day; the moment
   stock (on-hand + on-order) drops to or below R, order a fixed quantity Q.
   Q is derived from EOQ. Good for stable, high-volume "runner" SKUs.

2. Periodic Review (s, S)
   At or less than s, order S = target - s
   Only check stock on a fixed schedule (e.g. every 7 days) rather than
   continuously. If stock is below s, order up to S. Cheaper to administer
   (fewer checks/orders) but reacts slower to demand spikes -- realistic
   for suppliers who only accept orders on certain days, or teams that
   review inventory weekly rather than daily.

3. Min-Max
   At or less than Min order to Max
   Continuous review like (Q,R), but instead of a fixed order quantity,
   orders up to Max whenever stock falls below Min. This adapts order size
   to how far below Min the stock has fallen, which handles demand spikes
   better than a fixed Q -- often used for erratic, hard-to-forecast SKUs.
"""

import math
from dataclasses import dataclass


@dataclass
class PolicyParams:
    # Boilerplate for policy behaviour data
    """Computed policy parameters for one SKU, derived from its demand stats."""

    reorder_point: float
    order_qty: float
    review_period: int = 1
    min_level: float = math.inf
    max_level: float = -math.inf


def compute_eoq(annual_demand, ordering_cost, unit_cost, holding_cost_rate):
    """Standard Economic Order Quantity formula."""
    # Unit cost, times % of it's value that it cost to hold one unit per annum
    holding_cost_per_unit = unit_cost * holding_cost_rate
    if holding_cost_per_unit <= 0 or annual_demand <= 0:
        return 1
    eoq = math.sqrt((2 * annual_demand * ordering_cost) / holding_cost_per_unit)

    # At least 1, then round decimal points to nearest whole number
    return max(1, round(eoq))


def compute_safety_stock(demand_std_daily, lead_time_days, service_z=1.65):
    """
    Safety stock for a target service level (default z=1.65 ~ 95% cycle
    service level), scaled for lead-time demand uncertainty.
    """
    # Statistical Method for safety stock
    # Safety Stock = Z × σd × √L
    # L - Lead time in days
    # σd - Standard deviation of daily demand
    #      (how much does it does swing around the avrage)
    # Z - Service level
    #     (What % of times do we have our items when order comes in)
    #     90% service level = 1.28
    #     95% service level = 1.65
    #     99% service level = 2.33
    return service_z * demand_std_daily * math.sqrt(lead_time_days)


class BasePolicy:
    name = "base"

    def __init__(self, params: PolicyParams):
        self.params = params

    # Should review is assumed to be checked once per day.
    # For every day we go through a policy will run this function
    # to check if it should review stock in given day
    def should_review(self, day: int) -> bool:
        raise NotImplementedError

    def decide_order(self, inventory_level: float, day: int) -> float:
        """Return order quantity (0 if no order placed today)."""
        raise NotImplementedError


class FixedReorderPointPolicy(BasePolicy):
    """Continuous review (Q, R): order fixed Q whenever position <= R."""

    name = "Fixed Reorder Point (Q,R)"

    # We run this function once for every day in our timeline
    # And this policy is to be reviewed everyday
    def should_review(self, day: int) -> bool:
        return True  # checked every day

    def decide_order(self, inventory_level: float, day: int) -> float:
        # Inventory below or equal to R, order Q ammount of item
        if inventory_level <= self.params.reorder_point:
            return self.params.order_qty
        return 0


class PeriodicReviewPolicy(BasePolicy):
    """Periodic review (s, S): checked every N days, order up to S."""

    name = "Periodic Review (s,S)"

    def should_review(self, day: int) -> bool:
        return day % self.params.review_period == 0

    def decide_order(self, inventory_level: float, day: int) -> float:
        if not self.should_review(day):
            return 0
        s = self.params.reorder_point
        S = self.params.order_qty  # here order_qty field stores target level S
        if inventory_level < s:
            return max(0, S - inventory_level)
        return 0


class MinMaxPolicy(BasePolicy):
    """Continuous review Min-Max: order up to Max whenever below Min."""

    # This bad boy is a mix of the policies above
    # Checks everyday and orders a dynamic ammount
    # (so that we hit max lvl)

    name = "Min-Max"

    def should_review(self, day: int) -> bool:
        return True

    def decide_order(self, inventory_level: float, day: int) -> float:
        if inventory_level < self.params.min_level:
            return max(0, self.params.max_level - inventory_level)
        return 0


def build_policies_for_sku(
    sku_row, demand_mean_daily, demand_std_daily, review_period=7
):
    """
    Given a SKU's cost/lead-time attributes and demand statistics, compute
    parameters for all three policies and return ready-to-use policy objects.
    """
    # Defining policy behaviour based on annual data about item
    lead_time = sku_row["lead_time_days"]
    annual_demand = demand_mean_daily * 365

    safety_stock = compute_safety_stock(demand_std_daily, lead_time)
    lead_time_demand = demand_mean_daily * lead_time

    eoq = compute_eoq(
        annual_demand,
        sku_row["ordering_cost"],
        sku_row["unit_cost"],
        sku_row["holding_cost_rate"],
    )

    # --- Policy 1: Fixed Reorder Point ---
    # Classic Reorder point - safety stock + items to cover demand till next shipment
    rop = lead_time_demand + safety_stock
    p1 = FixedReorderPointPolicy(PolicyParams(reorder_point=rop, order_qty=eoq))

    # --- Policy 2: Periodic Review (s, S) ---
    # s covers safety stock + demand till next review +
    #   + lead time (items to cover demand till next shipment)
    review_period_demand = demand_mean_daily * review_period
    s = lead_time_demand + review_period_demand + safety_stock
    # order-up-to target (math is done inside of class' instance)
    S = s + eoq
    p2 = PeriodicReviewPolicy(
        PolicyParams(reorder_point=s, order_qty=S, review_period=review_period)
    )

    # --- Policy 3: Min-Max ---
    min_level = lead_time_demand + safety_stock
    max_level = min_level + eoq
    p3 = MinMaxPolicy(
        PolicyParams(
            reorder_point=min_level,
            order_qty=max_level,
            min_level=min_level,
            max_level=max_level,
        )
    )

    return {
        "Fixed Reorder Point (Q,R)": p1,
        "Periodic Review (s,S)": p2,
        "Min-Max": p3,
    }
