import pandas as pd

def analyze_ma_trend(df: pd.DataFrame) -> dict:
    if len(df) < 50:
        return {"is_perfect_uptrend": False, "trend_label": "Chưa đủ dữ liệu", "is_extended_up": False}
        
    ma10 = df['MA10'] if 'MA10' in df.columns else df['Close'].rolling(10).mean()
    ma20 = df['MA20'] if 'MA20' in df.columns else df['Close'].rolling(20).mean()
    ma50 = df['MA50'] if 'MA50' in df.columns else df['Close'].rolling(50).mean()
    ma100 = df['MA100'] if 'MA100' in df.columns else df['Close'].rolling(100).mean()
    ma200 = df['MA200'] if 'MA200' in df.columns else df['Close'].rolling(200).mean()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    ma10_last = float(ma10.iloc[-1])
    ma20_last = float(ma20.iloc[-1])
    ma50_last = float(ma50.iloc[-1])
    ma100_last = float(ma100.iloc[-1]) if not pd.isna(ma100.iloc[-1]) else 0
    ma200_last = float(ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else 0
    
    ma10_prev = float(ma10.iloc[-2])
    ma20_prev = float(ma20.iloc[-2])
    ma50_prev = float(ma50.iloc[-2])
    
    # MA10 > MA20 > MA50 > MA100 > MA200
    ma_order = (ma10_last > ma20_last) and (ma20_last > ma50_last) and (ma50_last > ma100_last) and (ma100_last > ma200_last)
    
    # Tất cả MA dốc lên
    ma_slope_up = (ma10_last > ma10_prev) and (ma20_last > ma20_prev) and (ma50_last > ma50_prev)
    
    # Close > MA20
    close_above_ma20 = last['Close'] > ma20_last
    
    # Không thủng MA50: Lowest Low 10 >= MA50
    ll10 = df['Low'].rolling(10).min().iloc[-1]
    above_ma50_last10 = ll10 >= ma50_last
    
    is_perfect = (ma_order and close_above_ma20 and above_ma50_last10)
    
    # Label trend
    if close_above_ma20 and ma20_last > ma50_last:
        trend_label = "Tăng"
    elif not close_above_ma20 and ma20_last < ma50_last:
        trend_label = "Giảm"
    else:
        trend_label = "Đi ngang"
        
    # Extended (tăng nóng)
    is_extended_up = (last['Close'] > ma20_last * 1.08) or (last['Close'] > ma50_last * 1.15)
    
    return {
        "is_perfect_uptrend": is_perfect,
        "trend_label": trend_label,
        "is_extended_up": is_extended_up
    }
