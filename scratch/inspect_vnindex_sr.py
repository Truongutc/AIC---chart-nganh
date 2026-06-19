import os
import sys
import io
import pandas as pd
from datetime import datetime

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Set base path to import local modules
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

from tinvest.storage_manager import StorageManager
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.advanced_entry import classify_entry
from tinvest.data_loader import enrich_dataframe

def inspect_vnindex():
    storage = StorageManager()
    vn_df = storage.load_ticker_data("VNINDEX")
    if vn_df is None or vn_df.empty:
        print("❌ Cannot load VNINDEX data from storage.")
        return

    print(f"Loaded VNINDEX dataframe with {len(vn_df)} rows.")
    print(f"Last date in data: {vn_df['Date'].iloc[-1]}")
    print(f"Last close price: {vn_df['Close'].iloc[-1]}")

    # Enrich data to make sure all indicators are up to date
    df_rich = enrich_dataframe(vn_df)

    # Classify entry signal
    entry_info = classify_entry(df_rich)
    print(f"Entry Info: {entry_info}")

    # Evaluate valuation (which computes supports/resistances)
    res = evaluate_stock_valuation("VNINDEX", df_rich, entry_info)
    
    print("\n================== VNINDEX EVALUATION ==================")
    print(f"Price: {res.get('price')}")
    print(f"State: {res.get('state')}")
    print(f"Action: {res.get('action')}")
    print(f"Support S1: {res.get('s1')}")
    print(f"Support S2: {res.get('s2')}")
    print(f"Resistance R1: {res.get('r1')}")
    print(f"Resistance R2: {res.get('r2')}")
    print(f"Resistance R3: {res.get('r3')}")
    print(f"Cutloss Partial (SL): {res.get('cutloss_partial')}")
    print(f"Cutloss Full (Sell all): {res.get('cutloss_full')}")
    print(f"Trailing Stop: {res.get('trailing_stop')}")
    print("========================================================")

if __name__ == "__main__":
    inspect_vnindex()
