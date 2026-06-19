import sys
import os
sys.path.append(r"e:\1. Projects\phan-nay-bi-loi")

import pandas as pd
import numpy as np
import time
from tinvest.data_loader import enrich_dataframe
from tinvest.storage_manager import StorageManager

sm = StorageManager(r"e:\1. Projects\phan-nay-bi-loi\data")
df = sm.load_raw_prices('VNINDEX')
if df is None:
    df = sm.load_raw_prices('SSI') # fallback
    
print(f"Data shape: {df.shape}")

start = time.time()
try:
    df_rich = enrich_dataframe(df)
    print(f"Success! Time taken: {time.time() - start:.4f} seconds")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("FAILED!")
