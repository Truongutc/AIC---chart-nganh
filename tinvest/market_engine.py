"""

Module 8 – Market Regime Engine (v2.0 – 7 States)

===================================================

Analyzes Index data (VNINDEX, HNXINDEX) to evaluate CANSLIM Market conditions:

- Distribution Days

- Rally Attempts (RA) – chỉ kích hoạt sau cú giảm > 10%

- Follow-Through Days (FTD) – ngày 4-7 mạnh, ngày 8+ yếu

- 7 trạng thái thị trường chi tiết



Returns the current Market Regime, safety scores, and action recommendations.

"""



import logging

import pandas as pd

import numpy as np



logger = logging.getLogger(__name__)



def analyze_market_index(df_index: pd.DataFrame, breadth_pct_ma20: float = 50.0,

                         breadth_pct_ma50: float = 50.0, momentum_data: dict = None) -> dict:

    """

    Quét dữ liệu VNINDEX để xác định trạng thái thị trường chung.

    Phiên bản 2.0: 7 trạng thái, RA chỉ sau giảm >10%, FTD phân loại mạnh/yếu.



    Parameters

    ----------

    df_index : pd.DataFrame - Dữ liệu Index (OHLCV + Date)

    breadth_pct_ma20 : float - % cổ phiếu nằm trên MA20 (từ breadth engine)

    breadth_pct_ma50 : float - % cổ phiếu nằm trên MA50 (từ breadth engine)

    momentum_data : dict - Dữ liệu phân kỳ RSI/MACD (từ momentum engine)

    """

    if df_index is None or df_index.empty or len(df_index) < 50:

        return {

            "regime": "UNKNOWN",

            "ftd_active": False,

            "ftd_quality": None,

            "ra_day": 0,

            "distribution_count": 0,

            "distribution_dates": [],

            "action": "STANDBY",

            "decline_from_peak_pct": 0

        }



    mom = momentum_data or {}



    df = df_index.copy()

    df['MA10'] = df['Close'].rolling(10).mean()

    df['MA20'] = df['Close'].rolling(20).mean()

    df['MA50'] = df['Close'].rolling(50).mean()



    # Kijun 26

    hi26 = df['High'].rolling(26).max()

    lo26 = df['Low'].rolling(26).min()

    df['Kijun'] = (hi26 + lo26) / 2



    regime = "DOWNTREND"

    ra_day = 0

    ra_low = float('inf')

    ftd_active = False

    ftd_quality = None  # "STRONG" hoặc "WEAK"

    ftd_low = float('inf')  # Giá thấp nhất của phiên FTD

    ftd_date = "N/A"

    dist_days = []



    # Track đỉnh gần nhất để tính % giảm

    rolling_peak = float(df['Close'].iloc[0])

    decline_triggered_8 = False  # True khi giảm > 8% từ đỉnh (cho RECOVERY)

    decline_triggered_10 = False  # True khi giảm > 10% từ đỉnh (cho RA/FTD/STABLE_RECOVERY)



    for i in range(1, len(df)):

        c = float(df['Close'].iloc[i])

        o = float(df['Open'].iloc[i])

        h = float(df['High'].iloc[i])

        l = float(df['Low'].iloc[i])

        v = float(df['Volume'].iloc[i])



        pc = float(df['Close'].iloc[i-1])

        pv = float(df['Volume'].iloc[i-1])



        ma10 = float(df['MA10'].iloc[i]) if not pd.isna(df['MA10'].iloc[i]) else c

        ma20 = float(df['MA20'].iloc[i]) if not pd.isna(df['MA20'].iloc[i]) else c

        ma50 = float(df['MA50'].iloc[i]) if not pd.isna(df['MA50'].iloc[i]) else c

        kijun = float(df['Kijun'].iloc[i]) if not pd.isna(df['Kijun'].iloc[i]) else c



        pct_change = (c - pc) / pc

        # 2. ĐẾM NGÀY PHÂN PHỐI (DISTRIBUTION DAYS)

        # Reset rolling peak if new high

        if h > rolling_peak:

            rolling_peak = h

            # Nếu đang trong Downtrend mà vượt đỉnh cũ, coi như reset trạng thái giảm

            decline_triggered_10 = False

            decline_triggered_8 = False

        decline_pct = (rolling_peak - c) / rolling_peak

        if decline_pct >= 0.08:

            decline_triggered_8 = True

        if decline_pct >= 0.10:

            decline_triggered_10 = True

        tr = h - l + 1e-10



        # 1. CLEAN UP DISTRIBUTION DAYS

        valid_dist_days = []

        for d in dist_days:

            days_passed = i - d['index']

            if days_passed <= 25 and (c < d['close'] * 1.05):

                valid_dist_days.append(d)

        dist_days = valid_dist_days



        # 2. CHECK NEW DISTRIBUTION DAY

        if pct_change <= -0.002 and v > pv:

            if (c - l) / tr < 0.6:

                dist_days.append({

                    'index': i,

                    'close': c,

                    'date': df['Date'].iloc[i]

                })



        # 3. KIỂM TRA MẤT FTD (CÁC ĐIỀU KIỆN HUỶ)

        if ftd_active:

            # Điều kiện 1: Giá thủng mức thấp nhất của phiên RA1 (Thay vì phiên FTD)

            if l < ra_low:

                ftd_active = False

                ftd_quality = None

                ftd_date = "N/A"

                ra_day = 0

                ra_low = float('inf')

            # Điều kiện 2: Thị trường giảm trên 10% từ đỉnh

            elif decline_pct >= 0.10:

                ftd_active = False

                ftd_quality = None

                ftd_date = "N/A"

                ra_day = 0

                ra_low = float('inf')



        # 4. RALLY ATTEMPT & FOLLOW-THROUGH DAY

        # CHỈ BẮT ĐẦU TÌM RA SAU KHI GIẢM > 10%

        if ra_day > 0 and not ftd_active:

            # Tiếp tục đếm RA nếu Close > Low(RA1)

            if c < ra_low:

                ra_day = 0

                ra_low = float('inf')

            else:

                ra_day += 1



                # Tính Vol trung bình 20 phiên

                avg_vol_20 = float(df['Volume'].iloc[max(0,i-20):i].mean()) if i >= 20 else v



                # Test FTD (Từ ngày 4 trở lên)

                if ra_day >= 4 and pct_change > 0.012 and v > pv:

                    ftd_active = True

                    try:

                        ftd_date = str(df['Date'].iloc[i].date()) if hasattr(df['Date'].iloc[i], 'date') else str(df['Date'].iloc[i])

                    except:

                        ftd_date = str(df['Date'].iloc[i])

                    # Reset rolling_peak để tính toán 10% từ Đỉnh Mới kể từ khi có FTD

                    rolling_peak = h

                    

                    # Phân loại FTD mạnh/yếu

                    if v > avg_vol_20 and ra_day <= 7:

                        ftd_quality = "STRONG"

                    else:

                        ftd_quality = "WEAK"

                    

                    # Xóa một phần phân phối cũ

                    dist_days = [d for d in dist_days if i - d['index'] <= 10]



        # Khởi tạo RA Day 1 – CHỈ KHI ĐÃ GIẢM > 10%

        if ra_day == 0 and decline_triggered_10:

            # Điều kiện 1: Tạo đáy mới nhưng rút chân đóng cửa ở nửa trên thanh nến

            candle_body_upper = (c - l) / tr > 0.5 and c > (h + l) / 2

            # Điều kiện 2: Phiên tăng điểm sau chuỗi giảm (Chỉ cần pct_change > 0)

            is_positive_day = pct_change > 0



            if candle_body_upper or is_positive_day:

                ra_day = 1

                ra_low = l



    # ==================================

    # PHIÊN CUỐI CÙNG – PHÂN LOẠI 7 TRẠNG THÁI

    # ==================================

    last_idx = len(df) - 1

    c_last = float(df['Close'].iloc[-1])

    ma10_last = float(df['MA10'].iloc[-1]) if not pd.isna(df['MA10'].iloc[-1]) else c_last

    ma20_last = float(df['MA20'].iloc[-1]) if not pd.isna(df['MA20'].iloc[-1]) else c_last

    ma50_last = float(df['MA50'].iloc[-1]) if not pd.isna(df['MA50'].iloc[-1]) else c_last

    kijun_last = float(df['Kijun'].iloc[-1]) if not pd.isna(df['Kijun'].iloc[-1]) else c_last



    dist_count = len(dist_days)

    decline_from_peak = (rolling_peak - c_last) / rolling_peak

    has_divergence = mom.get('rsi_divergence', False) or mom.get('macd_divergence', False)



    # Tính MA50 slope (hướng MA50)

    if len(df) >= 55 and not pd.isna(df['MA50'].iloc[-5]):

        ma50_5d_ago = float(df['MA50'].iloc[-5])

        ma50_slope_pct = (ma50_last - ma50_5d_ago) / (ma50_5d_ago + 1e-10)

    else:

        ma50_slope_pct = 0



    # Tính MA10 slope

    if len(df) >= 13 and not pd.isna(df['MA10'].iloc[-3]):

        ma10_3d_ago = float(df['MA10'].iloc[-3])

        ma10_slope_pct = (ma10_last - ma10_3d_ago) / (ma10_3d_ago + 1e-10)

    else:

        ma10_slope_pct = 0



    ma50_flat = abs(ma50_slope_pct) < 0.001  # MA50 đi ngang



    # ---- TÍNH RSI & MACD LATEST ----

    rsi_last = float(df['RSI'].iloc[-1]) if 'RSI' in df.columns else 50

    macd_last = float(df['MACD'].iloc[-1]) if 'MACD' in df.columns else 0



    # ---- PHÂN LOẠI 8 TRẠNG THÁI (ƯU TIÊN TỪ TRÊN XUỐNG) ----
    # Pre-calculate conditions for cleaner if-else
    # 1. DOWNTREND: Giảm giá mạnh (>10%), chưa có RA
    is_downtrend = (decline_from_peak >= 0.10) and (ra_day == 0) and not ftd_active
    # 2. WEAK_RECOVERY: Đang Nỗ lực hồi phục nhưng chưa có FTD
    is_weak_recovery = (decline_from_peak >= 0.10) and (ra_day > 0) and not ftd_active
    # 3. RECOVERY: Vừa giảm mạnh >10%, đã có FTD nhưng có thể chưa vượt MA50
    is_recovery = ftd_active and (rolling_peak - c_last)/rolling_peak < 0.10 and c_last <= ma50_last
    # Mây
    cloud_bottom = min(float(df['SpanA'].iloc[-1]), float(df['SpanB'].iloc[-1])) if 'SpanA' in df.columns else c_last
    # 4. MARKET_WEAKENING: Suy yếu (nằm dưới ma50 hoặc k65), tenkan < k65, giá dưới mây
    tenkan_last = float(df['Tenkan'].iloc[-1]) if 'Tenkan' in df.columns else c_last
    kijun65_last = float(df['Kijun65'].iloc[-1]) if 'Kijun65' in df.columns else ma50_last
    is_weakening = (c_last < ma50_last or c_last < kijun65_last) and (tenkan_last < kijun65_last) and (c_last < cloud_bottom)
    
    sideway_cond = abs(c_last - ma50_last) / (ma50_last + 1e-10) <= 0.05
    
    # Evaluate Regimes
    if is_downtrend:
        regime = "DOWNTREND"
        action = "ĐỨNG NGOÀI – Chỉ Mua Sớm (Bắt Đáy) nếu có tín hiệu."
        
    elif is_weak_recovery:
        regime = "WEAK_RECOVERY"
        action = "MUA SỚM – Hồi phục yếu, giới hạn tỷ trọng."
        
    elif is_weakening and not ftd_active:
        regime = "MARKET_WEAKENING"
        action = "THU TIỀN – Thị trường suy yếu nguy hiểm."

    # --- Ưu tiên các trạng thái Hồi phục khi có FTD nhưng còn dưới MA50 ---
    elif ftd_active:
        # Check if it's early recovery (within 15 days of FTD)
        is_early_recovery = False
        if ftd_date != "N/A":
            try:
                # Find how many bars since ftd_date
                ftd_dt = pd.to_datetime(ftd_date)
                bars_since = (pd.to_datetime(df['Date']) >= ftd_dt).sum()
                if bars_since <= 15:
                    is_early_recovery = True
            except: pass

        if (c_last <= ma50_last or is_early_recovery) and (decline_triggered_10 or is_early_recovery):
            # If early recovery, don't jump to 'Under Pressure' even if dist count is higher
            if c_last > ma20_last or c_last > kijun_last:
                regime = "STABLE_RECOVERY"
                action = "HỒI PHỤC ỔN ĐỊNH – Tăng tỷ trọng 50-75%."
            elif c_last > ma10_last:
                regime = "RECOVERY"
                action = "HỒI PHỤC – Thăm dò 30-50%."
            else:
                regime = "WEAK_RECOVERY"
                action = "FTD YẾU – Giá còn nằm quá sâu dưới các MA."
        else:

            # Price > MA50 or (c_last <= ma50_last but decline_triggered_10 is False and not early recovery)
            if c_last <= ma50_last:
                if is_weakening:
                    regime = "MARKET_WEAKENING"
                    action = "THU TIỀN – Thị trường suy yếu nguy hiểm."
                elif sideway_cond:
                    regime = "SIDEWAY"
                    action = "SWING TRADE – Giao dịch tại biên."
                else:
                    regime = "UPTREND_UNDER_PRESSURE"
                    action = "HẠ TỶ TRỌNG – Áp lực phân phối lớn."
            else:
                # Price > MA50 and NOT early recovery
                if dist_count >= 4 or (c_last < ma20_last and dist_count >= 2):
                    regime = "UPTREND_UNDER_PRESSURE"
                    action = "HẠ TỶ TRỌNG – Áp lực phân phối lớn."
                elif c_last > ma20_last and dist_count < 3 and rsi_last > 45:
                    regime = "UPTREND"
                    action = "TRADE MẠNH – Tập trung vào cổ phiếu Leader."
                elif decline_triggered_8:
                    regime = "WEAK_UPTREND"
                    action = "TĂNG TỶ TRỌNG – Vừa lấy lại MA50."
                else:
                    regime = "UPTREND"
                    action = "TRADE MẠNH – Bám sát danh mục."

    elif sideway_cond:
        regime = "SIDEWAY"
        action = "SWING TRADE – Giao dịch tại biên."
        
    else:
        # Fallback
        regime = "SIDEWAY"
        action = "THEO DÕI – Chờ thị trường rõ xu hướng."



    last_date = df['Date'].iloc[-1]



    result = {

        "date": last_date.strftime("%Y-%m-%d"),

        "regime": regime,

        "ftd_active": ftd_active,

        "ftd_quality": ftd_quality,

        "ftd_date": ftd_date,

        "ra_day": ra_day,

        "ra_low": round(ra_low, 2) if ra_low != float('inf') else None,

        "distribution_count": dist_count,

        "distribution_dates": [d['date'].strftime("%Y-%m-%d") for d in dist_days],

        "action": action,

        "decline_from_peak_pct": round(decline_from_peak * 100, 2),

        "rsi_bias": "BULLISH" if rsi_last > 50 else "BEARISH",

        "macd_bias": "UP" if macd_last > 0 else "DOWN"

    }



    logger.info(f"Market Analysis (Date: {result['date']}): {regime} | Dist: {dist_count} | RA: {ra_day} | Action: {action}")

    return result



