from data_generator import generate_full_dataset
from policies import build_policies_for_sku
from simulation import run_simulation, summarize_results

sku_master, demand_df = generate_full_dataset(n_skus=5, days=365, seed=42)

results = []
for _, sku_row in sku_master.iterrows():
    series = (
        demand_df[demand_df.sku_id == sku_row.sku_id]
        .sort_values("date")["demand"]
        .values
    )
    mean = series.mean()
    std = series.std()
    policies = build_policies_for_sku(sku_row, mean, std)
    for pname, policy in policies.items():
        res = run_simulation(sku_row, series, policy)
        results.append(res)

summary = summarize_results(results)
print(summary.to_string(index=False))
print("\nAny negative stock?", any((r.daily_log.on_hand < 0).any() for r in results))
