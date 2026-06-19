import pandas as pd
import numpy as np
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from tinvest.advanced_entry import _check_early_buy_logic_only, ensure_indicators

def generate_base_df(n=200):
    dates = pd.date_range(start="2023-01-01", periods=n)
    close = np.linspace(100, 100, n)
    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1000000] * n
    })
    return df

def test_ma_case1():
    print("\n--- Testing MA Case 1: Bottoming + Vol Exhaustion ---")
    df = generate_base_df()
    # 1. Price trend down
    df.loc[df.index[-30:-5], 'Close'] = np.linspace(110, 90, 25)
    df.loc[df.index[-30:-5], 'Low'] = df.loc[df.index[-30:-5], 'Close'] - 1
    
    # 2. Volume trend down
    df.loc[df.index[-30:-15], 'Volume'] = 2000000
    df.loc[df.index[-15:], 'Volume'] = 500000
    
    # 3. Lowest Low in last 10 session was at -3
    df.loc[df.index[-3], 'Low'] = 88.0
    
    # 4. Today Bounce: Price > MA10, MA10/20 slope up, Price above LL
    # We set close high to ensure MA slopes up
    df.loc[df.index[-1], 'Close'] = 98.0
    df.loc[df.index[-1], 'Low'] = 91.0 # 91 <= 88 * 1.05 = 92.4 (True)
    
    df = ensure_indicators(df)
    
    res = _check_early_buy_logic_only(df, len(df)-1)
    print(f"MA Case 1 Logic Only: {res}")

def test_ichi_case3():
    print("\n--- Testing Ichimoku Case 3: Kijun 65 Bounce ---")
    df = generate_base_df()
    # Prereq: Price > CloudTop
    # Case: Price near K65 (1-3%) + Bounce
    df.loc[df.index[-5:], 'CloudTop'] = 90
    df.loc[df.index[-5:], 'Kijun65'] = 100
    df.loc[df.index[-5:], 'Tenkan'] = 105
    df.loc[df.index[-5:], 'Kijun'] = 104
    
    df.loc[df.index[-2], 'Close'] = 102
    df.loc[df.index[-1], 'Close'] = 103 # Bounce
    df.loc[df.index[-1], 'Low'] = 101.5 # 101.5 / 100 = 1.015 (1.5% near)
    
    df = ensure_indicators(df)
    res = _check_early_buy_logic_only(df, len(df)-1)
    print(f"Ichi Case 3 Logic Only: {res}")

test_ma_case1()
test_ichi_case3()
