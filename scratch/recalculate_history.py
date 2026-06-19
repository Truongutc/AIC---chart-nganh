import os
import sys
import glob

# Add base path to sys.path
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

from tinvest.storage_manager import StorageManager
from tinvest.chart_exporter import export_ticker_history_json

def main():
    print("Initializing StorageManager...")
    storage = StorageManager()
    output_dir = "Output"

    # Load VNINDEX first for RS calculation
    data_dict = {}
    print("Loading VNINDEX...")
    vn_df = storage.load_ticker_data("VNINDEX")
    if vn_df is not None:
        data_dict["VNINDEX"] = vn_df

    # Find tickers that already have history JSON files
    history_files = glob.glob(os.path.join(output_dir, "history", "*.json"))
    tickers = [os.path.splitext(os.path.basename(f))[0].upper() for f in history_files]
    
    print(f"Found {len(tickers)} tickers in history. Loading price data...")
    for t in tickers:
        if t == "VNINDEX":
            continue
        df = storage.load_ticker_data(t)
        if df is not None:
            data_dict[t] = df

    print(f"Loaded {len(data_dict)} tickers. Running export_ticker_history_json...")
    export_ticker_history_json(data_dict, {}, output_dir)
    print("History recalculation complete!")

if __name__ == "__main__":
    main()
