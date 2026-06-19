import pandas as pd
import numpy as np

def get_vsa_signals(df, idx):
    if len(df) < abs(idx) + 20: return {"demand": False, "stopping": False, "no_supply": False, "test_supply": False, "sc": False}
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    vol = float(last['Volume'])
    avg_vol20 = float(last['AvgVolume20'])
    spread = float(last['High'] - last['Low'])
    avg_spread20 = float(df['Spread'].iloc[idx-20:idx].mean() if len(df) >= abs(idx)+20 else df['Spread'].mean())
    
    # Selling Climax
    sc = (last['Close'] < prev['Close'] * 0.96) and (vol > 1.8 * avg_vol20)
    
    # Stopping Volume
    stopping = (vol > 1.4 * avg_vol20) and (spread > 0.8 * avg_spread20) and (last['Close'] > last['Low'] + 0.3 * spread)
    
    # No Supply
    is_down_bar = (last['Close'] < last['Open']) and (last['Close'] < prev['Close'])
    no_supply = (vol < 0.7 * avg_vol20) and (spread < avg_spread20) and is_down_bar
    
    # Test for Supply
    test_supply = (vol < avg_vol20) and (spread < avg_spread20 * 0.8) and (last['Close'] > (last['Low'] + 0.4 * spread))
    
    # Demand Candle (Cầu vào): Giá tăng, đóng cửa > mở cửa, vol > avg_vol20
    demand = (last['Close'] > last['Open']) and (last['Close'] > prev['Close']) and (vol > avg_vol20)
    
    return {"demand": demand, "stopping": stopping, "no_supply": no_supply, "test_supply": test_supply, "sc": sc}

def _eval_with_cache(cache_key, func, df, idx):
    if not hasattr(df, 'attrs'): df.attrs = {}
    if cache_key not in df.attrs: df.attrs[cache_key] = {}
    if idx in df.attrs[cache_key]: return df.attrs[cache_key][idx]
    res = func(df, idx)
    df.attrs[cache_key][idx] = res
    return res

def _check_early_buy_logic_only_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    cross_tk = (prev['Close'] <= prev['Tenkan']) and (last['Close'] > last['Tenkan'])
    cross_ma10 = (prev['Close'] <= prev['MA10']) and (last['Close'] > last['MA10'])
    
    # Swing low tracking: needs recent 2 swing lows
    recent_lows = [v for v in df['SwingLow'].iloc[:idx+1 if idx < -1 else None] if v > 0]
    
    is_higher_low = False
    if len(recent_lows) >= 2:
        is_higher_low = recent_lows[-1] >= recent_lows[-2]
    
    vsa = get_vsa_signals(df, idx)
    c_demand = vsa['demand'] or vsa['stopping'] or vsa['test_supply']
    
    if (cross_tk or cross_ma10) and is_higher_low and c_demand:
        return "EARLY_BUY_REVERSAL"
    
    return False

def check_early_buy(df, idx):
    return _eval_with_cache('early_logic', _check_early_buy_logic_only_impl, df, idx)

def _check_add1_strict_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10, ma20, ma50 = last['MA10'], last['MA20'], last['MA50']
    
    # Case 1: MA Pullback
    # MA20 > MA50. Giá chạm MA20 rồi bật
    case1 = (ma20 > ma50) and (last['Low'] <= ma20 * 1.025) and (last['Close'] >= ma20) and (last['Close'] > last['Open'])
    
    # Case 2: MA Cross
    cross_10_20 = (prev['MA10'] <= prev['MA20']) and (last['MA10'] > last['MA20'])
    cross_20_50 = (prev['MA20'] <= prev['MA50']) and (last['MA20'] > last['MA50'])
    case2 = cross_10_20 or cross_20_50
    
    # Case 3: Ichimoku Bounce
    # Trên mây, chạm Kijun or Kijun65
    above_cloud = last['Close'] > last['CloudTop']
    touch_kijun = last['Low'] <= last['Kijun'] * 1.015 and last['Close'] >= last['Kijun']
    touch_k65 = last['Low'] <= last['Kijun65'] * 1.015 and last['Close'] >= last['Kijun65']
    case3 = above_cloud and (touch_kijun or touch_k65) and (last['Close'] > last['Open'])
    
    # Case 4: Ichimoku Cross
    below_cloud = last['Close'] < last['CloudBottom']
    tk_cross_up = (prev['Tenkan'] <= prev['Kijun']) and (last['Tenkan'] > last['Kijun'])
    case4 = below_cloud and tk_cross_up
    
    if case1: return "MA_PULLBACK"
    if case2: return "MA_CROSS"
    if case3: return "ICHI_BOUNCE"
    if case4: return "ICHI_CROSS"
    return False

def check_add1(df, idx):
    return _eval_with_cache('add1_strict', _check_add1_strict_impl, df, idx)

