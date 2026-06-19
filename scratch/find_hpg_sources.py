import os
from pathlib import Path

print("=== Searching for HPG.parquet ===")
for root, dirs, files in os.walk("."):
    for f in files:
        if "HPG" in f.upper():
            p = Path(root) / f
            print(f"Found: {p} (Size: {p.stat().st_size} bytes, Modified: {p.stat().st_mtime})")
