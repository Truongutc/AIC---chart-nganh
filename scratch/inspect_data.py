import os
import pandas as pd
from pathlib import Path

prices_dir = Path("data_storage/prices")
files = list(prices_dir.glob("*.parquet"))
print(f"Total price Parquet files: {len(files)}")

if files:
    # Get sizes and row counts for a few files
    stats = []
    for f in files[:10]:
        df = pd.read_parquet(f)
        stats.append({
            "Ticker": f.stem,
            "Rows": len(df),
            "Min Date": df['Date'].min(),
            "Max Date": df['Date'].max()
        })
    print(pd.DataFrame(stats))
