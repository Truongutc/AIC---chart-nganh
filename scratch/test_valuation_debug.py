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
    
    # Add missing swing columns to prevent KeyError
    df['SwingHigh'] = 0
    df['SwingLow'] = 0
    return df

print("--- TEST 1: test_aic_valuation_buffers ---")
df1 = create_mock_df()
entry_info1 = {"entry_type": "EARLY"}
res1 = evaluate_stock_valuation("TEST", df1, entry_info1)
for k in ["s1", "cutloss_partial", "tp1", "action", "risk_score"]:
    val = res1.get(k)
    if isinstance(val, str):
        val = val.encode('ascii', 'backslashreplace').decode('ascii')
    print(f"{k}: {val}")

print("\n--- TEST 2: test_risk_score_low ---")
df2 = create_mock_df()
entry_info2 = {"entry_type": "STRONG"}
res2 = evaluate_stock_valuation("TEST", df2, entry_info2)
for k in ["risk_score", "risk_desc"]:
    val = res2.get(k)
    if isinstance(val, str):
        val = val.encode('ascii', 'backslashreplace').decode('ascii')
    print(f"{k}: {val}")

print("\n--- TEST 3: test_risk_score_high ---")
df3 = create_mock_df()
df3.loc[df3.index[-1], "Close"] = 80
df3.loc[df3.index[-1], "MA20"] = 100
df3.loc[df3.index[-1], "Tenkan"] = 90
df3.loc[df3.index[-1], "Kijun"] = 95
df3.loc[df3.index[-1], "CloudTop"] = 100
df3.loc[df3.index[-1], "Kijun65"] = 100
res3 = evaluate_stock_valuation("TEST", df3, {})
for k in ["risk_score", "risk_desc"]:
    val = res3.get(k)
    if isinstance(val, str):
        val = val.encode('ascii', 'backslashreplace').decode('ascii')
    print(f"{k}: {val}")

print("\n--- TEST 4: test_actionable_conclusion ---")
df4 = create_mock_df()
res4 = evaluate_stock_valuation("TEST", df4, {})
for k in ["action", "rr_ratio"]:
    val = res4.get(k)
    if isinstance(val, str):
        val = val.encode('ascii', 'backslashreplace').decode('ascii')
    print(f"{k}: {val}")
