import os
import pandas as pd
from pathlib import Path

def find_corrupted():
    prices_dir = Path("data_storage/prices")
    indicators_dir = Path("data_storage/indicators")
    
    print("=== Scanning Prices Parquet files ===")
    for p in prices_dir.glob("*.parquet"):
        try:
            pd.read_parquet(p, columns=['Date'])
        except Exception as e:
            print(f"CORRUPTED PRICE FILE: {p.name} - size: {p.stat().st_size} bytes - Error: {e}")
            
    print("=== Scanning Indicators Parquet files ===")
    for p in indicators_dir.glob("*.parquet"):
        try:
            pd.read_parquet(p, columns=['Date'])
        except Exception as e:
            print(f"CORRUPTED INDICATOR FILE: {p.name} - size: {p.stat().st_size} bytes - Error: {e}")

if __name__ == "__main__":
    find_corrupted()
