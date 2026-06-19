import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

import tinvest.data_loader as dl

def create_index_stats_v3():
    p_path = Path(r"e:\1. Projects\2. Codeinvest\Codeinvest\data_storage\prices\VNINDEX.parquet")
    df = pd.read_parquet(p_path)
    df = dl.enrich_dataframe(df)
    
    ma20, ma50 = df['MA20'], df['MA50']
    c = df['Close']
    is_downtrend = (c < ma50) & (ma20 < ma50)
    
    # 63-day ROC (Performance over last quarter)
    df['ROC63'] = ((df['Close'] - df['Close'].shift(63)) / df['Close'].shift(63)) * 100
    
    stats = pd.DataFrame({
        "Date": df["Date"],
        "index_state": np.where(is_downtrend, "DOWNTREND", "UPTREND"),
        "index_roc63": df['ROC63']
    })
    
    # T-1 states
    stats["index_state_T1"] = stats["index_state"].shift(1)
    stats["index_roc63_T1"] = stats["index_roc63"].shift(1)
    
    stats.to_csv("VNINDEX_stats_v3.csv", index=False)
    print("VNINDEX_stats_v3.csv created.")

if __name__ == "__main__":
    create_index_stats_v3()
