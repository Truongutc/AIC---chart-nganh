import pandas as pd
from pathlib import Path

prices_dir = Path("data_storage/prices")
print("=== Price files ===")
for p in prices_dir.glob("*.parquet"):
    if "INDEX" in p.stem.upper() or "HNX" in p.stem.upper():
        try:
            df = pd.read_parquet(p)
            print(f"{p.name}: {len(df)} rows, from {df['Date'].min()} to {df['Date'].max()}")
        except Exception as e:
            print(f"Error reading {p.name}: {e}")

print("=== Active Registry ===")
import json
reg_path = Path("data_storage/active_tickers.json")
if reg_path.exists():
    with open(reg_path, "r", encoding="utf-8") as f:
        reg = json.load(f)
        indices = [t for t in reg if "INDEX" in t or "HNX" in t]
        print("Indices in active registry:", indices)
else:
    print("No active registry file found")
