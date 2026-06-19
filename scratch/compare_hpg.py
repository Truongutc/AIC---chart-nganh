import pandas as pd
import os
import glob

# 1. Check local files in 0. Data gia co phieu
local_dir = "e:/1. Projects/0. Data gia co phieu"

# 3. Read DXG from local CSV (0. Data gia co phieu)
local_hsx = os.path.join(local_dir, "CafeF.HSX.Upto28.05.2026.csv")
if os.path.exists(local_hsx):
    print("\nReading DXG from local HSX CSV (first 5 rows for DXG)...")
    df_local = pd.read_csv(local_hsx)
    # Normalize headers
    df_local.columns = [c.strip().replace("<", "").replace(">", "") for c in df_local.columns]
    df_dxg_local = df_local[df_local['Ticker'] == 'DXG']
    
    # Check May 12, 2026
    sub = df_dxg_local[df_dxg_local['DTYYYYMMDD'] == 20260512]
    print("\nDXG on May 12 in local CSV:")
    print(sub)
else:
    print(f"\nLocal HSX CSV not found at {local_hsx}")

# 4. Read DXG from import_data CSV
import_dir = "import_data"
import_hsx = os.path.join(import_dir, "CafeF.HSX.Upto07.05.2026.csv")
if os.path.exists(import_hsx):
    print("\nReading DXG from import_data HSX CSV (first 5 rows for DXG)...")
    df_import = pd.read_csv(import_hsx)
    df_import.columns = [c.strip().replace("<", "").replace(">", "") for c in df_import.columns]
    df_dxg_import = df_import[df_import['Ticker'] == 'DXG']
    
    # Check May 12, 2026
    sub_import = df_dxg_import[df_dxg_import['DTYYYYMMDD'] == 20260512]
    print("\nDXG on May 12 in import_data CSV:")
    print(sub_import)
else:
    print(f"\nimport_data HSX CSV not found at {import_hsx}")
