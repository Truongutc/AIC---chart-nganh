import pandas as pd
import numpy as np

def evaluate_rsi(df: pd.DataFrame, idx: int = -1) -> dict:
    """"Phân tích chuyên sâu RSI dựa theo Trend và Volume."""
    if len(df) < abs(idx) + 10:
        return {"status": "Không đủ dữ liệu", "action": "N/A"}
        
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    rsi = float(last.get('RSI', 50))
    rsi_prev = float(prev.get('RSI', 50))
    
    ma20 = float(last.get('MA20', last['Close']))
    ma50 = float(last.get('MA50', last['Close']))
    
    vol = float(last.get('Volume', 0))
    avg_vol = float(last.get('AvgVolume20', vol))
    
    # Trend Context
    is_uptrend = ma20 > ma50 and last['Close'] > ma50
    is_downtrend = ma20 < ma50 and last['Close'] < ma50
    is_sideway = not is_uptrend and not is_downtrend
    
    status = []
    action = []
    
    # --- Divergence Check ---
    recent_lows = df[df['SwingLow'] > 0]
    if len(recent_lows) >= 2:
        idx1 = recent_lows.index[-1]
        idx2 = recent_lows.index[-2]
        p1, p2 = recent_lows['Low'].iloc[-1], recent_lows['Low'].iloc[-2]
        
        # Need RSI at those precise points
        r1, r2 = df['RSI'].loc[idx1], df['RSI'].loc[idx2]
        if p1 < p2 and r1 > r2:
            status.append("PHÂN KỲ ĐÁY (Bullish Divergence): Giá tạo đáy thấp hơn nhưng RSI tạo đáy cao hơn.")
            action.append("Lực bán đã suy kiệt. Chờ nến xác nhận hoặc break trendline để MUA ngay.")
            
    recent_highs = df[df['SwingHigh'] > 0]
    if len(recent_highs) >= 2:
        idx1 = recent_highs.index[-1]
        idx2 = recent_highs.index[-2]
        p1, p2 = recent_highs['High'].iloc[-1], recent_highs['High'].iloc[-2]
        
        r1, r2 = df['RSI'].loc[idx1], df['RSI'].loc[idx2]
        if p1 > p2 and r1 < r2:
            status.append("PHÂN KỲ ĐỈNH (Bearish Divergence): Giá tạo đỉnh mới nhưng RSI thấp hơn.")
            action.append("Lực mua yếu đi rõ rệt. Cẩn trọng sập, chuẩn bị CHỐT LỜI/SHORT.")
    # -----------------------
    
    # 1. Trạng thái Quá Mua / Quá Bán
    if rsi > 70:
        if is_uptrend:
            status.append("Quá mua (RSI > 70) trong Uptrend: Trend đang rất khỏe.")
            action.append("Giữ lệnh, không chốt non.")
        elif is_sideway:
            status.append("Quá mua (RSI > 70) trong Sideway: Rủi ro đảo chiều cao.")
            action.append("Canh chốt lời / Tránh Mua Đuổi.")
            
    elif rsi < 30:
        if is_downtrend:
            status.append("Quá bán (RSI < 30) trong Downtrend: Giá đang rơi tự do.")
            action.append("Đứng ngoài, không bắt đáy mù quáng.")
        elif is_sideway:
            status.append("Quá bán (RSI < 30) trong Sideway: Đạt biên dưới.")
            action.append("Canh bắt nhịp hồi.")
            
    # 2. Các Case Hành Động (Giao Cắt & Setup)
    # Pullback Uptrend
    if is_uptrend and 40 <= rsi <= 55 and rsi > rsi_prev:
        if vol > avg_vol:
            status.append("Tín hiệu KHỎE NHẤT: Pullback RSI về vùng 40-50, Vol xác nhận.")
            action.append("TÌM ĐIỂM MUA ngay khi RSI cắt lên 50.")
        else:
            status.append("RSI Pullback về vùng hỗ trợ nhưng Volume yếu.")
            
    # Downtrend Bounce
    if is_downtrend and 50 <= rsi <= 60 and rsi < rsi_prev:
        status.append("Tín hiệu XẤU: Nhịp hồi kỹ thuật (RSI chạm 50-60) thất bại.")
        action.append("CƠ CẤU / BÁN ngay khi rsi cắt xuống 50.")
        
    # Bull Trap
    if rsi > 70 and vol < avg_vol * 0.8:
        status.append("BULL TRAP: RSI cao (>70) nhưng Volume hụt hơi.")
        action.append("Chú ý tạo đỉnh giả, cân nhắc Hạ Tỷ Trọng.")
        
    # Bottom Catch
    if rsi < 30 and vol < avg_vol * 0.6:
        status.append("Cạn cung vùng đáy: RSI < 30 và Volume cạn kiệt.")
        action.append("Tín hiệu tích cực báo hiệu sắp có nhịp hồi, đưa vào Watchlist.")
        
    # Breakout có lực
    if rsi > 60 and vol > avg_vol * 1.5 and last['Close'] > last['Open']:
        status.append("Breakout chuẩn: RSI > 60 kèm Vol lớn.")
        action.append("Breakout có lực, có thể bám Trend.")
        
    if not status:
        bieng = "Tăng" if rsi > 50 else "Giảm"
        status.append(f"Vùng trung lập (RSI = {rsi:.1f}). Bias thị trường: {bieng}.")
        action.append("Dùng làm màng lọc xu hướng. Chỉ mua khi > 50.")

    return {
        "value": rsi,
        "status": " | ".join(status),
        "action": " | ".join(action)
    }