def analyze_market_breadth(data_dict: dict, vnindex_ticker="VNINDEX") -> dict:

    """

    Quét toàn bộ cổ phiếu trên data (data_dict) để đo độ rộng.

    Trả về tỷ lệ Mã Tăng/Giảm, Dòng tiền lan toả và Phân kỳ RSI (nếu có).

    Lưu ý: Yêu cầu data_dict chứa nhiều mã cổ phiếu của toàn thị trường.

    """

    total_stocks = 0

    up_stocks = 0

    down_stocks = 0

    flat_stocks = 0



    # Leader tracks

    breakout_count = 0

    strong_stocks_ma50 = 0

    strong_stocks_ma20 = 0



    # Lấy ngày tham chiếu từ VNINDEX
    idx_df = data_dict.get(vnindex_ticker)
    ref_date = idx_df['Date'].iloc[-1] if idx_df is not None and not idx_df.empty else None

    for ticker, df in list(data_dict.items()):
        if ticker in [vnindex_ticker, "HNXINDEX", "UPCOM", "VN30", "HNX30"]:
            continue

        if len(df) < 50: 
            continue

        # 1. Kiểm tra nếu mã đã ngưng giao dịch quá lâu (>30 ngày) -> Loại bỏ
        if ref_date is not None:
            last_date = df['Date'].iloc[-1]
            if (ref_date - last_date).days > 30:
                continue

        # 2. Lấy dữ liệu phiên cuối có giá trị (ffill logic)
        # Nếu phiên cuối Vol=0, vẫn lấy giá Close của nó (vì giá thường được giữ nguyên)
        last_row = df.iloc[-1]
        c = float(last_row['Close'])
        v = float(last_row['Volume'])
        
        # Chỉ loại bỏ nếu giá không hợp lệ (<=0) hoặc dữ liệu rỗng hoàn toàn
        if pd.isna(c) or c <= 0:
            continue

        pc = float(df['Close'].iloc[-2])
        av20 = float(df['Volume'].iloc[-20:].mean())

        total_stocks += 1

        pct = (c - pc) / pc

        if pct > 0.01:

            up_stocks += 1

        elif pct < -0.01:

            down_stocks += 1

        else:

            flat_stocks += 1



        # Check Breakout (Very basic proxy: nổ vol vượt đỉnh ngắn)

        highest_20 = df['High'].iloc[-21:-1].max() if len(df) > 21 else df['High'][:-1].max()

        if c > highest_20 and v > av20 * 1.5:

            breakout_count += 1



        # Dòng tiền giữ giá: Close > MA50

        ma50 = df['Close'].iloc[-50:].mean() if len(df) >= 50 else df['Close'].mean()

        if c > ma50:

            strong_stocks_ma50 += 1



        # Close > MA20

        ma20 = df['Close'].iloc[-20:].mean() if len(df) >= 20 else df['Close'].mean()

        if c > ma20:

            strong_stocks_ma20 += 1



    breadth_ratio = "TỐT" if up_stocks > down_stocks * 1.5 else ("XẤU" if down_stocks > up_stocks * 1.5 else "CÂN BẰNG")



    return {

        "total_scanned": total_stocks,

        "advances": up_stocks,

        "declines": down_stocks,

        "unaltered": flat_stocks,

        "breadth_label": breadth_ratio,

        "breakout_leaders": breakout_count,

        "strong_stocks_pct": round(strong_stocks_ma50 / total_stocks * 100, 1) if total_stocks > 0 else 0,

        "strong_stocks_ma20_pct": round(strong_stocks_ma20 / total_stocks * 100, 1) if total_stocks > 0 else 0

    }



