import os
import sys

# Set python path to current directory
sys.path.append(os.getcwd())

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.chart_exporter import export_ticker_history_json
import logging

logging.basicConfig(level=logging.INFO)

print("[1] Initializing StorageManager...")
storage = StorageManager()

data_dict = {}
analysis_cache = {}

for ticker in ["VNINDEX", "HNX-INDEX"]:
    print(f"[2] Loading {ticker}...")
    df = storage.load_ticker_data(ticker)
    if df is not None and not df.empty:
        print(f"    Loaded {len(df)} rows. Enriching indicators...")
        df_rich = enrich_dataframe(df)
        data_dict[ticker] = df_rich
        analysis_cache[ticker] = {'df': df_rich}
    else:
        print(f"    Failed to load {ticker} data.")

if data_dict:
    print("[3] Exporting history JSON files to Output/history/...")
    output_dir = os.path.join(os.getcwd(), "Output")
    export_ticker_history_json(data_dict, analysis_cache, output_dir)
    print("    Export completed successfully!")
else:
    print("    No data to export.")
