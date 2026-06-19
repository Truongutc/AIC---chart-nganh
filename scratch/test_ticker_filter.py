import pandas as pd
from datetime import datetime, timedelta

def test_filtering_logic(tickers_data):
    """
    Simulates the filtering logic in _process_files_bg.
    tickers_data: list of (ticker, last_date_str)
    """
    affected_tickers = set()
    today = datetime.now()
    
    print(f"Current Time: {today}")
    print("-" * 30)
    
    for t_raw, last_date_str in tickers_data:
        t = str(t_raw).upper().strip()
        
        # 1. Strict 3-char filter (except indices)
        is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
        if not (len(t) == 3 and t.isalnum()) and not is_idx:
            print(f"Skipping {t}: Failed 3-char rule")
            continue
            
        # 2. Recency filter (last 30 days)
        last_date = pd.to_datetime(last_date_str)
        if (today - last_date).days > 30 and not is_idx:
            print(f"Skipping {t}: Data too old ({last_date_str})")
            continue
            
        affected_tickers.add(t)
        print(f"Keeping {t}: Valid (Last date: {last_date_str})")

    return affected_tickers

# Test cases
test_data = [
    ("HPG", "2026-04-16"),   # Valid
    ("VIC", "2026-03-10"),   # Old data (>30 days from 2026-04-17)
    ("SAB ", "2026-04-15"),  # Valid (with space)
    ("FLC", "2022-01-01"),   # Delisted long ago
    ("VNINDEX", "2026-04-16"), # Index (not 3 chars but allowed)
    ("HNX-INDEX", "2026-04-16"), # Index (not 3 chars but allowed)
    ("ABCD", "2026-04-16"),  # 4 chars (should be skipped)
    ("X20", "2026-04-16"),   # Valid (has number)
]

results = test_filtering_logic(test_data)
print("-" * 30)
print(f"Final affected tickers: {results}")

expected = {"HPG", "SAB", "VNINDEX", "HNX-INDEX", "X20"}
if results == expected:
    print("TEST PASSED")
else:
    print(f"TEST FAILED. Expected: {expected}")
