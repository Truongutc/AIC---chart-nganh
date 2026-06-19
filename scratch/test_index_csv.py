import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')

from tinvest.data_loader import _normalize_columns, _clean_dataframe
from tinvest.storage_manager import StorageManager

def test_index_csv_import():
    print("=== STARTING CAFEF INDEX CSV IMPORT TEST ===")
    csv_path = "import_data/CafeF.INDEX.Upto07.05.2026.csv"
    
    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        return
        
    try:
        # Load the raw CSV
        df_raw = pd.read_csv(csv_path)
        print(f"[+] Loaded CSV. Shape: {df_raw.shape}")
        print("Raw Columns:", list(df_raw.columns))
        
        # Normalize
        df_norm = _normalize_columns(df_raw)
        print("Normalized Columns:", list(df_norm.columns))
        
        # Simulating AICcode.py groupby ticker logic
        if "Ticker" in df_norm.columns:
            grouped = df_norm.groupby("Ticker")
            print(f"Found tickers in CSV: {list(grouped.groups.keys())}")
            
            for ticker_val, group in grouped:
                t = str(ticker_val).upper().strip()
                print(f"\n[*] Processing ticker in loop: '{t}' (raw value: '{ticker_val}')")
                
                # Filter 3-char or index
                is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
                if not (len(t) == 3 and t.isalnum()) and not is_idx:
                    print(f"   [-] Skipped ticker filter: not 3 chars and not index.")
                    continue
                    
                sub_df = group.drop(columns=["Ticker"]).copy()
                try:
                    clean_sub = _clean_dataframe(sub_df, ticker=t)
                    print(f"   [+] Cleaned df: {len(clean_sub)} rows, from {clean_sub['Date'].min()} to {clean_sub['Date'].max()}")
                    
                    # Check the 30-day filter
                    last_date = clean_sub['Date'].max()
                    days_diff = (datetime.now() - last_date).days
                    print(f"   [+] Max date: {last_date.date()} (days diff: {days_diff})")
                    if days_diff > 30 and not is_idx:
                        print(f"   [-] Skipped: too old (> 30 days diff: {days_diff} days)")
                        continue
                        
                    # Simulating database write
                    print(f"   [+] Syncing {t} to database...")
                except Exception as ex:
                    print(f"   [❌] Error cleaning/processing: {ex}")
        else:
            print("❌ No 'Ticker' column found in normalized dataframe!")
            
    except Exception as e:
        print(f"❌ Critical Error during import: {e}")

if __name__ == "__main__":
    test_index_csv_import()
