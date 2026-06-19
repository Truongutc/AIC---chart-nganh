import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def run_refined_v2():
    # 1. Load Index States (T-1)
    idx_df = pd.read_csv("VNINDEX_states_T1.csv")
    idx_df['Date'] = pd.to_datetime(idx_df['Date'])
    
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB", "MBB", "VPB", "SIP", "IDC", "HHV", "HDG", "PC1", "REE", "KBC", "DIG", "DXG", "VNM", "TPB", "PNJ", "CEO", "ACV", "MSN", "HVN", "VGI", "VSC"]
    all_res = []; t_stats = {}
    p_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p = p_dir / f"{t}.parquet"
        if not p.exists(): continue
        
        df = dl.enrich_dataframe(pd.read_parquet(p))
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Merge Index States
        df = df.merge(idx_df[['Date', 'index_state_T1']], on='Date', how='left')
        
        # Indicators
        ma10, ma20, ma50 = df['MA10'], df['MA20'], df['MA50']
        c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
        
        # Signals
        early_sig = (c > ma10) & (c.shift(1) <= ma10.shift(1)) & (df['Volume'] > df['AvgVolume20']) & (df['RSI'] < 50)
        add1_sig = (ma20 > ma50) & (l <= ma20 * 1.015) & (c > ma20) & (c > o)
        add2_sig = (ma10 > ma20) & (l <= ma10 * 1.01) & (c > ma10)
        h20 = h.rolling(20).max().shift(1)
        strong_sig = (c > h20) & (df['Volume'] > 1.2 * df['AvgVolume20']) & (c > o)

        results = []
        active_lots = []
        current_tp = 0
        current_sl = 0
        
        for i in range(100, len(df)):
            curr = df.iloc[i]
            cur_price, cur_date, atr = curr['Close'], curr['Date'], curr['ATR14']
            idx_state_T1 = curr['index_state_T1']
            
            total_qty = sum(lot['qty_pct'] for lot in active_lots)
            
            # --- EXIT ---
            if total_qty > 0:
                triggered = False; exit_reason = None
                if curr['Low'] <= current_sl: triggered = True; exit_reason = "SL"
                elif curr['High'] >= current_tp: triggered = True; exit_reason = "TP"
                elif ma20.iloc[i] < ma50.iloc[i] and cur_price < ma20.iloc[i]: triggered = True; exit_reason = "DOWN"
                
                if triggered:
                    tradable = [l for l in active_lots if l['tradable_idx'] <= i]
                    if tradable:
                        exit_p = min(curr['Open'], current_sl) if exit_reason == "SL" else (max(curr['Open'], current_tp) if exit_reason == "TP" else cur_price)
                        q = sum(l['qty_pct'] for l in tradable)
                        avg_e = sum(l['price'] * l['qty_pct'] for l in tradable) / q
                        results.append({"ticker":t, "entry":avg_e, "exit":exit_p, "qty":q, "types":[l['type'] for l in tradable]})
                        active_lots = [l for l in active_lots if l['tradable_idx'] > i]
                        if not active_lots: current_tp = 0; current_sl = 0

            # --- ENTRY (With Filters) ---
            if total_qty < 1.0:
                sig_type = None
                # Condition 1: Distance to MA20 must be <= 10%
                if cur_price > ma20.iloc[i] * 1.10: continue
                
                if total_qty == 0:
                    if early_sig.iloc[i]: sig_type = "EARLY"
                    elif strong_sig.iloc[i]:
                        # Condition 2: Index Guard T-1
                        if idx_state_T1 != "DOWNTREND": sig_type = "STRONG"
                else:
                    # Scaling up: Only if Index is not in DOWNTREND
                    if idx_state_T1 != "DOWNTREND":
                        if total_qty <= 0.2 and add1_sig.iloc[i]: sig_type = "ADD_1"
                        elif total_qty <= 0.5 and add2_sig.iloc[i]: sig_type = "ADD_2"
                        elif total_qty <= 0.7 and strong_sig.iloc[i]: sig_type = "STRONG"

                if sig_type:
                    sizing = {"EARLY": 0.20, "ADD_1": 0.30, "ADD_2": 0.20, "STRONG": 0.30}
                    q_buy = sizing.get(sig_type, 0.1)
                    if total_qty == 0:
                        current_tp = cur_price + 2.5 * atr
                        current_sl = cur_price - 1.5 * atr
                    active_lots.append({"price":cur_price, "qty_pct":q_buy, "tradable_idx":i+3, "type":sig_type})

        t_stats[t] = calculate_stats_basic(results)
        all_res.extend(results)
    
    # Report
    print_report(all_res, t_stats)

def calculate_stats_basic(res):
    if not res: return None
    wins = [r for r in res if r['exit'] > r['entry']]
    wr = len(wins)/len(res)*100
    avg_win = sum((r['exit']-r['entry'])/r['entry'] for r in wins)/len(wins)*100 if wins else 0
    avg_loss = sum((r['exit']-r['entry'])/r['entry'] for r in [r for r in res if r['exit']<=r['entry']])/ (len(res)-len(wins)) * 100 if len(res)>len(wins) else 0
    roi = sum(((r['exit']-r['entry'])/r['entry'])*r['qty'] for r in res)*100
    return {"wr": wr, "aw": avg_win, "al": avg_loss, "roi": roi, "cnt": len(res)}

def print_report(all_res, t_stats):
    print("\n" + "="*80)
    print("      PRECISION BACKTEST REPORT (T-1 INDEX GUARD + MA20 FILTER)")
    print("="*80)
    gs = calculate_stats_basic(all_res)
    print(f"\n[1. OVERALL] WR: {gs['wr']:.1f}% | Avg Win: {gs['aw']:.2f}% | Avg Loss: {gs['al']:.2f}% | ROI: {gs['roi']:.1f}%")
    print(f"\n[2. TICKER]\n{'Ticker':<10} {'Trades':<8} {'WR%':<8} {'AvgWin%':<10} {'AvgLoss%':<10} {'ROI%':<10}")
    for t, s in t_stats.items():
        if s: print(f"{t:<10} {s['cnt']:<8} {s['wr']:<8.1f} {s['aw']:<10.2f} {s['al']:<10.2f} {s['roi']:<10.1f}")

if __name__ == "__main__":
    run_refined_v2()
