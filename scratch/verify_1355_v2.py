import pandas as pd
import glob
import os
from datetime import datetime
import sys

# Set output encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

path = r'D:\Github\CafeF.Index.Upto26032026'
files = glob.glob(os.path.join(path, "*.csv"))

now = datetime(2026, 5, 10)
ticker_last_dates = {}

for f in files:
    try:
        df = pd.read_csv(f)
        cols = {c: c.lower().strip().replace("<", "").replace(">", "") for c in df.columns}
        df = df.rename(columns=cols)
        
        if 'ticker' not in df.columns: continue
        if 'dtyyyymmdd' in df.columns: date_col = 'dtyyyymmdd'
        elif 'date' in df.columns: date_col = 'date'
        else: continue
            
        grouped = df.groupby('ticker')
        for t_val, group in grouped:
            t = str(t_val).upper().strip()
            is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
            if not (len(t) == 3 and t.isalnum()) and not is_idx:
                continue
            try:
                date_series = group[date_col].astype(str).str.replace(r"\.0$", "", regex=True)
                if date_series.str.match(r"^\d{8}$").all():
                    last_d = pd.to_datetime(date_series.max(), format="%Y%m%d")
                else:
                    last_d = pd.to_datetime(date_series.max(), errors="coerce")
            except: continue
            if pd.isna(last_d): continue
            if t not in ticker_last_dates or last_d > ticker_last_dates[t]:
                ticker_last_dates[t] = last_d
    except Exception as e:
        print(f"Error processing {f}: {e}")

valid_tickers = []
skipped_old = []

for t, last_d in ticker_last_dates.items():
    is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
    days_diff = (now - last_d).days
    if days_diff > 30 and not is_idx:
        skipped_old.append((t, last_d, days_diff))
    else:
        valid_tickers.append((t, last_d))

print(f"--- DATA STATISTICS ---")
print(f"Current Reference Date: {now.strftime('%Y-%m-%d')}")
print(f"Total 3-char/Index tickers found in CSVs: {len(ticker_last_dates)}")
print(f"Valid tickers (traded within last 30 days): {len(valid_tickers)}")
print(f"Skipped tickers (no trade for > 30 days): {len(skipped_old)}")

print("\nExamples of skipped tickers (last trade > 30 days ago):")
skipped_old.sort(key=lambda x: x[2])
for t, d, diff in skipped_old[:20]:
    print(f"  - {t}: Last trade {d.strftime('%Y-%m-%d')} ({diff} days ago)")

print("\n--- CONCLUSION ---")
if abs(len(valid_tickers) - 1355) < 5:
    print(f"The number 1355 is ACCURATE based on the 30-day filter.")
else:
    print(f"The calculation resulted in {len(valid_tickers)} tickers.")
