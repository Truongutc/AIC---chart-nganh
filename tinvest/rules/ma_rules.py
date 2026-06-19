import pandas as pd
import numpy as np

def evaluate_ma(df: pd.DataFrame, idx: int = -1) -> dict:
    """"Phân tích hành vi thị trường dựa trên hệ thống Đường Trung Bình Động (MA)."""
    if len(df) < abs(idx) + 200: # Cần dữ liệu đủ sâu cho MA200, xử lý an toàn
        # Nếu chưa đủ 200 phiên, fallback chạy bộ MA ngắn
        has_ma200 = False
    else:
        has_ma200 = True
        
    if len(df) < abs(idx) + 50:
        return {"status": "Không đủ dữ liệu chạy MA", "action": "N/A",
                "is_break_confirmed": False, "has_any_break_signal": False}
        
    last = df.iloc[idx]
    prev1 = df.iloc[idx-1]
    prev5 = df.iloc[idx-5] if len(df) >= abs(idx)+5 else prev1
    # Lookback 10 phiên cho phát hiện xu hướng gãy
    prev10 = df.iloc[idx-10] if len(df) >= abs(idx)+10 else prev5

    price = float(last['Close'])
    ma10 = float(last.get('MA10', price))
    ma20 = float(last.get('MA20', price))
    ma50 = float(last.get('MA50', price))
    ma200 = float(last.get('MA200', price)) if has_ma200 and 'MA200' in df.columns and not pd.isna(last.get('MA200')) else None
    
    ma20_prev = float(prev1.get('MA20', ma20))
    ma50_prev = float(prev1.get('MA50', ma50))
    
    ma20_slope = (ma20 - float(prev5.get('MA20', ma20))) / 5
    ma50_slope = (ma50 - float(prev5.get('MA50', ma50))) / 5
    
    # Check if MAs are "dốc lên" (Rising)
    is_ma20_rising = ma20 > ma20_prev and ma20_slope > 0
    is_ma50_rising = ma50 > ma50_prev and ma50_slope > 0
    is_ma_flat = abs(ma20_slope) < (price * 0.001) # Rất phẳng
    
    status = []
    action = []
    
    # 🌟 ĐỘ KHỎE (MOMENTUM) & VỊ TRÍ GIÁ
    distance_to_ma20 = (price - ma20) / ma20
    is_too_far = distance_to_ma20 > 0.07 # Cách xa > 7%
    is_near_ma20 = -0.015 <= distance_to_ma20 <= 0.03 # Giá quanh MA20
    
    # 🌟 TẦNG 1: XU HƯỚNG & 4 TRẠNG THÁI THỊ TRƯỜNG
    
    # TẦNG 1: UPTREND CHUẨN — is_downtrend bỏ hẳn (xử lý bởi state_engine.trend_bias=-1)
    if ma200 is not None:
        is_perfect_uptrend = price > ma20 > ma50 > ma200
    else:
        is_perfect_uptrend = price > ma20 > ma50

    # --- Phát hiện xu hướng gãy (lookback 10 phiên) ---
    # Kiểm tra xem trong 10 phiên qua có phiên nào đang trong uptrend ĐẦY ĐỦ không:
    # giá > MA20 > MA50 VÀ MA10 > MA50 (đảm bảo không phải nhịp hồi kỹ thuật ngắn)
    had_uptrend_recently = False
    if 'MA20' in df.columns and 'MA50' in df.columns and 'MA10' in df.columns:
        start_idx = idx - 10 if len(df) >= abs(idx) + 10 else -len(df)
        if idx < 0:
            recent_df = df.iloc[start_idx:idx]
        else:
            recent_df = df.iloc[max(0, idx-10):idx]
            
        # Uptrend "đầy đủ": giá > MA20 > MA50 và MA10 cũng nằm trên MA50
        # Điều kiện MA10 > MA50 loại trừ các nhịp hồi kỹ thuật ngắn trong downtrend
        cond = ((recent_df['Close'] > recent_df['MA20'])
                & (recent_df['MA20'] > recent_df['MA50'])
                & (recent_df['MA10'] > recent_df['MA50']))
        had_uptrend_recently = cond.any()

    # ── NHÓM A: Cảnh báo xu hướng sớm (CHƯA GÃY, cần theo dõi thêm) ──────────────
    #
    # pre_break_1: Cảnh báo sớm loại 1 (có lookback uptrend đầy đủ)
    #   Trong 10p trước từng có uptrend đầy đủ (giá>MA20>MA50 & MA10>MA50).
    #   Hiện tại: giá thủng MA50 nhưng MA20 vẫn còn trên MA50 (death cross chưa xảy ra)
    #   + giá < MA10 (loại trừ trường hợp giá chỉ đóng xoắn quanh MA50)
    pre_break_1 = (had_uptrend_recently
                   and price < ma50 and ma20 > ma50
                   and price < ma10)

    # pre_break_2: Cảnh báo sớm loại 2 (không cần lookback)
    #   Giá thủng hết cả MA10, MA20, MA50 nhưng chưa giảm quá 5% dưới MA50
    #   → Vẫn trong ngưỡng có thể hồi về — chưa xác nhận downtrend (yêu cầu MA10 > MA50)
    pre_break_2 = (price < ma10 and price < ma20 and price < ma50
                   and price >= ma50 * 0.95 and ma10 > ma50)

    # ── NHÓM B: Gãy trend ĐÃ XÁC NHẬN (nên cắt lỗ) ──────────────────────────────
    #
    # break_confirmed_1: Xác nhận gãy loại 1 (có lookback uptrend đầy đủ)
    #   Trong 10p trước từng có uptrend đầy đủ.
    #   Hiện tại: giá < MA20, MA20 cắt xuống dưới MA50 (death cross xảy ra)
    #   + giá < MA10 (đảm bảo không phải đóng xoắn MA)
    break_confirmed_1 = (had_uptrend_recently
                         and price < ma50 and price < ma20 and ma20 < ma50
                         and price < ma10)

    # break_confirmed_2: Xác nhận gãy loại 2 (không cần lookback)
    #   Giá thủng MA10, MA20 và giảm hơn 5% dưới MA50
    #   → Phá hỗ trợ động nghiêm trọng, xu hướng không thể phục hồi ngắn hạn
    break_confirmed_2 = (price < ma10 and price < ma20 and price < ma50 * 0.95)

    # Tổng hợp: có bất kỳ tín hiệu nào (sớm hoặc xác nhận)
    has_any_break_signal = pre_break_1 or break_confirmed_1 or pre_break_2 or break_confirmed_2

    # is_break_confirmed: CHỈ True khi gãy trend ĐƯỢC XÁC NHẬN HOÀN TOÀN.
    # Đây là field dùng trong portfolio_engine và valuation_engine để quyết định bán/thoát.
    # KHÔNG bao giờ dùng has_any_break_signal hay string matching để làm lệnh bán.
    is_break_confirmed = break_confirmed_1 or break_confirmed_2

    # TRẠNG THÁI 1: STRONG TREND
    if is_perfect_uptrend and is_ma20_rising and is_ma50_rising:
        if is_too_far:
            status.append("BẪY: Giá quá xa MA20 trong Strong Trend.")
            action.append("90% dính Pullback. Không FOMO mua đuổi, chờ giá hãm phanh.")
        elif is_near_ma20:
            status.append("STRONG TREND (Kèo ngon): Giá > MA20 > MA50 > 200, các đường MA dốc lên.")
            action.append("Chỉ BUY Pullback. Entry cực đẹp quanh MA20 hoặc MA50.")
        else:
            status.append("STRONG TREND: Xu hướng mạnh (MA xếp lớp chuẩn).")
            action.append("Dòng tiền đang vào, ưu tiên nắm giữ theo trend.")
            
    # TRẠNG THÁI 2: EARLY TREND
    elif price > ma50 and float(prev5['Close']) <= float(prev5.get('MA50', price)) and is_ma50_rising:
        status.append("EARLY TREND: Giá vừa vượt MA50 và MA50 bắt đầu xoay lên.")
        action.append("Trend mới nhú, có thể MUA SỚM (Risk cao hơn).")
        
    # TRẠNG THÁI 3: XU HƯỚNG GÃY (phân biệt cảnh báo sớm vs. xác nhận)
    elif has_any_break_signal:
        if break_confirmed_2:
            # Xác nhận gãy mạnh: giá < MA10 < MA20, giá < 0.95*MA50
            status.append("TREND GÃY (Xác nhận mạnh): Giá < MA10 < MA20 < MA50 và phá thêm 5% dưới MA50 — Downtrend nghiêm trọng.")
            action.append("Xu hướng tăng đã chết hoàn toàn. CẮT LỖ KHẨN CẤP. Tuyệt đối không bắt đáy.")
        elif break_confirmed_1:
            # Xác nhận gãy loại 1: death cross MA20 cắt xuống MA50
            status.append("TREND GÃY (Xác nhận): Giá < MA10 < MA20, MA20 cắt xuống MA50 — Downtrend hoàn toàn.")
            action.append("Xu hướng tăng đã chết. CẮT LỖ KHẨN CẤP. Tuyệt đối không bắt đáy.")
        elif pre_break_2:
            # Cảnh báo sớm loại 2: giá thủng cả 3 MA nhưng chưa quá 5% dưới MA50
            status.append("CẢNH BÁO XU HƯỚNG (Sớm): Giá thủng cả MA10, MA20, MA50 nhưng chưa quá 5% dưới MA50 — Đang phá hỗ trợ.")
            action.append("CANH EXIT khẩn. Giảm vị thế phòng thủ. Nếu giá không hồi về trên MA50 → thoát hết.")
        else:
            # Cảnh báo sớm loại 1: giá thủng MA50, MA20 vẫn trên MA50 (chưa death cross)
            status.append("CẢNH BÁO XU HƯỚNG (Sớm): Giá thủng MA50 trong khi MA20 vẫn trên MA50 — Xu hướng đang suy yếu.")
            action.append("Giảm vị thế phòng thủ. Chờ xác nhận thêm — nếu MA20 cắt xuống MA50 thì thoát hết.")

    # TRẠNG THÁI 4: SIDEWAY / Trung gian (downtrend nhẹ xử lý bởi state_engine)
    elif not is_perfect_uptrend:
        # Cross lên cắt xuống liên tục hoặc giá quấn quanh MA20/50
        cross_up = ma20 > ma50 and ma20_prev <= ma50_prev
        cross_down = ma20 < ma50 and ma20_prev >= ma50_prev
        if is_ma_flat or cross_up or cross_down:
            status.append("SIDEWAY / WHIPSAW: Giá quấn quanh MA, đường MA nằm ngang.")
            action.append("Thị trường đi ngang nhiễu loạn, bị vả liên tục nếu đánh Trend. BỤ QUA.")
  
    # 🌟 CÁC SETUP KIẾM TIỀN THEO MA
    
    # Breakout Đỉnh (Swing High) và MA20 Support
    past_swings = [h for h in df['SwingHigh'].iloc[-15:idx] if h > 0]
    if past_swings and price > past_swings[-1] and price > ma20 and is_ma20_rising:
        status.append("SETUP 3 (BREAKOUT + MA SUPPORT): Giá phá đỉnh, MA20 nâng đỡ dưới chân.")
        action.append("Trend được củng cố. Tiếp tục HOLD dồn vị thế.")
        
    # Setup 1 & 2: Pullback và Bounce
    # Check nếu nến hiện tại xanh (Open < Close) và chạm hỗ trợ
    if price > float(last['Open']): # Nến tăng
        low_price = float(last['Low'])
        # Chạm MA20 và Rút Chân
        if low_price <= ma20 and price > ma20 and is_perfect_uptrend:
            status.append("SETUP 1 (PULLBACK MA20): Kèo ăn dày nhất. Giá test MA20 thành công.")
            action.append("BUY MẠNH. Hỗ trợ MA20 đã đỡ giá tốt trong Uptrend.")
        # Chạm MA50 và Rút Chân
        elif low_price <= ma50 and price > ma50 and ma50_slope > 0:
            status.append("SETUP 2 (MA50 BOUNCE): Chạm hỗ trợ trung hạn MA50 và bật lên.")
            action.append("BUY AN TOÀN. Mức RR (Risk/Reward) lúc này là rất tốt.")
            
    # Xử lý BẪY TRẬP
    if is_ma_flat and price > ma20:
        status.append("BẪY MOMENTUM: Giá nằm trên MA20 nhưng MA20 phẳng lì.")
        action.append("Dòng tiền yểu điệu, không phải Trend khỏe thực thụ.")
        
    if ma200 is not None:
        golden_cross = ma50 > ma200 and ma50_prev <= float(prev1.get('MA200', ma200))
        if golden_cross:
            status.append("BẪY CHẾT NGƯỜI: Golden Cross (MA50 cắt MA200) vừa xảy ra.")
            action.append("Tín hiệu có độ trễ cực cao (Lag nặng). Thận trọng vì giá đa phần đã xả hàng lúc này.")

    # FALLBACK NẾU KHÔNG VÀO CASE NÀO
    if not status:
        status.append(f"Giá nằm {'Tên' if price > ma20 else 'Dưới'} MA20, thiếu xung lực rõ ràng.")
        action.append("Quan sát thêm các mốc giá, chưa có Setup chuẩn theo MA.")

    return {
        "status": status[0] if len(status) == 1 else "\n".join("- " + s for s in status),
        "action": action[0] if len(action) == 1 else "\n".join("- " + a for a in action),
        # ── Boolean fields ──────────────────────────────────────────────────────────
        # is_break_confirmed: ĐÚNG khi gãy trend ĐÃ XÁC NHẬN HOÀN TOÀN.
        #   Dùng trong portfolio_engine, valuation_engine, analyzer để ra lệnh thoát/bán.
        #   Không bao giờ dùng string matching trên 'status' để thay thế field này.
        "is_break_confirmed": is_break_confirmed,
        # has_any_break_signal: True khi có bất kỳ tín hiệu cảnh báo hoặc xác nhận nào.
        #   Chỉ dùng để hiển thị cảnh báo/màu sắc trên UI, KHÔNG dùng để ra lệnh bán.
        "has_any_break_signal": has_any_break_signal,
    }
