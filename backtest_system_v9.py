import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def run_v9():
    tickers = ["MWG", "HCM", "FPT", "HPG", "TCB"]
    summary = []
    price_dir = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices")
    
    for t in tickers:
        p_path = price_dir / f"{t}.parquet"
        if not p_path.exists(): continue
            
        print(f"\n>>> BACKTESTING {t} (T+3 Strictly) <<<", flush=True)
        df_raw = pd.read_parquet(p_path)
        df = dl.enrich_dataframe(df_raw)
        
        # VECTORIZED SIGNALS
        ma10, ma20, ma50 = df['MA10'], df['MA20'], df['MA50']
        c, o, h, l = df['Close'], df['Open'], df['High'], df['Low']
        
        # Signal conditions
        early_buy = (c > ma10) & (c.shift(1) <= ma10.shift(1)) & (df['Volume'] > df['AvgVolume20']) & (df['RSI'] < 45)
        add1_buy = (ma20 > ma50) & (l <= ma20 * 1.01) & (c > ma20) & (c > o)
        high20 = h.rolling(20).max().shift(1)
        strong_buy = (c > high20) & (df['Volume'] > 1.2 * df['AvgVolume20'])
        
        trades = []
        active_trade = None
        
        for i in range(100, len(df)):
            curr = df.iloc[i]
            
            if active_trade is None:
                st_type = None
                if strong_buy.iloc[i]: st_type = "STRONG"
                elif add1_buy.iloc[i]: st_type = "ADD_1"
                elif early_buy.iloc[i]: st_type = "EARLY"
                
                if st_type:
                    atr = curr['ATR14']
                    alloc = {"EARLY": 0.20, "ADD_1": 0.40, "ADD_2": 0.60, "STRONG": 0.85}.get(st_type, 0.2)
                    active_trade = {
                        "type": st_type,
                        "e_date": curr["Date"],
                        "e_price": curr["Close"],
                        "tp": curr["Close"] + (2.8 * atr if st_type == "STRONG" else 2.2 * atr),
                        "sl": curr["Close"] - 1.5 * atr,
                        "alloc": alloc,
                        "days": 0
                    }
            else:
                active_trade["days"] += 1
                if active_trade["days"] >= 3:
                    # 1. T+3 Gap Down
                    if active_trade["days"] == 3 and curr["Open"] < active_trade["sl"]:
                        active_trade.update({"x_price": curr["Open"], "x_date": curr["Date"], "res": "GAP"})
                        trades.append(active_trade); active_trade = None; continue
                    
                    # 2. SL / TP
                    if curr["Low"] <= active_trade["sl"]:
                        active_trade.update({"x_price": active_trade["sl"], "x_date": curr["Date"], "res": "SL"})
                        trades.append(active_trade); active_trade = None; continue
                    if curr["High"] >= active_trade["tp"]:
                        active_trade.update({"x_price": active_trade["tp"], "x_date": curr["Date"], "res": "TP"})
                        trades.append(active_trade); active_trade = None; continue
                    
                    # 3. Market State Exit
                    if ma20.iloc[i] < ma50.iloc[i] and c.iloc[i] < ma20.iloc[i]:
                        active_trade.update({"x_price": curr["Close"], "x_date": curr["Date"], "res": "DOWN"})
                        trades.append(active_trade); active_trade = None; continue

        if trades:
            wins = len([tr for tr in trades if tr["x_price"] > tr["e_price"]])
            pnl = sum([(tr["x_price"] - tr["e_price"])/tr["e_price"] for tr in trades])
            summary.append({"Ticker": t, "T": len(trades), "W": wins, "WR%": round(wins/len(trades)*100,1), "Ret%": round(pnl*100,1)})
            
            print(f"  Result: {len(trades)} trades, {round(wins/len(trades)*100,1)}% Win Rate", flush=True)
            for s in ["EARLY", "ADD_1", "STRONG"]:
                st = [tr for tr in trades if tr["type"] == s]
                if st:
                    sw = len([tr for tr in st if tr["x_price"] > tr["e_price"]])
                    print(f"    {s:8}: {len(st):3} trades, {round(sw/len(st)*100,1)}% WR", flush=True)

    print("\n" + "="*55)
    print("      BACKTEST SUMMARY (T+3 VN-MARKET DELAY)")
    print("="*55)
    print("{:<10} {:<5} {:<5} {:<10} {:<10}".format("Ticker", "Trades", "Wins", "WinRate%", "TotalRet%"))
    print("-" * 55)
    for s in summary:
        print("{:<10} {:<5} {:<5} {:<10} {:<10}".format(s['Ticker'], s['T'], s['W'], s['WR%'], s['Ret%']))
    print("="*55)

if __name__ == "__main__":
    run_v9()
