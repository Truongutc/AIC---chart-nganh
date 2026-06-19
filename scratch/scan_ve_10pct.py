import os
import json
import glob
import pandas as pd

def main():
    history_dir = "Output/history"
    prices_dir = "data_storage/prices"
    json_files = glob.glob(os.path.join(history_dir, "*.json"))
    
    results_with_vol = []
    results_no_vol = []
    
    print(f"Scanning {len(json_files)} history files for 20-day VE > current price by 10%...")
    
    for json_file in json_files:
        ticker = os.path.splitext(os.path.basename(json_file))[0].upper()
        if any(idx in ticker for idx in ["INDEX", "HNX30", "VN30"]):
            continue
            
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            wi = data.get("whatif")
            if not wi or wi.get("error"):
                continue
                
            dist = wi.get("distribution", {})
            f20 = dist.get("future_20", {})
            mean_20 = f20.get("mean")
            
            if mean_20 is None or mean_20 <= 10.0:
                continue
                
            # Get current price
            price = wi["price"]
            ev_20 = price * (1 + mean_20 / 100)
            
            # Read volume to see if Avg Vol 10D > 100k
            parquet_path = os.path.join(prices_dir, f"{ticker}.parquet")
            avg_vol_10 = 0
            if os.path.exists(parquet_path):
                df_price = pd.read_parquet(parquet_path, columns=["Volume"])
                if not df_price.empty and "Volume" in df_price.columns:
                    avg_vol_10 = float(df_price["Volume"].tail(10).mean())
                    
            item = {
                "ticker": ticker,
                "current_price": price,
                "mean_20": mean_20,
                "ev_20": round(ev_20, 2),
                "avg_vol_10": round(avg_vol_10, 0)
            }
            
            if avg_vol_10 > 100000:
                results_with_vol.append(item)
            else:
                results_no_vol.append(item)
                
        except Exception:
            continue
            
    # Sort by highest 20-day expected return
    results_with_vol.sort(key=lambda x: x["mean_20"], reverse=True)
    results_no_vol.sort(key=lambda x: x["mean_20"], reverse=True)
    
    print("\n--- STOCKS WITH 10D AVG VOLUME > 100K ---")
    for i, x in enumerate(results_with_vol):
        print(f"#{i+1}: {x['ticker']} | Price: {x['current_price']} | VE 20D: {x['ev_20']} (+{x['mean_20']:.2f}%) | Vol: {x['avg_vol_10']:,.0f}")
        
    print("\n--- STOCKS WITH LOW LIQUIDITY (< 100K VOLUME) ---")
    for i, x in enumerate(results_no_vol):
        print(f"#{i+1}: {x['ticker']} | Price: {x['current_price']} | VE 20D: {x['ev_20']} (+{x['mean_20']:.2f}%) | Vol: {x['avg_vol_10']:,.0f}")

if __name__ == "__main__":
    main()
