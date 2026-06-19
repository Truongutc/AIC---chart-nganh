import pandas as pd

def analyze_accumulation(df: pd.DataFrame) -> dict:
    if len(df) < 50:
        return {"is_accumulation": False, "base_quality": "NONE", "ready_to_break": False, "notes": []}
        
    last = df.iloc[-1]
    
    # Calculate required indicators with 30-day window
    hh30 = df['High'].rolling(30).max().iloc[-1]
    ll30 = df['Low'].rolling(30).min().iloc[-1]
    
    close = last['Close']
    
    # 1. Price range compression
    # HIGH: < 7%, MEDIUM: < 12%
    price_range = (hh30 - ll30) / close
    price_tight = price_range < 0.12
    
    # 2. Volume contraction
    vol_sma10 = df['Volume'].rolling(10).mean().iloc[-1]
    vol_sma30 = df['Volume'].rolling(30).mean().iloc[-1]
    vol_avg_low = vol_sma10 < vol_sma30 * 1.3
    
    # 3. Price stays around MA30
    ma30 = df['Close'].rolling(30).mean().iloc[-1]
    near_ma30 = close >= ma30 * 0.98 # Allow 2% dip for sideway
    
    # 4. Check VSA signal recently (within 7 sessions)
    def check_vsa_at(d, i):
        if abs(i) >= len(d): return False
        c, o, v = d['Close'].iloc[i], d['Open'].iloc[i], d['Volume'].iloc[i]
        s = d['High'].iloc[i] - d['Low'].iloc[i]
        vs30 = d['Volume'].rolling(30).mean().iloc[i]
        as30 = (d['High'] - d['Low']).rolling(30).mean().iloc[i]
        if pd.isna(vs30) or pd.isna(as30): return False
        
        no_s = (c < o) and (v < vs30) and (s < as30)
        ts_s = (c < o) and (s < as30) and (v < d['Volume'].iloc[i-1]) and (v < d['Volume'].iloc[i-2])
        return no_s or ts_s

    vsa_recently = any([check_vsa_at(df, -1-i) for i in range(7)])
    
    is_accum = price_tight and vol_avg_low and near_ma30
    
    notes = []
    if price_range < 0.07: notes.append("Nền thắt chặt (Tight Base <7%)")
    elif price_tight: notes.append("Biên độ bắt đầu thu hẹp (<12%)")
    if vol_avg_low: notes.append("Áp lực bán cạn kiệt (Volume low)")
    if vsa_recently: notes.append("Xuất hiện điểm cạn cung (No/Test Supply)")
    
    quality = "HIGH" if (is_accum and vsa_recently and price_range < 0.08) else "MEDIUM"

    return {
        "is_accumulation": is_accum,
        "base_quality": quality,
        "ready_to_break": is_accum and (close > ma30) and vsa_recently,
        "notes": notes,
        "range_pct": round(price_range * 100, 2)
    }

def check_breakout_accumulation(df: pd.DataFrame) -> bool:
    if len(df) < 32:
        return False
        
    # Check T-1: Accumulation yesterday, close exceeds 30-day high today
    accum_t1 = analyze_accumulation(df.iloc[:-1])
    if accum_t1.get("is_accumulation", False):
        hh30_t1 = df['High'].rolling(30).max().iloc[-2]
        if df['Close'].iloc[-1] > hh30_t1:
            return True
            
    # Check T-2: Accumulation 2 sessions ago, close exceeds 30-day high today
    accum_t2 = analyze_accumulation(df.iloc[:-2])
    if accum_t2.get("is_accumulation", False):
        hh30_t2 = df['High'].rolling(30).max().iloc[-3]
        if df['Close'].iloc[-1] > hh30_t2:
            return True
            
    return False
