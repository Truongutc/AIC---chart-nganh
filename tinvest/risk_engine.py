"""
Module 10 – Risk Management Engine
==================================
Calculates automatic Stop Loss (SL) and Trailing Stop (TS) logic based on TINVEST rules.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Standard Average True Range (14)."""
    h_l = df['High'] - df['Low']
    h_pc = abs(df['High'] - df['Close'].shift(1))
    l_pc = abs(df['Low'] - df['Close'].shift(1))
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_swing_low(df: pd.DataFrame, window: int = 10) -> float:
    """Finds the lowest low in the last N bars."""
    return float(df['Low'].tail(window).min())

def get_risk_label(risk_pct: float) -> str:
    """Categorizes risk based on percentage."""
    if risk_pct < 5:
        return "Low Risk"
    elif risk_pct <= 8:
        return "Medium Risk"
    else:
        return "High Risk"

def calculate_stoploss(df: pd.DataFrame, entry_type: str, current_close: float, signal_details: dict = None) -> dict:
    """
    Calculates Entry, Stop Loss, and Target prices based on refined TINVEST rules.
    """
    if df is None or len(df) < 20:
        return {"entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0, "risk_pct": 0.0, "risk_label": "Unknown", "is_valid": False}

    last = df.iloc[-1]
    signal_details = signal_details or {}
    
    # Common Indicators
    swing_low = calculate_swing_low(df, 10)
    kijun = last.get('Kijun', current_close * 0.95)
    ma20 = last.get('MA20', current_close * 0.95)
    tenkan = last.get('Tenkan', current_close * 0.98)
    cloud_top = last.get('CloudTop', current_close * 0.90)
    
    high_curr = float(last['High'])
    high_prev = signal_details.get('high_prev', high_curr)
    
    entry_price = current_close
    sl_price = 0.0

    # 1. EARLY BUY
    if entry_type == "EARLY":
        # Entry = High + 0.1%
        entry_price = high_curr * 1.001
        # SL = min(SwingLow, Kijun) or fallback 5%
        sl_price = min(swing_low, kijun)
        if (entry_price - sl_price) / entry_price > 0.05:
            sl_price = entry_price * 0.95

    # 2. ADD 1
    elif entry_type == "ADD_1":
        # Entry = max(Close, High nến trước)
        entry_price = max(current_close, high_prev)
        # SL = min(Kijun, MA20) or fallback 7%
        sl_price = min(kijun, ma20)
        if (entry_price - sl_price) / entry_price > 0.07:
            sl_price = entry_price * 0.93

    # 3. ADD 2
    elif entry_type == "ADD_2":
        # Entry = High HA confirm + 0.1%
        ha_high = signal_details.get('ha_high', high_curr)
        entry_price = ha_high * 1.001
        # SL = min(Cloud Top, Tenkan) or fallback 10%
        sl_price = min(cloud_top, tenkan)
        if (entry_price - sl_price) / entry_price > 0.10:
            sl_price = entry_price * 0.90

    # 4. STRONG BUY
    elif entry_type == "STRONG":
        if signal_details.get("is_ma_pullback"):
            entry_price = current_close
            sl_price = ma20
        elif signal_details.get("is_ichi_breakout"):
            entry_price = high_curr * 1.001
            sl_price = cloud_top
        elif signal_details.get("is_vsa_strong"):
            entry_price = high_curr * 1.001
            sl_price = last['Low']
        else:
            entry_price = current_close
            sl_price = entry_price * 0.92

    # Final Validation
    if entry_price <= sl_price:
        sl_price = entry_price * 0.95 # Emergency fallback

    risk_pct = (entry_price - sl_price) / entry_price * 100
    tp_price = entry_price * (1 + 2 * risk_pct / 100)
    
    is_valid = (risk_pct <= 10.0) and (entry_price > sl_price) and (entry_type != "NONE")

    return {
        "entry_price": round(entry_price, 2),
        "sl_price": round(sl_price, 2),
        "tp_price": round(tp_price, 2),
        "risk_pct": round(risk_pct, 2),
        "risk_label": get_risk_label(risk_pct),
        "is_valid": is_valid
    }

def calculate_trailing_stop(df: pd.DataFrame, entry_price: float, initial_sl: float) -> float:
    """
    Implements Trailing Stop rules based on current price and trends.
    """
    if df is None or len(df) < 1:
        return initial_sl

    last = df.iloc[-1]
    curr_price = last['Close']
    ma20 = last.get('MA20', 0)
    tenkan = last.get('Tenkan', 0)
    
    new_sl = initial_sl

    # Rule 1: If Profit > 10% -> SL = max(InitialSL, EntryPrice)
    if curr_price > entry_price * 1.10:
        new_sl = max(new_sl, entry_price)

    # Rule 2: If Profit > 20% -> SL = MA20
    if curr_price > entry_price * 1.20:
        if ma20 > 0:
            new_sl = max(new_sl, ma20)

    # Rule 3: If trend is strong -> SL = max(MA20, Tenkan)
    # Strong trend heuristic: MA10 > MA20 > MA50
    ma10 = last.get('MA10', 0)
    ma50 = last.get('MA50', 0)
    if ma10 > ma20 > ma50:
        strong_sl = max(ma20, tenkan)
        if strong_sl > 0:
            new_sl = max(new_sl, strong_sl)

    # Principle: Never move Stoploss down
    return max(initial_sl, new_sl)
