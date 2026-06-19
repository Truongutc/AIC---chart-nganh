import pandas as pd
import os
from tinvest.storage_manager import StorageManager

def check_mbb():
    storage = StorageManager()
    df = storage.load_ticker_data("MBB")
    if df is not None:
        print(f"--- MBB Local Storage (Last 5 rows) ---")
        print(df.tail(5))
    else:
        print("MBB not found in local storage.")

if __name__ == "__main__":
    check_mbb()
