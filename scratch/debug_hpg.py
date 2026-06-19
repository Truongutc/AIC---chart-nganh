import os
import sys
import pandas as pd

base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

def debug_vip():
    p_file = "data_storage/prices/VIP.parquet"
    df = pd.read_parquet(p_file)
    print(df[['Date', 'Close', 'High', 'Low', 'Volume', 'source', 'updated_at']].tail(10))

if __name__ == "__main__":
    debug_vip()
