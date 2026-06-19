import sys
import os
import tkinter as tk
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from AICcode import TinvestApp, analyze_ticker_worker

TICKERS = ['FPT', 'VCB', 'BID', 'VND', 'SSI']

def main():
    print("=" * 50)
    print(f"RECALCULATING: {', '.join(TICKERS)}")
    print("=" * 50)

    root = tk.Tk()
    root.withdraw()
    app = TinvestApp(root)

    def mock_log_sync(message, clear=False):
        try:
            print(f"[App] {message}")
        except UnicodeEncodeError:
            print(f"[App] {message.encode('ascii', 'ignore').decode('ascii')}")

    app.log_sync = mock_log_sync
    app.data_dict = {}
    app.analysis_cache = {}

    tickers = [t for t in TICKERS if app.storage._get_price_path(t).exists()]
    missing = [t for t in TICKERS if t not in tickers]
    if missing:
        print(f"[!] Tickers not found in storage: {missing}")

    total = len(tickers)
    print(f"[*] Processing {total} tickers...")

    for idx, ticker in enumerate(tickers):
        print(f"\n[{idx+1}/{total}] Calculating {ticker}...")
        try:
            df = app.storage.load_ticker_data(ticker)
            if df is not None and not df.empty:
                t_val, res = analyze_ticker_worker((ticker, df))
                if res:
                    app.data_dict[t_val] = res["df"]
                    app.analysis_cache[t_val] = res
                    app.storage.save_analysis(t_val, res)
                    print(f"    -> {ticker}: OK")
                else:
                    print(f"    -> {ticker}: analyze_ticker_worker returned None")
            else:
                print(f"    -> {ticker}: No data loaded")
        except Exception as e:
            print(f"    -> {ticker}: ERROR - {e}")
            traceback.print_exc()

    print("\n[*] Calculating market breadth...")
    app._update_breadth_from_cache()

    print("[*] Exporting analysis_results.json...")
    try:
        success = app.export_web_json()
        if success:
            print("\nSUCCESS! JSON updated. Refresh localhost to see new results.")
        else:
            print("\nFAILURE! export_web_json returned False.")
    except Exception:
        print("\nCRITICAL ERROR during export:")
        traceback.print_exc()

    root.destroy()

if __name__ == "__main__":
    main()
