import pandas as pd
from pathlib import Path

parquet_path = Path("data_storage/prices/HPG.parquet")
if parquet_path.exists():
    df = pd.read_parquet(parquet_path)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Filter for dates from 2026-02-01 onwards
    df_filtered = df[df['Date'] >= '2026-02-01'].sort_values('Date')
    
    print(f"HPG rows from 2026-02-01 onwards: {len(df_filtered)}")
    # Print the date, open, high, low, close, volume, source
    pd.set_option('display.max_rows', 150)
    print(df_filtered[['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'source']])
else:
    print("HPG.parquet not found")
