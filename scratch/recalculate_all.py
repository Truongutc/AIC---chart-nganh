import sys
import os
import tkinter as tk
import traceback

# Add parent directory to path so python can import AICcode
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from AICcode import TinvestApp, analyze_ticker_worker
from tinvest.storage_manager import StorageManager

def main():
    print("==================================================")
    print("RECALCULATING VN30 TICKERS FOR FAST LOCAL TESTING")
    print("==================================================")
    
    # Initialize Tkinter root headlessly
    print("[*] Initializing app...")
    root = tk.Tk()
    root.withdraw()
    app = TinvestApp(root)

    # Mock log_sync with encoding error fallback
    def mock_log_sync(message, clear=False):
        try:
            print(f"[App Log] {message}")
        except UnicodeEncodeError:
            clean_msg = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[App Log] {clean_msg}")
            
    app.log_sync = mock_log_sync

    # Limit to VN30 tickers + VNINDEX for breadth
    vn30_tickers = [
        'ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 
        'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 
        'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE',
        'VNINDEX'
    ]

    # Load only these tickers if they exist in storage
    tickers = [t for t in vn30_tickers if app.storage._get_price_path(t).exists()]
    total = len(tickers)
    print(f"[*] Found {total} testing tickers in storage. Starting recalculation...")

    # Reset in-memory cache
    app.data_dict = {}
    app.analysis_cache = {}

    # Run calculations for each ticker
    for idx, ticker in enumerate(tickers):
        try:
            df = app.storage.load_ticker_data(ticker)
            if df is not None and not df.empty:
                # Recalculate indicators
                t_val, res = analyze_ticker_worker((ticker, df))
                if res:
                    app.data_dict[t_val] = res["df"]
                    app.analysis_cache[t_val] = res
                    # Save recalculated analysis to storage
                    app.storage.save_analysis(t_val, res)
        except Exception as e:
            print(f"   ! Error on ticker {ticker}: {e}")
            
        print(f" ---> Progress: {idx + 1}/{total} tickers processed ({ticker})...")

    print("[*] Calculating market breadth...")
    app._update_breadth_from_cache()

    print("[*] Exporting analysis_results.json...")
    try:
        success = app.export_web_json()
        if success:
            print("SUCCESS! Local data has been successfully updated.")
        else:
            print("FAILURE! Failed to export JSON data.")
    except Exception as ex:
        print("CRITICAL ERROR during export:")
        traceback.print_exc()
        
    # Destroy root safely
    root.destroy()

if __name__ == "__main__":
    main()
