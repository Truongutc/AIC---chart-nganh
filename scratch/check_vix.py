import sys
sys.path.insert(0, '.')
from tinvest.storage_manager import StorageManager
from tinvest.rules.ma_rules import evaluate_ma

st = StorageManager()
df = st.load_ticker_data('VIX')
if df is not None:
    last = df.iloc[-1]
    p = float(last.get('Close', 0))
    ma10 = float(last.get('MA10', 0))
    ma20 = float(last.get('MA20', 0))
    ma50 = float(last.get('MA50', 0))
    print(f"VIX  Close={p:.2f}  MA10={ma10:.2f}  MA20={ma20:.2f}  MA50={ma50:.2f}")
    print(f"price > MA10 : {p > ma10}")
    print(f"price < MA20 : {p < ma20}")
    print(f"price < MA50 : {p < ma50}")
    print(f"MA20 > MA50  : {ma20 > ma50}")
    print()
    result = evaluate_ma(df, -1)
    print(f"status          : {result['status'][:100]}")
    print(f"is_trend_gay    : {result['is_trend_gay']}")
    print(f"is_break_confirmed: {result['is_break_confirmed']}")
else:
    print("Khong co du lieu VIX")
