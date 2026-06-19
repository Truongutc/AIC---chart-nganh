import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def run_v8():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\n>>> BACKTESTING {t} (T+3 Strictly) <<<", flush=True)
        df = pd.read_parquet(p_path)
        df = dl.enrich_dataframe(df)
        
        # 1. VECTORIZED SIGNALS (VSA + MA + MACD)
        # Mimic our engine logic without the slow loops
        ma10, ma20, ma50 = df['MA10'], df['MA20'], df['MA50']
        c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
        
        # Simple Early buy: Cross MA10 and RSI < 40 and Vol spike
        early_buy = (c > ma10) & (c.shift(1) <= ma10.shift(1)) & (df['Volume'] > df['AvgVolume20'])
        
        # Add 1: MA Pullback (C > MA20 and h_low <= MA20)
        add1_buy = (ma20 > ma50) & (l <= ma20 * 1.01) & (c > ma20) & (c > o)
        
        # Strong Buy: Breakout of 20-day high with Vol
        high20 = h.rolling(20).max().shift(1)
        strong_buy = (c > high20) & (df['Volume'] > 1.2 * df['AvgVolume20'])
        
        trades = []
        active_trade = None
        
        for i in range(100, len(df)):
            curr = df.iloc[i]
            
            if active_trade is None:
                # Prioritize: Strong > Add1 > Early
                st_type = None
                if strong_buy.iloc[i]: st_type = "STRONG"
                elif add1_buy.iloc[i]: st_type = "ADD_1"
                elif early_buy.iloc[i]: st_type = "EARLY"
                
                if st_type:
                    # Logic-based SL/TP (Mimics evaluate_stock_valuation)
                    atr = curr['ATR14']
                    active_trade = {
                        "type": st_type,
                        "e_date": curr["Date"],
                        "e_price": curr["Close"],
                        "tp": curr["Close"] + 2.5 * atr,
                        "sl": curr["Close"] - 1.5 * atr,
                        "days": 0
                    }
            else:
                active_trade["days"] += 1
                if active_trade["days"] >= 3:
                    # Exit conditions
                    # Gap down morning T+3
                    if active_trade["days"] == 3 and curr["Open"] < active_trade["sl"]:
                        active_trade.update({"x_price": curr["Open"], "x_date": curr["Date"], "res": "GAP_SL"})
                        trades.append(active_trade); active_trade = None; continue
                    
                    if curr["Low"] <= active_trade["sl"]:
                        active_trade.update({"x_price": active_trade["sl"], "x_date": curr["Date"], "res": "SL"})
                        trades.append(active_trade); active_trade = None; continue
                    
                    if curr["High"] >= active_trade["tp"]:
                        active_trade.update({"x_price": active_trade["tp"], "x_date": curr["Date"], "res": "TP"})
                        trades.append(active_trade); active_trade = None; continue
                    
                    # Emergency Downtrend
                    if ma20.iloc[i] < ma50.iloc[i] and c.iloc[i] < ma20.iloc[i]:
                        active_trade.update({"x_price": curr["Close"], "x_date": curr["Date"], "res": "DOWNTREND"})
                        trades.append(active_trade); active_trade = None; continue

        if trades:
            wins = len([tr for tr in trades if tr["x_price"] > tr["e_price"]])
            pnl = sum([(tr["x_price"] - tr["e_price"])/tr["e_price"] for tr in trades])
            summary.append({"Ticker": t, "Trades": len(trades), "WinRate%": round(wins/len(trades)*100,1), "TotalRet%": round(pnl*100,1), "AvgRet%": round((pnl/len(trades))*100,2)})
            print(f"  -> {t}: {len(trades)} trades, {round(wins/len(trades)*100,1)}% WR", flush=True)

    print("\n" + "="*50)
    print("      QUICK BACKTEST REPORT (STRICT T+3)")
    print("="*50)
    print(pd.DataFrame(summary).to_markdown())

if __name__ == "__main__":
    run_v8()
