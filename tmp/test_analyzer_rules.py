import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
from tinvest.data_loader import load_data
from tinvest.analyzer import analyze_stock, format_report

def main():
    try:
        data = load_data("test_cache.db") # Since there's no CSV, maybe load from SQLite if supported?
    except Exception:
        pass
        
    # Let's generate a dummy technical dataframe
    import numpy as np
    
    n_days = 200
    dates = pd.date_range("2023-01-01", periods=n_days)
    close = np.linspace(20, 30, n_days)
    
    # Simulate a pullback for standard ADX/MA calculation
    close[-10:] = np.linspace(30, 28, 10)
    close[-1] = 29 # bounce
    
    df = pd.DataFrame({
        "Date": dates,
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, n_days)
    })
    
    result = analyze_stock("TCB", df)
    print(format_report(result))
    
    from tinvest.market_engine import analyze_market_index
    market_res = analyze_market_index(df)
    print("\nMarket Regime Result:")
    print(market_res)

if __name__ == "__main__":
    main()
