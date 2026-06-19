"""
Script kiểm tra logic is_break_confirmed vs is_trend_gay sau khi sửa.
"""
import pandas as pd
import numpy as np
from tinvest.rules.ma_rules import evaluate_ma

def make_df(price, ma10, ma20, ma50, n=100):
    dates = pd.date_range('2024-01-01', periods=n)
    data = {
        'Open': [price] * n,
        'High': [price * 1.01] * n,
        'Low': [price * 0.99] * n,
        'Close': [price] * n,
        'Volume': [1000000] * n,
        'MA10': [ma10] * n,
        'MA20': [ma20] * n,
        'MA50': [ma50] * n,
        'MA100': [ma50 * 0.95] * n,
        'MA200': [ma50 * 0.90] * n,
        'SwingHigh': [0] * n,
        'SwingLow': [0] * n,
    }
    return pd.DataFrame(data, index=dates)

def check(label, df):
    result = evaluate_ma(df, -1)
    print(f"\n=== {label} ===")
    print(f"  status: {result['status'][:80]}")
    print(f"  is_trend_gay     : {result['is_trend_gay']}")
    print(f"  is_break_confirmed: {result['is_break_confirmed']}")

# Case 1: VIX-like - giá (17.70) > MA10 (17.50), uptrend thực sự - KHÔNG GÃY
check(
    "Case 1 (VIX - giá trên MA10, không gãy trend)",
    make_df(price=17.70, ma10=17.50, ma20=17.00, ma50=16.50)
)

# Case 2: Cảnh báo sớm (gay_early) - giá < MA10 nhưng MA20 vẫn > MA50
# → is_trend_gay=True, nhưng is_break_confirmed=False
check(
    "Case 2 (Cảnh báo sớm - giá < MA10, nhưng MA20 > MA50)",
    make_df(price=16.0, ma10=16.5, ma20=17.00, ma50=16.50)
)

# Case 3: Gãy confirmed - giá < MA10, MA20 < MA50, giá < MA20
# → is_break_confirmed=True
check(
    "Case 3 (Gãy trend xác nhận - giá < MA10, MA20 < MA50)",
    make_df(price=15.0, ma10=16.0, ma20=16.5, ma50=17.0)
)

print("\nDONE!")
