import json
import os
import glob

history_files = glob.glob("Output/history/*.json")
overlap_count = 0
for filepath in history_files[:50]: # Check first 50 files
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            d = json.load(f)
        except Exception:
            continue
        if 'dates' not in d or 'HK_BuySignal' not in d:
            continue
        ticker = d['ticker']
        dates = d['dates']
        hk_buy = d.get('HK_BuySignal', [])
        hk_buy_manh = d.get('HK_BuyManh', [])
        hk_sell = d.get('HK_SellSignal', [])
        hk_sell_manh = d.get('HK_SellManh', [])
        
        for i in range(len(dates)):
            is_buy = hk_buy[i] or hk_buy_manh[i]
            is_sell = hk_sell[i] or hk_sell_manh[i]
            if is_buy and is_sell:
                overlap_count += 1
                print(f"Overlap at {ticker} on {dates[i]}: Buy signal={hk_buy[i]}, Buy Manh={hk_buy_manh[i]}, Sell signal={hk_sell[i]}, Sell Manh={hk_sell_manh[i]}")

print("Total overlap count across first 50 files:", overlap_count)
