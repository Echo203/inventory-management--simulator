"""
data_generator.py
------------------
Generates a realistic synthetic multi-SKU demand dataset and SKU master
data (cost, lead time, etc.) for the inventory simulation engine.

Why synthetic data is designed this way:
Real SKU portfolios are never uniform. A retailer or distributor typically
has a mix of:
  - "runner" SKUs: high volume, low variability, steady demand
  - "seasonal" SKUs: demand spikes at predictable times of year
  - "erratic" SKUs: low volume, high variability, hard to forecast
This mix is what makes inventory policy selection an actual decision
problem rather than a trivial formula -- different SKUs need different
policies. The generator below builds a portfolio with this realistic mix
so the simulation results (which policy wins for which SKU type) reflect
real-world tradeoffs.
"""

import numpy as np
import pandas as pd


def generate_sku_master(n_skus: int = 30, seed: int = 42) -> pd.DataFrame:
    """Create SKU-level attributes: cost, lead time, demand profile type."""

    # Get our generator with provided seed
    rng = np.random.default_rng(seed)

    # Random choice with odds for behaviour of demand
    # We will change data based on profile later
    # Runner - High demand, steady sales
    # Seasonal - Predictible spikes in demand, based on time of the year
    # Erratic - Random spikes in volume through out the year
    profiles = rng.choice(
        ["runner", "seasonal", "erratic"],
        size=n_skus,
        p=[0.45, 0.25, 0.30],
    )

    unit_cost = rng.uniform(5, 200, n_skus).round(2)  # Cost per unit
    lead_time_days = rng.integers(3, 21, n_skus)  # supplier lead time
    holding_cost_rate = rng.uniform(0.15, 0.30, n_skus)  # annual % of unit cost
    ordering_cost = rng.uniform(20, 120, n_skus).round(2)  # cost per PO placed
    # Lost value [$] per unit missing
    # 50% - 150% of unit cost
    stockout_penalty = (unit_cost * rng.uniform(0.5, 1.5, n_skus)).round(2)

    # Demand generation
    # Runner - Steady Demand - 40-120 Units / Day (uniform distribiution)
    # Seasonal - Predictible rises in demand - 20-80 Units / Day (uniform distribiution)
    # Erratic - Random rises in demand - 3-20 Units / Day (uniform distribiution)
    base_demand = np.where(
        profiles == "runner",
        rng.uniform(40, 120, n_skus),
        np.where(
            profiles == "seasonal",
            rng.uniform(20, 80, n_skus),
            rng.uniform(3, 20, n_skus),
        ),
    )

    # CV - Coefficient of variation: std / mean
    # ^ this is how we would calculate in real world
    #   for generation purposes, we will randomly generate it based on previously
    #   generated profile (The more erratic behaviour the higher the CV)
    demand_cv = np.where(
        profiles == "runner",
        rng.uniform(0.15, 0.30, n_skus),
        np.where(
            profiles == "seasonal",
            rng.uniform(0.25, 0.45, n_skus),
            rng.uniform(0.6, 1.2, n_skus),
        ),
    )

    sku_ids = [f"SKU-{i + 1:03d}" for i in range(n_skus)]

    return pd.DataFrame(
        {
            "sku_id": sku_ids,
            "profile": profiles,
            "unit_cost": unit_cost,
            "lead_time_days": lead_time_days,
            "holding_cost_rate": holding_cost_rate,
            "ordering_cost": ordering_cost,
            "stockout_penalty": stockout_penalty,
            "base_demand": base_demand,
            "demand_cv": demand_cv,
        }
    )


def generate_demand_series(
    sku_row: pd.Series, days: int = 365, seed: int = 0
) -> np.ndarray:
    """
    Generate a daily demand series for one SKU using a negative-binomial-like
    process (via gamma-Poisson) so demand is always a non-negative integer
    with realistic overdispersion, plus seasonality for 'seasonal' SKUs.
    """
    # Generating day by day values

    # We are operating on a single row of data here
    # Get the rng generator
    # Then mean avg if demand
    # Then Variation coefficient
    # Then calculate standard deviation (reverse the CV)
    rng = np.random.default_rng(seed)
    mean = sku_row["base_demand"]
    cv = sku_row["demand_cv"]
    std = mean * cv

    # Gamma-Poisson mixture gives overdispersed count data (more realistic
    # than pure Poisson, which underestimates real-world demand variability)
    if std > 0:
        gamma_shape = (mean / std) ** 2
        gamma_scale = (std**2) / mean
        lam = rng.gamma(shape=gamma_shape, scale=gamma_scale, size=days)
    else:
        lam = np.full(days, mean)

    if sku_row["profile"] == "seasonal":
        t = np.arange(days)
        # one seasonal cycle per year + a mild upward pre-peak ramp
        seasonal_mult = 1 + 0.6 * np.sin(
            2 * np.pi * t / 365 - np.pi / 2
        ) ** 2 * np.where(np.sin(2 * np.pi * t / 365) > 0, 1, 0.3)
        lam = lam * seasonal_mult

    lam = np.clip(lam, 0.01, None)
    demand = rng.poisson(lam)
    return demand


def generate_full_dataset(n_skus: int = 30, days: int = 365, seed: int = 42):
    """Returns (sku_master_df, demand_df) where demand_df is long-format:
    columns = [date, sku_id, demand]"""

    # Call SKU generator
    sku_master = generate_sku_master(n_skus, seed)

    # Create a date range to generate behaviour of each item over the year
    dates = pd.date_range("2025-01-01", periods=days, freq="D")

    # This will be array of tuples (Date / SKU / Demand)
    # Each entry will be a day
    # It will be 365 entries of SKU-00X, then 365 entires of SKU-00X + 1
    records = []

    # Iterate over SKUs
    for i, row in sku_master.iterrows():
        # Generate 365 days of demand with variance
        series = generate_demand_series(row, days, seed + i.__hash__())

        for d, qty in zip(dates, series):
            # Bundle up Date / SKUs ID / Demand into a row
            # Append that row into an array of records
            records.append((d, row["sku_id"], int(qty)))

    # Move our records into DataFrame
    demand_df = pd.DataFrame(records, columns=["date", "sku_id", "demand"])

    # Return generated SKUs data and generated daily demand
    return sku_master, demand_df


if __name__ == "__main__":
    sku_master, demand_df = generate_full_dataset()
    print(sku_master.head())
    print(demand_df.head())
    print(f"\nGenerated {len(sku_master)} SKUs, {len(demand_df)} demand records")