# Removed evaluate_market_score as per request.



def analyze_momentum_divergence(df: pd.DataFrame) -> dict:

    """

    Tính RSI (14) và MACD (12, 26, 9) để dò tìm phân kỳ đỉnh (Bearish Divergence).

    Dựa trên sự đối chiếu so sánh đỉnh của 15 ngày qua với 15 ngày xa hơn.

    """

    if len(df) < 50:

        return {"rsi_val": 0, "macd_val": 0, "hist_val": 0, "rsi_divergence": False, "macd_divergence": False, "is_bad_zone": False}



    # Tính RSI

    delta = df['Close'].diff()

    up = delta.clip(lower=0)

    down = -delta.clip(upper=0)

    ma_up = up.ewm(com=13, adjust=False).mean()

    ma_down = down.ewm(com=13, adjust=False).mean()

    rs = ma_up / ma_down

    rsi = 100 - (100 / (1 + rs))



    # Tính MACD

    ema_fast = df['Close'].ewm(span=12, adjust=False).mean()

    ema_slow = df['Close'].ewm(span=26, adjust=False).mean()

    macd = ema_fast - ema_slow

    sig = macd.ewm(span=9, adjust=False).mean()

    hist = macd - sig



    # Phân kỳ Đỉnh (Bearish Divergence)

    # Define peak variables for divergence calculation
    price_top_1 = df['Close'].iloc[-15:].max()
    price_top_2 = df['Close'].iloc[-30:-15].max()
    rsi_last_15 = rsi.iloc[-15:].max()
    rsi_prev_15 = rsi.iloc[-30:-15].max()
    macd_last_15 = macd.iloc[-15:].max()
    macd_prev_15 = macd.iloc[-30:-15].max()

    rsi_div_bear = (price_top_1 > price_top_2) and (rsi_last_15 < rsi_prev_15 * 0.96)

    macd_div_bear = (price_top_1 > price_top_2) and (macd_last_15 < macd_prev_15 * 0.92)



    # Phân kỳ Đáy (Bullish Divergence)

    price_low_1 = df['Close'].iloc[-15:].min()

    price_low_2 = df['Close'].iloc[-30:-15].min()

    rsi_low_1 = rsi.iloc[-15:].min()

    rsi_low_2 = rsi.iloc[-30:-15].min()

    macd_low_1 = macd.iloc[-15:].min()

    macd_low_2 = macd.iloc[-30:-15].min()



    rsi_div_bull = (price_low_1 < price_low_2) and (rsi_low_1 > rsi_low_2 * 1.05)

    macd_div_bull = (price_low_1 < price_low_2) and (macd_low_1 > macd_low_2 + 0.1)



    # Vùng tin cậy cao

    is_rsi_extreme = rsi.iloc[-1] > 75 or rsi.iloc[-1] < 25



    return {

        "rsi_val": round(float(rsi.iloc[-1]), 2),

        "macd_val": round(float(macd.iloc[-1]), 2),

        "hist_val": round(float(hist.iloc[-1]), 2),

        "rsi_divergence": bool(rsi_div_bear),

        "macd_divergence": bool(macd_div_bear),

        "bullish_divergence": bool(rsi_div_bull or macd_div_bull),

        "is_bad_zone": bool(is_rsi_extreme or (macd.iloc[-1] < 0 and hist.iloc[-1] < 0))

    }



