import pandas as pd
import numpy as np
from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.whatif_engine import run_whatif_analysis

print('[1] Loading VND...')
storage = StorageManager()
df = storage.load_ticker_data("VND")
if df is None:
    print("No VND data found.")
    exit(1)

print('[2] Enriching dataframe...')
df_rich = enrich_dataframe(df.copy())
print(f'    Columns: {len(df_rich.columns)} total')

print('[3] Running What-If analysis...')
result = run_whatif_analysis('VND', df_rich, top_n=20, compute_forecast_series=True, forecast_days=90)

err = result.get('error')
if err:
    print(f'ERROR: {err}')
else:
    print(f'    Ticker: {result["ticker"]}')
    print(f'    Price:  {result["price"]}')
    print(f'    Zones:  {len(result["zones"])} zones')
    print(f'    Matches: {len(result.get("matches", []))} analogs')
    print(f'    Warning: {result.get("match_quality", {}).get("warning")}')
    print(f'    Forecast Series Length: {len(result.get("forecast_series", []))}')

print('[OK] Full analysis completed successfully!')
