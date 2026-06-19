import pytest
import pandas as pd
import numpy as np
from tinvest.risk_engine import calculate_stoploss, calculate_atr, calculate_swing_low

@pytest.fixture
def mock_df():
    """Creates a basic OHLCV dataframe for testing."""
    dates = pd.date_range(start="2023-01-01", periods=50)
    data = {
        "Date": dates,
        "Open": np.linspace(100, 110, 50),
        "High": np.linspace(102, 112, 50),
        "Low": np.linspace(98, 108, 50),
        "Close": np.linspace(101, 111, 50),
        "Volume": np.linspace(1000, 2000, 50),
        "MA20": np.linspace(100, 105, 50),
        "Tenkan": np.linspace(101, 106, 50),
        "Kijun": np.linspace(99, 104, 50),
        "CloudTop": np.linspace(98, 103, 50)
    }
    return pd.DataFrame(data)

def test_stoploss_early(mock_df):
    # EARLY: Entry = High * 1.001
    # SL = min(swing_low, kijun)
    current_close = 111.0
    result = calculate_stoploss(mock_df, "EARLY", current_close)
    
    assert result["entry_price"] == round(float(mock_df['High'].iloc[-1]) * 1.001, 2)
    assert result["is_valid"] is True
    assert result["tp_price"] > result["entry_price"]

def test_stoploss_add1(mock_df):
    # ADD1: Entry = max(Close, High_prev)
    current_close = 111.0
    high_prev = 115.0 # Force entry to be High_prev
    details = {"high_prev": high_prev}
    result = calculate_stoploss(mock_df, "ADD_1", current_close, details)
    
    assert result["entry_price"] == high_prev
    assert result["tp_price"] == round(high_prev + 2 * (high_prev - result["sl_price"]), 2)

def test_risk_filter(mock_df):
    # Force high risk: Entry = 100, SL = 85 (15% risk)
    # Using EARLY logic: if risk > 5%, SL = Entry * 0.95 (5% risk)
    # So we need a signal that doesn't have a safety fallback or where we can bypass it.
    # Actually, calculate_stoploss HAS safety fallbacks (5%, 7%, 10%) so it's hard to exceed 10%
    # unless it's STRONG buy with a manual LOW.
    
    entry_price = 100.0
    details = {"is_vsa_strong": True}
    # Modify mock_df to have a very low 'Low' at the end
    mock_df_bad = mock_df.copy()
    mock_df_bad.loc[mock_df_bad.index[-1], 'Low'] = 80.0 # 20% risk
    
    result = calculate_stoploss(mock_df_bad, "STRONG", 100.0, details)
    assert result["risk_pct"] >= 10.0
    assert result["is_valid"] == False

def test_tp_calculation():
    # R:R = 1:2 -> TP = Entry + 2 * (Entry - SL)
    # Entry=100, SL=95 (5% risk) -> TP = 100 + 2*5 = 110
    from tinvest.risk_engine import calculate_stoploss
    # Use mocks indirectly
    df = pd.DataFrame({"High": [100]*30, "Low": [90]*30, "Close": [99]*30, "MA20": [90]*30})
    res = calculate_stoploss(df, "STRONG", 99.0, {"is_ma_pullback": True})
    # Entry=99, SL=90 (MA20), Risk=9, TP=99 + 2*9 = 117
    assert res["tp_price"] == 117.0
