import pytest
import pandas as pd
import numpy as np
from tinvest.valuation_engine import evaluate_stock_valuation

def create_mock_df():
    dates = pd.date_range(start="2023-01-01", periods=100)
    close = [100] * 100
    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close,
        "Low": [c-1 for c in close],
        "Close": close,
        "Volume": [1000000] * 100
    })
    # Add indicators
    df['MA20'] = 98
    df['MA50'] = 95
    df['Tenkan'] = 99
    df['Kijun'] = 97
    df['Kijun65'] = 96
    df['SpanA'] = 94
    df['SpanB'] = 95
    df['CloudTop'] = 95
    df['CloudBottom'] = 94
    df['SwingHigh'] = 0
    df['SwingLow'] = 0
    return df

def test_aic_valuation_buffers():
    df = create_mock_df()
    # pass new format entry_info to match the engine
    entry_info = {"entry_type": "EARLY"}
    
    res = evaluate_stock_valuation("TEST", df, entry_info)
    assert res["is_valid"] is True
    assert res["s1"] == 99.0
    assert res["cutloss_partial"] == 93.0
    assert res["tp1"] == pytest.approx(105.0, rel=0.01)

def test_risk_score_low():
    df = create_mock_df()
    entry_info = {"entry_type": "STRONG"}
    res = evaluate_stock_valuation("TEST", df, entry_info)
    assert res["risk_score"] == 0
    assert res["risk_desc"] == "LOW"

def test_risk_score_high():
    df = create_mock_df()
    # Force bad state
    df.loc[df.index[-1], "Close"] = 80
    df.loc[df.index[-1], "MA20"] = 100 # Price < MA20 -> +5
    df.loc[df.index[-1], "MA50"] = 100 # Price < MA50 -> +5
    df.loc[df.index[-1], "MA200"] = 100 # Price < MA200 -> +10
    df.loc[df.index[-1], "Tenkan"] = 90
    df.loc[df.index[-1], "Kijun"] = 95 # Tenkan < Kijun -> +5
    df.loc[df.index[-1], "CloudBottom"] = 90 # Price < CloudBottom -> +10
    df.loc[df.index[-1], "Kijun65"] = 100 # Price < K65 -> +10
    
    # Trigger swing breakdown: set SwingLow at idx-5 to 90
    df.loc[df.index[-5], "SwingLow"] = 90 # Price < SwingLow -> +10
    
    # Trigger volume / VSA: down bar with high volume
    df.loc[df.index[-1], "Volume"] = 2000000 # Volume > 1.5 * AvgVol -> +15
    df.loc[df.index[-1], "AvgVolume20"] = 1000000
    
    res = evaluate_stock_valuation("TEST", df, {})
    # Total expected score: 5 + 5 + 10 + 5 + 10 + 10 + 10 + 15 = 70 (HIGH)
    assert res["risk_score"] == 70
    assert res["risk_desc"] == "HIGH"

def test_actionable_conclusion():
    df = create_mock_df()
    # Set entry type so that we can trigger YES action
    entry_info = {"entry_type": "EARLY"}
    res = evaluate_stock_valuation("TEST", df, entry_info)
    assert "YES" in res["action"]
