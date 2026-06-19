import pandas as pd
from pathlib import Path

parquet_path = Path("data_storage/prices/VNINDEX.parquet")
if parquet_path.exists():
    df = pd.read_parquet(parquet_path)
    print("Parquet Shape:", df.shape)
    print("Columns:", df.columns.tolist())
    print("First 5 rows:")
    print(df.head())
    print("Last 5 rows:")
    print(df.tail())
else:
    print("Parquet path does not exist")
