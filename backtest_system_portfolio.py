import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def simulate_portfolio_backtest(ticker, df_raw):
    # 1. Enrichment
    df = dl.enrich_dataframe(df_raw)
    
    # 2. Vectorized Signal Detection (Highly efficient)
    ma10, ma20, ma50 = df['MA10'], df['MA20'], df['MA50']
    c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
    
    # Simple logic-based signals for backtest speed & consistency
    # EARLY: Cross MA10 + Vol + Low RSI
    early_sig = (c > ma10) & (c.shift(1) <= ma10.shift(1)) & (df['Volume'] > df['AvgVolume20']) & (df['RSI'] < 45)
    # ADD_1: Pullback to MA20 + Uptrend
    add1_sig = (ma20 > ma50) & (l <= ma20 * 1.015) & (c > ma20) & (c > o)
    # ADD_2: Retest of a previous swing high range (simplified as MA10 > MA20 bounce)
    add2_sig = (ma10 > ma20) & (l <= ma10 * 1.01) & (c > ma10) & (abs(c.shift(1)-ma10.shift(1))/ma10.shift(1) < 0.02)
    # STRONG: Breakout 20-day high with High Vol
    h20 = h.rolling(20).max().shift(1)
    strong_sig = (c > h20) & (df['Volume'] > 1.2 * df['AvgVolume20']) & (c > o)

    results = []
    
    # Active trade management
    active_lots = [] # List of {date, price, qty_pct, tradable_date_idx, type}
    current_tp = 0
    current_sl = 0
    
    # Loop through historical data
    for i in range(100, len(df)):
        curr_row = df.iloc[i]
        curr_price = curr_row['Close']
        curr_date = curr_row['Date']
        atr = curr_row['ATR14']
        
        total_qty = sum(lot['qty_pct'] for lot in active_lots)
        
        # --- 1. EXIT CHECK (SL/TP) ---
        if total_qty > 0:
            # Check for Sell Trigger
            triggered = False
            exit_reason = None
            if curr_row['Low'] <= current_sl:
                triggered = True
                exit_reason = "STOP_LOSS"
            elif curr_row['High'] >= current_tp:
                triggered = True
                exit_reason = "TAKE_PROFIT"
            # Emergency logic: Downtrend
            elif ma20.iloc[i] < ma50.iloc[i] and curr_price < ma20.iloc[i]:
                triggered = True
                exit_reason = "DOWNTREND"
                
            if triggered:
                # Lot-based settlement: Only sell if tradable_date_idx <= i
                tradable_lots = [lot for lot in active_lots if lot['tradable_idx'] <= i]
                untradable_lots = [lot for lot in active_lots if lot['tradable_idx'] > i]
                
                if tradable_lots:
                    # Determine Exit Price
                    exit_price = 0
                    if exit_reason == "STOP_LOSS":
                        exit_price = min(curr_row['Open'], current_sl) # Handle Gap Down
                    elif exit_reason == "TAKE_PROFIT":
                        exit_price = max(curr_row['Open'], current_tp) # Handle Gap Up
                    else:
                        exit_price = curr_price
                        
                    # Average entry of these lots
                    avg_entry = sum(l['price'] * l['qty_pct'] for l in tradable_lots) / sum(l['qty_pct'] for l in tradable_lots)
                    trade_cycle = {
                        "ticker": ticker,
                        "exit_date": curr_date,
                        "exit_price": exit_price,
                        "avg_entry": avg_entry,
                        "qty_pct": sum(l['qty_pct'] for l in tradable_lots),
                        "reason": exit_reason,
                        "types": list(set(l['type'] for l in tradable_lots))
                    }
                    results.append(trade_cycle)
                    
                    # Remove tradable entries from active
                    active_lots = untradable_lots
                    if not active_lots:
                        current_tp = 0
                        current_sl = 0

        # --- 2. ENTRY/ADDITION CHECK ---
        # Only add if current weight is not maxed out
        if total_qty < 1.0:
            signal_type = None
            # Prioritize Strong signals for filling, prioritize Early for first entry
            if total_qty == 0:
                if early_sig.iloc[i]: signal_type = "EARLY"
                elif strong_sig.iloc[i]: signal_type = "STRONG"
            elif total_qty <= 0.2:
                if add1_sig.iloc[i]: signal_type = "ADD_1"
            elif total_qty <= 0.5:
                if add2_sig.iloc[i]: signal_type = "ADD_2"
            elif total_qty <= 0.7:
                if strong_sig.iloc[i]: signal_type = "STRONG"
                
            if signal_type:
                # Sizing
                sizing = {"EARLY": 0.20, "ADD_1": 0.30, "ADD_2": 0.20, "STRONG": 0.30}
                qty_to_buy = sizing.get(signal_type, 0.1)
                
                # Update SL/TP logic based on first entry or current volatility
                if total_qty == 0:
                    current_tp = curr_price + 2.5 * atr
                    current_sl = curr_price - 1.5 * atr
                else:
                    # Move SL to breakeven or slightly higher if in profit
                    # In this simplified model, we keep original SL/TP based on start to be conservative
                    pass
                
                new_lot = {
                    "price": curr_price,
                    "qty_pct": qty_to_buy,
                    "tradable_idx": i + 3, # T+3 means tradable 3 days later
                    "type": signal_type,
                    "date": curr_date
                }
                active_lots.append(new_lot)

    return results

