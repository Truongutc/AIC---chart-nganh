import pandas as pd
from pathlib import Path

csv_path = Path("import_data/CafeF.HSX.Upto07.05.2026.csv")
parquet_path = Path("data_storage/prices/HPG.parquet")

print("=== CHECKING RAW CSV FOR HPG ===")
if csv_path.exists():
    # Read only required columns if possible, but let's read the whole file chunk by chunk or filter
    # To save memory and time, let's filter HPG rows.
    chunks = []
    # Read in chunks of 50000 rows
    for chunk in pd.read_csv(csv_path, chunksize=50000):
        # Normalize headers first
        lower_cols = {c: c.lower().strip().replace(" ", "_").replace("<", "").replace(">", "") for c in chunk.columns}
        chunk = chunk.rename(columns=lower_cols)
        # Find ticker column
        ticker_col = None
        for alias in ["ticker", "symbol", "ma_ck", "mã_ck", "stock", "code", "name"]:
            if alias in chunk.columns:
                ticker_col = alias
                break
        if ticker_col:
            hpg_chunk = chunk[chunk[ticker_col].astype(str).str.upper().str.strip() == "HPG"]
            chunks.append(hpg_chunk)
    
    if chunks:
        df_csv = pd.concat(chunks, ignore_index=True)
        print(f"Total HPG rows in CSV: {len(df_csv)}")
        print("CSV Columns:", df_csv.columns.tolist())
        # Check duplicate dates in CSV
        date_col = None
        for alias in ["date", "time", "datetime", "ngay", "ngày", "trading_date", "dtyyyymmdd", "dtyyyymm", "date_time", "dtdate"]:
            if alias in df_csv.columns:
                date_col = alias
                break
        if date_col:
            df_csv['ParsedDate'] = pd.to_datetime(df_csv[date_col].astype(str).str.replace(r"\.0$", "", regex=True), errors='coerce')
            dups = df_csv[df_csv.duplicated(subset=['ParsedDate'], keep=False)]
            print(f"Number of duplicate dates in CSV: {len(dups)}")
            if len(dups) > 0:
                print("First few duplicate rows:")
                print(dups.sort_values('ParsedDate').head(10))
        print("First 5 CSV rows:")
        print(df_csv.head(5))
    else:
        print("No HPG rows found in CSV")
else:
    print("CafeF.HSX.Upto07.05.2026.csv does not exist")

print("\n=== CHECKING PARQUET STORAGE FOR HPG ===")
if parquet_path.exists():
    df_pq = pd.read_parquet(parquet_path)
    print(f"Total HPG rows in parquet: {len(df_pq)}")
    print("Parquet Columns:", df_pq.columns.tolist())
    print("Date range in parquet:", df_pq['Date'].min(), "to", df_pq['Date'].max())
    
    # Check duplicate dates
    dups_pq = df_pq[df_pq.duplicated(subset=['Date'], keep=False)]
    print(f"Number of duplicate dates in parquet: {len(dups_pq)}")
    if len(dups_pq) > 0:
        print("Duplicate rows in parquet:")
        print(dups_pq.sort_values('Date').head(10))
        
    # Check if dates are sorted chronologically
    is_sorted = df_pq['Date'].is_monotonic_increasing
    print("Is parquet sorted chronologically?", is_sorted)
    
    # Display last 10 rows to see actual price structure
    print("Last 10 parquet rows:")
    print(df_pq.tail(10))
else:
    print("HPG.parquet does not exist in data_storage/prices/")
