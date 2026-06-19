import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def simulate_portfolio_backtest(ticker, df_raw):
    df = dl.enrich_dataframe(df_raw)
    ma10, ma20, ma50 = df['MA10'], df['MA20'], df['MA50']
    c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
    
    early_sig = (c > ma10) & (c.shift(1) <= ma10.shift(1)) & (df['Volume'] > df['AvgVolume20']) & (df['RSI'] < 45)
    add1_sig = (ma20 > ma50) & (l <= ma20 * 1.015) & (c > ma20) & (c > o)
    add2_sig = (ma10 > ma20) & (l <= ma10 * 1.01) & (c > ma10)
    h20 = h.rolling(20).max().shift(1)
    strong_sig = (c > h20) & (df['Volume'] > 1.2 * df['AvgVolume20']) & (c > o)

    results = []
    active_lots = []
    current_tp = 0
    current_sl = 0
    
    for i in range(100, len(df)):
        curr_row = df.iloc[i]
        curr_price = curr_row['Close']
        curr_date = curr_row['Date']
        atr = curr_row['ATR14']
        total_qty = sum(lot['qty_pct'] for lot in active_lots)
        
        if total_qty > 0:
            triggered = False
            exit_reason = None
            if curr_row['Low'] <= current_sl:
                triggered = True; exit_reason = "STOP_LOSS"
            elif curr_row['High'] >= current_tp:
                triggered = True; exit_reason = "TAKE_PROFIT"
            elif ma20.iloc[i] < ma50.iloc[i] and curr_price < ma20.iloc[i]:
                triggered = True; exit_reason = "DOWNTREND"
                
            if triggered:
                tradable_lots = [lot for lot in active_lots if lot['tradable_idx'] <= i]
                untradable_lots = [lot for lot in active_lots if lot['tradable_idx'] > i]
                if tradable_lots:
                    exit_price = min(curr_row['Open'], current_sl) if exit_reason == "STOP_LOSS" else (max(curr_row['Open'], current_tp) if exit_reason == "TAKE_PROFIT" else curr_price)
                    q_total = sum(l['qty_pct'] for l in tradable_lots)
                    avg_entry = sum(l['price'] * l['qty_pct'] for l in tradable_lots) / q_total
                    results.append({
                        "ticker": ticker, "exit_date": curr_date, "exit_price": exit_price,
                        "avg_entry": avg_entry, "qty_pct": q_total, "reason": exit_reason,
                        "types": [l['type'] for l in tradable_lots]
                    })
                    active_lots = untradable_lots
                    if not active_lots: current_tp = 0; current_sl = 0

        if total_qty < 1.0:
            signal_type = None
            if total_qty == 0:
                if early_sig.iloc[i]: signal_type = "EARLY"
                elif strong_sig.iloc[i]: signal_type = "STRONG"
            elif total_qty <= 0.2 and add1_sig.iloc[i]: signal_type = "ADD_1"
            elif total_qty <= 0.5 and add2_sig.iloc[i]: signal_type = "ADD_2"
            elif total_qty <= 0.7 and strong_sig.iloc[i]: signal_type = "STRONG"
                
            if signal_type:
                sizing = {"EARLY": 0.20, "ADD_1": 0.30, "ADD_2": 0.20, "STRONG": 0.30}
                qty_to_buy = sizing.get(signal_type, 0.1)
                if total_qty == 0:
                    current_tp = curr_price + 2.5 * atr
                    current_sl = curr_price - 1.5 * atr
                active_lots.append({
                    "price": curr_price, "qty_pct": qty_to_buy,
                    "tradable_idx": i + 3, "type": signal_type, "date": curr_date
                })

    return results

def calculate_stats(results):
    if not results: return None
    wins = [r for r in results if r['exit_price'] > r['avg_entry']]
    losses = [r for r in results if r['exit_price'] <= r['avg_entry']]
    total = len(results)
    wr = (len(wins)/total)*100 if total > 0 else 0
    aw = sum((r['exit_price']-r['avg_entry'])/r['avg_entry'] for r in wins)/len(wins)*100 if wins else 0
    al = sum((r['exit_price']-r['avg_entry'])/r['avg_entry'] for r in losses)/len(losses)*100 if losses else 0
    roi = sum(((r['exit_price']-r['avg_entry'])/r['avg_entry'])*r['qty_pct'] for r in results)*100
    return {"wr": wr, "aw": aw, "al": al, "roi": roi, "cnt": total}

def run_massive():
    tickers = ["MBB", "VPB", "SIP", "IDC", "HHV", "HDG", "PC1", "REE", "KBC", "DIG", "DXG", "VNM", "TPB", "PNJ", "CEO", "ACV", "MSN", "HVN", "VGI", "VSC"]
    all_res = []; t_stats = {}
    p_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    for t in tickers:
        p = p_dir / f"{t}.parquet"
        if not p.exists(): continue
        print(f"Testing {t}...", flush=True)
        r = simulate_portfolio_backtest(t, pd.read_parquet(p))
        all_res.extend(r); t_stats[t] = calculate_stats(r)
    
    print("\n" + "="*70)
    print("      MASSIVE BACKTEST REPORT (20 ADDITIONAL TICKERS)")
    print("="*70)
    gs = calculate_stats(all_res)
    print(f"\n[1. OVERALL SUMMARY]\nWR: {gs['wr']:.1f}% | Avg Win: {gs['aw']:.2f}% | Avg Loss: {gs['al']:.2f}% | Total ROI: {gs['roi']:.1f}%")
    
    print(f"\n[2. TICKER BREAKDOWN]\n{'Ticker':<10} {'Trades':<8} {'WR%':<8} {'AvgWin%':<10} {'AvgLoss%':<10} {'ROI%':<10}")
    for t, s in t_stats.items():
        if s: print(f"{t:<10} {s['cnt']:<8} {s['wr']:<8.1f} {s['aw']:<10.2f} {s['al']:<10.2f} {s['roi']:<10.1f}")

    print(f"\n[3. SIGNAL BREAKDOWN]\n{'Signal':<10} {'WR%':<8} {'AvgWin%':<10} {'AvgLoss%':<10} {'ROI Impact%':<10}")
    for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
        sr = [r for r in all_res if sig in r['types']]
        ss = calculate_stats(sr)
        if ss: print(f"{sig:<10} {ss['wr']:<8.1f} {ss['aw']:<10.2f} {ss['al']:<10.2f} {ss['roi']:<10.1f}")

if __name__ == "__main__":
    run_massive()
