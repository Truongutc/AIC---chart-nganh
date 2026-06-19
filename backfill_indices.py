import pandas as pd
from tinvest.vietstock_client import VietstockClient
from tinvest.storage_manager import StorageManager
from datetime import datetime

def backfill_indices():
    vs = VietstockClient()
    sm = StorageManager()
    
    dates = ["2026-03-26", "2026-03-27"]
    indices = [
        ("VNINDEX", 1, -19),
        ("HNX-INDEX", 2, -18)
    ]
    
    for d_str in dates:
        print(f"\n--- Processing Date: {d_str} ---")
        for ticker, cat_id, stock_id in indices:
            print(f"Fetching {ticker} for {d_str}...")
            try:
                raw = vs.fetch_index_day(ticker, cat_id, stock_id, d_str)
                if raw:
                    df = vs.format_to_df(raw)
                    if not df.empty:
                        print(f"Successfully fetched {ticker}. Rows: {len(df)}")
                        # Sync to storage
                        t_min = sm.sync_prices(ticker, df, source='API_BACKFILL')
                        print(f"Synced {ticker}. T_min: {t_min}")
                else:
                    print(f"No data returned for {ticker} on {d_str}")
            except Exception as e:
                print(f"Error processing {ticker} on {d_str}: {e}")

if __name__ == "__main__":
    backfill_indices()
