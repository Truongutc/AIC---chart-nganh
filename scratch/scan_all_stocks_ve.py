import os
import sys
import json
import pandas as pd

# Add current directory to python path
sys.path.append(os.getcwd())

from tinvest.whatif_engine import run_whatif_analysis
from tinvest.data_loader import enrich_dataframe

# Load active tickers
with open("data_storage/active_tickers.json", "r", encoding="utf-8") as f:
    active_tickers = json.load(f)

print(f"Loaded {len(active_tickers)} active tickers.")

matching_stocks = []

for ticker in active_tickers:
    file_path = f"data_storage/prices/{ticker}.parquet"
    if not os.path.exists(file_path):
        continue
        
    try:
        df = pd.read_parquet(file_path)
        if len(df) < 100:
            continue
            
        df = enrich_dataframe(df)
        res = run_whatif_analysis(ticker, df)
        if "error" in res and res["error"]:
            continue
            
        dist = res.get("distribution", {})
        future_10 = dist.get("future_10", {})
        mean_pct = future_10.get("mean", 0)
        
        if mean_pct > 5.0:
            matching_stocks.append({
                "ticker": ticker,
                "current_price": res["price"],
                "mean_target": res["price"] * (1 + mean_pct / 100),
                "mean_pct": mean_pct,
                "prob_up": future_10.get("pct_up", 0)
            })
    except Exception as e:
        print(f"Error processing {ticker}: {e}")

# Sort by highest expected return
matching_stocks.sort(key=lambda x: x["mean_pct"], reverse=True)

print(f"\nFound {len(matching_stocks)} stocks with 20-day Expected Value (VE) > 5% above current price:\n")
for item in matching_stocks:
    print(f"Ticker: {item['ticker']} | Price: {item['current_price']:.2f} | 20d EV: {item['mean_target']:.2f} (+{item['mean_pct']:.2f}%) | Prob Up: {item['pct_above']}%")
