import pandas as pd
import json
from pathlib import Path

pq_path = Path("data_storage/prices/HPG.parquet")
json_path = Path("Output/history/HPG.json")

if pq_path.exists() and json_path.exists():
    df_pq = pd.read_parquet(pq_path)
    df_pq['Date'] = pd.to_datetime(df_pq['Date']).dt.strftime('%Y-%m-%d')
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    dates_js = data['dates']
    opens_js = data['opens']
    closes_js = data['closes']
    volumes_js = data['volumes']
    
    # We want to find the alignment. Let's look at the last 20 elements of the JSON
    print("=== Last 20 Elements of JSON vs Parquet ===")
    for i in range(len(dates_js) - 20, len(dates_js)):
        js_date = dates_js[i]
        js_open = opens_js[i]
        js_close = closes_js[i]
        js_vol = volumes_js[i]
        
        # Find matches in parquet where Open/Close ratio is close to 1.0 or 0.909
        pq_row = df_pq[df_pq['Date'] == js_date]
        if not pq_row.empty:
            pq_open = pq_row['Open'].values[0]
            pq_close = pq_row['Close'].values[0]
            pq_vol = pq_row['Volume'].values[0]
            ratio_open = js_open / pq_open if pq_open > 0 else 0
            ratio_close = js_close / pq_close if pq_close > 0 else 0
            print(f"Index {i} | Date {js_date} | JS [O:{js_open:.2f}, C:{js_close:.2f}, V:{js_vol}] | PQ [O:{pq_open:.2f}, C:{pq_close:.2f}, V:{pq_vol}] | Ratio [O:{ratio_open:.4f}, C:{ratio_close:.4f}]")
        else:
            # Let's search if this JS Open/Close exists on another date in parquet
            matched_date = "None"
            for _, row in df_pq.iterrows():
                # check if ratio is close to 1.0
                if abs(js_open - row['Open']) < 0.05 and abs(js_close - row['Close']) < 0.05:
                    matched_date = row['Date']
                    break
            print(f"Index {i} | Date {js_date} | JS [O:{js_open:.2f}, C:{js_close:.2f}, V:{js_vol}] | PQ: None (Matches PQ date: {matched_date})")

else:
    print("Files not found")
