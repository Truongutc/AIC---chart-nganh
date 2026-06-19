import io
import sys
import pandas as pd
import numpy as np

# Set stdout to utf-8 to avoid encoding errors on Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from tinvest.data_loader import enrich_dataframe
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.advanced_entry import classify_entry

def test_diagnostics():
    print("--- TESTING TECHNICAL HEALTH DIAGNOSTICS ---")
    
    # Create fake upward trend data
    dates = pd.date_range(start='2023-01-01', periods=100)
    # Price rising from 100
    close = [100.0 + i for i in range(100)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    open_p = [c - 0.5 for c in close]
    vol = [1000.0 for _ in range(100)]
    
    df = pd.DataFrame({
        'Date': dates,
        'Open': open_p,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': vol
    })
    
    df_rich = enrich_dataframe(df)
    adv = classify_entry(df_rich)
    val = evaluate_stock_valuation("TEST", df_rich, adv)
    
    print(f"Ticker: {val['ticker']}")
    print(f"Action: {val['action']}")
    print(f"Health Rating: {val['tech_health']['health_rating']}")
    print(f"ADX Label: {val['tech_health']['adx_label']}")
    print(f"RSI Label: {val['tech_health']['rsi_label']}")
    print(f"MACD Label: {val['tech_health']['macd_label']}")
    
    assert 'tech_health' in val
    # In a rising trend, score should at least be >= 2 (Improved/Strong)
    print(f"Health Score: {val['tech_health']['health_score']}")
    assert val['tech_health']['health_score'] >= 2
    print("\n✅ DIAGNOSTICS TEST PASSED!")

if __name__ == "__main__":
    try:
        test_diagnostics()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
