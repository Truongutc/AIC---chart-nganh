import sys
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager

storage = StorageManager()
df = storage.load_ticker_data("FPT")
if df is not None:
    print(f"Columns in HPG: {list(df.columns)}")
    print(df[['Close', 'Volume']].tail(15))
    
    # Check if indicators are saved in storage
    # Let's see if there is any other files or indicators in df
    print("Checking if indicators are in df:")
    ind_cols = [c for c in df.columns if 'MCDX' in c or 'RSI' in c]
    print(f"Indicator columns: {ind_cols}")
    if ind_cols:
        print(df[ind_cols].tail(15))
else:
    print("No FPT data found.")