def calculate_stats(results):
    if not results: return None
    
    wins = [r for r in results if r['exit_price'] > r['avg_entry']]
    losses = [r for r in results if r['exit_price'] <= r['avg_entry']]
    
    total_trades = len(results)
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win_pct = sum((r['exit_price'] - r['avg_entry'])/r['avg_entry'] for r in wins) / len(wins) * 100 if wins else 0
    avg_loss_pct = sum((r['exit_price'] - r['avg_entry'])/r['avg_entry'] for r in losses) / len(losses) * 100 if losses else 0
    
    # Cumulative ROI (Simplified as sum of weighted returns)
    total_roi = sum(((r['exit_price'] - r['avg_entry'])/r['avg_entry']) * r['qty_pct'] for r in results) * 100
    
    return {
        "wr": win_rate,
        "avg_win": avg_win_pct,
        "avg_loss": avg_loss_pct,
        "roi": total_roi,
        "count": total_trades
    }

def run_portfolio_stats():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    all_results = []
    ticker_stats = {}
    
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"Analyzing {t}...", flush=True)
        res = simulate_portfolio_backtest(t, pd.read_parquet(p_path))
        all_results.extend(res)
        ticker_stats[t] = calculate_stats(res)
        
    print("\n" + "="*80)
    print("      ADVANCED PORTFOLIO BACKTEST REPORT (DYNAMIC WEIGHTS + T+3)")
    print("="*80)
    
    # 1. SUMMARY ALL
    gs = calculate_stats(all_results)
    print("\n[1. OVERALL PORTFOLIO SUMMARY]")
    print(f"| Win Rate % | Avg Win % | Avg Loss % | Total ROI % |")
    print(f"| :--- | :--- | :--- | :--- |")
    print(f"| {gs['wr']:.1f}% | {gs['avg_win']:.2f}% | {gs['avg_loss']:.2f}% | {gs['roi']:.1f}% |")
    
    # 2. BY TICKER
    print("\n[2. TICKER BREAKDOWN]")
    print(f"| Ticker | Trades | WR% | Avg Win % | Avg Loss % | ROI % |")
    print(f"| :--- | :--- | :--- | :--- | :--- | :--- |")
    for t, s in ticker_stats.items():
        if s:
            print(f"| {t} | {s['count']} | {s['wr']:.1f}% | {s['avg_win']:.2f}% | {s['avg_loss']:.2f}% | {s['roi']:.1f}% |")

    # 3. BY SIGNAL
    print("\n[3. SIGNAL TYPE BREAKDOWN]")
    print(f"| Signal | WR% | Avg Win % | Avg Loss % | ROI Impact % |")
    print(f"| :--- | :--- | :--- | :--- | :--- |")
    for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
        sig_results = [r for r in all_results if sig in r['types']]
        ss = calculate_stats(sig_results)
        if ss:
            print(f"| {sig:8} | {ss['wr']:.1f}% | {ss['avg_win']:.2f}% | {ss['avg_loss']:.2f}% | {ss['roi']:.1f}% |")

if __name__ == "__main__":
    run_portfolio_stats()
