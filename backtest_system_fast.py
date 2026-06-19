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
from tinvest.state_engine import evaluate_state_rules

def simulate_backtest_fast(ticker, df_raw):
    # 1. Enrich data
    df = enrich_dataframe(df_raw)
    
    # 2. Pre-calculate Entry Signals for all days (This is the O(N) part)
    # Since _eval_day uses @cache, we just need to call it in a sequence.
    print(f"  - Pre-calculating signals for {ticker}...")
    entry_signals = []
    for i in range(len(df)):
        if i < 70: # Minimum indicator window
            entry_signals.append(None)
            continue
        # Use index relative to start
        res = _eval_day(df, i)
        entry_signals.append(res)
    
    # 3. Pre-calculate States for all days
    # The current evaluate_state_rules is vectorized, but it returns a dict for the LAST row.
    # To be fast, we SHOULD have used the vectorized series.
    # But to avoid breaking the engine, I'll just call it and rely on the fact that 
    # the backtest loop is now only calling it when a trade is active.
    
    trades = []
    active_trade = None
    
    # Starting index for analysis
    start_idx = 100 
    
    for i in range(start_idx, len(df)):
        current_bar = df.iloc[i]
        
        # --- IF NO ACTIVE TRADE, LOOK FOR ENTRY ---
        if active_trade is None:
            res = entry_signals[i]
            if res:
                entry_type = res["type"]
                # For valuation, we still need evaluate_stock_valuation
                # but we only call it ONCE per entry
                val = evaluate_stock_valuation(ticker, df.iloc[:i+1], {"entry_type": entry_type})
                
                # Allocation logic
                alloc_map = {"EARLY": 0.20, "ADD_1": 0.40, "ADD_2": 0.60, "STRONG": 0.85}
                
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
                # Sanity checks
                if active_trade["tp1"] <= active_trade["entry_price"]: active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["sl"] >= active_trade["entry_price"]: active_trade["sl"] = active_trade["entry_price"] * 0.95

        # --- IF ACTIVE TRADE, MONITOR FOR EXIT (strictly T+3) ---
        else:
            active_trade["days_held"] += 1
            
            # Use current bar for daily monitoring
            if active_trade["days_held"] >= 3:
                # 1. GAP DOWN on T+3 morning
                if active_trade["days_held"] == 3 and current_bar["Open"] < active_trade["sl"]:
                    active_trade.update({"exit_price": current_bar["Open"], "exit_date": current_bar["Date"], "exit_reason": "GAP_DOWN_SL"})
                    trades.append(active_trade); active_trade = None; continue

                # 2. SL or TS
                if current_bar["Low"] <= active_trade["sl"]:
                     active_trade.update({"exit_price": active_trade["sl"], "exit_date": current_bar["Date"], "exit_reason": "STOP_LOSS"})
                     trades.append(active_trade); active_trade = None; continue
                
                if active_trade["ts"] > 0 and current_bar["Low"] <= active_trade["ts"]:
                     active_trade.update({"exit_price": active_trade["ts"], "exit_date": current_bar["Date"], "exit_reason": "TRAILING_STOP"})
                     trades.append(active_trade); active_trade = None; continue

                # 3. TP Partial (records but continues)
                if not active_trade["partial_sold"] and current_bar["High"] >= active_trade["tp1"]:
                    active_trade["partial_sold"] = True

                # 4. TP Full
                if current_bar["High"] >= active_trade["tp2"]:
                     active_trade.update({"exit_price": active_trade["tp2"], "exit_date": current_bar["Date"], "exit_reason": "TAKE_PROFIT_FULL"})
                     trades.append(active_trade); active_trade = None; continue

                # 5. State Change (Emergency) - call only when needed
                st = evaluate_state_rules(df.iloc[:i+1])
                if st.get("primary") in ["DOWNTREND_START", "DOWNTREND"] or st.get("signal") == "EXIT_FAST":
                    active_trade.update({"exit_price": current_bar["Close"], "exit_date": current_bar["Date"], "exit_reason": "STATE_EMERGENCY"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_fast_backtest():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"Testing {t}...")
        df_raw = pd.read_parquet(p_path)
        trades = simulate_backtest_fast(t, df_raw)
        
        if trades:
            wins = len([tr for tr in trades if tr["exit_price"] > tr["entry_price"]])
            avg_p = sum([(tr["exit_price"] - tr["entry_price"])/tr["entry_price"] for tr in trades]) / len(trades)
            summary.append({"Ticker": t, "Trades": len(trades), "Wins": wins, "WR%": round(wins/len(trades)*100,1), "AvgRet%": round(avg_p*100,2)})
            
            # Print breakdown
            for sig in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                st = [tr for tr in trades if tr["entry_type"] == sig]
                if st:
                    sw = len([tr for tr in st if tr["exit_price"] > tr["entry_price"]])
                    print(f"    {sig}: {len(st)} trades, {round(sw/len(st)*100,1)}% WR")
        else:
            summary.append({"Ticker": t, "Trades": 0, "Wins": 0, "WR%": 0, "AvgRet%": 0})

    print("\n" + pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_fast_backtest()
