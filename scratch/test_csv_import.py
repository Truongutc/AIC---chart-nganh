import os
import sys

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import subprocess

def test_import():
    print("=== STARTING CSV IMPORT TEST ===")
    
    # 1. Generate mock data for stock AAA (250 days)
    np.random.seed(42)
    start_date = datetime.now() - timedelta(days=350)
    dates = []
    current = start_date
    while len(dates) < 250:
        if current.weekday() < 5:  # Weekdays only
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
        
    closes = []
    price = 10.0
    for _ in range(250):
        price = price * (1.0 + np.random.normal(0.0, 0.015))
        closes.append(round(price, 2))
        
    df = pd.DataFrame({
        "Date": dates,
        "Open": [round(c * (1.0 + np.random.normal(0.0, 0.005)), 2) for c in closes],
        "High": [round(c * 1.02, 2) for c in closes],
        "Low": [round(c * 0.98, 2) for c in closes],
        "Close": closes,
        "Volume": [int(np.random.randint(50000, 500000)) for _ in range(250)]
    })
    
    csv_dir = "scratch"
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "AAA.csv")
    df.to_csv(csv_path, index=False)
    print(f"[+] Created mock CSV at: {csv_path} with {len(df)} rows.")
    
    # 2. Run the update script with --import-csv
    cmd = ["python", "run_headless_update.py", "--import-csv", csv_path]
    print(f"[*] Running command: {' '.join(cmd)}")
    
    # Run the command and capture output
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    print("--- STDOUT ---")
    print(result.stdout)
    print("--- STDERR ---")
    print(result.stderr)
    
    if result.returncode == 0:
        print("✅ Command finished successfully!")
        
        # Verify database files
        price_parquet = "data_storage/prices/AAA.parquet"
        indicator_parquet = "data_storage/indicators/AAA.parquet"
        analysis_json = "data_storage/analysis/AAA.json"
        
        print("\n=== VERIFYING STORAGE ===")
        if os.path.exists(price_parquet):
            print(f"✅ Price Parquet exists at: {price_parquet}")
            df_p = pd.read_parquet(price_parquet)
            print(f"   Rows: {len(df_p)}, Columns: {list(df_p.columns)}")
        else:
            print(f"❌ Price Parquet missing: {price_parquet}")
            
        if os.path.exists(indicator_parquet):
            print(f"✅ Indicator Parquet exists at: {indicator_parquet}")
            df_i = pd.read_parquet(indicator_parquet)
            print(f"   Rows: {len(df_i)}, Columns: {list(df_i.columns[:10])}...")
        else:
            print(f"❌ Indicator Parquet missing: {indicator_parquet}")
            
        if os.path.exists(analysis_json):
            print(f"✅ Analysis JSON exists at: {analysis_json}")
        else:
            print(f"❌ Analysis JSON missing: {analysis_json}")
            
        # Verify output json
        output_results = "Output/analysis_results.json"
        if os.path.exists(output_results):
            print(f"✅ Output analysis JSON exists at: {output_results}")
            import json
            with open(output_results, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tickers = [t["Ticker"] for t in data.get("tickers_analysis", [])]
                print(f"   Total tickers in dashboard output: {len(tickers)}")
                if "AAA" in tickers:
                    print("   ✅ Ticker 'AAA' successfully compiled into final dashboard JSON!")
                else:
                    print("   ❌ Ticker 'AAA' missing from dashboard JSON (maybe filtered by volume/rules?)")
        else:
            print(f"❌ Output analysis JSON missing: {output_results}")
    else:
        print(f"❌ Command failed with return code {result.returncode}")

if __name__ == "__main__":
    test_import()
