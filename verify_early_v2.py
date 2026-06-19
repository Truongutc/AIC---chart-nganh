import pandas as pd
import numpy as np
import os
import sys

# Support Vietnamese characters in Windows terminal
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add current directory to path
sys.path.append(os.getcwd())

from tinvest.advanced_entry import check_early_buy, ensure_indicators

def generate_base_df(n=200):
    dates = pd.date_range(start="2023-01-01", periods=n)
    close = np.array([100.0] * n)
    df = pd.DataFrame({
        "Date": dates,
        "Open": close * 0.99,
        "High": close * 1.01,
        "Low": close * 0.98,
        "Close": close,
        "Volume": [1000000] * n
    })
    return df

def test_ma_case1():
    print("\n--- Testing MA Case 1: Bottoming + Vol Exhaustion ---")
    df = generate_base_df()
    # Force a downtrend then a bottom
    # MA10 < MA20
    df.loc[df.index[-20:], 'Close'] = np.linspace(100, 90, 20)
    df = ensure_indicators(df)
    
    # Bottom at -3
    df.loc[df.index[-3], 'Low'] = 85.0
    # Volume decreasing during bottom
    df.loc[df.index[-20:-5], 'Volume'] = 2000000
    df.loc[df.index[-5:], 'Volume'] = 500000
    
    # Today breaks MA10 and MA10/20 slope up
    df.loc[df.index[-1], 'Close'] = 95.0
    df = ensure_indicators(df) # Recalculate
    
    res = check_early_buy(df, len(df)-1)
    print(f"MA Case 1 Signal: {res}")

def test_ichi_case3():
    print("\n--- Testing Ichimoku Case 3: Kijun 65 Bounce ---")
    df = generate_base_df()
    df.loc[df.index[-1], 'Close'] = 110
    df.loc[df.index[-1], 'CloudTop'] = 100
    df.loc[df.index[-1], 'Kijun65'] = 105
    df.loc[df.index[-1], 'Tenkan'] = 107
    df.loc[df.index[-1], 'Kijun'] = 106
    df.loc[df.index[-1], 'Low'] = 106.5 # Near K65 (1-3%)
    df.loc[df.index[-2], 'Close'] = 109 # Bounce
    
    df = ensure_indicators(df)
    res = check_early_buy(df, len(df)-1)
    print(f"Ichi Case 3 Signal: {res}")

def test_no_prior_signal():
    print("\n--- Testing 'No Prior Signal' Constraint ---")
    df = generate_base_df()
    # Force a Strong Buy at index -5
    # (Actually we just need _eval_day_raw to return STRONG)
    # The logic is involved, but let's just see if it blocks a valid setup
    
    # Setup ichi case 2 (TK Cross)
    df.loc[df.index[-2], 'Tenkan'] = 100
    df.loc[df.index[-2], 'Kijun'] = 110
    df.loc[df.index[-1], 'Tenkan'] = 115
    df.loc[df.index[-1], 'Kijun'] = 110
    
    df = ensure_indicators(df)
    init_res = check_early_buy(df, len(df)-1)
    print(f"Early Buy with no prior: {init_res}")
    
    # Now force a flag in history that _eval_day_raw sees
    # E.g. Strong Buy at -5
    df.loc[df.index[-5], 'MA10'] = 200
    df.loc[df.index[-5], 'MA20'] = 190
    df.loc[df.index[-5], 'MA50'] = 180
    df.loc[df.index[-5], 'MA100'] = 170
    df.loc[df.index[-5], 'CloudTop'] = 150
    df.loc[df.index[-5], 'Close'] = 195
    df.loc[df.index[-5], 'Low'] = 185
    
    res_blocked = check_early_buy(df, len(df)-1)
    print(f"Early Buy with prior signal: {res_blocked}")

test_ma_case1()
test_ichi_case3()
test_no_prior_signal()
