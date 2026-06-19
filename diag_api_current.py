import json
import pandas as pd
from datetime import datetime
from tinvest.vietstock_client import VietstockClient
import logging

logging.basicConfig(level=logging.INFO)

def diag_api():
    client = VietstockClient()
    date_str = "2026-03-30"
    cat_id = 1 # HOSE
    
    print(f"--- Diag: Fetching {date_str} for Cat {cat_id} ---")
    try:
        raw, is_limited = client.fetch_market_day(cat_id, date_str)
        print(f"Count: {len(raw)}")
        print(f"Is Limited: {is_limited}")
        
        if raw:
            df = client.format_to_df(raw)
            print(f"MBB in data? {'MBB' in df['Ticker'].values}")
            if 'MBB' in df['Ticker'].values:
                print(df[df['Ticker'] == 'MBB'])
            else:
                print("MBB NOT FOUND in the returned 200 tickers.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diag_api()
