import json
import pandas as pd
from tinvest.vietstock_client import VietstockClient
import logging

logging.basicConfig(level=logging.INFO)

def check_url_status():
    client = VietstockClient()
    date_str = "2026-03-30" # Today
    
    total_count = 0
    print(f"--- Checking Vietstock URL Status ({date_str}) ---")
    
    any_exchange_200 = False
    
    for cat_id, cat_name in [(1, "HOSE"), (2, "HNX"), (3, "UPCOM")]:
        raw, is_limited = client.fetch_market_day(cat_id, date_str)
        count = len(raw)
        print(f"  + {cat_name}: {count} tickers. (Limited 200: {is_limited})")
        total_count += count
        if is_limited: any_exchange_200 = True
        
    print(f"\n=> TOTAL TICKERS: {total_count}")
    
    if total_count < 1200:
        print("!!! VERDICT: URL ERROR (Total < 1200). Need fresh cURL. !!!")
    elif any_exchange_200:
        print("!!! VERDICT: URL RESTRICTED (One exchange returned exactly 200). Recommended refresh. !!!")
    else:
        print("=> VERDICT: URL is WORKING FINE.")

if __name__ == "__main__":
    check_url_status()
