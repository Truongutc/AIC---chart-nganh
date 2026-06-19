from tinvest.storage_manager import StorageManager
from tinvest.market_engine import analyze_market_index
import pandas as pd

sm = StorageManager()
df = sm.load_ticker_data("VNINDEX")
if df is not None:
    # Find index for March 27th
    df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
    idx_27 = df[df['DateStr'] == '2026-03-27'].index
    if not idx_27.empty:
        idx = idx_27[0]
        # Look at data around 27th
        sub_df = df.iloc[max(0, idx-10):idx+5].copy()
        
        # Calculate moving averages for display
        sub_df['AvgVol20'] = df['Volume'].rolling(20).mean().shift(1) # Avg of 20 days before current
        
        print("Data around 2026-03-27:")
        cols = ['DateStr', 'Close', 'Open', 'Low', 'High', 'Volume', 'AvgVol20']
        print(sub_df[cols])
        
        # Check pct_change and volume condition for Mar 27
        c = sub_df.loc[idx, 'Close']
        pc = df.loc[idx-1, 'Close']
        v = sub_df.loc[idx, 'Volume']
        pv = df.loc[idx-1, 'Volume']
        avg_v = sub_df.loc[idx, 'AvgVol20']
        
        pct = (c - pc) / pc
        print(f"\nCondition Check for 2026-03-27:")
        print(f"Price Change: {pct*100:.2f}% (Required > 1.20%)")
        print(f"Volume: {v:,.0f}")
        print(f"Prev Volume: {pv:,.0f} (Required v > pv: {v > pv})")
        print(f"Avg 20 Vol: {avg_v:,.0f} (Required v > avg_v: {v > avg_v})")
        
        # Now run a debug version of the loop to see RA count
        # I'll just run analyze_market_index but maybe print steps?
        # Let's just run it and see the final result for that day
        res = analyze_market_index(df.iloc[:idx+1])
        print("\nAnalysis Result for 2026-03-27:")
        for k, v in res.items():
             if k != 'distribution_dates':
                print(f"{k}: {v}")
    else:
        print("Date 2026-03-27 not found in data.")
else:
    print("VNINDEX data not found.")
