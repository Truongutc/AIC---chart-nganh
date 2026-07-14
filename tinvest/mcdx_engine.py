import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, period: int) -> pd.Series:
    """Vectorized RSI calculation using EWM."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
        
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = np.where(avg_loss == 0, 100.0, np.where(avg_gain == 0, 0.0, 100 - (100 / (1 + rs))))
    
    return pd.Series(rsi, index=series.index)

def calculate_mfi_source(source: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """Calculates Money Flow Index (MFI) using a specific source (e.g., Close price)."""
    money_flow = source * volume
    # Positive if source > prev_source, Negative if source < prev_source
    positive_flow = np.where(source > source.shift(1), money_flow, 0)
    negative_flow = np.where(source < source.shift(1), money_flow, 0)
    
    pos_flow_sum = pd.Series(positive_flow, index=source.index).rolling(window=period).sum()
    neg_flow_sum = pd.Series(negative_flow, index=source.index).rolling(window=period).sum()
    
    mfr = pos_flow_sum / (neg_flow_sum + 1e-10)
    mfi = 100 - (100 / (1 + mfr))
    return mfi

def calculate_mcdx(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates MCDX (Banker, Hot Money, Retailer) and Money Flow features.
    Replicates the provided Pine Script logic.
    """
    out = pd.DataFrame(index=df.index)
    
    if len(df) < 50:
        return out
        
    close = df['Close']
    volume = df['Volume']
    
    # ── 1. MCDX (Banker, Hot Money, Retailer) ──
    rsi_50 = calculate_rsi(close, 50)
    rsi_40 = calculate_rsi(close, 40)
    
    rsi_banker = 1.5 * (rsi_50 - 50)
    rsi_banker = rsi_banker.clip(lower=0, upper=20)
    
    rsi_hot_money = 0.75 * (rsi_40 - 30)
    rsi_hot_money = rsi_hot_money.clip(lower=0, upper=20)
    
    out['MCDX_Banker'] = rsi_banker
    out['MCDX_HotMoney'] = rsi_hot_money
    out['MCDX_Retailer'] = 20.0  # Constant base line
    out['MCDX_Banker_MA'] = rsi_banker.rolling(window=36).mean()
    
    # ── 2. Stochastic RSI ──
    rsi_36 = calculate_rsi(close, 36)
    stoch_rsi_min = rsi_36.rolling(window=36).min()
    stoch_rsi_max = rsi_36.rolling(window=36).max()
    stoch_rsi = 100 * (rsi_36 - stoch_rsi_min) / (stoch_rsi_max - stoch_rsi_min + 1e-10)
    
    k = stoch_rsi.rolling(window=6).mean()
    d = k.rolling(window=6).mean()
    
    out['MCDX_StochRSI_K'] = (k / 100) * 20
    out['MCDX_StochRSI_D'] = (d / 100) * 20
    
    # ── 3. Money Inflow & Outflow ──
    rsi_14 = calculate_rsi(close, 14)
    mfi_14 = calculate_mfi_source(close, volume, 14)
    vol_ma_20 = volume.rolling(window=20).mean()
    vol_change_pct = ((volume - vol_ma_20) / (vol_ma_20 + 1e-10)) * 100
    
    out['MCDX_MoneyInflow'] = (rsi_14 > 50) & (mfi_14 > 50) & (vol_change_pct > 20)
    out['MCDX_MoneyOutflow'] = (rsi_14 < 50) & (mfi_14 < 50) & (vol_change_pct < -20)
    
    # ── 4. Peaks and Troughs ──
    out['MCDX_IsTrough'] = close == close.rolling(window=20).min()
    out['MCDX_IsPeak'] = close == close.rolling(window=20).max()
    
    return out

