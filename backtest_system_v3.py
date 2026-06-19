import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from tinvest.data_loader import enrich_dataframe
from tinvest.advanced_entry import classify_entry
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.state_engine import evaluate_state_rules

def simulate_backtest(ticker, df_raw):
    # 1. Enrich data
    # We enrich the whole DF at once to have all indicators
    df = enrich_dataframe(df_raw)
    
    trades = []
    active_trade = None
    
    # Starting index for analysis (need enough data for indicators)
    start_idx = 100 
    
    for i in range(start_idx, len(df)):
        current_bar = df.iloc[i]
        
        # --- IF NO ACTIVE TRADE, LOOK FOR ENTRY ---
        if active_trade is None:
            # We must use analysis based ON data up to day i
            # To simulate "real time", we slice data up to i
            df_slice = df.iloc[:i+1]
            
            # Identify Entry Signal
            adv = classify_entry(df_slice)
            entry_type = adv.get("entry_type", "NONE")
            
            if entry_type in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                # Get Valuation (TP, SL, TS)
                val = evaluate_stock_valuation(ticker, df_slice, adv)
                
                # Allocation logic
                alloc_map = {
                    "EARLY": 0.20,
                    "ADD_1": 0.40,
                    "ADD_2": 0.60,
                    "STRONG": 0.85
                }
                
                active_trade = {
                    "ticker": ticker,
                    "entry_date": current_bar["Date"],
                    "entry_price": current_bar["Close"],
                    "entry_type": entry_type,
                    "tp1": val.get("s1_as_tp", val.get("r1", 0)), # Fallback to R1
                    "tp2": val.get("r2", 0),
                    "sl": val.get("cutloss_full", 0),
                    "ts": val.get("trailing_stop", 0),
                    "alloc": alloc_map.get(entry_type, 0.1),
                    "days_held": 0,
                    "partial_sold": False,
                    "entry_idx": i
                }
                
                # Fix TP1 if it's 0 or below entry
                if active_trade["tp1"] <= active_trade["entry_price"]:
                    active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["tp2"] <= active_trade["tp1"]:
                    active_trade["tp2"] = active_trade["tp1"] * 1.10
                if active_trade["sl"] >= active_trade["entry_price"]:
                    active_trade["sl"] = active_trade["entry_price"] * 0.95

        # --- IF ACTIVE TRADE, MONITOR FOR EXIT (strictly T+3) ---
        else:
            active_trade["days_held"] += 1
            
            # Only allow exit from T+3 onwards
            if active_trade["days_held"] >= 3:
                # 1. Check for GAP DOWN at Open on T+3
                if active_trade["days_held"] == 3:
                    if current_bar["Open"] < active_trade["sl"]:
                        # Gap down exit
                        exit_price = current_bar["Open"]
                        active_trade["exit_price"] = exit_price
                        active_trade["exit_date"] = current_bar["Date"]
                        active_trade["exit_reason"] = "GAP_DOWN_SL"
                        trades.append(active_trade)
                        active_trade = None
                        continue

                # 2. Check for SL
                if current_bar["Low"] <= active_trade["sl"]:
                    exit_price = active_trade["sl"]
                    active_trade["exit_price"] = exit_price
                    active_trade["exit_date"] = current_bar["Date"]
                    active_trade["exit_reason"] = "STOP_LOSS"
                    trades.append(active_trade)
                    active_trade = None
                    continue

                # 3. Check for Trailing Stop
                if current_bar["Low"] <= active_trade["ts"] and active_trade["ts"] > 0:
                    exit_price = active_trade["ts"]
                    active_trade["exit_price"] = exit_price
                    active_trade["exit_date"] = current_bar["Date"]
                    active_trade["exit_reason"] = "TRAILING_STOP"
                    trades.append(active_trade)
                    active_trade = None
                    continue

                # 4. Check for TP1 (Partial 50%)
                if not active_trade["partial_sold"] and current_bar["High"] >= active_trade["tp1"]:
                    active_trade["partial_sold"] = True
                    # In this simple model, we just record it and continue
                    # To calculate profit correctly, we might need a more complex tracking
                    # but for now let's assume we hold for TP2 or TS
                    pass

                # 5. Check for TP2
                if current_bar["High"] >= active_trade["tp2"]:
                    exit_price = active_trade["tp2"]
                    active_trade["exit_price"] = exit_price
                    active_trade["exit_date"] = current_bar["Date"]
                    active_trade["exit_reason"] = "TAKE_PROFIT_FULL"
                    trades.append(active_trade)
                    active_trade = None
                    continue

                # 6. Check for State Emergency (DOWNTREND)
                df_slice = df.iloc[:i+1]
                st = evaluate_state_rules(df_slice)
                if st.get("primary") in ["DOWNTREND_START", "DOWNTREND"] or st.get("signal") == "EXIT_FAST":
                    exit_price = current_bar["Close"]
                    active_trade["exit_price"] = exit_price
                    active_trade["exit_date"] = current_bar["Date"]
                    active_trade["exit_reason"] = "STATE_EMERGENCY"
                    trades.append(active_trade)
                    active_trade = None
                    continue

    return trades

def run_full_backtest():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    results = []
    
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists():
            print(f"File not found: {p_path}")
            continue
            
        print(f"Testing {t}...")
        df_raw = pd.read_parquet(p_path)
        trades = simulate_backtest(t, df_raw)
        
        if not trades:
            results.append({
                "ticker": t, "total": 0, "wins": 0, "losses": 0, "wr": 0, "avg_p": 0
            })
            continue
            
        # Calculate stats
        wins = 0
        total_profit_pct = 0
        
        for tr in trades:
            p_pct = (tr["exit_price"] - tr["entry_price"]) / tr["entry_price"]
            # If partial sold, benefit is slightly higher, but let's keep it simple: win if profit > 0
            if p_pct > 0:
                wins += 1
            total_profit_pct += p_pct
            
        results.append({
            "ticker": t,
            "total": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "wr": round(wins/len(trades)*100, 1),
            "avg_p": round(total_profit_pct/len(trades)*100, 2)
        })
        
        # Break down by signal type
        for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
            sig_trades = [tr for tr in trades if tr["entry_type"] == sig]
            if sig_trades:
                s_wins = len([tr for tr in sig_trades if (tr["exit_price"] - tr["entry_price"]) > 0])
                print(f"  - {sig}: {len(sig_trades)} trades, WR: {round(s_wins/len(sig_trades)*100, 1)}%")

    print("\n--- FINAL SUMMARY ---")
    print(pd.DataFrame(results).to_markdown())

if __name__ == "__main__":
    run_full_backtest()
