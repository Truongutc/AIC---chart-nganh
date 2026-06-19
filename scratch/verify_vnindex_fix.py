import pandas as pd
import numpy as np
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from tinvest.valuation_engine import evaluate_stock_valuation

def test_vnindex_support_fallback():
    # 1. Create a dummy VNIndex dataframe without Ichimoku columns
    # Price is 1915 as in user report
    data = {
        'Date': pd.date_range(start='2026-01-01', periods=100),
        'Open': [1800 + i for i in range(100)],
        'High': [1810 + i for i in range(100)],
        'Low': [1790 + i for i in range(100)],
        'Close': [1800 + i for i in range(100)],
        'Volume': [1000000] * 100,
        'MA10': [1890] * 100,
        'MA20': [1850] * 100,
        'MA50': [1800] * 100,
        'SwingHigh': [0] * 100,
        'SwingLow': [0] * 100,
        'ATR14': [10.0] * 100
    }
    df = pd.DataFrame(data)
    
    # Set current price to 1915
    df.loc[df.index[-1], 'Close'] = 1915.0
    df.loc[df.index[-1], 'MA20'] = 1850.0
    df.loc[df.index[-1], 'MA50'] = 1800.0
    
    # 2. Define a signal (ADD_2)
    entry_info = {
        "entry_type": "ADD_2",
        "confidence": "GIA TANG 2",
        "details": {"source": "FALLBACK"}
    }
    
    # 3. Evaluate valuation
    print("Testing VNIndex with missing Ichimoku data...")
    res = evaluate_stock_valuation("VNINDEX", df, entry_info)
    
    print(f"Ticker: {res['ticker']}")
    print(f"Price: {res['price']}")
    print(f"Signal: {res['state']}")
    print(f"Support S1: {res['s1']}")
    print(f"Support S2: {res['s2']}")
    
    # Check if s1 and s2 are valid (not N/A/0)
    assert res['s1'] > 0, "S1 should be greater than 0"
    assert res['s2'] > 0, "S2 should be greater than 0"
    assert res['s1'] <= 1915, "S1 should be below price"
    
    # Specifically for Index, s1 should be at least MA20 (1850)
    assert res['s1'] >= 1850, f"S1 ({res['s1']}) should be at least MA20 (1850) for an Index"
    
    print("\n[SUCCESS] Verification SUCCESSFUL: Supports are correctly calculated using fallbacks.")

if __name__ == "__main__":
    try:
        test_vnindex_support_fallback()
    except Exception as e:
        print(f"\n[FAILED] Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
