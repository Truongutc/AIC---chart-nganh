import pytest
import pandas as pd
import numpy as np
from tinvest.advanced_entry import _eval_day, ensure_indicators
from tinvest.ichimoku_engine import compute_ichimoku

def create_dead_df():
    # Create a DF where NO signals are possible
    dates = pd.date_range(start="2023-01-01", periods=250)
    close = np.linspace(200, 100, 250)
    df = pd.DataFrame({
        "Date": dates,
        "Open": close + 1,
        "High": close + 2,
        "Low": close - 2,
        "Close": close,
        "Volume": [100000] * 250 # Low volume
    })
    # Force indicators to be bearish
    df['MA10'] = 250
    df['MA20'] = 300
    df['MA50'] = 400
    df['MA100'] = 500
    df['MA200'] = 600
    df['AvgVolume20'] = 500000
    df['Tenkan'] = 50
    df['Kijun'] = 60
    df['Kijun65'] = 70
    df['CloudTop'] = 500
    df['CloudBottom'] = 450
    df['SpanA'] = 450
    df['SpanB'] = 500
    df['HA_Color'] = 'Red'
    df['Spread'] = df['High'] - df['Low']
    df['Chikou'] = df['Close'].shift(-26)
    df['SwingLow'] = 0.0
    return df

def test_early_ma_trigger():
    df = create_dead_df()
    idx = -1
    # MA Early: Price > MA20 and MA20 up
    df.loc[df.index[idx], "Close"] = 105
    df.loc[df.index[idx], "MA20"] = 100
    df.loc[df.index[idx-1], "MA20"] = 99 # Up
    df.loc[df.index[idx], "Volume"] = 1000000 # High vol to pass noise filter
    df.loc[df.index[idx], "AvgVolume20"] = 500000
    
    # Satisfy new early buy logic (requires cross_ma10/cross_tk and higher swing low)
    df.loc[df.index[idx], "MA10"] = 100
    df.loc[df.index[idx-1], "MA10"] = 105
    df.loc[df.index[idx-10], "SwingLow"] = 90
    df.loc[df.index[idx-5], "SwingLow"] = 95
    
    res = _eval_day(df, idx)
    assert res is not None
    assert res["type"] == "EARLY"

def test_add1_logic():
    df = create_dead_df()
    idx = -1
    # 1. Setup Early at idx-5
    df.loc[df.index[idx-5], "Close"] = 105
    df.loc[df.index[idx-5], "MA20"] = 100
    df.loc[df.index[idx-6], "MA20"] = 99
    
    # 2. Setup Confirm today: Ichi Confirm (Close > Kijun)
    df.loc[df.index[idx], "Close"] = 120
    df.loc[df.index[idx], "Kijun"] = 110
    df.loc[df.index[idx], "Tenkan"] = 109 # Not strong
    df.loc[df.index[idx], "MA20"] = 150 # Avoid MA Early today
    df.loc[df.index[idx], "Volume"] = 1000000 
    df.loc[df.index[idx], "AvgVolume20"] = 500000

    res = _eval_day(df, idx)
    assert res is not None
    assert res["type"] == "ADD_1"

def test_add2_ha_trigger():
    df = create_dead_df()
    idx = -1
    # Above Cloud + TK Bullish
    df.loc[df.index[idx], "Close"] = 140
    df.loc[df.index[idx], "CloudTop"] = 110
    df.loc[df.index[idx], "Tenkan"] = 120
    df.loc[df.index[idx], "Kijun"] = 115
    df.loc[df.index[idx], "MA20"] = 135
    df.loc[df.index[idx], "Volume"] = 1000000 
    df.loc[df.index[idx], "AvgVolume20"] = 500000
    
    # Break Strong today by forcing Chikou blocked
    df.loc[df.index[idx-26], "Close"] = 200 # Chikou < Price(26)
    
    # HA Shift: Red to Green
    df.loc[df.index[idx-1], "HA_Color"] = "Red"
    df.loc[df.index[idx], "HA_Color"] = "Green"
    
    res = _eval_day(df, idx)
    assert res is not None
    assert res["type"] == "ADD_2"

def test_strong_priority():
    df = create_dead_df()
    idx = -1
    # Strong Ichi
    df.loc[df.index[idx], "Close"] = 140
    df.loc[df.index[idx], "CloudTop"] = 110
    df.loc[df.index[idx], "Tenkan"] = 120
    df.loc[df.index[idx], "Kijun"] = 115
    df.loc[df.index[idx], "MA20"] = 135
    df.loc[df.index[idx], "Volume"] = 1000000 
    df.loc[df.index[idx], "AvgVolume20"] = 500000
    # Chikou Confirm
    df.loc[df.index[idx-26], "Close"] = 100
    df.loc[df.index[idx], "SpanA"] = 500
    df.loc[df.index[idx], "SpanB"] = 500
    
    res = _eval_day(df, idx)
    assert res["type"] == "STRONG"
