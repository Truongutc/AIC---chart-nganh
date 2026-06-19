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

def get_all_engine_outputs(df):
    """
    Simulates the engine vectorized for the entire dataframe.
    This avoids O(N^2) or O(N^3) loops.
    """
    from tinvest.state_engine import evaluate_state_rules
    
    # We can't easily get the series out of evaluate_state_rules because it returns a dict.
    # However, for a backtest, we can afford a few seconds per ticker if we are smarter.
    # We will compute the indicators ONCE (already done in enrich_dataframe).
    
    # Let's perform a vectorized state calculation based on state_engine.py logic
    # but returning a DataFrame of results.
    
    # --- REDUCED ENGINE LOGIC (Vectorized) ---
    o, h, l, c, v = df['Open'], df['High'], df['Low'], df['Close'], df['Volume']
    ma20, ma50 = df['MA20'], df['MA50']
    adx, hist = df['ADX'], df['MACD_Hist']
    atr = df['ATR14']
    
    # Trend context
    ma_bull = ma20 > ma50
    ma_bear = ma20 < ma50
    
    trend_bias = np.where(ma_bull & (c > ma20), 1, 0)
    trend_bias = np.where(ma_bear & (c < ma20), -1, trend_bias)
    
    strong_trend = (adx > 25) & (adx > adx.shift(1))
    
    # Primary State simplified
    primary = np.where(trend_bias == 0, "NEUTRAL", "WEAK_UPTREND")
    primary = np.where(trend_bias == -1, "WEAK_DOWNTREND", primary)
    primary = np.where((trend_bias == -1) & strong_trend, "DOWNTREND", primary)
    primary = np.where((trend_bias == 1) & strong_trend, "UPTREND", primary)
    
    # Signal simplified (EXIT_FAST if secondary is TRAP - but TRAP needs complex check)
    # We'll stick to a slightly slower but more accurate approach:
    # Use a pre-cached version or just accept the 30s delay if we don't do it inside another loop.
    
    return pd.Series(primary, index=df.index)

def simulate_backtest_v5(ticker, df_raw):
    df = enrich_dataframe(df_raw)
    
    # Linear signal calculation (O(N))
    print(f"  - Pre-calculating signals...", flush=True)
    entry_signals = []
    for i in range(len(df)):
        entry_signals.append(_eval_day(df, i) if i >= 100 else None)
    
    # Linear state calculation (O(N))
    # We'll use a slightly more expensive but accurate way: call state engine every 5 bars 
    # and assume state stability, OR just call it once and hope it's not too slow.
    print(f"  - Pre-calculating primary states...", flush=True)
    primary_states = get_all_engine_outputs(df)
    
    trades = []
    active_trade = None
    
    for i in range(100, len(df)):
        current_bar = df.iloc[i]
        
        if active_trade is None:
            res = entry_signals[i]
            if res:
                entry_type = res["type"]
                # Valuation is cheap enough to call once per entry
                val = evaluate_stock_valuation(ticker, df.iloc[:i+1], {"entry_type": entry_type})
                
                active_trade = {
                    "ticker": ticker,
                    "entry_date": current_bar["Date"],
                    "entry_price": current_bar["Close"],
                    "entry_type": entry_type,
                    "tp1": val.get("s1_as_tp", val.get("r1", current_bar["Close"]*1.05)),
                    "tp2": val.get("r2", current_bar["Close"]*1.15),
                    "sl": val.get("cutloss_full", current_bar["Close"]*0.94),
                    "ts": val.get("trailing_stop", 0),
                    "days_held": 0
                }
                # Fix inverted targets if any
                if active_trade["tp1"] <= active_trade["entry_price"]: active_trade["tp1"] = active_trade["entry_price"] * 1.05
                if active_trade["tp2"] <= active_trade["tp1"]: active_trade["tp2"] = active_trade["tp1"] * 1.10
                if active_trade["sl"] >= active_trade["entry_price"]: active_trade["sl"] = active_trade["entry_price"] * 0.94

        else:
            active_trade["days_held"] += 1
            # T+3 Rule
            if active_trade["days_held"] >= 3:
                # Open Gap Down
                if active_trade["active_trade" if False else "days_held"] == 3 and current_bar["Open"] < active_trade["sl"]:
                    active_trade.update({"exit_price": current_bar["Open"], "exit_date": current_bar["Date"], "exit_reason": "GAP_DOWN_SL"})
                    trades.append(active_trade); active_trade = None; continue
                
                # SL or TS
                if current_bar["Low"] <= active_trade["sl"]:
                    active_trade.update({"exit_price": active_trade["sl"], "exit_date": current_bar["Date"], "exit_reason": "STOP_LOSS"})
                    trades.append(active_trade); active_trade = None; continue

                if active_trade["ts"] > 0 and current_bar["Low"] <= active_trade["ts"]:
                    active_trade.update({"exit_price": active_trade["ts"], "exit_date": current_bar["Date"], "exit_reason": "TRAILING_STOP"})
                    trades.append(active_trade); active_trade = None; continue

                # TP Full (conservative: 1-step TP for this backtest)
                if current_bar["High"] >= active_trade["tp1"]:
                    active_trade.update({"exit_price": active_trade["tp1"], "exit_date": current_bar["Date"], "exit_reason": "TAKE_PROFIT"})
                    trades.append(active_trade); active_trade = None; continue
                
                # Emergency Exit
                pri_state = primary_states.iloc[i]
                if pri_state in ["DOWNTREND", "DOWNTREND_START"]:
                    active_trade.update({"exit_price": current_bar["Close"], "exit_date": current_bar["Date"], "exit_reason": "DOWNTREND_EXIT"})
                    trades.append(active_trade); active_trade = None; continue

    return trades

def run_backtest_v5():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\n[{t}] Running analysis...", flush=True)
        df_raw = pd.read_parquet(p_path)
        trades = simulate_backtest_v5(t, df_raw)
        
        if trades:
            wins = len([tr for tr in trades if tr["exit_price"] > tr["entry_price"]])
            pnl = sum([(tr["exit_price"] - tr["entry_price"])/tr["entry_price"] for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "WinRate%": round(wins/len(trades)*100,1), "TotalRet%": round(pnl*100,1), "AvgRet%": round((pnl/len(trades))*100,2)})
            
            print(f"  - Results: {len(trades)} trades, {round(wins/len(trades)*100,1)}% WR", flush=True)
        else:
            summary.append({"Ticker": t, "Trades": 0, "WinRate%": 0, "TotalRet%": 0, "AvgRet%": 0})

    print("\n" + "="*60)
    print("      VN-MARKET BACKTEST REPORT (STRICT T+3 SETTLEMENT)")
    print("="*60)
    print(pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_backtest_v5()
