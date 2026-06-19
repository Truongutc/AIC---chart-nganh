import json

with open("Output/whatif_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

matching_tickers = []

for ticker, info in data.items():
    if not isinstance(info, dict) or "distribution" not in info or "price" not in info:
        continue
    
    price = info["price"]
    dist = info["distribution"]
    if not isinstance(dist, dict) or "future_10" not in dist:
        continue
        
    future_10 = dist["future_10"]
    if not isinstance(future_10, dict):
        continue
        
    mean_pct = future_10.get("mean", None)
    mean_target = price * (1 + mean_pct / 100) if mean_pct is not None else price
    
    # Calculate expected percent gain
    if price > 0:
        calc_pct = (mean_target - price) / price * 100
    else:
        calc_pct = 0
        
    # Check if either mean_pct > 5 or calculated pct > 5
    pct = mean_pct if mean_pct is not None else calc_pct
    
    if pct > 5.0:
        matching_tickers.append({
            "ticker": ticker,
            "current_price": price,
            "mean_target": mean_target,
            "expected_gain_pct": round(pct, 2)
        })

# Sort by highest expected gain
matching_tickers.sort(key=lambda x: x["expected_gain_pct"], reverse=True)

print(f"Total matching tickers: {len(matching_tickers)}")
print(json.dumps(matching_tickers, indent=4, ensure_ascii=False))
