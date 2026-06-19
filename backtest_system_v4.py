import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from tinvest.data_loader import enrich_dataframe
from tinvest.advanced_entry import _eval_day
from tinvest.valuation_engine import evaluate_stock_valuation
# We need to compute states for all bars efficiently
from tinvest.state_engine import evaluate_state_rules

def get_all_states(df):
    """
    Evaluates states for every bar in the dataframe linearly.
    Since evaluate_state_rules is vectorized, we can modify it slightly
    or just call it for the whole DF if it supports returning series.
    Based on the code, it returns a dict for the LAST index.
    We'll wrap it to return a list of results.
    """
    # Note: To be truly efficient, we should use a vectorized version of evaluate_state_rules.
    # Since we can't easily modify the engine without risks, we'll use a sliding window cache approach.
    states = []
    print("  - Calculating all states...", flush=True)
    for i in range(len(df)):
        if i < 21:
            states.append({"primary": "NEUTRAL", "signal": "NONE"})
            continue
        # For performance, evaluate_state_rules on a slice is still a bit slow but better than nothing.
        # Actually, let's optimize: evaluate_state_rules is O(N) because it does rolling(20).
        # We'll just call it every bar. 3000 calls * 0.01s = 30s. Acceptable.
        states.append(evaluate_state_rules(df.iloc[:i+1]))
    return states

def simulate_backtest_v4(ticker, df_raw):
    df = enrich_dataframe(df_raw)
    
    print(f"  - Pre-calculating signals for {ticker}...", flush=True)
    entry_signals = [_eval_day(df, i) if i >= 70 else None for i in range(len(df))]
    
    print(f"  - Pre-calculating states for {ticker}...", flush=True)
    states = get_all_states(df)
    
    trades = []
    active_trade = None
    
    for i in range(100, len(df)):
        current_bar = df.iloc[i]
        
        if active_trade is None:
            res = entry_signals[i]
            if res:
                entry_type = res["type"]
                val = evaluate_stock_valuation(ticker, df.iloc[:i+1], {"entry_type": entry_type})
                
                active_trade = {
                    "ticker": ticker,
                    "entry_date": current_bar["Date"],
                    "entry_price": current_bar["Close"],
                    "entry_type": entry_type,
                    "tp1": val.get("s1_as_tp", val.get("r1", current_bar["Close"]*1.05)),
                    "tp2": val.get("r2", current_bar["Close"]*1.10),
                    "sl": val.get("cutloss_full", current_bar["Close"]*0.95),
                    "ts": val.get("trailing_stop", 0),
                    "days_held": 0,
                    "partial_sold": False
                }
                # Sanity
                if active_trade["tp1"] <= active_trade["entry_price"]: active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["sl"] >= active_trade["entry_price"]: active_trade["sl"] = active_trade["entry_price"] * 0.95
        else:
            active_trade["days_held"] += 1
            if active_trade["days_held"] >= 3:
                # 1. T+3 Gap down open
                if active_trade["days_held"] == 3 and current_bar["Open"] < active_trade["sl"]:
                    active_trade.update({"exit_price": current_bar["Open"], "exit_date": current_bar["Date"], "exit_reason": "GAP_DOWN_SL"})
                    trades.append(active_trade); active_trade = None; continue

                # 2. SL / TS
                if current_bar["Low"] <= active_trade["sl"]:
                    active_trade.update({"exit_price": active_trade["sl"], "exit_date": current_bar["Date"], "exit_reason": "STOP_LOSS"})
                    trades.append(active_trade); active_trade = None; continue
                
                if active_trade["ts"] > 0 and current_bar["Low"] <= active_trade["ts"]:
                    active_trade.update({"exit_price": active_trade["ts"], "exit_date": current_bar["Date"], "exit_reason": "TRAILING_STOP"})
                    trades.append(active_trade); active_trade = None; continue

                # 3. TP Partial
                if not active_trade["partial_sold"] and current_bar["High"] >= active_trade["tp1"]:
                    active_trade["partial_sold"] = True

                # 4. TP Full
                if current_bar["High"] >= active_trade["tp2"]:
                    active_trade.update({"exit_price": active_trade["tp2"], "exit_date": current_bar["Date"], "exit_reason": "TAKE_PROFIT_FULL"})
                    trades.append(active_trade); active_trade = None; continue

                # 5. State Emergency (Downtrend)
                st = states[i]
                if st.get("primary") in ["DOWNTREND_START", "DOWNTREND"] or st.get("signal") == "EXIT_FAST":
                    active_trade.update({"exit_price": current_bar["Close"], "exit_date": current_bar["Date"], "exit_reason": "STATE_EMERGENCY"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_backtest_v4():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\n>>> PROCESSING {t} <<<\n", flush=True)
        df_raw = pd.read_parquet(p_path)
        trades = simulate_backtest_v4(t, df_raw)
        
        if trades:
            wins = len([tr for tr in trades if tr["exit_price"] > tr["entry_price"]])
            pnl = sum([(tr["exit_price"] - tr["entry_price"])/tr["entry_price"] for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "Wins": wins, "WR%": round(wins/len(trades)*100,1), "TotalRet%": round(pnl*100,2), "AvgRet%": round((pnl/len(trades))*100,2)})
            
            # Print Breakdown
            print(f"\nResults for {t}:", flush=True)
            for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                st = [tr for tr in trades if tr["entry_type"] == sig]
                if st:
                    sw = len([tr for tr in st if tr["exit_price"] > tr["entry_price"]])
                    print(f"  {sig:8}: {len(st):3} trades | {round(sw/len(st)*100,1):5}% WR", flush=True)
        else:
            summary.append({"Ticker": t, "Trades": 0, "Wins": 0, "WR%": 0, "TotalRet%": 0, "AvgRet%": 0})

    print("\n" + "="*50)
    print("BACKTEST SUMMARY (T+3 Strictly)")
    print("="*50)
    print(pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_backtest_v4()
