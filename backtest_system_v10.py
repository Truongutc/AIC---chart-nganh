import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl
import tinvest.valuation_engine as ve

def simulate_backtest_v10_fast(ticker, df_raw):
    df = dl.enrich_dataframe(df_raw)
    
    # --- VECTORIZED SIGNAL DETECTION (POINT-IN-TIME) ---
    c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
    ma10, ma20, ma50, ma100 = df['MA10'], df['MA20'], df['MA50'], df['MA100']
    ma200 = df.get('MA200', pd.Series(0, index=df.index))
    tenkan, kijun = df['Tenkan'], df['Kijun']
    kj65 = df.get('Kijun65', kijun)
    span_a, span_b = df['SpanA'], df['SpanB']
    cloud_top = df['CloudTop']
    cloud_bottom = df['CloudBottom']
    vol = df['Volume']
    avg_vol20 = df['AvgVolume20']
    ha_color = df['HA_Color']
    rsi = df['RSI']
    
    # 1. STRONG BUY Vectorized
    # PERFECT_MA: (ma10 > ma20 > ma50 > ma100) and (ma100 > ma200) and (low <= ma20*1.025 or low <= ma10*1.025) and close > ma20 and close > open
    perfect_ma = (ma10 > ma20) & (ma20 > ma50) & (ma50 > ma100) & (ma100 > ma200) & \
                 ((l <= ma20 * 1.025) | (l <= ma10 * 1.025)) & (c > ma20) & (c > o)
    # KUMO_BREAK: price_break_kumo and kumo_green and vol_break
    kumo_break = (c > cloud_top) & (c.shift(1) <= cloud_top.shift(1)) & (span_a >= span_b) & (vol > 1.2 * avg_vol20)
    strong_sig = perfect_ma | kumo_break
    
    # 2. ADD_2 Vectorized
    # Above cloud and kijun and (ha_reversal OR tk_cross)
    above_all = (c > cloud_top) & (tenkan > cloud_top) & (kijun > cloud_top)
    ha_reversal = (ha_color == 'Green') & (ha_color.shift(1) == 'Red') & (tenkan >= kijun)
    tk_cross = (ha_color == 'Green') & (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
    add2_sig = above_all & (ha_reversal | tk_cross)
    
    # 3. ADD_1 Vectorized
    # MA_PULLBACK: ma20 > ma50 and low <= ma20*1.025 and close >= ma20 and close > open
    ma_pullback = (ma20 > ma50) & (l <= ma20 * 1.025) & (c >= ma20) & (c > o)
    # MA_CROSS: 10/20 cross or 20/50 cross
    ma_cross = ((ma10 > ma20) & (ma10.shift(1) <= ma20.shift(1))) | ((ma20 > ma50) & (ma20.shift(1) <= ma50.shift(1)))
    # ICHI_BOUNCE: above cloud and (touch kijun or touch k65) and close > open
    ichi_bounce = (c > cloud_top) & ((l <= kijun * 1.015) | (l <= kj65 * 1.015)) & (c >= kijun) & (c > o)
    # ICHI_CROSS: below cloud and tk_cross_up
    ichi_cross = (c < cloud_bottom) & (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
    add1_sig = ma_pullback | ma_cross | ichi_bounce | ichi_cross
    
    # 4. EARLY Vectorized
    # (Cross Tenkan or MA10) and Higher Low and VSA Demand
    cross_early = ((c > tenkan) & (c.shift(1) <= tenkan.shift(1))) | ((c > ma10) & (c.shift(1) <= ma10.shift(1)))
    # VSA Demand: simple version
    vsa_demand = (c > o) & (c > c.shift(1)) & (vol > avg_vol20)
    # Note: Higher Low check is complex, let's use a simpler proxy for backtest speed
    # or just omit it to be slightly more aggressive
    early_sig = cross_early & vsa_demand & (rsi < 45)

    # Pre-calculate States (Vectorized)
    primary_states = np.where(ma20 > ma50, "UPTREND", "DOWNTREND")
    primary_states = np.where((ma20 < ma50) & (c > ma20), "RECOVERY", primary_states)
    
    trades = []
    active_trade = None
    
    for i in range(100, len(df)):
        curr = df.iloc[i]
        
        if active_trade is None:
            st_type = None
            if strong_sig.iloc[i]: st_type = "STRONG"
            elif add2_sig.iloc[i]: st_type = "ADD_2"
            elif add1_sig.iloc[i]: st_type = "ADD_1"
            elif early_sig.iloc[i]: st_type = "EARLY"
            
            if st_type:
                try:
                    # Still call valuation only on entry bar to get precise R2/SL
                    df_slice = df.iloc[max(0, i-100):i+1]
                    val = ve.evaluate_stock_valuation(ticker, df_slice, {"entry_type": st_type})
                    tp = val.get("tp1", curr["Close"]*1.10)
                    sl1 = val.get("cutloss_partial", curr["Close"]*0.97)
                    sl2 = val.get("cutloss_full", curr["Close"]*0.94)
                except:
                    tp, sl1, sl2 = curr["Close"]*1.10, curr["Close"]*0.97, curr["Close"]*0.94
                
                active_trade = {
                    "entry_type": st_type,
                    "e_date": curr["Date"], "e_price": curr["Close"],
                    "tp": tp, "sl1": sl1, "sl2": sl2,
                    "qty": 1.0, "exits": [], "days": 0
                }
                if active_trade["tp"] <= active_trade["e_price"]: active_trade["tp"] = active_trade["e_price"] * 1.07
                if active_trade["sl1"] >= active_trade["e_price"]: active_trade["sl1"] = active_trade["e_price"] * 0.97
                if active_trade["sl2"] >= active_trade["sl1"]: active_trade["sl2"] = active_trade["sl1"] * 0.97
        else:
            active_trade["days"] += 1
            if active_trade["days"] >= 3:
                # TP
                if curr["High"] >= active_trade["tp"]:
                    px = max(curr["Open"], active_trade["tp"])
                    active_trade["exits"].append({"px": px, "date": curr["Date"], "qty": active_trade["qty"], "reason": "TP_R2"})
                    trades.append(active_trade); active_trade = None; continue
                # SL1 (50%)
                if active_trade["qty"] > 0.5 and curr["Low"] <= active_trade["sl1"]:
                    px = min(curr["Open"], active_trade["sl1"])
                    active_trade["exits"].append({"px": px, "date": curr["Date"], "qty": 0.5, "reason": "SL_50%"})
                    active_trade["qty"] -= 0.5
                # SL2 (Full)
                if active_trade["qty"] > 0 and curr["Low"] <= active_trade["sl2"]:
                    px = min(curr["Open"], active_trade["sl2"])
                    active_trade["exits"].append({"px": px, "date": curr["Date"], "qty": active_trade["qty"], "reason": "SL_FULL"})
                    trades.append(active_trade); active_trade = None; continue
                # Emergency
                if ma20.iloc[i] < ma50.iloc[i] and c.iloc[i] < ma20.iloc[i]:
                    active_trade["exits"].append({"px": curr["Close"], "date": curr["Date"], "qty": active_trade["qty"], "reason": "STATE_EXIT"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_v10_fast():
    tickers = "mbb hpg acv acb tcb hcm vci msr msn php ree dhc imp kbc dig dxg ceo mwg gmd idc sip gex".upper().split()
    all_trades = []
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
        print(f"[{t}] Backtesting...", flush=True)
        trades = simulate_backtest_v10_fast(t, pd.read_parquet(p_path))
        all_trades.extend(trades)
        
        if trades:
            wins = len([tr for tr in trades if sum([(e["px"] - tr["e_price"])*e["qty"] for e in tr["exits"]]) > 0])
            pnl = sum([sum([(e["px"] - tr["e_price"])/tr["e_price"]*e["qty"] for e in tr["exits"]]) for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "WR%": round(wins/len(trades)*100,1), "Ret%": round(pnl*100,1)})
    
    print("\n" + "="*50)
    print("      BACKTEST RESULTS V10 FAST")
    print("="*50)
    print(pd.DataFrame(summary).to_string(index=False))
    
    print("\n" + "="*50)
    print("      SIGNAL PERFORMANCE")
    print("="*50)
    sig_stats = []
    for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
        st = [tr for tr in all_trades if tr["entry_type"] == sig]
        if st:
            sw = len([tr for tr in st if sum([(e["px"] - tr["e_price"])*e["qty"] for e in tr["exits"]]) > 0])
            s_ret = sum([sum([(e["px"] - tr["e_price"])/tr["e_price"]*e["qty"] for e in tr["exits"]]) for tr in st])
            sig_stats.append({"Signal": sig, "WinRate%": round(sw/len(st)*100,1), "AvgRet%": round(s_ret/len(st)*100,2)})
    print(pd.DataFrame(sig_stats).to_string(index=False))

if __name__ == "__main__":
    run_v10_fast()
