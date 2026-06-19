import os
import sys
import shutil
import pandas as pd

# Add parent directory of scratch to sys.path to find tinvest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from tinvest.storage_manager import StorageManager
from run_headless_update import run_csv_import

def generate_test_csvs(dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    
    # Base date
    end_date = datetime.now() - timedelta(days=1) # 2026-05-24
    
    # PHP_HNX.csv: 250 rows ending on 2025-10-01 (older data, > 30 days ago)
    hnx_end = datetime(2025, 10, 1)
    hnx_dates = [hnx_end - timedelta(days=i) for i in range(250)]
    hnx_dates.reverse()
    
    hnx_data = {
        'Date': [d.strftime('%Y%m%d') for d in hnx_dates],
        'Open': [10.0 + i * 0.01 for i in range(250)],
        'High': [10.5 + i * 0.01 for i in range(250)],
        'Low': [9.5 + i * 0.01 for i in range(250)],
        'Close': [10.2 + i * 0.01 for i in range(250)],
        'Volume': [100000] * 250
    }
    df_hnx = pd.DataFrame(hnx_data)
    df_hnx.to_csv(os.path.join(dest_dir, "PHP_HNX.csv"), index=False)
    
    # PHP_UPCOM.csv: 50 rows starting on 2025-10-02 and ending on 2026-05-24 (recent data, but < 200 rows)
    upcom_dates = [end_date - timedelta(days=i) for i in range(50)]
    upcom_dates.reverse()
    
    upcom_data = {
        'Date': [d.strftime('%Y%m%d') for d in upcom_dates],
        'Open': [20.0 + i * 0.02 for i in range(50)],
        'High': [20.8 + i * 0.02 for i in range(50)],
        'Low': [19.2 + i * 0.02 for i in range(50)],
        'Close': [20.1 + i * 0.02 for i in range(50)],
        'Volume': [150000] * 50
    }
    df_upcom = pd.DataFrame(upcom_data)
    df_upcom.to_csv(os.path.join(dest_dir, "PHP_UPCOM.csv"), index=False)
    print(f"Generated test CSV files in {dest_dir}")

def test_merge_and_import():
    test_dir = "scratch/temp_verify_data"
    generate_test_csvs(test_dir)
    
    # Initialize storage manager
    storage = StorageManager()
    
    # Clear previous PHP data if exists
    php_price_path = storage._get_price_path("PHP")
    if php_price_path.exists():
        php_price_path.unlink()
        print("Removed existing PHP parquet file from storage.")
        
    php_ind_path = storage._get_indicators_path("PHP")
    if php_ind_path.exists():
        php_ind_path.unlink()
        
    php_ana_path = storage._get_analysis_path("PHP")
    if php_ana_path.exists():
        php_ana_path.unlink()
        
    try:
        print("Running run_csv_import with test directory...")
        # Run import
        run_csv_import([test_dir])
        
        # Verify
        if not php_price_path.exists():
            print("❌ Failure: PHP was NOT loaded and saved to storage!")
            return False
            
        df_loaded = pd.read_parquet(php_price_path)
        print(f"Loaded PHP data size: {len(df_loaded)} rows.")
        
        if len(df_loaded) != 300:
            print(f"❌ Failure: Expected 300 merged rows, but loaded {len(df_loaded)} rows.")
            return False
            
        # Check first and last dates
        first_date = pd.to_datetime(df_loaded['Date'].iloc[0]).strftime('%Y-%m-%d')
        last_date = pd.to_datetime(df_loaded['Date'].iloc[-1]).strftime('%Y-%m-%d')
        print(f"PHP Date range: {first_date} to {last_date}")
        
        # Check if we have HNX price range (around 10.0) and UPCOM price range (around 20.0)
        has_hnx_price = (df_loaded['Close'] < 15.0).any()
        has_upcom_price = (df_loaded['Close'] > 19.0).any()
        
        if not (has_hnx_price and has_upcom_price):
            print("❌ Failure: Loaded PHP data does not contain both HNX and UPCOM prices!")
            return False
            
        print("✅ SUCCESS: PHP was successfully grouped, merged, cleaned, filtered, and saved!")
        return True
        
    finally:
        # Cleanup temp directory
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"Cleaned up test directory {test_dir}")

if __name__ == "__main__":
    test_merge_and_import()
