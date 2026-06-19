import pandas as pd
import numpy as np
import logging
import os
from datetime import datetime, timedelta
from tinvest.db_manager import DatabaseManager
from tinvest.data_loader import enrich_dataframe

# Setup logging to console
logging.basicConfig(level=logging.INFO)

def test_integration():
    db = DatabaseManager("test_tinvest.db")
    
    print("\n--- Phase 1: Creating Sample Data ---")
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(50)]
    data = {
        'Ticker': ['AAA'] * 50 + ['BBB'] * 50,
        'Date': dates + dates,
        'Open': np.random.uniform(10, 20, 100),
        'High': np.random.uniform(20, 30, 100),
        'Low': np.random.uniform(5, 10, 100),
        'Close': np.random.uniform(10, 25, 100),
        'Volume': np.random.randint(1000, 100000, 100)
    }
    df = pd.DataFrame(data)
    
    print("\n--- Phase 2: Testing save_prices ---")
    try:
        db.save_prices(df)
        print("[OK] save_prices successful")
    except Exception as e:
        print(f"[FAIL] save_prices failed: {e}")
        return

    print("\n--- Phase 3: Testing load_ticker_data & enrich_dataframe ---")
    try:
        df_aaa = db.load_ticker_data("AAA")
        print(f"Loaded {len(df_aaa)} rows for AAA")
        
        df_enriched = enrich_dataframe(df_aaa)
        print("[OK] enrich_dataframe successful")
        print(f"Enriched columns: {list(df_enriched.columns)}")
    except Exception as e:
        print(f"[FAIL] enrich/load failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n--- Phase 4: Testing save_indicators ---")
    try:
        db.save_indicators(df_enriched, ticker="AAA")
        print("[OK] save_indicators successful")
    except Exception as e:
        print(f"[FAIL] save_indicators failed: {e}")
        return

    print("\n--- Phase 5: Testing incremental update ---")
    try:
        # Add 1 new row
        new_row = {
            'Ticker': ['AAA'],
            'Date': [datetime(2023, 3, 1)],
            'Open': [20.0], 'High': [21.0], 'Low': [19.0], 'Close': [20.5], 'Volume': [50000]
        }
        df_new = pd.DataFrame(new_row)
        db.save_prices(df_new)
        
        # Reload and re-enrich
        df_full = db.load_ticker_data("AAA")
        df_incremental = enrich_dataframe(df_full)
        db.save_indicators(df_incremental, ticker="AAA")
        print("[OK] Incremental enrich & save successful")
    except Exception as e:
        print(f"[FAIL] Incremental test failed: {e}")
        return

    print("\n--- Phase 6: Testing save_analysis ---")
    try:
        test_analysis = {"ichi": "Bullish", "vsa": "No Demand"}
        db.save_analysis("AAA", df_incremental['Date'].iloc[-1], test_analysis)
        print("[OK] save_analysis successful")
        
        loaded = db.load_latest_analysis("AAA")
        print(f"Loaded analysis: {loaded}")
    except Exception as e:
        print(f"[FAIL] save_analysis failed: {e}")
        return

    print("\n\n>>> ALL INTEGRATIONS TESTS PASSED! <<<")
    
    # Cleanup
    if os.path.exists("test_tinvest.db"):
        os.remove("test_tinvest.db")

if __name__ == "__main__":
    test_integration()
