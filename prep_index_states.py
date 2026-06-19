import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def create_index_states():
    p_path = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices\VNINDEX.parquet")
    df = pd.read_parquet(p_path)
    df = dl.enrich_dataframe(df)
    
    # Replicate state_engine logic briefly
    ma20 = df['MA20']
    ma50 = df['MA50']
    c = df['Close']
    
    # Simplified Downtrend: C < MA50 and MA20 < MA50
    is_downtrend = (c < ma50) & (ma20 < ma50)
    
    states = pd.DataFrame({
        "Date": df["Date"],
        "index_state": np.where(is_downtrend, "DOWNTREND", "UPTREND")
    })
    
    # Shift to get T-1 state for Day T
    states["index_state_T1"] = states["index_state"].shift(1)
    
    states.to_csv("VNINDEX_states_T1.csv", index=False)
    print("VNINDEX_states_T1.csv created.")

if __name__ == "__main__":
    create_index_states()
