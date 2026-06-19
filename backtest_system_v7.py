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

def patch_ensure_indicators(df):
    return df

def get_primary_states_linear(df):
    """Calculates primary state for all bars in O(N)."""
    # Mimic state_engine logic but vectorized
    ma20 = df['MA20']
    ma50 = df['MA50']
    adx = df['ADX']
    c = df['Close']
    
    ma_bull = ma20 > ma50
    ma_bear = ma20 < ma50
    
    trend_bias = np.where(ma_bull & (c > ma20), 1, 0)
    trend_bias = np.where(ma_bear & (c < ma20), -1, trend_bias)
    trend_bias = np.where(ma_bear & (c > ma20), 0.5, trend_bias)
    
    strong_trend = (adx > 25) & (adx > adx.shift(1))
    
    primary = pd.Series("NEUTRAL", index=df.index)
    primary = np.where(trend_bias == 0.5, "RECOVERY", primary)
    primary = np.where(trend_bias == 1, "WEAK_UPTREND", primary)
    primary = np.where(trend_bias == -1, "WEAK_DOWNTREND", primary)
    primary = np.where((trend_bias == -1) & strong_trend, "DOWNTREND", primary)
    primary = np.where((trend_bias == 1) & strong_trend, "UPTREND", primary)
    
    return pd.Series(primary, index=df.index)

@patch('tinvest.advanced_entry.ensure_indicators', side_effect=patch_ensure_indicators)
def simulate_backtest_v7(ticker, df_raw, mock1):
    print(f"  - Preparations for {ticker}...", flush=True)
    df = dl.enrich_dataframe(df_raw)
    
    # 1. Pre-calculate Signals
    entry_signals = [ae._eval_day(df, i) if i >= 100 else None for i in range(len(df))]
    
    # 2. Pre-calculate States (Linearized)
    primary_states = get_primary_states_linear(df)
    
    print(f"  - Running simulation...", flush=True)
    trades = []
    active_trade = None
    
    for i in range(100, len(df)):
        current_bar = df.iloc[i]
        
        if active_trade is None:
            res = entry_signals[i]
            if res:
                entry_type = res["type"]
                try:
                    val = ve.evaluate_stock_valuation(ticker, df.iloc[:i+1], {"entry_type": entry_type})
                except:
                    val = {"r1": current_bar["Close"]*1.05, "cutloss_full": current_bar["Close"]*0.94}
                
                active_trade = {
                    "entry_date": current_bar["Date"],
                    "entry_price": current_bar["Close"],
                    "entry_type": entry_type,
                    "tp1": val.get("s1_as_tp", val.get("r1", current_bar["Close"]*1.05)),
                    "sl": val.get("cutloss_full", current_bar["Close"]*0.94),
                    "ts": val.get("trailing_stop", 0),
                    "days_held": 0
                }
                if active_trade["tp1"] <= active_trade["entry_price"]: active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["sl"] >= active_trade["entry_price"]: active_trade["sl"] = active_trade["entry_price"] * 0.94
        else:
            active_trade["days_held"] += 1
            if active_trade["days_held"] >= 3:
                # T+3 Rule
                if active_trade["days_held"] == 3 and current_bar["Open"] < active_trade["sl"]:
                    active_trade.update({"exit_price": current_bar["Open"], "exit_date": current_bar["Date"], "exit_reason": "GAP_DOWN"})
                    trades.append(active_trade); active_trade = None; continue

                if current_bar["Low"] <= active_trade["sl"]:
                    active_trade.update({"exit_price": active_trade["sl"], "exit_date": current_bar["Date"], "exit_reason": "STOP_LOSS"})
                    trades.append(active_trade); active_trade = None; continue
                
                if active_trade["ts"] > 0 and current_bar["Low"] <= active_trade["ts"]:
                    active_trade.update({"exit_price": active_trade["ts"], "exit_date": current_bar["Date"], "exit_reason": "TRAILING_STOP"})
                    trades.append(active_trade); active_trade = None; continue
                
                if current_bar["High"] >= active_trade["tp1"]:
                    active_trade.update({"exit_price": active_trade["tp1"], "exit_date": current_bar["Date"], "exit_reason": "TAKE_PROFIT"})
                    trades.append(active_trade); active_trade = None; continue

                # Emergency State Exit (Downtrend)
                if primary_states.iloc[i] in ["DOWNTREND", "DOWNTREND_START"]:
                    active_trade.update({"exit_price": current_bar["Close"], "exit_date": current_bar["Date"], "exit_reason": "STATE_DOWNTREND"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_v7():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\n[{t}] Starting...", flush=True)
        df_raw = pd.read_parquet(p_path)
        trades = simulate_backtest_v7(t, df_raw)
        
        if trades:
            wins = len([tr for tr in trades if tr["exit_price"] > tr["entry_price"]])
            pnl = sum([(tr["exit_price"] - tr["entry_price"])/tr["entry_price"] for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "WR%": round(wins/len(trades)*100,1), "TotalRet%": round(pnl*100,1)})
            print(f"  -> {len(trades)} trades | {round(wins/len(trades)*100,1)}% WR", flush=True)
        else:
            summary.append({"Ticker": t, "Trades": 0, "WR%": 0, "TotalRet%": 0})

    print("\n" + "="*50)
    print("      BACKTEST RESULTS (T+3 CONSERVATIVE)")
    print("="*50)
    print(pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_v7()
