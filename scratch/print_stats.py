import json

with open("Output/whatif_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Total tickers in whatif_results.json:", len(data))
print("Tickers list:", list(data.keys()))

all_stats = []
for ticker, info in data.items():
    if "distribution" in info and "future_10" in info["distribution"]:
        dist = info["distribution"]
        future_10 = dist["future_10"]
        all_stats.append({
            "ticker": ticker,
            "price": info.get("price"),
            "mean_target": future_10.get("mean"),
            "mean_pct": future_10.get("mean")
        })

# Sort by mean_pct
all_stats.sort(key=lambda x: x["mean_pct"] if x["mean_pct"] is not None else -999, reverse=True)
print("\nTop 15 tickers by 10-day mean_pct:")
for item in all_stats[:15]:
    print(item)
