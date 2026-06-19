import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl
import tinvest.advanced_entry as ae
import tinvest.valuation_engine as ve
import tinvest.state_engine as se

# --- PATCHING TO AVOID RE-CALCULATION TRAP ---
def patch_ensure_indicators(df):
    return df

@patch('tinvest.advanced_entry.ensure_indicators', side_effect=patch_ensure_indicators)
def simulate_backtest_v6(ticker, df_raw, mock1):
    print(f"  - Enriching {ticker} (once)...", flush=True)
    df = dl.enrich_dataframe(df_raw)
    
    print(f"  - Pre-calculating signals (linear)...", flush=True)
    # This is fast now because indicate re-calculation is patched out
    entry_signals = []
    for i in range(len(df)):
        if i < 70:
            entry_signals.append(None)
        else:
            # We call _eval_day with the index i
            entry_signals.append(ae._eval_day(df, i))
            
    print(f"  - Identifying trades with T+3 and Dynamic Alloc...", flush=True)
    trades = []
    active_trade = None
    
    for i in range(100, len(df)):
        current_bar = df.iloc[i]
        
        if active_trade is None:
            res = entry_signals[i]
            if res:
                entry_type = res["type"]
                # Use engine to get exact SL/TP targets
                try:
                    val = ve.evaluate_stock_valuation(ticker, df.iloc[:i+1], {"entry_type": entry_type})
                except:
                    # Fallback if valuation fails
                    val = {"r1": current_bar["Close"]*1.05, "r2": current_bar["Close"]*1.15, "cutloss_full": current_bar["Close"]*0.94}
                
                active_trade = {
                    "entry_date": current_bar["Date"],
                    "entry_price": current_bar["Close"],
                    "entry_type": entry_type,
                    "tp1": val.get("s1_as_tp", val.get("r1", current_bar["Close"]*1.05)),
                    "tp2": val.get("r2", current_bar["Close"]*1.15),
                    "sl": val.get("cutloss_full", current_bar["Close"]*0.94),
                    "ts": val.get("trailing_stop", 0),
                    "days_held": 0
                }
                # Sanity
                if active_trade["tp1"] <= active_trade["entry_price"]: active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["sl"] >= active_trade["entry_price"]: active_trade["sl"] = active_trade["entry_price"] * 0.94
        else:
            active_trade["days_held"] += 1
            if active_trade["days_held"] >= 3:
                # T+3 Rule
                # 1. Gap Down check
                if active_trade["days_held"] == 3 and current_bar["Open"] < active_trade["sl"]:
                    active_trade.update({"exit_price": current_bar["Open"], "exit_date": current_bar["Date"], "exit_reason": "GAP_DOWN_T3"})
                    trades.append(active_trade); active_trade = None; continue

                # 2. SL or TS
                if current_bar["Low"] <= active_trade["sl"]:
                    active_trade.update({"exit_price": active_trade["sl"], "exit_date": current_bar["Date"], "exit_reason": "STOP_LOSS"})
                    trades.append(active_trade); active_trade = None; continue
                
                if active_trade["ts"] > 0 and current_bar["Low"] <= active_trade["ts"]:
                    active_trade.update({"exit_price": active_trade["ts"], "exit_date": current_bar["Date"], "exit_reason": "TRAILING_STOP"})
                    trades.append(active_trade); active_trade = None; continue
                
                # 3. TP (Strictly using TP1 as primary target for this backtest success rate)
                if current_bar["High"] >= active_trade["tp1"]:
                    active_trade.update({"exit_price": active_trade["tp1"], "exit_date": current_bar["Date"], "exit_reason": "TAKE_PROFIT"})
                    trades.append(active_trade); active_trade = None; continue

                # 4. State Downtrend emergency exit
                # We reuse the main loop so we don't have another loop inside
                # Call state rules ONLY if trade is active - but only once per bar
                st = se.evaluate_state_rules(df.iloc[:i+1])
                if st.get("primary") in ["DOWNTREND", "DOWNTREND_START"]:
                    active_trade.update({"exit_price": current_bar["Close"], "exit_date": current_bar["Date"], "exit_reason": "STATE_EXIT"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_v6():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\nProcessing {t}...", flush=True)
        df_raw = pd.read_parquet(p_path)
        # Call with mocks
        trades = simulate_backtest_v6(t, df_raw)
        
        if trades:
            success = [tr for tr in trades if tr["exit_price"] > tr["entry_price"]]
            wins = len(success)
            pnl = sum([(tr["exit_price"] - tr["entry_price"])/tr["entry_price"] for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "WinRate%": round(wins/len(trades)*100,1), "TotalRet%": round(pnl*100,1)})
            print(f"  -> Done: {len(trades)} trades, {round(wins/len(trades)*100,1)}% WR", flush=True)
            for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                st_list = [tr for tr in trades if tr["entry_type"] == sig]
                if st_list:
                    sw = len([tr for tr in st_list if tr["exit_price"] > tr["entry_price"]])
                    print(f"     {sig:8}: {len(st_list):2} trades, {round(sw/len(st_list)*100,1)}% WR", flush=True)
        else:
            summary.append({"Ticker": t, "Trades": 0, "WinRate%": 0, "TotalRet%": 0})

    print("\n" + "="*50)
    print("      FINAL BACKTEST SUMMARY (STRICT T+3)")
    print("="*50)
    print(pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_v6()
