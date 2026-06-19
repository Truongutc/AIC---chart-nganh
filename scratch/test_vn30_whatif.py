import os
import json

tickers = ["FPT", "HPG", "TCB", "SSI", "MBB", "MSN", "MWG", "ACB"]
history_dir = "Output/history"

print("Updated What-If Scenario Tree data for major VN30 stocks:")
for t in tickers:
    json_path = os.path.join(history_dir, f"{t}.json")
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            wi = data.get("whatif")
            if wi and not wi.get("error"):
                dist = wi["distribution"]
                f10 = dist["future_10"]
                f20 = dist["future_20"]
                print(f"\nTicker: {t}")
                print(f"  Current Price: {wi['price']}")
                print(f"  10-day Analog Forecast:")
                print(f"    - EV % Change (Mean): {f10['mean']}%")
                print(f"    - Prob Up: {f10['pct_up']}% | Prob Down: {f10['pct_down']}%")
                print(f"  20-day Analog Forecast:")
                print(f"    - EV % Change (Mean): {f20['mean']}%")
                print(f"    - Prob Up: {f20['pct_up']}% | Prob Down: {f20['pct_down']}%")
            else:
                print(f"\nTicker: {t} - No What-If data or error: {wi.get('error') if wi else 'N/A'}")