def evaluate_mcdx_rules(df: pd.DataFrame) -> dict:
    """Evaluate stock/market health based on MCDX signals."""
    if 'MCDX_Banker' not in df.columns:
        return {"status": "N/A", "action": "Chưa có dữ liệu MCDX", "details": "", "banker_weakening": False}

    if len(df) < 3:
        return {"status": "N/A", "action": "Dữ liệu quá ngắn", "details": "", "banker_weakening": False}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    banker = last['MCDX_Banker']
    banker_prev = prev['MCDX_Banker']
    banker_prev2 = prev2['MCDX_Banker']
    
    banker_ma = last['MCDX_Banker_MA']
    banker_ma_prev = prev['MCDX_Banker_MA']
    
    hot = last['MCDX_HotMoney']
    hot_prev = prev['MCDX_HotMoney']
    
    k = last['MCDX_StochRSI_K']
    d = last['MCDX_StochRSI_D']
    k_prev = prev['MCDX_StochRSI_K']
    d_prev = prev['MCDX_StochRSI_D']
    
    inflow = last['MCDX_MoneyInflow']
    inflow_prev = prev['MCDX_MoneyInflow']
    outflow = last['MCDX_MoneyOutflow']
    
    close = last['Close']
    close_prev = prev['Close']
    vol = last['Volume']
    vol_ma = last.get('AvgVolume20', vol)

    # 1. ĐIỂM MUA ĐẸP NHẤT (Nổ dòng tiền)
    banker_cross_up = (banker > banker_ma) and (banker_prev <= banker_ma_prev)
    stoch_cross_up = (k > d) and (k_prev <= d_prev) and (k < 4) # k < 4 (thang 20) tương đương k < 20 (thang 100)
    best_buy = banker_cross_up and (banker_prev < 10) and (vol > vol_ma) and stoch_cross_up

    # 2. CỔ PHIẾU KHỎE (Tiền lớn đang gom)
    is_strong = (banker > banker_prev) and (banker > banker_ma) and inflow

    # 3. MUA THĂM DÒ (Dòng tiền chớm vào)
    probe_buy = inflow or inflow_prev

    # 4. PHÂN PHỐI / FOMO
    fomo = (hot > hot_prev + 2) and (banker <= banker_prev)
    divergence = (close > close_prev) and (banker < banker_prev)
    overbought = k > 16 # > 80 trong thang 100
    vol_spike = vol > 2.5 * vol_ma
    distribution = fomo or divergence or overbought or vol_spike

    # 5. TÍN HIỆU BÁN (Tiền lớn suy yếu)
    # MCDX xấu theo định nghĩa AIC:
    #   - Nếu banker > 3: xấu khi banker hôm nay < banker hôm qua HOẶC < banker t-2
    #   - Hoặc banker < 3 (dòng tiền tạo lập quá yếu)
    banker_weakening = (
        (banker < 3)
        or (banker > 3 and (banker < banker_prev or banker < banker_prev2))
    )
    banker_cross_down = (banker < banker_ma) and (banker_prev >= banker_ma_prev)
    sell_signal = banker_weakening or banker_cross_down

    # 6. RÚT TIỀN (Outflow / Gãy nền)
    strong_sell = outflow

    # Evaluate priority
    if strong_sell:
        return {
            "status": "DÒNG TIỀN RÚT RA (Outflow / Gãy nền)",
            "action": "THẬN TRỌNG - ƯU TIÊN QUẢN TRỊ RỦI RO",
            "details": "Tiền lớn thoát dứt khoát, nổ vol chiều bán.",
            "banker_weakening": banker_weakening
        }
    elif sell_signal:
        return {
            "status": "TIỀN LỚN SUY YẾU",
            "action": "CANH CHỐT LỜI BỚT - NGƯNG MUA",
            "details": "Banker (Đỏ) cắt xuống MA đen hoặc giảm liên tục 3 phiên.",
            "banker_weakening": banker_weakening
        }
    elif distribution:
        return {
            "status": "RỦI RO PHÂN PHỐI / FOMO",
            "action": "HẠN CHẾ MUA ĐUỔI, CANH CHỐT LỜI DẦN",
            "details": "Vàng tăng nhưng Đỏ giảm, Stoch RSI overbought hoặc Volume nổ quá lớn.",
            "banker_weakening": banker_weakening
        }
    elif best_buy:
        return {
            "status": "ĐIỂM NỔ DÒNG TIỀN TẠO LẬP",
            "action": "MUA ĐẸP NHẤT (Breakout / Cắt lên MA)",
            "details": "Đỏ cắt lên Đen từ nền thấp (<10), Stoch RSI cắt lên từ vùng quá bán.",
            "banker_weakening": banker_weakening
        }
    elif is_strong:
        return {
            "status": "DÒNG TIỀN TẠO LẬP GOM HÀNG",
            "action": "NẮM GIỮ / GIA TĂNG TỶ TRỌNG",
            "details": "Đỏ tăng dần, nằm trên MA đen, có dòng tiền vào (Inflow).",
            "banker_weakening": banker_weakening
        }
    elif probe_buy:
        return {
            "status": "DÒNG TIỀN VỪA XUẤT HIỆN",
            "action": "MUA THĂM DÒ",
            "details": "Tín hiệu Inflow chớm nở, theo dõi chờ xác nhận.",
            "banker_weakening": banker_weakening
        }
    else:
        return {
            "status": "TRUNG TÍNH (Chưa rõ xu hướng MCDX)",
            "action": "THEO DÕI",
            "details": "Dòng tiền tạo lập (Đỏ) và dòng tiền đầu cơ (Vàng) đi ngang.",
            "banker_weakening": banker_weakening
        }
