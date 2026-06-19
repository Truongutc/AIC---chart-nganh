import os
import json
import pandas as pd
import glob

# Path to history folder and prices folder
history_dir = "Output/history"
prices_dir = "data_storage/prices"

json_files = glob.glob(os.path.join(history_dir, "*.json"))

matching_stocks = []

for json_file in json_files:
    ticker = os.path.splitext(os.path.basename(json_file))[0].upper()
    
    # Skip indices
    if any(idx in ticker for idx in ["INDEX", "HNX30", "VN30"]):
        continue
        
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if "whatif" not in data:
            continue
            
        wi = data["whatif"]
        if "distribution" not in wi or "price" not in wi:
            continue
            
        dist = wi["distribution"]
        if "future_10" not in dist or "future_20" not in dist:
            continue
            
        f10 = dist["future_10"]
        f20 = dist["future_20"]
        
        # We need mean percentage change
        if "mean" not in f10 or "mean" not in f20:
            continue
            
        mean_10 = f10["mean"]
        mean_20 = f20["mean"]
        price = wi["price"]
        
        # Condition 2: 20-day Analog EV > 10-day Analog EV
        # (Equivalent to 20-day mean % change > 10-day mean % change)
        if mean_20 <= mean_10:
            continue
            
        # Condition 3: 20-day Analog EV > current price by > 5%
        # (Equivalent to 20-day mean % change > 5.0)
        if mean_20 <= 5.0:
            continue
            
        # Condition 1: 10-day average volume > 100,000 shares
        # OPTIMIZATION: Only read the "Volume" column to be 10x faster
        parquet_path = os.path.join(prices_dir, f"{ticker}.parquet")
        if not os.path.exists(parquet_path):
            continue
            
        df_price = pd.read_parquet(parquet_path, columns=["Volume"])
        if df_price.empty or "Volume" not in df_price.columns:
            continue
            
        avg_vol_10 = float(df_price["Volume"].tail(10).mean())
        if avg_vol_10 <= 100000:
            continue
            
        # Calculate EV prices
        ev_10 = price * (1 + mean_10 / 100)
        ev_20 = price * (1 + mean_20 / 100)
        
        matching_stocks.append({
            "ticker": ticker,
            "current_price": price,
            "mean_10": mean_10,
            "mean_20": mean_20,
            "ev_10": round(ev_10, 2),
            "ev_20": round(ev_20, 2),
            "avg_vol_10": round(avg_vol_10, 0)
        })
        
    except Exception as e:
        continue

# Sort by highest 20-day expected return
matching_stocks.sort(key=lambda x: x["mean_20"], reverse=True)

print(f"Total matching stocks: {len(matching_stocks)}")
print(json.dumps(matching_stocks, indent=4, ensure_ascii=False))
