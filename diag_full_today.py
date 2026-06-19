import json
import pandas as pd
from tinvest.vietstock_client import VietstockClient
import logging

logging.basicConfig(level=logging.INFO)

def diag_full():
    client = VietstockClient()
    date_str = "2026-03-30"
    
    total_count = 0
    results = {}
    
    for cat_id, cat_name in [(1, "HOSE"), (2, "HNX"), (3, "UPCOM")]:
        print(f"\n--- Diag: Fetching {cat_name} ({date_str}) ---")
        raw, is_limited = client.fetch_market_day(cat_id, date_str)
        print(f"  Count: {len(raw)}")
        print(f"  Is Limited: {is_limited}")
        total_count += len(raw)
        results[cat_name] = {"count": len(raw), "is_limited": is_limited}
        
        if raw:
            df = client.format_to_df(raw)
            if 'MBB' in df['Ticker'].values:
                print(f"  MBB FOUND in {cat_name}!")
    
    print(f"\nTOTAL MÃ: {total_count}")
    if total_count <= 610:
        print("!!! TEST FAIL: Ngày này bị giới hạn (<= 610 mã) !!!")
    else:
        print("!!! TEST SUCCESS: Ngày này có dữ liệu đầy đủ (> 610 mã) !!!")

if __name__ == "__main__":
    diag_full()
