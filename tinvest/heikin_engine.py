import pandas as pd
import numpy as np

def calculate_wma(series, window):
    """Calculates Weighted Moving Average."""
    weights = np.arange(1, window + 1)
    return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(series, window):
    """Calculates Hull Moving Average."""
    half_window = int(window / 2)
    sqrt_window = int(np.sqrt(window))
    
    wma_half = calculate_wma(series, half_window)
    wma_full = calculate_wma(series, window)
    
    diff = 2 * wma_half - wma_full
    return calculate_wma(diff, sqrt_window)

def calculate_ema(series, window):
    """Calculates Exponential Moving Average."""
    return series.ewm(span=window, adjust=False).mean()

def calculate_vwma(close, volume, window):
    """Calculates Volume Weighted Moving Average."""
    return (close * volume).rolling(window).sum() / volume.rolling(window).sum()

def calculate_rma(series, window):
    """Calculates Wilder's Moving Average (RMA)."""
    alpha = 1.0 / window
    return series.ewm(alpha=alpha, adjust=False).mean()

def analyze_trendcolor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implements Trend Color logic from PineScript.
    - DMI/ADX Bar Coloring
    - EMA Stack (VWMA)
    - Trend EMA 13
    - Stop Line (ATR)
    """
    out = df.copy()
    
    # 1. DMI / ADX
    high_diff = out['High'] - out['High'].shift(1)
    low_diff = out['Low'].shift(1) - out['Low']
    
    bullish_dmi = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
    bearish_dmi = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
    
    tr = pd.concat([
        out['High'] - out['Low'],
        (out['High'] - out['Close'].shift(1)).abs(),
        (out['Low'] - out['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    
    tr_rma = calculate_rma(tr, 14)
    dmi_up = 100 * calculate_rma(pd.Series(bullish_dmi), 14) / tr_rma
    dmi_down = 100 * calculate_rma(pd.Series(bearish_dmi), 14) / tr_rma
    
    adx_x = 100 * (dmi_up - dmi_down).abs() / (dmi_up + dmi_down).replace(0, 1)
    adx = calculate_rma(adx_x, 14)
    
    # Color Bars
    # Bullish if DMIUp > DMIDown and ADX > 20
    out['TC_BarColor'] = np.where((dmi_up > dmi_down) & (adx > 20), '#27c22e',
                         np.where((dmi_up < dmi_down) & (adx > 20), '#ff0000', '#434651'))
    
    # 2. EMA Stack (using VWMA per script)
    v = out['Volume']
    e8 = calculate_vwma(out['Close'], v, 8)
    e13 = calculate_vwma(out['Close'], v, 13)
    e21 = calculate_vwma(out['Close'], v, 21)
    e34 = calculate_vwma(out['Close'], v, 34)
    
    emaup = (e8 > e13) & (e13 > e21) & (e21 > e34)
    emadn = (e8 < e13) & (e13 < e21) & (e21 < e34)
    
    # Trend Line (EMA 13)
    trend = out['Close'].ewm(span=13, adjust=False).mean()
    out['TC_Trend'] = trend
    
    # Trend Line Color
    out['TC_TrendColor'] = np.where(emadn & (out['Close'] <= trend), '#ff0000',
                           np.where(emaup & (out['Close'] >= trend), '#27c22e', '#434651'))
    
    # 3. Stop Line (ATR)
    atr_length = 80 # Normal mode
    atr_val = (atr_length / 100.0) * tr.ewm(span=8, adjust=False).mean()
    
    up_sig = out['Close'] > (trend + atr_val)
    down_sig = out['Close'] < (trend - atr_val)
    
    t_sig = np.zeros(len(out))
    for i in range(1, len(out)):
        if up_sig.iloc[i]:
            t_sig[i] = 1
        elif down_sig.iloc[i]:
            t_sig[i] = -1
        else:
            t_sig[i] = t_sig[i-1]
            
    out['TC_StopLine'] = np.where(t_sig == 1, trend - atr_val, trend + atr_val)
    out['TC_StopColor'] = np.where(t_sig == 1, '#27c22e', '#ff0000')
    out['TC_T'] = t_sig

    return out

def analyze_2trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implements 2trend logic from PineScript.
    - SMA Dynamic Score
    - Supertrend Dynamic Score
    """
    out = df.copy()
    c = out['Close']
    
    # 1. SMA Dynamic Score
    ma_len = 20
    window_len = 50
    sma = c.rolling(ma_len).mean()
    out['T2_SMA'] = sma
    
    scores = np.zeros(len(out))
    sma_vals = sma.values
    c_vals = c.values
    for i in range(window_len + ma_len, len(out)):
        curr_c = c_vals[i]
        window_smas = sma_vals[i-window_len:i]
        scores[i] = np.sum(np.where(curr_c > window_smas, 1, np.where(curr_c < window_smas, -1, 0)))
    
    out['T2_SMA_Score'] = scores
    
    t_state = np.zeros(len(out))
    for i in range(1, len(out)):
        if scores[i] > 40:
            t_state[i] = 1
        elif scores[i] < -10:
            t_state[i] = -1
        else:
            t_state[i] = t_state[i-1]
    out['T2_SMA_Trend'] = t_state
    
    # 2. Supertrend Dynamic Score
    atr_len = 20
    atr_mult = 1.5
    
    tr = pd.concat([
        out['High'] - out['Low'],
        (out['High'] - out['Close'].shift(1)).abs(),
        (out['Low'] - out['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_len).mean()
    
    sma_atr = c.rolling(atr_len).mean()
    upper = sma_atr + atr * atr_mult
    lower = sma_atr - atr * atr_mult
    out['T2_ST_Upper'] = upper
    out['T2_ST_Lower'] = lower
    
    scores2 = np.zeros(len(out))
    upper_vals = upper.values
    lower_vals = lower.values
    for i in range(window_len + atr_len, len(out)):
        curr_c = c_vals[i]
        w_upper = upper_vals[i-window_len:i]
        w_lower = lower_vals[i-window_len:i]
        scores2[i] = np.sum(np.where(curr_c > w_upper, 1, np.where(curr_c < w_lower, -1, 0)))
    
    out['T2_ST_Score'] = scores2
    
    t_state2 = np.zeros(len(out))
    for i in range(1, len(out)):
        if scores2[i] > 40:
            t_state2[i] = 1
        elif scores2[i] < -10:
            t_state2[i] = -1
        else:
            t_state2[i] = t_state2[i-1]
    out['T2_ST_Trend'] = t_state2
    
    return out

def analyze_heikin(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combined Heikin, Trend Color, and 2trend Engine.
    """
    out = df.copy()
    
    # --- Heikin Part ---
    k = 2.5
    per = 3
    j = (out['Open'] + out['High'] + out['Low'] + out['Close']) / 4
    rfsctor = calculate_wma(out['High'] - out['Low'], per)
    revers = k * rfsctor
    trend = np.ones(len(out))
    nw = np.zeros(len(out))
    j_vals = j.values
    revers_vals = revers.fillna(0).values
    for i in range(1, len(out)):
        if trend[i-1] == 1:
            if j_vals[i] < nw[i-1]:
                trend[i] = -1; nw[i] = j_vals[i] + revers_vals[i]
            else:
                trend[i] = 1; nw[i] = max(nw[i-1], j_vals[i] - revers_vals[i])
        else:
            if j_vals[i] > nw[i-1]:
                trend[i] = 1; nw[i] = j_vals[i] - revers_vals[i]
            else:
                trend[i] = -1; nw[i] = min(nw[i-1], j_vals[i] + revers_vals[i])
    out['HK_NW'] = nw
    out['HK_Trend'] = trend
    
    # Flower
    prd1 = 4; prd2 = 7
    tr = pd.concat([out['High'] - out['Low'], (out['High'] - out['Close'].shift(1)).abs(), (out['Low'] - out['Close'].shift(1)).abs()], axis=1).max(axis=1)
    atr_wilder = tr.ewm(alpha=1/prd1, adjust=False).mean()
    green = (out['Low'].rolling(prd1).min() + atr_wilder).rolling(prd2).max()
    red = (out['High'].rolling(prd1).max() - atr_wilder).rolling(prd2).min()
    flower_close = calculate_ema((out['Open'] + out['High'] + out['Low'] + out['Close']) / 4, 3)
    flower_open = calculate_ema(((out['Open'].shift(1) + flower_close.shift(1)) / 2).bfill(), 3)
    flower_high = calculate_ema(np.maximum(np.maximum(out['High'], flower_open), flower_close), 3)
    flower_low = calculate_ema(np.minimum(np.minimum(out['Low'], flower_open), flower_close), 3)
    out['HK_Flower_Open'] = flower_open; out['HK_Flower_Close'] = flower_close; out['HK_Flower_High'] = flower_high; out['HK_Flower_Low'] = flower_low
    out['HK_BarColor'] = np.where(out['Close'] > green, 'brightGreen', np.where(out['Close'] < red, 'red', 'white'))
    
    # Hull
    mhull = calculate_hma(out['Close'], 40); shull = mhull.shift(4); out['HK_MHull'] = mhull; out['HK_SHull'] = shull
    
    # Signals
    out['HK_BuySignal'] = (out['Close'] > green) & (out['Close'].shift(1) < green) & \
                          (out['Open'] < green) & (out['Open'].shift(1) < green) & \
                          (flower_open < green) & (flower_close > green) & \
                          (flower_open.shift(1) < green) & (flower_close.shift(1) < green)
    out['HK_SellSignal'] = (out['Close'] < red) & (flower_close < red) & (flower_close.shift(1) > red)
    out['HK_BuyManh'] = (j > out['HK_NW']) & (j.shift(1) <= out['HK_NW'].shift(1))
    out['HK_SellManh'] = (j < out['HK_NW']) & (j.shift(1) >= out['HK_NW'].shift(1))

    # --- Trend Color Part ---
    tc_cols = ['TC_BarColor', 'TC_Trend', 'TC_TrendColor', 'TC_StopLine', 'TC_StopColor', 'TC_T']
    tc_out = analyze_trendcolor(df)
    for col in tc_cols:
        if col in tc_out.columns:
            out[col] = tc_out[col]

    # --- 2trend Part ---
    t2_cols = ['T2_SMA', 'T2_SMA_Score', 'T2_SMA_Trend', 'T2_ST_Upper', 'T2_ST_Lower', 'T2_ST_Score', 'T2_ST_Trend']
    t2_out = analyze_2trend(df)
    for col in t2_cols:
        if col in t2_out.columns:
            out[col] = t2_out[col]

    return out
