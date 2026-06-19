import os
import json
import pandas as pd
import numpy as np

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
        if len(df) < 60:
            continue
            
        price = float(df['Close'].iloc[-1])
        log_returns = np.log(df['Close'] / df['Close'].shift(1)).dropna().values
        if len(log_returns) < 20:
            continue
            
        # Vectorized Monte Carlo Simulation
        rng = np.random.default_rng(42)
        n_sim = 1000
        horizon = 20
        
        # Sample log returns for all simulations and all days at once
        sampled = rng.choice(log_returns, size=(n_sim, horizon), replace=True)
        # Cumulative sum along the columns (days) for each path
        cum_sampled = np.cumsum(sampled, axis=1)
        # Price paths
        paths = price * np.exp(cum_sampled)
        
        # Day 20 price at index 19
        prices_20d = paths[:, 19]
        
        # Calculate expected returns
        pct_changes = (prices_20d - price) / price * 100
        mean_pct = round(float(np.mean(pct_changes)), 2)
        mean_target = round(float(np.mean(prices_20d)), 2)
        pct_above = round(float(np.mean(prices_20d > price) * 100), 1)
        
        if mean_pct > 5.0:
            matching_stocks.append({
                "ticker": ticker,
                "current_price": price,
                "mean_target": mean_target,
                "mean_pct": mean_pct,
                "pct_above": pct_above
            })
    except Exception as e:
        print(f"Error processing {ticker}: {e}")

# Sort by highest expected return
matching_stocks.sort(key=lambda x: x["mean_pct"], reverse=True)

print(f"\nFound {len(matching_stocks)} stocks with 20-day Expected Value (VE) > 5% above current price:\n")
for item in matching_stocks:
    print(f"Ticker: {item['ticker']} | Price: {item['current_price']:.2f} | 20d EV: {item['mean_target']:.2f} (+{item['mean_pct']:.2f}%) | Prob Up: {item['pct_above']}%")
