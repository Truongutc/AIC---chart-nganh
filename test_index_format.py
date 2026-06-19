from tinvest.vietstock_client import VietstockClient
import pandas as pd
import json

vc = VietstockClient()
vc.refresh_from_config()

date_str = "2026-03-31"
ticker = "VNINDEX"
tid = 1
sid = -19

idx_raw = vc.fetch_index_day(ticker, tid, sid, date_str)
print(f"Raw Index JSON: {json.dumps(idx_raw, indent=2)}")

if idx_raw:
    df = vc.format_to_df(idx_raw)
    print("\nFormatted DataFrame:")
    print(df)
    print("\nColumns:", df.columns.tolist())
    if not df.empty:
        print("\nFirst row:", df.iloc[0].to_dict())
