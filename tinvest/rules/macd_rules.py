import pandas as pd

def evaluate_macd(df: pd.DataFrame, idx: int = -1) -> dict:
    """"Phân tích chuyên sâu MACD: Zero-line, Giao cắt, và Histogram."""
    if len(df) < abs(idx) + 10:
        return {"status": "Không đủ dữ liệu", "action": "N/A"}
        
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    macd = float(last.get('MACD', 0))
    macd_prev = float(prev.get('MACD', 0))
    
    # Signal is exactly MACD - Hist
    hist = float(last.get('MACD_Hist', 0))
    hist_prev = float(prev.get('MACD_Hist', 0))
    hist_prev2 = float(df.iloc[idx-2].get('MACD_Hist', 0)) if len(df) > abs(idx)+2 else hist_prev
    
    rsi = float(last.get('RSI', 50))
    vol = float(last.get('Volume', 0))
    avg_vol = float(last.get('AvgVolume20', vol))
    
    ma20 = float(last.get('MA20', last['Close']))
    ma50 = float(last.get('MA50', last['Close']))
    is_sideway = (abs(last['Close'] - ma50)/ma50 < 0.05) and (abs(ma20 - ma50)/ma50 < 0.05)
    
    status = []
    action = []
    
    # --- Divergence Check ---
    recent_lows = df[df['SwingLow'] > 0]
    if len(recent_lows) >= 2:
        idx1 = recent_lows.index[-1] # most recent
        idx2 = recent_lows.index[-2] # previous
        p1, p2 = recent_lows['Low'].iloc[-1], recent_lows['Low'].iloc[-2]
        
        m1, m2 = df['MACD'].loc[idx1], df['MACD'].loc[idx2]
        if p1 < p2 and m1 > m2:
            status.append("PHÂN KỲ ĐÁY MACD (Bullish Divergence): Giá tạo đáy thấp rớt đáy nhưng MACD tạo đáy cao hơn.")
            action.append("Lực bán đã hết đà, chờ xác nhận nến để MUA VÀO.")

    recent_highs = df[df['SwingHigh'] > 0]
    if len(recent_highs) >= 2:
        idx1 = recent_highs.index[-1]
        idx2 = recent_highs.index[-2]
        p1, p2 = recent_highs['High'].iloc[-1], recent_highs['High'].iloc[-2]
        
        m1, m2 = df['MACD'].loc[idx1], df['MACD'].loc[idx2]
        if p1 > p2 and m1 < m2:
            status.append("PHÂN KỲ ĐỈNH MACD (Bearish Divergence): Giá kéo đỉnh mới nhưng MACD đỉnh lại thấp hơn.")
            action.append("Lực kéo kéo xả (Rủi ro Sập). Chờ xác nhận để CHỐT LỜI/SHORT.")
    # -----------------------
    
    # 1. Trạng thái Histogram (Động lượng)
    if hist > 0 and hist < hist_prev and hist_prev < hist_prev2:
        status.append("Histogram Dương nhưng đang CO LẠI (Momentum tăng yếu đi).")
        action.append("Chuẩn bị chốt lời / Không mở mua mới.")
    elif hist < 0 and hist > hist_prev and hist_prev > hist_prev2:
        status.append("Histogram Âm nhưng đang THU HẸP (Lực bán cạn).")
        action.append("Chuẩn bị tạo đáy, theo dõi chặt chẽ.")
        
    # 2. Vị thế Zero Line (Setup Trend)
    # Pullback Entry: MACD > 0, price adjust, Hist drops then rises.
    if macd > 0 and hist > hist_prev and hist_prev < 0:
        status.append("Setup Pullback: MACD > 0, Histogram bắt đầu đảo chiều tăng.")
        action.append("ENTRY NGON: Điểm mua chuẩn nhất theo MACD.")
        
    elif macd > 0:
        status.append("MACD > 0 (Trend tăng trung hạn).")
    elif macd < 0:
        status.append("MACD < 0 (Trend giảm trung hạn).")
        
    # 3. Giao Cắt Signal (Giao cắt MACD vs Signal = Hist cắt 0)
    cross_up = hist > 0 and hist_prev <= 0
    cross_dn = hist < 0 and hist_prev >= 0
    
    if cross_up:
        if is_sideway:
            status.append("Giao Cắt Tăng (Cross Up) NHƯNG đang Sideway (Rất dễ nhiễu).")
        elif macd > 0 and rsi > 50:
            status.append("Giao Cắt Tăng XỊN: Trend KHỎE (MACD > 0, RSI > 50).")
            action.append("Trend tăng + Momentum xác nhận -> HOLD HOẶC BUY.")
    elif cross_dn:
        if macd < 0 and rsi < 50:
            status.append("Giao Cắt Giảm: Trend suy yếu nặng.")
            action.append("Tránh xa / Canh bán.")

    # 4. Filter Fake Breakout
    # Giá tăng mạnh hôm nay, vol thấp, macd yếu => Fake
    price_surge = last['Close'] > prev['Close'] * 1.03
    if price_surge:
        if hist > hist_prev and vol > avg_vol * 1.2:
            status.append("Breakout Thật: Giá tăng + Vol tăng + Histogram mở rộng.")
            action.append("Follow dòng tiền.")
        elif vol < avg_vol:
            status.append("BULL TRAP / Fake Breakout: Giá kéo mạnh nhưng MACD yếu và Vol thấp.")
            action.append("Cẩn thận sập nền.")
            
    if not status:
        status.append("MACD vận động bình thường.")
        action.append("Dùng MACD đóng vai trò Trend Filter (Ưu tiên mua khi MACD > 0).")
        
    return {
        "value": f"{macd:.2f} / Hist: {hist:.2f}",
        "status": " | ".join(status),
        "action": " | ".join(action)
    }
