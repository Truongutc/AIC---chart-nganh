import os
import sys
import pandas as pd
import shutil
from pathlib import Path

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')

from tinvest.data_loader import _normalize_columns, _clean_dataframe
from tinvest.storage_manager import StorageManager

def test_index_db_write():
    print("=== STARTING INDEX DB WRITE TEST ===")
    csv_path = "import_data/CafeF.INDEX.Upto07.05.2026.csv"
    
    # 1. Back up existing parquet files
    storage = StorageManager()
    vn_parquet = storage._get_price_path("VNINDEX")
    vn_backup = Path("data_storage/prices/VNINDEX.parquet.backup")
    if vn_parquet.exists():
        shutil.copyfile(vn_parquet, vn_backup)
        print("[+] Created backup of VNINDEX.parquet")
        
    try:
        # Load and clean
        df_raw = pd.read_csv(csv_path)
        df_norm = _normalize_columns(df_raw)
        
        # Get VNINDEX data
        vn_group = df_norm[df_norm["Ticker"] == "VNINDEX"].drop(columns=["Ticker"]).copy()
        clean_vn = _clean_dataframe(vn_group, ticker="VNINDEX")
        print(f"[+] Loaded VNINDEX CSV data: {len(clean_vn)} rows, from {clean_vn['Date'].min()} to {clean_vn['Date'].max()}")
        
        # Inspect current parquet file
        df_old = pd.read_parquet(vn_parquet)
        print(f"[+] Current VNINDEX parquet on disk: {len(df_old)} rows, from {df_old['Date'].min()} to {df_old['Date'].max()}")
        
        # Run sync_prices
        t_min = storage.sync_prices("VNINDEX", clean_vn, source='CSV')
        print(f"[+] sync_prices returned t_min: {t_min}")
        
        # Read it back and verify
        df_new = pd.read_parquet(vn_parquet)
        print(f"[+] Updated VNINDEX parquet on disk: {len(df_new)} rows, from {df_new['Date'].min()} to {df_new['Date'].max()}")
        print(f"Number of rows with source='CSV': {len(df_new[df_new['source'] == 'CSV'])}")
        print(f"Number of rows with source='API': {len(df_new[df_new['source'] == 'API'])}")
        
    except Exception as e:
        print(f"❌ Error during DB write: {e}")
        
    finally:
        # Restore backup
        if vn_backup.exists():
            shutil.copyfile(vn_backup, vn_parquet)
            os.remove(vn_backup)
            print("[+] Restored backup of VNINDEX.parquet")

if __name__ == "__main__":
    test_index_db_write()