def calculate_index_sr(df: pd.DataFrame) -> dict:

    """

    Tính vùng Hỗ trợ / Kháng cự cho Index theo thuật toán riêng.

    Cải tiến: Tìm đỉnh/đáy cục bộ trong 250 phiên để có dữ liệu tin cậy hơn.

    """

    if df is None or df.empty or len(df) < 50:

        return {"s1": 0, "s2": 0, "r1": 0, "r2": 0}



    cp = float(df['Close'].iloc[-1])

    

    # 0. Tính toán các chỉ báo bổ trợ

    ma20_s = df['Close'].rolling(20).mean()

    ma100_s = df['Close'].rolling(100).mean()

    ma200_s = df['Close'].rolling(200).mean()

    

    ma20 = float(ma20_s.iloc[-1]) if not pd.isna(ma20_s.iloc[-1]) else 0

    ma100 = float(ma100_s.iloc[-1]) if not pd.isna(ma100_s.iloc[-1]) else 0

    ma200 = float(ma200_s.iloc[-1]) if not pd.isna(ma200_s.iloc[-1]) else 0

    

    # Kijun (Đường trung bình 26 phiên của High/Low)

    hi26 = df['High'].rolling(26).max()

    lo26 = df['Low'].rolling(26).min()

    kijun = float((hi26.iloc[-1] + lo26.iloc[-1]) / 2) if not (pd.isna(hi26.iloc[-1]) or pd.isna(lo26.iloc[-1])) else 0



    # 1. Thu thập các Đỉnh (Peaks) và Đáy (Valleys) cục bộ trong 250 phiên

    lookback = min(90, len(df) - 10)

    peaks = []

    valleys = []

    

    # Quét từ quá khứ đến sát hiện tại (loại bỏ 2 nến cuối để tránh nhiễu nến đang chạy)

    for i in range(len(df) - lookback, len(df) - 2):

        if i < 5: continue

        window_high = df['High'].iloc[i-5:i+6].max()

        window_low = df['Low'].iloc[i-5:i+6].min()

        

        val_high = float(df['High'].iloc[i])

        val_low = float(df['Low'].iloc[i])

        

        if val_high == window_high:

            peaks.append(val_high)

        if val_low == window_low:

            valleys.append(val_low)



    # Loại bỏ trùng lặp và sắp xếp

    # Keep chronological order
    # peaks = sorted(list(set(peaks)))

    # valleys = sorted(list(set(valleys)))



    # 2. Tính Hỗ trợ (S)

    s_candidates = []

    

    # - Đỉnh cũ đã vượt qua gần nhất (Peak < cp, lấy max)

    peaks_below = [p for p in peaks if p < cp]

    if peaks_below:

        s_candidates.append(peaks_below[-1])

        

    # - Đáy cũ đã vượt qua gần nhất bên dưới (Valley < cp, lấy max)

    # - Đáy cũ thứ 2 đã vượt qua thấp hơn (Valley < cp, lấy max thứ 2)

    valleys_below = [v for v in valleys if v < cp]

    if len(valleys_below) >= 1:

        s_candidates.append(valleys_below[-1])

    if len(valleys_below) >= 2:

        s_candidates.append(valleys_below[-2])

        

    # - MA100, MA200 nếu giá hiện tại đang nằm trên chúng

    if ma20 > 0 and cp > ma20: s_candidates.append(ma20)
    if ma50 > 0 and cp > ma50: s_candidates.append(ma50)
    if ma100 > 0 and cp > ma100: s_candidates.append(ma100)

    if ma200 > 0 and cp > ma200: s_candidates.append(ma200)



    # Quy tắc: s1 = max, s2 = max thứ 2 (s2 < s1)

    s_candidates = sorted(list(set(s_candidates)), reverse=True)

    s1 = s_candidates[0] if len(s_candidates) > 0 else 0

    s2 = s_candidates[1] if len(s_candidates) > 1 else 0



    # 3. Tính Kháng cự (R)

    r_candidates = []

    

    # - Đáy cũ phía trên giá hiện tại (Valley > cp, lấy min)

    valleys_above = [v for v in valleys if v > cp]

    if valleys_above:

        r_candidates.append(valleys_above[-1])

        

    # - Đỉnh gần nhất phía trên giá hiện tại (Peak > cp, lấy min)

    peaks_above = [p for p in peaks if p > cp]

    if peaks_above:

        r_candidates.append(peaks_above[-1])

        

    # - MA100, MA200 nếu giá hiện tại nằm dưới chúng

    if ma100 > 0 and cp < ma100: r_candidates.append(ma100)

    if ma200 > 0 and cp < ma200: r_candidates.append(ma200)

    

    # - Đường MA20 nếu giá hiện tại nằm dưới MA20

    if ma20 > 0 and cp < ma20: r_candidates.append(ma20)

    

    # - Đường Kijun nếu giá hiện tại nằm dưới Kijun

    if kijun > 0 and cp < kijun: r_candidates.append(kijun)



    # Quy tắc: r1 = min, r2 = min thứ 2 (r2 > r1)

    r_candidates = sorted(list(set(r_candidates)))

    r1 = r_candidates[0] if len(r_candidates) > 0 else 0

    r2 = r_candidates[1] if len(r_candidates) > 1 else 0



    return {

        "s1": round(s1, 2),

        "s2": round(s2, 2),

        "r1": round(r1, 2),

        "r2": round(r2, 2)

    }

