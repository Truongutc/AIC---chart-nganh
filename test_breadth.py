from AICcode import TinvestApp
import pandas as pd
import tkinter as tk
from tinvest.storage_manager import StorageManager
from concurrent.futures import ThreadPoolExecutor

tk_root = tk.Tk()
app = TinvestApp(tk_root)
app.storage = StorageManager()

tickers = app.storage.get_all_tickers()[:50] # Load 50 tickers to check
print(f"Loading {len(tickers)} tickers...")

app.analysis_cache = {}
for t in tickers:
    df = app.storage.load_ticker_data(t)
    if df is not None:
        analysis = app.storage.load_latest_analysis(t)
        if analysis:
            analysis['df'] = df
            app.analysis_cache[t] = analysis

app._update_breadth_from_cache()
mb = app.market_breadth

print(mb.tail(20))
