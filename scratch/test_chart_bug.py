import sys
import os
import tkinter as tk
import matplotlib.pyplot as plt

# Add current workspace to path
sys.path.append(r"E:\1. Projects\Code-pro-analys")

# Mock plt.show to prevent blocking
plt.show = lambda *args, **kwargs: print("MOCKED: plt.show() called successfully")

from AICcode import TinvestApp
from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe

if __name__ == '__main__':
    # Initialize Tkinter root in headless mode or just simple Tk
    root = tk.Tk()
    root.withdraw() # Hide GUI window
    
    app = TinvestApp(root)
    df = app.storage.load_ticker_data("AAA")
    
    if df is not None:
        print(f"Loaded ticker AAA, shape: {df.shape}")
        df = enrich_dataframe(df)
        print("Enriched dataframe successfully")
        
        try:
            print("Testing app.show_heikin_window...")
            app.show_heikin_window("AAA", df)
            print("SUCCESS: show_heikin_window ran without exceptions!")
        except Exception as e:
            print(f"show_heikin_window failed: {e}")
            import traceback
            traceback.print_exc()

        try:
            print("Testing app.show_greenpink_window...")
            app.show_greenpink_window("AAA", df)
            print("SUCCESS: show_greenpink_window ran without exceptions!")
        except Exception as e:
            print(f"show_greenpink_window failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("AAA ticker not found in storage!")
