"""
Module 5 – Scoring Engine V2
==========================
Aggregates Ichimoku, VSA, and AIC into a total score V2 based on exact trade characteristics.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def calculate_score(df: pd.DataFrame, ichi_result: dict = None) -> dict:
    """
    Calculate TINVEST SCORE V2.
    """
    if len(df) < 50:
        return {"total_score": 0, "classification": "AVOID", "pass_risk": False, "breakdown": {}, "details": {}}

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    # Helper variables
    avg_vol20 = float(df['Volume'].iloc[-20:].mean()) if len(df) >= 20 else float(df['Volume'].mean())
    ma20 = float(df['Close'].iloc[-20:].mean()) if len(df) >= 20 else float(df['Close'].mean())
    ma50 = float(df['Close'].iloc[-50:].mean()) if len(df) >= 50 else float(df['Close'].mean())

    # --- 1. ICHIMOKU (Max 3) ---
    ichi_score = 0
    if ichi_result:
        ichi_score = ichi_result.get("score", 0)
    else:
        if 'SpanA' in df.columns and 'SpanB' in df.columns:
            cloud_top = max(last['SpanA'], last['SpanB'])
            if last['Close'] > cloud_top: ichi_score += 1
        if 'Tenkan' in df.columns and 'Kijun' in df.columns:
            future_a = (last["Tenkan"] + last["Kijun"]) / 2
            future_b = (df["High"].iloc[-52:].max() + df["Low"].iloc[-52:].min()) / 2
            if future_a >= future_b: ichi_score += 1
            kijun_prev = df['Kijun'].iloc[-5] if len(df) >= 5 else df['Kijun'].iloc[0]
            if last['Kijun'] > kijun_prev: ichi_score += 1

    # --- 2. VSA V2 (Max 3) ---
    vsa_score = 0

    # Có Stopping Vol / No Supply (Quét chuỗi 5 ngày gần nhất để tìm vùng tích luỹ)
    has_stop_no_supply = False
    for i in range(1, min(6, len(df))):
        c, o = float(df['Close'].iloc[-i]), float(df['Open'].iloc[-i])
        h, l = float(df['High'].iloc[-i]), float(df['Low'].iloc[-i])
        v = float(df['Volume'].iloc[-i])
        
        av = float(df['Volume'].iloc[-(i+20):-i].mean()) if len(df) >= i+20 else avg_vol20
        asp = float((df['High'] - df['Low']).iloc[-(i+20):-i].mean()) if len(df) >= i+20 else (h - l)
        
        b = abs(c - o)
        tr = h - l + 1e-10
        lw = min(o, c) - l
        
        stopping = (v > 1.5 * av) and (b / tr < 0.35) and (lw / tr > 0.4)
        no_supply = (c <= o) and (v < 0.8 * av) and (tr < asp * 0.9)  # Nới vol < 0.8 trung bình
        
        if stopping or no_supply:
            has_stop_no_supply = True
            break
            
    if has_stop_no_supply:
        vsa_score += 1

    # Không có Upthrust / Supply
    # Upthrust = High > Highest(High, 10)[1] AND Close < (High + Low)/2 AND Volume > MA(Volume,20) * 1.2
    highest_10_prev = float(df['High'].iloc[-11:-1].max()) if len(df) >= 11 else float(df['High'][:-1].max())
    upthrust = (last['High'] > highest_10_prev) and (last['Close'] < (last['High'] + last['Low']) / 2) and (last['Volume'] > avg_vol20 * 1.2)

    # Supply (Distribution Sequence): Giá giảm + Vol tăng liên tiếp.
    dist_days = 0
    for i in range(1, min(6, len(df))):
        c = float(df['Close'].iloc[-i])
        pc = float(df['Close'].iloc[-i-1]) if i+1 <= len(df) else c
        v = float(df['Volume'].iloc[-i])
        av = float(df['Volume'].iloc[-(i+20):-i].mean()) if len(df) >= i+20 else avg_vol20
        if (c < pc) and (v > av):
            dist_days += 1
            
    recent_trend_down = last['Close'] < (float(df['Close'].iloc[-5]) if len(df) >= 5 else float(df['Close'].iloc[0]))
    distribution = (dist_days >= 2) and recent_trend_down

    if not (upthrust or distribution):
        vsa_score += 1

    # Uptrend Confirm = Close > MA20 AND Volume > MA(Volume,20)
    uptrend_confirm = (last['Close'] > ma20) and (last['Volume'] > avg_vol20)
    if uptrend_confirm:
        vsa_score += 1

    # --- 3. SETUP AIC (Max 4) ---
    aic_score = 0
    # Pullback = |Close - MA20| < 4% AND (Volume cạn hoặc Vừa nảy xanh) AND MA20 > MA50
    near_ma20 = abs(last['Close'] - ma20) / ma20 <= 0.04
    pulling_back = near_ma20 and (last['Volume'] < avg_vol20)
    bouncing = near_ma20 and (last['Close'] > last['Open']) and (last['Volume'] > prev['Volume'])
    pullback = (pulling_back or bouncing) and (ma20 > ma50)
    
    # Breakout = Close > Highest(High, 20) AND Volume > MA(Volume,20) * 1.2 AND Close gần High
    highest_20_prev = float(df['High'].iloc[-21:-1].max()) if len(df) >= 21 else float(df['High'][:-1].max())
    near_high = last['Close'] >= last['Low'] + 0.65 * (last['High'] - last['Low'] + 1e-10)
    breakout = (last['Close'] > highest_20_prev) and (last['Volume'] > avg_vol20 * 1.2) and near_high
    
    # Early = Volume > MA(Volume,20) * 1.5 AND Close > Open AND Low ≈ Lowest(Low, 10)
    lowest_10 = float(df['Low'].iloc[-10:].min()) if len(df) >= 10 else float(df['Low'].min())
    early = (last['Volume'] > avg_vol20 * 1.5) and (last['Close'] > last['Open']) and (last['Low'] <= lowest_10 * 1.02)
    
    setup_name = "NONE"
    if pullback:
        aic_score = 4
        setup_name = "Pullback"
    elif breakout:
        aic_score = 3
        setup_name = "Breakout"
    elif early:
        aic_score = 2
        setup_name = "Early"

    # --- 4. RISK FILTER BẮT BUỘC ---
    # Spike: (Close - Open)/Open > 0.07 AND Volume > MA(Volume,20) * 2
    spike = ((last['Close'] - last['Open']) / last['Open'] > 0.07) and (last['Volume'] > avg_vol20 * 2.0)
    fomo = last['Close'] > ma20 * 1.10
    
    pass_risk = not (fomo or distribution or spike)

    # --- TỔNG ĐIỂM & PHÂN LOẠI ---
    total = ichi_score + vsa_score + aic_score

    classification = "AVOID"
    if total >= 8 and pass_risk:
        classification = "STRONG BUY"
    elif total >= 7 and pass_risk:
        classification = "BUY ZONE"
    elif total >= 7:
        classification = "WATCHLIST"
        
    result = {
        "total_score": total,
        "classification": classification,
        "pass_risk": pass_risk,
        "breakdown": {
            "ichimoku": ichi_score,
            "vsa": vsa_score,
            "aic": aic_score,
        },
        "details": {
            "setup": setup_name,
            "upthrust": upthrust,
            "distribution": distribution,
            "spike": spike,
            "fomo": fomo,
            "uptrend_confirm": uptrend_confirm
        }
    }
    logger.debug(f"Score: {result}")
    return result
