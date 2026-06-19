from tinvest.storage_manager import StorageManager
from tinvest.market_engine import analyze_market_index
import pandas as pd
import sys

# Set encoding for Vietnamese
sys.stdout.reconfigure(encoding='utf-8')

sm = StorageManager()
df = sm.load_ticker_data("VNINDEX")

def trace_logic(df):
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

    print(f"{'Date':<12} | {'C':<8} | {'RA':<2} | {'FTD':<5} | {'Dec%':<6} | {'C>L(RA)':<7} | {'RA1_Cond'}")
    print("-" * 80)

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

        # LOGIC REPLICATION
        ra1_hit = False
        if ra_day == 0 and decline_triggered_10:
             candle_body_upper = (c - l) / tr > 0.5 and c > (h + l) / 2
             is_positive_day = pct_change > 0
             if candle_body_upper or is_positive_day:
                 ra_day = 1
                 ra_low = l
                 ra1_hit = True

        elif ra_day > 0 and not ftd_active:
             if c < ra_low:
                 ra_day = 0
                 ra_low = float('inf')
             else:
                 ra_day += 1
                 if ra_day >= 4 and pct_change > 0.012 and v > pv:
                     ftd_active = True

        date_str = df['Date'].iloc[i].strftime("%Y-%m-%d")
        if "2026-03" in date_str:
            c_gt_low = (c > ra_low) if ra_day > 0 else "-"
            ra1_info = "HIT" if ra1_hit else "-"
            print(f"{date_str:<12} | {c:<8.2f} | {ra_day:<2} | {str(ftd_active):<5} | {decline_pct*100:<6.2f} | {str(c_gt_low):<7} | {ra1_info}")

trace_logic(df)
