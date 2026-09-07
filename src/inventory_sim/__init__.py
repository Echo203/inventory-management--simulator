"""
app.py
------
Streamlit dashboard for the Multi-Policy Inventory Simulation Engine.

Run with:  streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from data_generator import generate_full_dataset  # type: ignore
from policies import build_policies_for_sku  # type: ignore
from simulation import run_simulation, summarize_results  # type: ignore

st.set_page_config(page_title="Inventory Management Simulator", layout="wide")

# -------------------------------- sidebar ----------------------------------
st.sidebar.title("Simulation Settings")
n_skus = st.sidebar.slider("Number of SKUs", 5, 200, 30, step=5)
days = st.sidebar.slider("Simulation horizon (days)", 90, 730, 365, step=30)
seed = st.sidebar.number_input("Random seed", value=42, step=1)
review_period = st.sidebar.slider("Periodic review interval (days)", 3, 30, 7)

run_button = st.sidebar.button("Run Simulation", type="primary")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**About this tool**\n\n"
    "Simulates daily demand for a pre-generated SKU portfolio (a mix of steady "
    "'runner', seasonal, and erratic items) and tests three inventory "
    "reorder policies against it: Fixed Reorder Point, Periodic Review, "
    "and Min-Max. Compares cost and service-level tradeoffs so you can see "
    "which policy fits which type of SKU."
)


# ------------------------------- caching ----------------------------------
@st.cache_data(show_spinner=False)
def load_data(n_skus, days, seed):
    return generate_full_dataset(n_skus=n_skus, days=days, seed=seed)


@st.cache_data(show_spinner=False)
def run_all_simulations(n_skus, days, seed, review_period):
    sku_master, demand_df = load_data(n_skus, days, seed)
    results = []
    for _, sku_row in sku_master.iterrows():
        series = (
            demand_df[demand_df.sku_id == sku_row.sku_id]
            .sort_values("date")["demand"]
            .values
        )
        mean, std = series.mean(), series.std()
        policies = build_policies_for_sku(
            sku_row, mean, std, review_period=review_period
        )
        for policy in policies.values():
            results.append(run_simulation(sku_row, series, policy))
    summary = summarize_results(results)
    return sku_master, demand_df, results, summary


# --------------------------------- main -----------------------------------
st.title("Multi-Policy Inventory Managment Simulation Engine")
st.caption(
    "A day-by-day simulation comparing three inventory reorder policies "
    "across a pre-generated SKU portfolio, to decide which policy minimizes "
    "cost while hitting a target service level."
)

# Control the state of the app
if "has_run" not in st.session_state:
    st.session_state.has_run = False
if run_button:
    st.session_state.has_run = True

if not st.session_state.has_run:
    # Stop rendering if there's no data generated
    st.info("Set your parameters in the sidebar and click **Run Simulation** to begin.")
    st.stop()

with st.spinner("Simulating..."):
    sku_master, demand_df, results, summary = run_all_simulations(
        n_skus, days, seed, review_period
    )

# ------------------------------- overview ---------------------------------
st.header("Portfolio Overview")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("SKUs simulated", n_skus)
col2.metric("Simulation days", days)
profile_counts = sku_master["profile"].value_counts()
col3.metric("Runner SKUs", int(profile_counts.get("runner", 0)))
col4.metric("Erratic SKUs", int(profile_counts.get("erratic", 0)))
col5.metric("Seasonal SKUs", int(profile_counts.get("seasonal", 0)))

# ------------------------------- policy comparison ------------------------
st.header("Policy Comparison — Portfolio Totals")

policy_totals = (
    summary.groupby("policy")
    .agg(
        total_cost=("total_cost", "sum"),
        holding_cost=("holding_cost", "sum"),
        ordering_cost=("ordering_cost", "sum"),
        stockout_cost=("stockout_cost", "sum"),
        avg_service_level=("service_level_pct", "mean"),
        total_orders=("num_orders", "sum"),
        inventory_turns=("inventory_turns", "mean"),
    )
    .reset_index()
)

c1, c2 = st.columns([1, 1])

with c1:
    fig_cost = px.bar(
        policy_totals.melt(
            id_vars=["policy"],
            value_vars=["holding_cost", "ordering_cost", "stockout_cost"],
            var_name="cost_type",
            value_name="cost",
        ),
        x="policy",
        y="cost",
        color="cost_type",
        title="Total Cost Breakdown by Policy",
        labels={"cost": "Cost ($)", "policy": "Policy", "cost_type": "Cost Type"},
    )
    st.plotly_chart(fig_cost, width="stretch")

with c2:
    fig_tradeoff = px.scatter(
        policy_totals,
        x="avg_service_level",
        y="total_cost",
        color="policy",
        size="total_orders",
        text="policy",
        title="Cost vs. Service Level Tradeoff",
        labels={
            "avg_service_level": "Avg Service Level (%)",
            "total_cost": "Total Cost ($)",
        },
    )
    fig_tradeoff.update_traces(textposition="top center")
    st.plotly_chart(fig_tradeoff, width="stretch")

st.dataframe(
    policy_totals.style.format(
        {
            "total_cost": "${:,.0f}",
            "holding_cost": "${:,.0f}",
            "ordering_cost": "${:,.0f}",
            "stockout_cost": "${:,.0f}",
            "inventory_turns": "{:,.0f}",
            "avg_service_level": "{:.1f}%",
        }
    ),
    use_container_width=True,
)

# --- auto-generated business impact summary ---
lowest_cost_policy = policy_totals.loc[policy_totals.total_cost.idxmin(), "policy"]
highest_service_policy = policy_totals.loc[
    policy_totals.avg_service_level.idxmax(), "policy"
]
highest_cost = policy_totals.total_cost.max()
lowest_cost = policy_totals.total_cost.min()
savings_pct = 100 * (highest_cost - lowest_cost) / highest_cost

st.success(
    f"**Business impact:** *{lowest_cost_policy}* delivers the lowest total cost "
    f"across the portfolio, **{savings_pct:.1f}% cheaper** than the most expensive "
    f"policy tested. *{highest_service_policy}* achieves the highest average service "
    f"level. The right choice depends on whether stockout risk or holding cost is "
    f"the bigger business concern for this portfolio."
)

# ------------------------------- best policy per SKU ---------------------
st.header("Recommended Policy by SKU")
st.caption("For each SKU, the policy with the lowest total simulated cost.")

best_per_sku = summary.loc[summary.groupby("sku_id")["total_cost"].idxmin()]
best_per_sku = best_per_sku.merge(sku_master[["sku_id", "profile"]], on="sku_id")

fig_best = px.histogram(
    best_per_sku,
    x="profile",
    color="policy",
    barmode="group",
    title="Which Policy Wins, by SKU Demand Profile",
    labels={"profile": "SKU Demand Profile", "count": "Number of SKUs"},
)
st.plotly_chart(fig_best, width="stretch")

st.dataframe(
    best_per_sku[["sku_id", "profile", "policy", "service_level_pct", "total_cost"]]
    .sort_values("total_cost", ascending=False)
    .style.format({"total_cost": "${:,.0f}", "service_level_pct": "{:.1f}%"}),
    width="stretch",
    height=300,
)

# ------------------------------- SKU drill-down -------------------------------
st.header("SKU Drill-Down")
selected_sku = st.selectbox("Select a SKU to inspect", sku_master["sku_id"].tolist())

sku_row = sku_master[sku_master.sku_id == selected_sku].iloc[0]
st.markdown(
    f"**Profile:** {sku_row['profile']} &nbsp;|&nbsp; "
    f"**Unit cost:** ${sku_row['unit_cost']:.2f} &nbsp;|&nbsp; "
    f"**Lead time:** {sku_row['lead_time_days']} days &nbsp;|&nbsp; "
    f"**Base daily demand:** {sku_row['base_demand']:.0f} units"
)

sku_results = [r for r in results if r.sku_id == selected_sku]

fig_stock = go.Figure()
for r in sku_results:
    fig_stock.add_trace(
        go.Scatter(
            x=r.daily_log["day"],
            y=r.daily_log["on_hand"],
            mode="lines",
            name=r.policy_name,
        )
    )
fig_stock.update_layout(
    title=f"On-Hand Inventory Over Time — {selected_sku}",
    xaxis_title="Day",
    yaxis_title="Units on Hand",
)
st.plotly_chart(fig_stock, width="stretch")

sku_summary = summary[summary.sku_id == selected_sku].sort_values("total_cost")
st.dataframe(
    sku_summary.style.format(
        {
            "holding_cost": "${:,.0f}",
            "ordering_cost": "${:,.0f}",
            "stockout_cost": "${:,.0f}",
            "total_cost": "${:,.0f}",
            "service_level_pct": "{:.1f}%",
        }
    ),
    width="stretch",
)

# ------------------------------- data --------------------------------------
with st.expander("View raw SKU master data"):
    st.dataframe(sku_master, use_container_width=True)

with st.expander("Download simulation summary as CSV"):
    csv = summary.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "simulation_summary.csv", "text/csv")
