from tinvest.storage_manager import StorageManager
from tinvest.market_engine import analyze_market_index
import pandas as pd

sm = StorageManager()
df = sm.load_ticker_data("VNINDEX")

def debug_ra_ftd(df):
    df = df.copy()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    hi26 = df['High'].rolling(26).max()
    lo26 = df['Low'].rolling(26).min()
    df['Kijun'] = (hi26 + lo26) / 2

    ra_day = 0
    ra_low = float('inf')
    ftd_active = False
    rolling_peak = float(df['Close'].iloc[0])
    decline_triggered_10 = False

    print(f"{'Date':<12} | {'Close':<8} | {'RA':<3} | {'FTD':<5} | {'Decline':<8} | {'V > PV':<6} | {'V > A20':<7}")
    print("-" * 75)

    for i in range(1, len(df)):
        c = float(df['Close'].iloc[i])
        pc = float(df['Close'].iloc[i-1])
        v = float(df['Volume'].iloc[i])
        pv = float(df['Volume'].iloc[i-1])
        h = float(df['High'].iloc[i])
        l = float(df['Low'].iloc[i])
        o = float(df['Open'].iloc[i])
        tr = h - l + 1e-10

        if c > rolling_peak:
            rolling_peak = c
            decline_triggered_10 = False
        
        decline_pct = (rolling_peak - c) / rolling_peak
        if decline_pct >= 0.10:
            decline_triggered_10 = True
        
        pct_change = (c - pc) / pc
        avg_vol_20 = float(df['Volume'].iloc[max(0,i-20):i].mean()) if i >= 20 else v

        # Logic from engine...
        if ftd_active:
             if l < ra_low or decline_pct >= 0.10:
                ftd_active = False
                ra_day = 0
                ra_low = float('inf')

        if ra_day > 0 and not ftd_active:
             if c < ra_low:
                 ra_day = 0
                 ra_low = float('inf')
             else:
                 ra_day += 1
                 if ra_day >= 4 and pct_change > 0.012 and v > pv and v > avg_vol_20:
                     ftd_active = True

        if ra_day == 0 and decline_triggered_10:
             candle_body_upper = (c - l) / tr > 0.5 and c > (h + l) / 2
             is_green_after_decline = pct_change > 0 and c >= o
             if candle_body_upper or is_green_after_decline:
                 ra_day = 1
                 ra_low = l

        date_str = df['Date'].iloc[i].strftime("%Y-%m-%d")
        if "2026-03" in date_str:
            print(f"{date_str:<12} | {c:<8.2f} | {ra_day:<3} | {str(ftd_active):<5} | {decline_pct*100:<7.2f}% | {str(v > pv):<6} | {str(v > avg_vol_20):<7}")

debug_ra_ftd(df)
