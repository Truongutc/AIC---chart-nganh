import pandas as pd
import numpy as np

def evaluate_state_rules(df: pd.DataFrame) -> dict:
    """
    Evaluates the 18 steps of the State Rule (Rule trạng thái).
    Returns a dictionary of the state properties for the last row.
    Uses pandas vectorization for performance.
    """
    if len(df) < 21:
        return {
            "regime": "NEUTRAL", "primary": "NEUTRAL", 
            "secondary": "NORMAL", "signal": "NONE", 
            "confidence": 0, "avoid_entry": False
        }
        
    o = df['Open']
    h = df['High']
    l = df['Low']
    c = df['Close']
    v = df['Volume']
    
    ma20 = df['MA20']
    ma50 = df['MA50']
    
    adx = df['ADX']
    macd = df['MACD']
    hist = df['MACD_Hist']
    
    atr = df['ATR14']
    vol_ma20 = df['AvgVolume20']

    # ── 2. MARKET REGIME ──
    highest_20 = h.rolling(20).max()
    lowest_20 = l.rolling(20).min()
    range_width = highest_20 - lowest_20
    
    ma_slope = ma20 - ma20.shift(5)
    ma_flat = ma_slope.abs() < 0.5 * atr
    
    low_vol = v < vol_ma20
    chop = adx < 15
    
    range_regime = (adx < 20) & (range_width < 2.5 * atr) & ma_flat
    trend_regime = (adx > 20) & (range_width > 2 * atr)
    squeeze_regime = (range_width < 1.5 * atr) & (adx < 15)
    
    regime = pd.Series("SIDEWAY", index=df.index)
    regime = np.where(trend_regime, "TREND", regime)
    regime = np.where(range_regime, "RANGE", regime)
    regime = np.where(squeeze_regime, "SQUEEZE", regime)
    regime = pd.Series(regime, index=df.index)

    # ── 3. STRUCTURE ──
    swing_high = df.get('SwingHigh', pd.Series(0, index=df.index)) > 0
    swing_low = df.get('SwingLow', pd.Series(0, index=df.index)) > 0
    
    last_high = df.get('SwingHigh', pd.Series(0, index=df.index)).replace(0, np.nan).ffill().shift(1)
    last_low = df.get('SwingLow', pd.Series(0, index=df.index)).replace(0, np.nan).ffill().shift(1)
    
    hh = swing_high & (h > last_high)
    hl = swing_low & (l > last_low)
    lh = swing_high & (h < last_high)
    ll = swing_low & (l < last_low)
    
    up_structure = hh | (hl & (c > ma20))
    down_structure = ll | (lh & (c < ma20))
    
    structure_bias = pd.Series(0, index=df.index)
    structure_bias = np.where(up_structure, 1, structure_bias)
    structure_bias = np.where(down_structure, -1, structure_bias)
    structure_bias = pd.Series(structure_bias, index=df.index)

    # ── 4. TREND CONTEXT ──
    ma_bull = ma20 > ma50
    ma_bear = ma20 < ma50
    
    trend_bias = pd.Series(0, index=df.index)
    trend_bias = np.where(ma_bull & (c > ma20), 1, trend_bias)
    trend_bias = np.where(ma_bear & (c < ma20), -1, trend_bias)
    trend_bias = np.where(ma_bear & (c > ma20), 0.5, trend_bias) # Hồi phục: trên MA20 nhưng MA20 < MA50
    trend_bias = pd.Series(trend_bias, index=df.index)
    
    strong_trend = (adx > 25) & (adx > adx.shift(1))

    # ── 5. MOMENTUM ──
    hist_1 = hist.shift(1)
    hist_2 = hist.shift(2)
    hist_3 = hist.shift(3)
    momentum_up = (macd > 0) & (hist > 0) & (hist > hist_1)
    momentum_down = (macd < 0) & (hist < 0) & (hist < hist_1)
    # Siet chat: Phai giam 3 phien lien tiep VA hist dang am dan ro ret
    momentum_weak = (hist < hist_1) & (hist_1 < hist_2) & (hist_2 < hist_3) & (hist < 0)

    # ── 6. VOLUME ──
    vol_spike = v > 1.5 * vol_ma20
    vol_dry = v < 0.8 * vol_ma20

    # ── 7. BREAKOUT & PULLBACK (AIC PROFESSIONAL LOGIC) ──
    atr_slope = df.get('ATR14_Slope', pd.Series(0, index=df.index))
    body = (c - o).abs()
    candle_range = h - l
    strong_candle = body > 0.6 * candle_range
    spread_ok = candle_range > 0.8 * atr
    
    # 7.1 Breakout Valid: Base compression (ATR slope <=0) + Vol Expansion (>1.5x)
    base_valid = atr_slope <= 0
    breakout_up = (c > highest_20.shift(1)) & base_valid & vol_spike & strong_candle & spread_ok
    breakout_down = (c < lowest_20.shift(1)) & strong_candle & vol_spike
    
    # 7.2 Pullback Valid (Core Position): Near MA20 + Low Vol
    pullback_zone = c <= (ma20 * 1.02)
    pullback = (trend_bias == 1) & pullback_zone & vol_dry & (l > last_low)
    failed_pullback = pullback.shift(1).fillna(False) & (c < ma20)

    # 7.3 Retest Logic: Low >= R1*0.97 and Low Vol
    # Use highest_20.shift(2) as a proxy for the 'broken' R1
    retest = (c > last_high) & (l >= last_high * 0.97) & (l <= last_high * 1.03) & (v < vol_ma20)
    
    # 7.4 Continuation: Higher High confirmed
    continuation = (c > last_high) & (v >= vol_ma20) & (df['Dist_MA20'] < 0.1)

    # ── 8. ANTI-TRAP FILTER ──
    overextended = df['Dist_MA20'] > 0.1
    rsi_overheat = df['RSI'] > 75
    too_many_green = df['Green_Count_3'] >= 3
    
    # Block buying if overextended or overheated
    anti_trap_block = overextended | rsi_overheat | too_many_green
    
    bull_trap = (c > highest_20.shift(1)) & (c < o) & vol_spike
    bear_trap = (c < lowest_20.shift(1)) & (c > o) & vol_spike
    failed_breakout = breakout_up.shift(1).fillna(False) & (c < ma20) & (v > vol_ma20)
    trap = bull_trap | bear_trap | failed_breakout

    # ── 9. ACCUMULATION / DISTRIBUTION ──
    accumulation = (regime == "RANGE") & vol_dry & (l > lowest_20.shift(1))
    distribution = (trend_bias == 1) & vol_spike & (hist < hist_1) & (c < o)

    # ── 10. SPECIAL STATES ──
    roll_over = (trend_bias == 1) & (hist < hist_1) & vol_spike
    reversal_build = (trend_bias == -1) & (hist > hist_1) & vol_dry

    # ── 11. PRIMARY STATE ──
    primary = pd.Series("NEUTRAL", index=df.index)
    primary = np.where(regime == "SQUEEZE", "SQUEEZE", primary)
    primary = np.where(regime == "RANGE", "RANGE", primary)
    primary = np.where(trend_bias == -1, "WEAK_DOWNTREND", primary)
    primary = np.where(trend_bias == 0.5, "RECOVERY", primary)
    primary = np.where(trend_bias == 1, "WEAK_UPTREND", primary)
    primary = np.where((trend_bias == -1) & strong_trend, "DOWNTREND", primary)
    primary = np.where((trend_bias == 1) & strong_trend, "UPTREND", primary)
    primary = np.where(breakout_down, "DOWNTREND_START", primary)
    primary = np.where(breakout_up, "UPTREND_START", primary)
    primary = pd.Series(primary, index=df.index)

    # ── 12. SECONDARY STATE ──
    secondary = pd.Series("NORMAL", index=df.index)
    secondary = np.where(reversal_build, "REVERSAL_BUILD", secondary)
    exhaustion_confirmed = (hist < hist_1) & (hist_1 < hist_2) & ((c < o) | vol_spike)
    secondary = np.where(exhaustion_confirmed, "EXHAUSTION", secondary)
    secondary = np.where(pullback, "PULLBACK", secondary)
    secondary = np.where(retest, "RETEST", secondary)
    secondary = np.where(failed_pullback, "FAILED_PULLBACK", secondary)
    secondary = np.where(roll_over, "ROLL_OVER", secondary)
    secondary = np.where(accumulation, "ACCUMULATION", secondary)
    secondary = np.where(distribution, "DISTRIBUTION", secondary)
    secondary = np.where(trap, "TRAP", secondary)
    
    # NEW: UNDER_PRESSURE - Price within 0.3% above MA20 or if it broken recent valley
    near_ma20 = (c > ma20) & (c <= ma20 * 1.003)
    broken_recent_low = (c < last_low) & (c > last_low * 0.98)
    under_pressure = (regime == "TREND") & (near_ma20 | broken_recent_low)
    secondary = np.where(under_pressure, "UNDER_PRESSURE", secondary)
    
    secondary = pd.Series(secondary, index=df.index)

    # ── 13. SIGNAL GENERATION ──
    signal = pd.Series("NONE", index=df.index)
    
    sig_pullback_buy = primary.isin(["UPTREND", "WEAK_UPTREND"]) & (secondary == "PULLBACK")
    sig_breakout_buy = (primary == "UPTREND_START") & breakout_up & (~anti_trap_block)
    sig_retest_buy = (secondary == "RETEST") & (~anti_trap_block)
    sig_continuation_buy = continuation & (~anti_trap_block)

    signal = np.where(sig_pullback_buy, "PULLBACK_BUY", signal)
    signal = np.where(sig_breakout_buy, "BREAKOUT_BUY", signal)
    signal = np.where(sig_retest_buy, "RETEST_BUY", signal)
    signal = np.where(sig_continuation_buy, "CONTINUATION_BUY", signal)
    
    # SELL Signals
    sig_short = (primary == "DOWNTREND") | (primary == "DOWNTREND_START")
    sig_exit_fast = secondary == "TRAP"
    sig_exit_short = (secondary == "DISTRIBUTION") & (trend_bias == -1)
    sig_take_profit = rsi_overheat | (primary.isin(["UPTREND", "WEAK_UPTREND"]) & secondary.isin(["EXHAUSTION", "ROLL_OVER"]))
    
    signal = np.where(sig_short, "SHORT", signal)
    signal = np.where(sig_exit_fast, "EXIT_FAST", signal)
    signal = np.where(sig_exit_short, "EXIT_OR_SHORT", signal)
    signal = np.where(sig_take_profit, "TAKE_PROFIT", signal)
    signal = pd.Series(signal, index=df.index)

    # ── 14. RISK FILTER ──
    avoid_entry = chop | overextended | trap | (primary == "SQUEEZE") | anti_trap_block
    signal = np.where(avoid_entry & (~signal.isin(["TAKE_PROFIT", "SHORT", "EXIT_FAST", "EXIT_OR_SHORT"])), "NO_TRADE", signal)
    signal = pd.Series(signal, index=df.index)

    # ── 17. CONFIDENCE ──
    adx_bonus = np.where(adx > 25, 1, 0)
    mom_up_bonus = np.where(momentum_up, 1, 0)
    mom_down_penalty = np.where(momentum_down, 1, 0)
    confidence = structure_bias + trend_bias + adx_bonus + mom_up_bonus - mom_down_penalty

    # ── 18. OUTPUT ──
    last_idx = df.index[-1]
    
    return {
        "regime": str(regime.loc[last_idx]),
        "primary": str(primary.loc[last_idx]),
        "secondary": str(secondary.loc[last_idx]),
        "signal": str(signal.loc[last_idx]),
        "confidence": int(confidence.loc[last_idx]),
        "avoid_entry": bool(avoid_entry.loc[last_idx]),
        "metrics": {
            "adx": float(adx.loc[last_idx]),
            "macd": float(macd.loc[last_idx]),
            "hist": float(hist.loc[last_idx]),
            "atr": float(atr.loc[last_idx]),
            "range_width": float(range_width.loc[last_idx]),
            "vol_spike": bool(vol_spike.loc[last_idx]),
            "vol_dry": bool(vol_dry.loc[last_idx]),
            "ma_flat": bool(ma_flat.loc[last_idx]),
            "chop": bool(chop.loc[last_idx]),
            "structure_bias": int(structure_bias.loc[last_idx]),
            "trend_bias": float(trend_bias.loc[last_idx]),
            "strong_trend": bool(strong_trend.loc[last_idx]),
            "strong_candle": bool(strong_candle.loc[last_idx]),
            "breakout_up": bool(breakout_up.loc[last_idx]),
            "breakout_down": bool(breakout_down.loc[last_idx]),
            "base_valid": bool(base_valid.loc[last_idx]),
            "retest": bool(retest.loc[last_idx]),
            "continuation": bool(continuation.loc[last_idx]),
            "anti_trap_block": bool(anti_trap_block.loc[last_idx]),
            "dist_ma20": float(df['Dist_MA20'].loc[last_idx]),
            "rsi": float(df['RSI'].loc[last_idx])
        }
    }
