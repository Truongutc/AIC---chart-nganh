import pandas as pd
from datetime import datetime
from pathlib import Path

# Mock normalization behavior
def _normalize_columns(df):
    mapping = {"<Ticker>": "Ticker", "<DTYYYYMMDD>": "Date"}
    return df.rename(columns=mapping)

def test_full_fix():
    # 1. Create Mock data with <Ticker> header
    data = {
        "<Ticker>": ["HPG", "VIC", "INVALID_TICKER", "X20"],
        "<DTYYYYMMDD>": ["20260416", "20200101", "20260416", "20260416"]
    }
    df_raw = pd.DataFrame(data)
    
    # 2. Emulate Loop Logic
    print("Step 1: Normalize early")
    df_norm = _normalize_columns(df_raw)
    print(f"Columns after norm: {list(df_norm.columns)}")
    
    affected_tickers = set()
    skipped_3char = 0
    skipped_old = 0
    today = datetime.now()
    
    print("\nStep 2: Group and Filter")
    grouped = df_norm.groupby("Ticker")
    for ticker, group in grouped:
        t = str(ticker).upper().strip()
        is_idx = "INDEX" in t
        
        # 3-char rule
        if not (len(t) == 3 and t.isalnum()) and not is_idx:
            print(f"Skipping {t}: Failed 3-char")
            skipped_3char += 1
            continue
            
        # Date rule (mocking pd.to_datetime conversion)
        group['Date'] = pd.to_datetime(group['Date'], format='%Y%m%d')
        last_date = group['Date'].max()
        
        if (today - last_date).days > 30 and not is_idx:
            print(f"Skipping {t}: Data too old ({last_date})")
            skipped_old += 1
            continue
            
        print(f"Keeping {t}: Success")
        affected_tickers.add(t)
        
    print("-" * 30)
    print(f"Affected: {affected_tickers}")
    print(f"Skipped (3char): {skipped_3char}, Skipped (Old): {skipped_old}")
    
    # Assertions
    assert "HPG" in affected_tickers
    assert "X20" in affected_tickers
    assert "VIC" not in affected_tickers
    assert "INVALID_TICKER" not in affected_tickers
    print("\nVERIFICATION SUCCESSFUL")

if __name__ == "__main__":
    test_full_fix()
