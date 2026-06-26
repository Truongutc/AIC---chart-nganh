import logging
import pandas as pd
import numpy as np
from tinvest.rules.rsi_rules import evaluate_rsi
from tinvest.rules.macd_rules import evaluate_macd
from tinvest.rules.adx_rules import evaluate_adx
from tinvest.rules.ichimoku_rules import evaluate_ichimoku
from tinvest.rules.ma_rules import evaluate_ma

logger = logging.getLogger(__name__)

def _get_indicators(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    
    def _get_val(col, default=0.0):
        val = last.get(col, default)
        try:
            return float(val) if not pd.isna(val) else default
        except:
            return default

    return {
        "price": _get_val('Close'),
        "ma10": _get_val('MA10'),
        "ma20": _get_val('MA20'),
        "ma50": _get_val('MA50'),
        "ma100": _get_val('MA100'),
        "ma200": _get_val('MA200'),
        "tenkan": _get_val('Tenkan'),
        "kijun": _get_val('Kijun'),
        "k65": _get_val('Kijun65'),
        "span_a": _get_val('SpanA'),
        "span_b": _get_val('SpanB'),
        "cloud_top": _get_val('CloudTop'),
        "cloud_bottom": _get_val('CloudBottom'),
        "rsi": _get_val('RSI', 50),
        "macd": _get_val('MACD'),
        "macd_hist": _get_val('MACD_Hist'),
        "adx": _get_val('ADX'),
        "di_plus": _get_val('DI_Plus'),
        "di_minus": _get_val('DI_Minus')
    }

def _find_swing_points(df: pd.DataFrame) -> dict:
    """Find swing points within the last 90 trading days, maintaining chronological order."""
    recent_df = df.iloc[-90:] if len(df) >= 90 else df
    sh = recent_df[recent_df['SwingHigh'] > 0]['SwingHigh'].tolist()
    sl = recent_df[recent_df['SwingLow'] > 0]['SwingLow'].tolist()
    return {"peaks": sh, "valleys": sl}

def _get_entry_levels(df: pd.DataFrame) -> dict:
    from .advanced_entry import _eval_day, ensure_indicators
    df_eval = ensure_indicators(df.copy())
    levels = {"EARLY": 0.0, "ADD_1": 0.0, "ADD_2": 0.0, "STRONG": 0.0}
    for i in range(1, 21):
        idx = -i
        if abs(idx) > len(df_eval): break
        res = _eval_day(df_eval, idx)
        if res:
            t = res["type"]
            if t in levels and levels[t] == 0:
                levels[t] = float(df_eval['Close'].iloc[idx])
    return levels

def _has_consolidation(df: pd.DataFrame, idx: int = -1, lookback: int = 4) -> bool:
    """
    Kiểm tra 'nghỉ' (flag/siết) trước điểm breakout:
    Chỉ mua gia tăng khi trước đó có vùng nén giá hẹp.
    Tiêu chí: biên độ cao-thấp trong `lookback` phiên gần nhất < 1.5 x ATR14.
    """
    start = max(0, len(df) + idx - lookback) if idx < 0 else max(0, idx - lookback)
    end   = len(df) + idx + 1 if idx < 0 else idx + 1
    recent = df.iloc[start:end]
    if len(recent) < 2:
        return True  # Không đủ data → mặc định coi là có nghỉ
    atr = float(df.iloc[idx].get('ATR14', 0))
    if atr <= 0:
        return True
    price_range = float(recent['High'].max()) - float(recent['Low'].min())
    return price_range < 1.5 * atr


def _calculate_topup_level(df: pd.DataFrame, inds: dict, entry_info: dict,
                            exits: dict) -> dict:
    """
    Tính toán Điểm Mua Gia Tăng (Add Level) cho từng trường hợp:

    EARLY   → Add = Break R1 (Kijun hoặc MA20 — kháng cự gần nhất phía trên)
    ADD_1:
      - MA_PULLBACK / MA_CROSS / ICHI_BOUNCE (giá trên mây)
              → Add = Break đỉnh ngắn hạn gần nhất (R1)
      - ICHI_CROSS (giá dưới mây)
              → Add = min(Kijun, Kijun65, CloudBottom) trong số các mức > giá
    ADD_2   → Add = Break đỉnh gần nhất (Swing High)
    STRONG  → Add = R2 (đỉnh tiếp theo)

    Nguyên tắc: "Break SAU KHI NGHỈ" — chỉ hợp lệ khi trước đó có nén (flag/siết).
    """
    p = inds["price"]
    entry_type = entry_info.get("entry_type", "NONE")
    source     = entry_info.get("details", {}).get("source", "UNKNOWN")
    above_cloud = p > inds["cloud_top"]
    below_cloud = p < inds["cloud_bottom"]

    # Tìm đỉnh swing gần nhất phía trên giá
    swings = _find_swing_points(df)
    peaks_above = sorted([v for v in swings["peaks"] if v > p * 1.005])
    nearest_peak_above = peaks_above[0] if peaks_above else None
    second_peak_above  = peaks_above[1] if len(peaks_above) > 1 else None

    # Đỉnh ngắn hạn gần nhất (max cửa sổ 10 phiên)
    recent_window = min(10, len(df) - 1)
    recent_high = float(df['High'].iloc[-recent_window:-1].max()) if recent_window > 1 else p * 1.05
    short_term_high = recent_high if recent_high > p * 1.005 else (nearest_peak_above or p * 1.05)

    has_rest = _has_consolidation(df)
    rest_note = "✅ Có nền ngắn (flag/siết)" if has_rest else "⚠️ Chưa thấy rõ nền nghỉ — cần thêm vài phiên nén trước khi buy"

    topup = None
    topup_lbl = ""

    # ── EARLY → Break R1 (Kijun hoặc MA20) ────────────────────────────
    if entry_type == "EARLY":
        kijun = inds["kijun"]
        ma20  = inds["ma20"]
        # Lấy mức kháng cự gần nhất phía trên
        cands = sorted([v for v in [kijun, ma20] if v > p])
        topup = cands[0] if cands else (exits.get("r1") or p * 1.05)
        which = "Kijun" if (topup == kijun and kijun > p) else "MA20"
        topup_lbl = f"Break R1={which} ({topup:.2f})"

    # ── ADD_1 ────────────────────────────────────────────────────────────
    elif entry_type == "ADD_1":
        above_cloud_sources = {"MA_PULLBACK", "MA_CROSS", "ICHI_BOUNCE"}
        if source in above_cloud_sources or above_cloud:
            # Giá trên mây hoặc từ pullback/cross MA → dùng Swing High gần nhất
            topup = nearest_peak_above or p * 1.05
            topup_lbl = f"Break Swing High gần nhất ({topup:.2f})"
        elif source == "ICHI_CROSS" or below_cloud:
            # Giá dưới mây → dùng min(Kijun, K65, CloudBottom) > giá
            candidates = [
                (inds["kijun"],        "Kijun"),
                (inds["k65"],          "Kijun65"),
                (inds["cloud_bottom"], "Đáy mây"),
            ]
            valid = [(v, lbl) for v, lbl in candidates if v > p]
            if valid:
                topup, lbl_name = min(valid, key=lambda x: x[0])
                topup_lbl = f"Vượt {lbl_name} ({topup:.2f}) — cản thấp nhất phía trên"
            else:
                topup = exits.get("r1") or p * 1.05
                topup_lbl = f"Break R1 ({topup:.2f}) khi các cản Ichimoku đều dưới giá"
        else:
            topup = short_term_high
            topup_lbl = f"Break đỉnh ngắn hạn ({topup:.2f})"

    # ── ADD_2 → Break đỉnh swing gần nhất ───────────────────────────────
    elif entry_type == "ADD_2":
        topup = nearest_peak_above or p * 1.05
        topup_lbl = f"Break đỉnh gần nhất ({topup:.2f})"

    # ── STRONG → Swing High gần nhất ───────────────────────────────────
    elif entry_type == "STRONG":
        topup = nearest_peak_above or p * 1.05
        topup_lbl = f"Break Swing High gần nhất ({topup:.2f})"

    if topup is None or topup <= p:
        return {"topup_price": 0.0, "topup_desc": "Chưa xác định điểm gia tăng.",
                "topup_has_rest": has_rest}

    return {
        "topup_price": round(topup, 2),
        "topup_desc":  f"{topup_lbl} | {rest_note}",
        "topup_has_rest": has_rest
    }


def _classify_position(price: float, levels: dict) -> str:
    if levels["STRONG"] > 0 and price >= levels["STRONG"]:
        return "Vượt điểm mua MẠNH"
    if levels["ADD_2"] > 0 and price >= levels["ADD_2"]:
        return "Vượt điểm gia tăng 2"
    if levels["ADD_1"] > 0 and price >= levels["ADD_1"]:
        return "Vượt điểm gia tăng 1"
    if levels["EARLY"] > 0:
        if price >= levels["EARLY"] * 1.01:
            return "Vượt điểm mua sớm"
        if price >= levels["EARLY"] * 0.98:
            return "Vùng điểm mua sớm"
        return "Nằm dưới điểm mua sớm"
    return "Chưa có tín hiệu mua"

def _calculate_exits_and_sr(df: pd.DataFrame, inds: dict, entry_info: dict, ticker: str = "", is_breakdown: bool = False) -> dict:
    is_index = ticker.upper().endswith("INDEX") or "VN30" in ticker.upper()
    p = inds["price"]
    entry_type = entry_info.get("entry_type", "NONE")
    source = entry_info.get("details", {}).get("source", "UNKNOWN")
    
    swings = _find_swing_points(df)
    
    # Valleys Below Current Price (Supports)
    valleys_below = [v for v in swings["valleys"] if v < p]
    nearest_valley_below = valleys_below[-1] if valleys_below else None
    
    # Peaks Below Current Price (R-to-S Support candidates)
    peaks_below = [v for v in swings["peaks"] if v < p]
    nearest_peak_below = peaks_below[-1] if peaks_below else None
    
    # Peaks Above Current Price (Resistances)
    peaks_above = [v for v in swings["peaks"] if v > p]
    nearest_peak_above = peaks_above[-1] if peaks_above else None
    second_peak_above = peaks_above[-2] if len(peaks_above) >= 2 else None
    
    # Valleys Above Current Price (Resistance candidates)
    valleys_above = [v for v in swings["valleys"] if v > p]
    nearest_valley_above = valleys_above[-1] if valleys_above else None
    
    if is_breakdown:
        # Special support / SL rules for breakdown condition
        s1_cands = [v for v in [nearest_peak_below, nearest_valley_below] if v is not None]
        s1 = max(s1_cands) if s1_cands else 0.0
        s2 = 0.0
        sl1 = max(p * 0.95, s1 * 0.98 if s1 > 0 else 0)
        sl2 = p * 0.90  # since S2 is None/0.0, max(p * 0.90, S2 * 0.98) is p * 0.90
        ts = sl1
        tp = p * 1.05
    else:
        # ── 1. NO BUY ─────────────────────────────────────────────────────────────
        if entry_type == "NONE":
            # S1: first valley below or MA20
            cands_s1 = [v for v in [nearest_valley_below, nearest_peak_below, inds["ma20"]] if v is not None and v < p]
            if is_index:
                valid_s1 = [round(v, 1) for v in cands_s1 if v < p * 0.998]
            else:
                valid_s1 = [v for v in cands_s1 if v < p * 0.99]
            s1 = max(valid_s1) if valid_s1 else (max(cands_s1) if cands_s1 else p * 0.95)
            
            # S2: deeper support (Minimum 5% from p)
            cands_s2 = [v for v in valleys_below if v < p * 0.95]
            if not cands_s2: # fallback using MA50 or K65 if valid
                cands_s2 = [v for v in [inds["ma50"], inds["k65"]] if v is not None and v < p * 0.95]
            s2 = max(cands_s2) if cands_s2 else s1 * 0.92
            
            tp = p * 1.05
            sl1 = max(p * 0.95, s1 * 0.98 if s1 > 0 else 0)
            sl2 = max(p * 0.90, s2 * 0.98 if s2 > 0 else 0)
            ts = sl1

        # ── 2. EARLY BUY ──────────────────────────────────────────────────────────
        elif entry_type == "EARLY":
            # Support: max(Tenkan, MA10, MA20) if below price
            cands_s1 = [v for v in [inds["tenkan"], inds["ma10"], inds["ma20"]] if v > 0 and v < p]
            s1 = max(cands_s1) if cands_s1 else (nearest_valley_below or p * 0.97)
            
            # S2: Min 5% from p
            cands_s2 = [v for v in valleys_below if v < p * 0.95]
            s2 = max(cands_s2) if cands_s2 else s1 * 0.92
            
            tp = p * 1.05
            sl1 = min(s1 * 0.98, p * 0.93)
            sl2 = s2 * 0.98
            ts = sl1

        # ── 3. ADD_1 BUY ──────────────────────────────────────────────────────────
        elif entry_type == "ADD_1":
            low10 = df['Low'].iloc[-10:].min() if len(df) >= 10 else p * 0.95
            
            if source == "MA_PULLBACK":
                s1, s2 = inds["ma20"], inds["ma50"]
            elif source == "MA_CROSS":
                s1, s2 = max(p * 0.99, inds["ma10"]), low10
            elif source == "ICHI_BOUNCE":
                s1, s2 = max(inds["kijun"], inds["tenkan"]), max(inds["cloud_top"], inds["k65"])
            elif source == "ICHI_CROSS":
                s1, s2 = max(inds["kijun"], inds["tenkan"]), low10
            else: # Fallback
                s1, s2 = (inds["ma20"] or nearest_valley_below), (inds["ma50"] or s1 * 0.95)
                
            # Ensure s1 is valid
            if not s1 or s1 >= p:
                s1 = max([v for v in [inds["ma20"], inds["tenkan"], nearest_valley_below] if v and v < p] or [p * 0.97])

            sl1, sl2 = s1 * 0.98, s2 * 0.98 if s2 else s1 * 0.95
            ts = sl1
            tp = p * 1.05

        # ── 4. ADD_2 BUY ──────────────────────────────────────────────────────────
        elif entry_type == "ADD_2":
            if source == "HA_REVERSAL":
                s1 = max([v for v in [inds["tenkan"], inds["ma10"], inds["ma20"]] if v < p] or [p * 0.97])
                s2 = max([v for v in [inds["kijun"], inds["ma20"], inds["ma50"]] if v < s1] or [s1 * 0.95])
                sl1 = s1 * 0.97
                sl2 = max(s2 * 0.97, inds["cloud_top"])
            elif source == "TK_CROSS_UP":
                tk_cross_val = min(inds["tenkan"], inds["kijun"]) if (inds["tenkan"] > 0 and inds["kijun"] > 0) else inds["ma20"]
                s1 = max([v for v in [tk_cross_val, inds["k65"], inds["ma20"]] if v < p] or [p * 0.97])
                cands_s2 = [v for v in [tk_cross_val, inds["k65"], inds["ma50"]] if v < s1]
                s2 = max(cands_s2) if cands_s2 else (nearest_valley_below or s1 * 0.95)
                sl1 = s1 * 0.97
                sl2 = max(s2 * 0.97, inds["cloud_top"])
            else:
                s1 = max([v for v in [inds["tenkan"], inds["ma10"], inds["ma20"]] if v < p] or [p * 0.97])
                s2 = max([v for v in [inds["kijun"], inds["ma20"], inds["ma50"]] if v < s1] or [s1 * 0.95])
                sl1, sl2 = s1 * 0.97, s2 * 0.97
            ts = sl1
            tp = p * 1.05

        # ── 5. STRONG BUY ─────────────────────────────────────────────────────────
        elif entry_type == "STRONG" or entry_type == "UNKNOWN":
            if source == "PERFECT_MA":
                s1 = inds["ma10"] if p >= inds["ma10"] else inds["ma20"]
                s2 = inds["ma20"]
                sl1 = max(inds["ma10"] * 0.95, p * 0.90)
                sl2 = inds["ma20"] * 0.95
            elif source == "KUMO_BREAK":
                s1, s2 = inds["tenkan"], inds["kijun"]
                sl1 = max(inds["tenkan"] * 0.95, p * 0.90)
                sl2 = inds["kijun"] * 0.97
            else:
                s1, s2 = inds["ma10"], inds["ma20"]
                sl1, sl2 = s1 * 0.95, s2 * 0.95
            ts = sl1
            tp = p * 1.05

        # Index Specific Support Override (If not breakdown)
        if is_index:
            s_cands = []
            if nearest_valley_below and nearest_valley_below < p:
                s_cands.append(nearest_valley_below)
            if nearest_peak_below and nearest_peak_below < p:
                s_cands.append(nearest_peak_below)
                
            ma50_val = inds["ma50"]
            ma100_val = inds["ma100"]
            ma200_val = inds["ma200"]
            ma20_val = inds["ma20"]
            tenkan_val = inds["tenkan"]
            kijun_val = inds["kijun"]
            cloud_bottom_val = inds["cloud_bottom"]
            
            has_ma50_ma100_close = False
            if ma50_val > 0 and ma100_val > 0 and ma50_val < p and ma100_val < p:
                if abs(ma50_val - ma100_val) / max(ma50_val, ma100_val) <= 0.02:
                    has_ma50_ma100_close = True
                    lower_ma = min(ma50_val, ma100_val)
                    s_cands.append(lower_ma)
            
            if not has_ma50_ma100_close:
                if ma50_val > 0 and ma50_val < p: s_cands.append(ma50_val)
                if ma100_val > 0 and ma100_val < p: s_cands.append(ma100_val)
                
            if ma200_val > 0 and ma200_val < p: s_cands.append(ma200_val)
            if ma20_val > 0 and ma20_val < p: s_cands.append(ma20_val)
            if tenkan_val > 0 and tenkan_val < p: s_cands.append(tenkan_val)
            if kijun_val > 0 and kijun_val < p: s_cands.append(kijun_val)
            if cloud_bottom_val > 0 and cloud_bottom_val < p: s_cands.append(cloud_bottom_val)
            
            s_cands = sorted(list(set(s_cands)), reverse=True)
            s1 = s_cands[0] if len(s_cands) > 0 else (nearest_valley_below or p * 0.95)
            s2 = s_cands[1] if len(s_cands) > 1 else (nearest_peak_below or s1 * 0.95)
            
            # Recalculate SL, Sell All and trailing stop based on overridden index supports
            sl1 = s1 * 0.98
            sl2 = s2 * 0.98 if s2 > 0 else sl1 * 0.95
            ts = sl1

    # ── Unified Ascending Resistance Logic for ALL cases ─────────────────────
    res_candidates = []
    for val in [
        inds.get("tenkan"),
        inds.get("kijun"),
        inds.get("ma10"),
        inds.get("ma20"),
        nearest_peak_above,
        second_peak_above,
        inds.get("cloud_top"),
        inds.get("k65"),
        inds.get("ma50"),
        inds.get("ma100"),
        inds.get("ma200")
    ]:
        if val is not None and not pd.isna(val) and val > p:
            res_candidates.append(float(val))
            
    sorted_res = sorted(list(set(res_candidates)))
    
    r1 = sorted_res[0] if len(sorted_res) > 0 else p * 1.05
    
    if not is_index:
        r2_cands = [x for x in sorted_res if x > r1 * 1.03]
        r2 = r2_cands[0] if len(r2_cands) > 0 else r1 * 1.03
        
        r3_cands = [x for x in sorted_res if x > r2 * 1.03]
        r3 = r3_cands[0] if len(r3_cands) > 0 else r2 * 1.03
    else:
        r2 = sorted_res[1] if len(sorted_res) > 1 else r1 * 1.03
        r3 = sorted_res[2] if len(sorted_res) > 2 else r2 * 1.03
    
    # Enforce R2 <= R3
    if r2 > r3:
        r2, r3 = r3, r2
        
    if tp <= p:
        tp = r1

    # Ultimate Support Safeguard (handles 0, NaN, or s1 >= p)
    if not s1 or pd.isna(s1) or s1 >= p:
        valid_valleys = [v for v in valleys_below if v < p * 0.998] if is_index else [v for v in valleys_below if v < p * 0.99]
        if valid_valleys:
            s1 = valid_valleys[-1]
        else:
            s1 = inds["ma20"] if (inds["ma20"] > 0 and inds["ma20"] < p) else p * 0.96
            
    if not is_breakdown:
        if not s2 or pd.isna(s2) or s2 >= s1:
            s2 = nearest_valley_below if (nearest_valley_below and nearest_valley_below < s1) else s1 * 0.95
    else:
        s2 = 0.0
    
    if not s2: s2 = 0.0
    
    if not sl1 or pd.isna(sl1) or sl1 >= p: sl1 = p * 0.97
    if not sl2 or pd.isna(sl2) or sl2 >= sl1: sl2 = sl1 * 0.96

    # Tính trailing stop (ts) linh hoạt theo khoảng cách giá
    if p > r1 * 0.97:
        ts = max(s1, r1 * 0.97)
    else:
        if p * 0.95 > s1:
            ts = p * 0.95
        else:
            ts = s1
            
    if not ts or pd.isna(ts):
        ts = sl1

    if s1 > 0 and s2 > 0 and s2 > s1:
        s1, s2 = s2, s1

    return {
        "s1": float(s1) if s1 else 0.0, "s2": float(s2) if s2 else 0.0, 
        "r1": float(r1), "r2": float(r2), "r3": float(r3),
        "tp1": float(tp), "tp2": float(r3 if r3 > p else tp * 1.05),
        "trailing_stop": float(ts),
        "cutloss_partial": float(sl1),
        "cutloss_full": float(sl2),
        "break_buy": float(r1 * 1.01) if r1 > 0 else float(p * 1.05)
    }

def _calculate_scores(df: pd.DataFrame, inds: dict) -> tuple:
    p = inds["price"]
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    
    # 1. RISK SCORE
    risk = 0
    # A. Trend Breakdown
    if p < inds["ma20"]: risk += 5
    if p < inds["ma50"]: risk += 5
    if p < inds["ma200"]: risk += 10
    
    # B. Ichimoku
    if inds["tenkan"] < inds["kijun"]: risk += 5
    if inds["cloud_bottom"] <= p <= inds["cloud_top"]: risk += 5
    if p < inds["cloud_bottom"]: risk += 10
    
    # C. Support Breakdown
    if p < inds["k65"]: risk += 10
    recent_swings = [v for v in df['SwingLow'].iloc[-15:] if v > 0]
    if recent_swings and p < recent_swings[-1]: risk += 10
    
    # D. Volume - VSA
    avg_vol20 = float(last.get('AvgVolume20', last['Volume']))
    is_down = last['Close'] < prev['Close']
    if is_down and (last['Volume'] > 1.5 * avg_vol20): risk += 15
    if last['Volume'] < 0.5 * avg_vol20: risk += 10
    
    # E. Bull Trap / Fakeout
    # Break peak but close below
    recent_peaks = [v for v in df['SwingHigh'].iloc[-15:-1] if v > 0]
    bull_trap = False
    if recent_peaks and last['High'] > recent_peaks[-1] and last['Close'] < recent_peaks[-1]:
        bull_trap = True
        risk += 15
        
    risk = min(100, max(0, risk))

    # 2. OPPORTUNITY SCORE
    opp = 0
    # A. Trend Strength
    if p > inds["ma20"] > inds["ma50"]: opp += 10
    if inds["ma10"] > prev.get('MA10', p): opp += 10
    if p > inds["cloud_top"]: opp += 10
    if p > inds["ma10"] and p > inds["tenkan"]: opp += 10
    
    # B. Structure
    hl = recent_swings[-1] > recent_swings[-2] if len(recent_swings) >= 2 else False
    hh = recent_peaks[-1] > recent_peaks[-2] if len(recent_peaks) >= 2 else False
    if hl and hh: opp += 10
    
    base_cond = (df['High'].iloc[-15:].max() - df['Low'].iloc[-15:].min()) / p < 0.08
    if base_cond: opp += 10 # Tight range
    
    # C. Breakout
    if recent_peaks and last['Close'] > recent_peaks[-1]: opp += 15
    if last['Volume'] > 1.5 * avg_vol20 and last['Close'] > last['Open']: opp += 10
    if True: # Simulating Retest
        if abs(p - inds["ma20"]) / p < 0.02 or abs(p - inds["kijun"]) / p < 0.02:
            if last['Close'] > last['Open']: opp += 10

    # D. Momentum
    if inds["rsi"] > 55: opp += 5
    if inds["adx"] > 20: opp += 5
    if inds["adx"] > 25: opp += 5
    if inds["di_plus"] > inds["di_minus"]: opp += 5

    opp = min(100, max(0, opp))
    
    return risk, opp, bull_trap

def evaluate_stock_valuation(ticker: str, df: pd.DataFrame, entry_info: dict) -> dict:
    if len(df) < 2: return {"is_valid": False, "reason": "Dữ liệu quá ngắn"}
    
    inds = _get_indicators(df)
    price = inds["price"]
    state = entry_info.get("entry_type", "NONE")
    
    # Check breakdown condition
    is_breakdown = False
    if len(df) >= 2:
        cond_price = (price < inds["k65"]) and (price < inds["ma50"]) and (price < inds["ma10"])
        prev_ma20 = float(df["MA20"].iloc[-2]) if "MA20" in df.columns and len(df) >= 2 else inds["ma20"]
        cond_ma20_slope = inds["ma20"] < prev_ma20
        cond_cloud = price < inds["cloud_bottom"]
        
        swings = _find_swing_points(df)
        sh = swings["peaks"]
        sl = swings["valleys"]
        cond_lh = len(sh) >= 2 and sh[-1] < sh[-2]
        cond_ll = len(sl) >= 2 and sl[-1] < sl[-2]
        
        if cond_price and cond_ma20_slope and cond_cloud and cond_lh and cond_ll:
            is_breakdown = True
            state = "NONE"
            entry_info = entry_info.copy()
            entry_info["entry_type"] = "NONE"
            
    exits = _calculate_exits_and_sr(df, inds, entry_info, ticker=ticker, is_breakdown=is_breakdown)
    risk_col, opp_col, bull_trap = _calculate_scores(df, inds)
    
    levels = _get_entry_levels(df)
    pos = _classify_position(price, levels)
    
    hist = inds["macd_hist"]
    p_hist = hist
    if 'MACD_Hist' in df.columns and len(df) > 1:
        try:
            p_hist = float(df['MACD_Hist'].iloc[-2])
        except:
            p_hist = hist
            
    macd_status = "Tích cực (Histogram tăng)" if hist > p_hist else "Tiêu cực (Histogram giảm)"
    if inds["macd"] > 0 and hist > 0:
        macd_status = "Đà tăng mạnh (MACD > 0 & Hist > 0)"
    
    risk_amt = max(0.01, price - exits["cutloss_partial"])
    reward_amt = max(0.01, exits["tp1"] - price)
    rr = round(reward_amt / risk_amt, 2)
    
    risk_desc = "LOW"
    if risk_col > 75: risk_desc = "EXTREME"
    elif risk_col > 45: risk_desc = "HIGH"
    elif risk_col > 25: risk_desc = "MEDIUM"

    opp_desc = "Yếu"
    if opp_col > 80: opp_desc = "Rất mạnh"
    elif opp_col > 60: opp_desc = "Tốt"
    elif opp_col >= 40: opp_desc = "Trung bình"
    
    # Cập nhật dán nhãn hành động dựa trên Tỷ trọng khuyến nghị của phần đánh giá tổng hợp
    ma_diag = evaluate_ma(df, -1)
    # Dùng field boolean is_break_confirmed thay vì string matching.
    # String matching "GÃY" bắt cả cảnh báo sớm (early warning) → false positive.
    # is_break_confirmed = True chỉ khi gãy trend ĐÃ XÁC NHẬN (break_confirmed_1 hoặc break_confirmed_2).
    is_trend_broken = bool(ma_diag.get("is_break_confirmed", False))

    # Khi AI đã xác nhận tín hiệu tốt (STRONG/ADD_2/ADD_1/EARLY),
    # chỉ gãy trend thực sự mới được override sang "Đứng ngoài".
    # risk_col cao đơn thuần KHÔNG đủ để phủ nhận tín hiệu AI bullish.
    ai_bullish = state in ('STRONG', 'ADD_2', 'ADD_1', 'EARLY')

    target_pct = "0% (Theo dõi thêm)"
    if is_trend_broken or (risk_col > 60 and not ai_bullish):
        target_pct = "0% (Đứng ngoài phòng thủ)"
    else:
        if state == "STRONG":
            target_pct = "70–100% (Mua Mạnh/Gồng lãi)"
        elif state == "ADD_2":
            target_pct = "50–70% (Gia tăng 2)"
        elif state == "ADD_1":
            target_pct = "30–50% (Thăm dò/Gia tăng 1)"
        elif state == "EARLY":
            target_pct = "15–25% (Mua sớm)"
        elif opp_col >= 65:
            target_pct = "20–40% (Giữ vị thế/Chờ điểm nổ)"
        elif opp_col >= 45:
            target_pct = "10–20% (Quan sát chặt)"

    action = "WAIT (Chờ tín hiệu rõ ràng)"
    if is_trend_broken or (risk_col > 70 and not ai_bullish):
        action = "NO (Đứng ngoài)"
    elif price >= exits["tp1"] and opp_col >= 50:
        action = "TAKE PROFIT (Chốt lời bớt)"
    elif target_pct.startswith("0%"):
        action = "WAIT (Chờ tín hiệu rõ ràng)"
    elif "70–100%" in target_pct or "50–70%" in target_pct or "70-100%" in target_pct or "50-70%" in target_pct:
        action = "YES (Nên tham gia)"
    else:
        action = "YES (Có thể cân nhắc)"

    # Calculate suggested entry price based on tag & R/R profile
    curr_risk = max(0.01, price - exits["cutloss_partial"])
    curr_reward = max(0.01, exits["tp1"] - price)
    
    entry_price = price
    is_wait = "WAIT" in action.upper()
    is_yes = "YES" in action.upper()
    
    if is_wait or (is_yes and curr_reward < curr_risk):
        if exits["s1"] > 0 and exits["s1"] < price:
            entry_price = exits["s1"]
            
    # Calculate R/R ratio at suggested entry price
    risk_amt = max(0.01, entry_price - exits["cutloss_partial"])
    reward_amt = max(0.01, exits["tp1"] - entry_price)
    rr = round(reward_amt / risk_amt, 2)

    topup = _calculate_topup_level(df, inds, entry_info, exits)
    
    # Mức độ an toàn: (Cơ hội * 0.6 + (100 - Rủi ro) * 0.4)
    topup_safety = int(opp_col * 0.6 + (100 - risk_col) * 0.4)

    return {
        "is_valid": True, "ticker": ticker, "state": state, "position": pos,
        "price": entry_price, "s1": exits["s1"], "s2": exits["s2"],
        "r1": exits["r1"], "r2": exits["r2"], "r3": exits.get("r3", exits["r2"]), "break_buy": exits["break_buy"],
        "cutloss_partial": exits["cutloss_partial"], "cutloss_full": exits["cutloss_full"],
        "tp1": exits["tp1"], "tp2": exits["tp2"], "trailing_stop": exits["trailing_stop"],
        "risk_score": risk_col, "risk_desc": risk_desc,
        "opp_score": opp_col, "opp_desc": opp_desc,
        "rr_ratio": rr, "risk_pct": round((risk_amt / entry_price) * 100, 2),
        "reward_pct": round((reward_amt / entry_price) * 100, 2),
        "action": action, "bull_trap": bull_trap,
        "topup_price": topup["topup_price"],
        "topup_desc":  topup["topup_desc"],
        "topup_has_rest": topup["topup_has_rest"],
        "topup_safety": topup_safety,
        "tech_health": {
            "adx_label": str(df['ADX_Color'].iloc[-1]) if 'ADX_Color' in df.columns else "N/A",
            "rsi_label": f"{inds['rsi']:.1f}",
            "macd_label": macd_status,
            "health_rating": opp_desc,
            "health_score": opp_col,
            "diagnostics": {
                "rsi": evaluate_rsi(df, -1),
                "macd": evaluate_macd(df, -1),
                "adx": evaluate_adx(df, -1),
                "ichimoku": evaluate_ichimoku(df, -1),
                "ma": evaluate_ma(df, -1)
            }
        },
        "details": {"ma20": inds["ma20"], "ma50": inds["ma50"]}
    }
