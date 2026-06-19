import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Reconfigure stdout/stderr for Windows UTF-8
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')

from tinvest.data_loader import _normalize_columns, _clean_dataframe
from tinvest.storage_manager import StorageManager

def test_hpg_sync():
    print("=== STARTING HPG SYNC TEST ===")
    
    # 1. Reconstruct the user's HPG CSV data from the screenshot
    # Prepend mock data for 200 trading days prior to 2026-05-04
    data = []
    # Generates dates going backward
    curr_date = datetime(2026, 4, 30)
    while len(data) < 200:
        if curr_date.weekday() < 5:
            d_str = curr_date.strftime("%Y%m%d")
            # Using unadjusted-like mock prices for April and earlier
            data.append(["HPG", d_str, 28.0, 28.5, 27.5, 28.0, 10000000])
        curr_date -= timedelta(days=1)
    
    # Reverse so dates are ascending for prepending
    data.reverse()

    # Append the actual 19 rows from the screenshot
    actual_rows = [
        ["HPG", "20260528", 24.15, 24.25, 24.0, 24.0, 15668300],
        ["HPG", "20260527", 24.4, 24.5, 24.15, 24.15, 23114500],
        ["HPG", "20260526", 24.1, 24.25, 24.0, 24.25, 20723700],
        ["HPG", "20260525", 24.25, 24.35, 24.1, 24.1, 26989100],
        ["HPG", "20260522", 24.1821, 24.2275, 23.9548, 23.9548, 25794000],
        ["HPG", "20260521", 23.9522, 24.2703, 23.9067, 24.1366, 30562500],
        ["HPG", "20260520", 23.9067, 23.9976, 23.4068, 23.8184, 40983800],
        ["HPG", "20260519", 24.0912, 24.2275, 23.8639, 23.8639, 25111900],
        ["HPG", "20260518", 24.0912, 24.273, 23.8639, 24.0457, 27485500],
        ["HPG", "20260515", 24.5885, 24.6339, 24.0431, 24.1366, 75838200],
        ["HPG", "20260514", 24.8184, 24.9093, 24.5912, 24.5912, 14047100],
        ["HPG", "20260513", 24.4976, 24.7703, 24.3612, 24.6366, 21544700],
        ["HPG", "20260512", 24.5457, 24.7275, 24.4093, 24.4548, 19170900],
        ["HPG", "20260511", 25.0003, 25.0003, 24.5457, 24.5457, 23658100],
        ["HPG", "20260508", 24.7724, 24.9063, 24.5939, 24.8627, 20678200],
        ["HPG", "20260507", 24.8171, 24.9063, 24.6385, 24.7734, 20348100],
        ["HPG", "20260506", 24.46, 24.8171, 24.3707, 24.6395, 27672000],
        ["HPG", "20260505", 24.6832, 24.7278, 24.2814, 24.3717, 30692800],
        ["HPG", "20260504", 24.7724, 24.951, 24.46, 24.6395, 32374300],
    ]
    data.extend(actual_rows)
    columns = ["<Ticker>", "<DTYYYYMMDD>", "<Open>", "<High>", "<Low>", "<Close>", "<Volume>"]
    df_raw = pd.DataFrame(data, columns=columns)
    
    # 2. Write it to a temporary CSV file
    csv_path = "scratch/HPG_test.csv"
    df_raw.to_csv(csv_path, index=False)
    print(f"[+] Saved reconstructed CSV to {csv_path}")
    
    # 3. Read it back and normalize/clean like AICcode.py does
    df_read = pd.read_csv(csv_path)
    print("Columns read from CSV:", list(df_read.columns))
    
    df_norm = _normalize_columns(df_read)
    print("Columns after normalization:", list(df_norm.columns))
    
    # Check HPG dataframe extraction
    group = df_norm[df_norm["Ticker"] == "HPG"].drop(columns=["Ticker"]).copy()
    clean_df = _clean_dataframe(group, ticker="HPG")
    print(f"Cleaned dataframe: {len(clean_df)} rows, from {clean_df['Date'].min()} to {clean_df['Date'].max()}")
    print(clean_df.head(5))
    
    # 4. Save current parquet backup
    storage = StorageManager()
    hpg_parquet_path = storage._get_price_path("HPG")
    hpg_backup_path = Path("data_storage/prices/HPG.parquet.backup")
    if hpg_parquet_path.exists():
        import shutil
        shutil.copyfile(hpg_parquet_path, hpg_backup_path)
        print("[+] Created backup of HPG.parquet")
    
    # 5. Call sync_prices
    print("\n[*] Syncing constructed CSV data to storage...")
    t_min = storage.sync_prices("HPG", clean_df, source='CSV')
    print(f"[*] sync_prices returned t_min: {t_min}")
    
    # 6. Read updated parquet and inspect May 11 - May 28 rows
    df_updated = pd.read_parquet(hpg_parquet_path)
    print("\n=== UPDATED HPG PARQUET TAIL (May 11 - May 28) ===")
    may_rows = df_updated[df_updated["Date"] >= "2026-05-04"]
    print(may_rows.to_string())
    
    # Restore backup
    if hpg_backup_path.exists():
        shutil.copyfile(hpg_backup_path, hpg_parquet_path)
        os.remove(hpg_backup_path)
        print("[+] Restored backup of HPG.parquet")

if __name__ == "__main__":
    test_hpg_sync()