def _check_add2_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    tk, kj = last['Tenkan'], last['Kijun']
    cloud_top = last['CloudTop']
    
    if not (last['Close'] > cloud_top and tk > cloud_top and kj > cloud_top):
        return False
        
    case1_ha_reversal = (tk >= kj) and (prev['HA_Color'] == 'Red') and (last['HA_Color'] == 'Green')
    case2_tk_cross = (last['HA_Color'] == 'Green') and (prev['Tenkan'] <= prev['Kijun']) and (tk > kj)
    
    if case1_ha_reversal: return "HA_REVERSAL"
    if case2_tk_cross: return "TK_CROSS_UP"
    return False

def check_add2(df, idx):
    return _eval_with_cache('add2_strict', _check_add2_impl, df, idx)

def _check_strong_buy_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10, ma20, ma50, ma100 = last['MA10'], last['MA20'], last['MA50'], last['MA100']
    ma200 = last.get('MA200', 0)
    
    # Case 1: Perfect MA Stack with Pullback/Bounce to MA10 or MA20
    perfect_stack = (ma10 > ma20 > ma50 > ma100) and (ma100 > ma200)
    bounce_ma = (last['Low'] <= ma20 * 1.025 or last['Low'] <= ma10 * 1.025) and (last['Close'] > ma20)
    case1_perfect = perfect_stack and bounce_ma and (last['Close'] > last['Open'])
    
    # Case 2: Breakout Kumo + Chikou break + Volume
    price_break_kumo = (prev['Close'] <= prev['CloudTop']) and (last['Close'] > last['CloudTop'])
    kumo_green = last['SpanA'] >= last['SpanB']
    chikou_break = last['Chikou'] > last['Close'] if not pd.isna(last['Chikou']) else True # Approximation 
    vol_break = last['Volume'] > 1.2 * last['AvgVolume20']
    
    case2_kumo = price_break_kumo and chikou_break and kumo_green and vol_break
    
    if case1_perfect: return "PERFECT_MA"
    if case2_kumo: return "KUMO_BREAK"
    return False

def check_strong_buy(df, idx):
    return _eval_with_cache('strong_buy', _check_strong_buy_impl, df, idx)

def _eval_day(df: pd.DataFrame, idx: int):
    if len(df) < abs(idx) + 65: return None
    
    # Chú ý: thứ tự kiểm tra quan trọng. STRONG > ADD2 > ADD1 > EARLY
    r_strong = check_strong_buy(df, idx)
    if r_strong: return {"type": "STRONG", "confidence": "MẠNH", "size": "50%", "details": {"source": r_strong}}
    
    r_add2 = check_add2(df, idx)
    if r_add2: return {"type": "ADD_2", "confidence": "GIA TĂNG 2", "size": "30%", "details": {"source": r_add2}}
    
    r_add1 = check_add1(df, idx)
    if r_add1: return {"type": "ADD_1", "confidence": "GIA TĂNG 1", "size": "20%", "details": {"source": r_add1}}
    
    r_early = check_early_buy(df, idx)
    if r_early: return {"type": "EARLY", "confidence": "SỚM", "size": "20%", "details": {"source": r_early}}
    
    return None

def ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 10: return df
    if 'MA10' in df.columns and 'Tenkan' in df.columns:
        return df
    from .data_loader import enrich_dataframe
    return enrich_dataframe(df)

def classify_entry(df: pd.DataFrame) -> dict:
    if len(df) < 20: 
        return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}
    
    # Tìm kiếm Tín hiệu mua GẦN NHẤT trong 15 phiên qua (Holding State)
    current_price = float(df['Close'].iloc[-1])
    
    for i in range(1, 151):
        res = _eval_day(df, -i)
        if res:
            signal_price = float(df['Close'].iloc[-i])
            
            # KIỂM CHỨNG HIỆU LỰC (VALIDATION CỰC KỲ QUAN TRỌNG)
            # Nếu giá hiện tại đã rớt thủng sâu hơn giá của cái ngày báo tín hiệu Mua đó (qúa 1.5% độ nhiễu)
            # -> Tín hiệu này đã GÃY (Invalidated), không được lấy nó làm mốc để phán đoán Hỗ trợ/Kháng cự nữa!
            if current_price < signal_price * 0.985:
                continue # Lờ đi tín hiệu xịt này, lùi về quá khứ tìm xem còn nền tảng nào vững hơn không
                
            flags = []
            if i == 1:
                flags.append("Tín hiệu bùng nổ T-0 (Phiên nay)")
            elif i == 2:
                flags.append("Tín hiệu xác nhận phiên Hôm Qua (T-1)")
            else:
                flags.append(f"Vị thế đang nắm giữ (Theo tín hiệu T-{i-1})")
                
            return {
                "entry_type": res["type"], 
                "confidence": res["confidence"], 
                "position_size": res["size"], 
                "details": res.get("details", {}), 
                "risk_flags": flags
            }
            
    return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}
