import pandas as pd
import numpy as np

def evaluate_ichimoku(df: pd.DataFrame, idx: int = -1) -> dict:
    """"Phân tích chuyên sâu hệ thống Ichimoku dựa theo 4 tầng giao dịch."""
    if len(df) < abs(idx) + 26:
        return {"status": "Không đủ dữ liệu", "action": "N/A"}
        
    last = df.iloc[idx]
    
    price = float(last['Close'])
    def _get_val(col, i=idx, default=price):
        if col not in df.columns: return default
        val = df[col].iloc[i]
        try:
            return float(val) if not pd.isna(val) else default
        except:
            return default

    tenkan = _get_val('Tenkan')
    kijun = _get_val('Kijun')
    span_a = _get_val('SpanA')
    span_b = _get_val('SpanB')
    
    cloud_top = max(span_a, span_b)
    cloud_bottom = min(span_a, span_b)
    cloud_thickness = cloud_top - cloud_bottom
    is_cloud_green = span_a >= span_b
    
    # Kumo ahead
    prev_span_a = _get_val('SpanA', idx-5) if len(df) >= abs(idx)+5 else span_a
    is_kumo_rising = span_a > prev_span_a
    
    # Chikou Span: Giá hiện tại so với giá của 26 phiên trước 
    price_26_ago = _get_val('Close', idx-26)
    chikou_bullish = price > price_26_ago
    
    # Xác định các tín hiệu
    tk_cross_up = tenkan > kijun
    tk_cross_down = tenkan < kijun
    
    # Vị trí giá so với Mây Kumo
    above_cloud = price > cloud_top
    below_cloud = price < cloud_bottom
    inside_cloud = cloud_bottom <= price <= cloud_top
    
    status = []
    action = []
    
    # ============================================================
    # 🌟 4 TRẠNG THÁI THỊ TRƯỜNG THEO ICHIMOKU
    # ============================================================
    
    # 🟢 1. STRONG TREND (KÈO NGON NHẤT)
    if above_cloud and tk_cross_up and is_kumo_rising and chikou_bullish:
        status.append("STRONG UPTREND (Xu hướng MẠNH NHẤT): Giá trên mây, Tenkan > Kijun, Chikou trống đường.")
        action.append("All-in mindset. Canh giá Pullback về Tenkan (nhanh) hoặc Kijun (an toàn) để BUY.")
        
    # 🟡 2. WEAK TREND (NẰM TRÊN MÂY NHƯNG TK SUY YẾU)
    elif above_cloud and tk_cross_down:
        status.append("WEAK UPTREND: Giá trên mây nhưng động lượng yếu (Tenkan cắt xuống Kijun).")
        action.append("Trend yếu, dễ điều chỉnh. Giảm size lệnh và chờ xác nhận lại.")
        
    # 🔴 4. REVERSAL (ĐẢO CHIỀU)
    elif inside_cloud and tk_cross_down and not chikou_bullish:
        # Nếu trước đó đang trên mây (check 5-10 phiên trước)
        past_price = _get_val('Close', idx-5)
        past_span_a = _get_val('SpanA', idx-5)
        past_span_b = _get_val('SpanB', idx-5)
        past_cloud_top = max(past_span_a, past_span_b)
        if past_price > past_cloud_top:
            status.append("REVERSAL (ĐẢO CHIỀU): Giá từ trên mây chui vào mây, Tenkan < Kijun, Chikou bị cản.")
            action.append("Trend đang CHẾT. Hạn chế mua mới, hạ tỷ trọng ngay lập tức.")
            
    # ⚪ 3. SIDEWAY (DEATH ZONE)
    elif inside_cloud:
        status.append("SIDEWAY (DEATH ZONE): Giá kẹt trong vùng chiến tranh (Kumo).")
        action.append("Nhiễu tín hiệu. Đứng ngoài / CẤM TRADE.")
        
    # ============================================================
    # KHÚC TRỪ TRỜI (DOWN TREND RÕ RÀNG)
    elif below_cloud:
        if tk_cross_down and not is_kumo_rising:
            status.append("STRONG DOWNTREND: Giá rớt dưới mây, Mây dốc xuống.")
            action.append("Chỉ canh SHORT / Tránh mua tuyệt đối.")
        elif tk_cross_up:
            status.append("BEAR MARKET RALLY: Sóng hồi kỹ thuật dưới đáy mây (Tenkan cắt lên Kijun dưới Kumo).")
            action.append("Sóng hồi yếu, chỉ đánh T+ ngắn tỷ trọng nhỏ hoặc chờ chốt.")
            
    # ============================================================
    # 🚀 SETUP KIẾM TIỀN - HỖ TRỢ ĐỘNG
    # ============================================================
    
    # Setup 2: KUMO BREAKOUT
    # Kểm tra nếu vừa break lên từ dưới
    past_price_2 = _get_val('Close', idx-2)
    past_span_a_2 = _get_val('SpanA', idx-2)
    past_span_b_2 = _get_val('SpanB', idx-2)
    past_cloud_top_2 = max(past_span_a_2, past_span_b_2)
    if past_price_2 <= past_cloud_top_2 and price > cloud_top and tk_cross_up and is_cloud_green:
        status.append("SETUP 2 (KUMO BREAKOUT): Xuyên mây thành công, Tenkan cắt Kijun, Kumo xanh tương lai.")
        action.append("Bắt đầu Trend Uptrend mới. TÍN HIỆU MUA XÁC NHẬN.")
        
    # Setup 3: KIJUN BOUNCE / PULLBACK
    if above_cloud and tk_cross_up:
        # Kijun là Nam châm giá
        if abs(price - kijun)/kijun < 0.015:  # Chạm Kijun (dao động 1.5%)
            open_price = _get_val('Open')
            if price > open_price: # Nến bật lên (xanh)
                status.append("SETUP 3 (KIJUN BOUNCE): Giá nhúng về Kijun và bật lên trong Uptrend.")
                action.append("Entry MUA cực đẹp. Vào hàng ngay vùng giá này.")
        
    # Kumo Thickness Evaluation
    if above_cloud and (price - cloud_top) / price < 0.03: # Ráp mây
        if cloud_thickness / price > 0.05:
            status.append("Hỗ trợ Kumo: Mây đỡ bên dưới rất DÀY.")
            action.append("Khó có khả năng thủng mây, yên tâm nắm giữ.")
        else:
            status.append("Hỗ trợ Kumo: Mây đỡ bên dưới rất MỎNG.")
            action.append("Xác suất bị xuyên thủng cao, cần cảnh giác bảo vệ vị thế.")
            
    # Giao cắt Tenkan/Kijun Analysis
    prev_tenkan = _get_val('Tenkan', idx-1)
    prev_kijun = _get_val('Kijun', idx-1)
    if tk_cross_up and not prev_tenkan > prev_kijun:
        # Vừa mới cắt lên 
        if above_cloud:
            status.append("Tín hiệu MUA MẠNH: Giao cắt Vàng (Tenkan lên Kijun) TRÊN MÂY.")
        elif inside_cloud:
            status.append("Tín hiệu MUA TRUNG BÌNH: Giao cắt Vàng (Tenkan lên Kijun) TRONG MÂY.")
        else:
            status.append("Tín hiệu MUA YẾU: Giao cắt Vàng (Tenkan lên Kijun) DƯỚI MÂY.")

    if not status:
        status.append("Trạng thái tích lũy mờ nhạt, chưa có tín hiệu Ichimoku nổi bật.")
        action.append("Tiếp tục quan sát diễn biến hoặc tham khảo indicator khac.")

    return {
        "status": status[0] if len(status) == 1 else "\n".join("- " + s for s in status),
        "action": action[0] if len(action) == 1 else "\n".join("- " + a for a in action)
    }
