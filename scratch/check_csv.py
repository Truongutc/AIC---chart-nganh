import pandas as pd
from pathlib import Path

csv_path = Path("import_data/CafeF.INDEX.Upto07.05.2026.csv")
if csv_path.exists():
    df = pd.read_csv(csv_path)
    print("CSV Shape:", df.shape)
    print("Columns:", df.columns.tolist())
    print("First 5 rows:")
    print(df.head())
    print("Last 5 rows:")
    print(df.tail())
    # Check tickers
    if 'Ticker' in df.columns:
        print("Tickers:", df['Ticker'].unique().tolist())
    elif '<Ticker>' in df.columns:
        print("Tickers:", df['<Ticker>'].unique().tolist())
else:
    print("CSV path does not exist")
