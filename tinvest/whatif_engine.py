"""
What-If Scenario Forecast Engine
=================================
Module phân tích xác suất tương lai dựa trên:
- Historical Analog Matching (Cosine Similarity)
- Indicator State Vector (50+ features từ enrich_dataframe)
- Support/Resistance Zone Detection & Reaction Analysis
- Probability Distribution (thực tế sau 3/5/10 phiên)
- What-If Scenario Tree
- Target Projection (ATR + Measured Move)

CRITICAL DESIGN PRINCIPLE:
  - Không dùng Market Score / Composite Score làm đầu vào
  - Mọi xác suất đều từ dữ liệu lịch sử thực tế
  - Hoạt động với VNINDEX, HNX-INDEX, VN30, UPCOM, Individual Stocks
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)



# ── Trend Exhaustion & Temporal Diversity ────────────────────
EXHAUSTION_RET_PERIOD = 10
EXHAUSTION_WINDOW     = 100
EXHAUSTION_MIN_SAMPLES = 20
MIN_MATCH_GAP_SESSIONS = 5

def _calc_trend_exhaustion(col_arrays: dict, idx: int) -> float:
    """
    Đo mức độ "giãn quá đà" của xu hướng hiện tại so với phân phối
    lịch sử return N phiên của CHÍNH cổ phiếu đó (z-score).

    z càng âm (gần -1) -> giá đã giảm mạnh hơn bình thường rất nhiều
       -> xu hướng có thể đã "kiệt sức", khả năng hồi cao hơn dữ liệu
          chỉ-toàn-trend-continuation gợi ý.
    z càng dương (gần +1) -> giá đã tăng mạnh hơn bình thường
       -> khả năng chững lại / điều chỉnh.
    z gần 0 -> xu hướng đang ở mức "bình thường" so với lịch sử, chưa
       có dấu hiệu kiệt sức.

    Output: clip về [-1, 1].
    """
    close = col_arrays['Close']
    p = EXHAUSTION_RET_PERIOD

    if idx < p:
        return 0.0

    def _ret(j):
        base = close[j - p]
        if base != base or base == 0:  # NaN or zero
            return None
        return (close[j] - base) / base * 100.0

    current_ret = _ret(idx)
    if current_ret is None:
        return 0.0

    start = max(p, idx - EXHAUSTION_WINDOW)
    hist_rets = []
    for j in range(start, idx):
        r = _ret(j)
        if r is not None and r == r:  # not NaN
            hist_rets.append(r)

    if len(hist_rets) < EXHAUSTION_MIN_SAMPLES:
        return 0.0

    hist_arr = np.array(hist_rets)
    mean = float(np.mean(hist_arr))
    std = float(np.std(hist_arr))

    if std <= 1e-9:
        return 0.0

    z = (current_ret - mean) / std
    return float(np.clip(z / 3.0, -1.0, 1.0))

# ── Multi-horizon consensus weights ──────────────────────────
CONSENSUS_WEIGHT_3  = 0.2
CONSENSUS_WEIGHT_5  = 0.5
CONSENSUS_WEIGHT_10 = 0.3

CONSENSUS_LABELS = {
    "strong_bull":  "Tăng mạnh",
    "mild_bull":    "Tăng nhẹ",
    "neutral":      "Chưa rõ xu hướng",
    "mild_bear":    "Giảm nhẹ",
    "strong_bear":  "Giảm mạnh",
}

# ── Anomaly detection ────────────────────────────────────────
ANOMALY_STD_THRESHOLD = 3.0   # outlier if |value - rolling_mean| > 3 * rolling_std
ANOMALY_WINDOW        = 50    # rolling window 50 sessions
FALLBACK_WEIGHT       = 1.0   # fallback weight when anomalous

# ── Weight config ───────────────────────────────────────────
DEFAULT_WEIGHT_CONFIG: dict[str, float] = {
    # ── MCDX / Banker ─── weight 1.5
    "banker_norm":     1.5,
    "hot_money_norm":  1.5,
    "banker_vs_ma":    1.5,
    "banker_trend":    1.5,
    # ── ADX / DI ─────── weight 1.5
    "adx_norm":        1.5,
    "adx_color":       1.5,
    "adx_vs_diplus":   1.5,
    "adx_vs_diminus":  1.5,
    "di_dominance":    1.5,
    "di_gap_change":   1.5,
    "adx_momentum":    1.5,
    # ── MACD ─────────── weight 1.5
    "macd_hist":       1.5,
    "macd_hist_slope": 1.5,
    "macd_vs_signal":  1.5,
    "macd_cross":      1.5,
    "macd_slope":      1.5,
    "macd_expanding":  1.5,
    # ── RSI ──────────── weight 1.5
    "rsi":             1.5,
    "rsi_zone":        1.5,
    "rsi_slope":       1.5,
    "rsi_accel":       1.5,
    "rsi_phase":       1.5,
    "rsi_diverge":     1.5,
    # ── MA Structure ─── weight 4.0 (primary focus)
    "ma_price_zone":   4.0,
    "ma_slope_short":  4.0,
    "ma_slope_mid":    4.0,
    # ── Ichimoku ─────── weight 1.5
    "tk_diverge":      1.5,
    "dist_kijun65":    1.5,
    "dist_kijun":      1.5,
    "price_vs_cloud":  3.0,
    "dist_cloud_top":  3.0,
    # ── Price Momentum ── weight 1.5
    "price_streak":    1.5,
    "trend_exhaustion": 1.5,
}

# ── Tiered Similarity Matching Constants ──────────────────────
TIER1_THRESHOLD = 0.86
TIER2_THRESHOLD = 0.80
TIER3_THRESHOLD = 0.75
TIER4_FLOOR     = 0.65

MIN_MATCHES_TARGET = 20
MAX_MATCHES_RETURN = 30

TIER_MULTIPLIERS = {
    1: 1.0,
    2: 0.6,
    3: 0.3,
    4: 0.1
}

KUMO_SAME_STATE_BOOST = 1.15  # Tăng 15% trọng số cho phiên có cùng trạng thái giá vs mây


TIER_LABELS = {
    1: "High Confidence",
    2: "Medium Confidence",
    3: "Low Confidence",
    4: "Fallback"
}

CONFIDENCE_LABELS = {
    1: "Tin cậy cao",
    2: "Tin cậy trung bình",
    3: "Tin cậy thấp",
    4: "Không đủ tin cậy"
}

WARNING_MESSAGES = {
    1: None,
    2: "Một phần matches ở mức Medium Confidence",
    3: "Ít phiên tương đồng cao — kết quả mang tính tham khảo",
    4: "Không đủ phiên tương đồng — không nên ra quyết định dựa trên kết quả này"
}


def _classify_tier(similarity: float) -> Optional[int]:
    if similarity >= TIER1_THRESHOLD:
        return 1
    elif similarity >= TIER2_THRESHOLD:
        return 2
    elif similarity >= TIER3_THRESHOLD:
        return 3
    # Bỏ Tier 4 (< 75%)
    return None


def calculate_consensus_direction(dist: dict) -> dict:
    """
    Tính consensus direction từ 3 horizon (3/5/10 phiên).
    Trả về consensus score, direction label, confidence label,
    và flag conflict nếu ngắn hạn và trung hạn mâu thuẫn.
    """
    def net(key):
        d = dist.get(key, {})
        return d.get('pct_up', 50) - d.get('pct_down', 50)

    net_3  = net('future_3')
    net_5  = net('future_5')
    net_10 = net('future_10')

    consensus = (
        CONSENSUS_WEIGHT_3  * net_3 +
        CONSENSUS_WEIGHT_5  * net_5 +
        CONSENSUS_WEIGHT_10 * net_10
    )

    # Direction label
    if consensus > 15:
        direction = "strong_bull"
    elif consensus > 5:
        direction = "mild_bull"
    elif consensus >= -5:
        direction = "neutral"
    elif consensus >= -15:
        direction = "mild_bear"
    else:
        direction = "strong_bear"

    # Confidence label
    abs_consensus = abs(consensus)
    if abs_consensus > 15:
        confidence_label = "Độ tin cậy cao"
    elif abs_consensus > 5:
        confidence_label = "Độ tin cậy trung bình"
    else:
        confidence_label = "Tín hiệu chưa rõ ràng — thận trọng"

    # Conflict detection: future_3 và future_10 ngược chiều nhau
    short_bull = net_3 > 5
    long_bull  = net_10 > 5
    short_bear = net_3 < -5
    long_bear  = net_10 < -5
    conflict = (short_bull and long_bear) or (short_bear and long_bull)

    return {
        "consensus_score":   round(consensus, 2),
        "direction":         direction,
        "direction_label":   CONSENSUS_LABELS[direction],
        "confidence_label":  confidence_label,
        "is_bullish":        consensus > 0,
        "short_long_conflict": conflict,
        "conflict_warning":  (
            "Tín hiệu ngắn hạn và trung hạn mâu thuẫn nhau — thận trọng"
            if conflict else None
        ),
        "net_3":  round(net_3, 2),
        "net_5":  round(net_5, 2),
        "net_10": round(net_10, 2),
    }


REQUIRED_COLS = [
    'Close', 'MA10', 'MA20', 'MA50', 'MA100', 'MA200',
    'ADX', 'DI_Plus', 'DI_Minus', 'ADX_Color',
    'CloudTop', 'CloudBottom', 'Tenkan', 'Kijun', 'Kijun65',
    'RSI', 'MACD', 'MACD_Signal', 'MACD_Hist', 'MCDX_Banker',
    'ATR14', 'ATR14_Slope', 'OCT_A1', 'MCDX_HotMoney', 'MCDX_Banker_MA',
    'Volume', 'AvgVolume20', 'OCT_Color', 'HA_Color', 'HK_Trend',
    'T2_SMA_Score', 'T2_ST_Score'
]


def _build_col_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """
    Convert các cột cần thiết của df thành dict[str, np.ndarray]
    để _calc_dynamic_features và build_state_vector_fast truy cập theo idx.
    """
    n = len(df)
    col_arrays: dict[str, np.ndarray] = {}
    for col in REQUIRED_COLS:
        if col in df.columns:
            col_arrays[col] = df[col].to_numpy()
        else:
            if col in ['OCT_Color', 'HA_Color', 'ADX_Color']:
                col_arrays[col] = np.full(n, '', dtype=object)
            else:
                col_arrays[col] = np.full(n, np.nan, dtype=np.float64)
    return col_arrays


def _calc_dynamic_features(col_arrays: dict, idx: int, safe_atr: float) -> dict:
    """
    Tính các features động phản ánh xu hướng vận động thực sự.
    Gồm 5 nhóm: MA Structure, ADX/DI, Ichimoku, RSI/MACD/Banker, Price Momentum.
    Tất cả output nằm trong [-1, 1].
    """
    def g(col, default=0.0):
        v = col_arrays[col][idx]
        return float(v) if v == v and v is not None else default

    def gp(col, default=0.0):
        v = col_arrays[col][max(idx - 1, 0)]
        return float(v) if v == v and v is not None else default

    def gp2(col, default=0.0):
        v = col_arrays[col][max(idx - 2, 0)]
        return float(v) if v == v and v is not None else default

    def gp3(col, default=0.0):
        v = col_arrays[col][max(idx - 3, 0)]
        return float(v) if v == v and v is not None else default

    price    = g('Close', 1.0)
    close_p  = gp('Close', price)
    close_p2 = gp2('Close', price)
    close_p3 = gp3('Close', price)

    ma10   = g('MA10', price);   ma10_p  = gp('MA10', ma10)
    ma20   = g('MA20', price);   ma20_p  = gp('MA20', ma20)
    ma50   = g('MA50', price);   ma50_p  = gp('MA50', ma50)
    ma100  = g('MA100', price);  ma100_p = gp('MA100', ma100)
    ma200  = g('MA200', price)

    adx      = g('ADX', 0.0);    adx_p   = gp('ADX', 0.0)
    di_plus  = g('DI_Plus', 0.0);  di_plus_p  = gp('DI_Plus', 0.0)
    di_minus = g('DI_Minus', 0.0); di_minus_p = gp('DI_Minus', 0.0)

    cloud_top   = g('CloudTop', price);   cloud_top_p = gp('CloudTop', price)
    cloud_bot   = g('CloudBottom', price)
    cloud_bot_p = gp('CloudBottom', price)
    tenkan      = g('Tenkan', price);     tenkan_p    = gp('Tenkan', price)
    kijun       = g('Kijun', price);      kijun_p     = gp('Kijun', price)

    rsi      = g('RSI', 50.0)
    rsi_p    = gp('RSI', 50.0)
    rsi_p2   = gp2('RSI', 50.0)
    rsi_p3   = gp3('RSI', 50.0)

    macd_hist    = g('MACD_Hist', 0.0)
    macd_hist_p  = gp('MACD_Hist', 0.0)

    banker   = g('MCDX_Banker', 10.0)
    banker_p = gp('MCDX_Banker', 10.0)
    banker_p2 = gp2('MCDX_Banker', 10.0)

    # ── NHÓM 1: MA Structure (3 hướng, 6 features) ──────────
    def above(ma): return 1.0 if price > ma else -1.0
    ma_price_zone = (
        above(ma10)  * 0.30 +
        above(ma20)  * 0.25 +
        above(ma50)  * 0.20 +
        above(ma100) * 0.15 +
        above(ma200) * 0.10
    )

    ma_slope_short = np.clip(
        (0.6 * (ma10 - ma10_p) + 0.4 * (ma20 - ma20_p)) / safe_atr,
        -1.0, 1.0
    )
    ma_slope_mid = np.clip(
        (ma50 - ma50_p) / safe_atr, -1.0, 1.0
    )
    ma_slope_long = np.clip(
        (ma100 - ma100_p) / safe_atr, -1.0, 1.0
    )

    mas_below = [(ma, mp) for ma, mp in
                 [(ma10, ma10_p), (ma20, ma20_p),
                  (ma50, ma50_p), (ma100, ma100_p)]
                 if ma < price]
    mas_above = [(ma, mp) for ma, mp in
                 [(ma10, ma10_p), (ma20, ma20_p),
                  (ma50, ma50_p), (ma100, ma100_p)]
                 if ma >= price]

    if mas_below:
        nearest_sup, nearest_sup_p = max(mas_below, key=lambda x: x[0])
        dist_sup_now  = (price - nearest_sup) / safe_atr
        dist_sup_prev = (close_p - nearest_sup_p) / safe_atr
        ma_support_dist_change = np.clip(
            (dist_sup_now - dist_sup_prev) / 2.0, -1.0, 1.0
        )
    else:
        ma_support_dist_change = 0.0

    if mas_above:
        nearest_res, nearest_res_p = min(mas_above, key=lambda x: x[0])
        dist_res_now  = (nearest_res - price) / safe_atr
        dist_res_prev = (nearest_res_p - close_p) / safe_atr
        ma_resist_dist_change = np.clip(
            (dist_res_prev - dist_res_now) / 2.0, -1.0, 1.0
        )
    else:
        ma_resist_dist_change = 0.0

    # ── NHÓM 2: ADX/DI Dynamic ───────────────────────────────
    adx_momentum = np.clip((adx - adx_p) / 5.0, -1.0, 1.0)
    di_gap_now  = di_plus - di_minus
    di_gap_prev = di_plus_p - di_minus_p
    di_gap_change = np.clip((di_gap_now - di_gap_prev) / 5.0, -1.0, 1.0)
    adx_breakout = 1.0 if (adx >= 20 and adx_p < 20) else 0.0

    # ── NHÓM 3: Ichimoku Dynamic ─────────────────────────────
    dist_cloud_now = (
        (price - cloud_top) / safe_atr if price > cloud_top
        else (price - cloud_bot) / safe_atr
    )
    dist_cloud_prev = (
        (close_p - cloud_top_p) / safe_atr if close_p > cloud_top_p
        else (close_p - cloud_bot_p) / safe_atr
    )
    cloud_dist_change = np.clip(
        (dist_cloud_now - dist_cloud_prev) / 2.0, -1.0, 1.0
    )

    tk_gap_now  = tenkan - kijun
    tk_gap_prev = tenkan_p - kijun_p
    tk_diverge  = np.clip((tk_gap_now - tk_gap_prev) / safe_atr, -1.0, 1.0)

    tk_cross_signal = (
         1.0 if (tenkan > kijun and tenkan_p <= kijun_p) else
        -1.0 if (tenkan < kijun and tenkan_p >= kijun_p) else
         0.0
    )

    # ── NHÓM 4: RSI/MACD/Banker Phase ────────────────────────
    rsi_vel   = rsi - rsi_p
    rsi_accel = rsi_vel - (rsi_p - rsi_p2)
    rsi_phase = np.clip(rsi_accel / 5.0, -1.0, 1.0)

    price_dir_3 = 1.0 if price > close_p3 else -1.0
    rsi_dir_3   = 1.0 if rsi > rsi_p3 else -1.0
    rsi_diverge = -1.0 if price_dir_3 != rsi_dir_3 else 1.0

    macd_expanding = np.clip(
        (abs(macd_hist) - abs(macd_hist_p)) /
        max(abs(macd_hist_p) + 0.001, 0.001),
        -1.0, 1.0
    )

    macd_flip = (
         1.0 if (macd_hist > 0 and macd_hist_p <= 0) else
        -1.0 if (macd_hist < 0 and macd_hist_p >= 0) else
         0.0
    )

    banker_trend = np.clip((banker - banker_p2) / 5.0, -1.0, 1.0)

    # ── NHÓM 5: Price Momentum ───────────────────────────────
    closes = [price, close_p, close_p2, close_p3]
    streak = 0
    for i in range(len(closes) - 1):
        if closes[i] > closes[i + 1]:
            streak += 1
        elif closes[i] < closes[i + 1]:
            streak -= 1
        else:
            break
    price_streak = np.clip(streak / 3.0, -1.0, 1.0)

    ret1 = (price - close_p) / safe_atr
    ret2 = (close_p - close_p2) / safe_atr
    momentum_accel = np.clip((ret1 - ret2) / 2.0, -1.0, 1.0)

    trend_exhaustion = _calc_trend_exhaustion(col_arrays, idx)

    return {
        # MA Structure
        "ma_price_zone":          float(ma_price_zone),
        "ma_slope_short":         float(ma_slope_short),
        "ma_slope_mid":           float(ma_slope_mid),
        "ma_slope_long":          float(ma_slope_long),
        "ma_support_dist_change": float(ma_support_dist_change),
        "ma_resist_dist_change":  float(ma_resist_dist_change),

        # ADX/DI Dynamic
        "adx_momentum":   float(adx_momentum),
        "di_gap_change":  float(di_gap_change),
        "adx_breakout":   float(adx_breakout),

        # Ichimoku Dynamic
        "cloud_dist_change": float(cloud_dist_change),
        "tk_diverge":        float(tk_diverge),
        "tk_cross_signal":   float(tk_cross_signal),

        # RSI/MACD/Banker Phase
        "rsi_phase":      float(rsi_phase),
        "rsi_diverge":    float(rsi_diverge),
        "macd_expanding": float(macd_expanding),
        "macd_flip":      float(macd_flip),
        "banker_trend":   float(banker_trend),

        # Price Momentum
        "price_streak":    float(price_streak),
        "momentum_accel":  float(momentum_accel),
        "trend_exhaustion": float(trend_exhaustion),
    }


def _detect_anomalous_features(
    sv: dict,
    feature_history: dict[str, np.ndarray] | None,
    idx: int | None,
    weight_config: dict[str, float],
) -> set[str]:
    """
    Trả về tập các feature key được coi là "bất thường" và cần
    fallback weight về FALLBACK_WEIGHT.
    """
    anomalous: set[str] = set()

    for key in weight_config:
        if key not in sv:
            continue

        value = sv[key]

        # Bước 1 — NaN check
        if value is None or (isinstance(value, float) and np.isnan(value)):
            anomalous.add(key)
            logger.warning(
                f"[anomaly] feature '{key}' is NaN/None — "
                f"fallback weight to {FALLBACK_WEIGHT}"
            )
            continue

        # (Removed rolling outlier check)
    return anomalous


# ─────────────────────────────────────────────────────────────
# PHASE 2 – INDICATOR STATE VECTOR
# ─────────────────────────────────────────────────────────────

def build_state_vector(df: pd.DataFrame, idx: int = -1) -> dict:
    """
    Build a normalized indicator state vector for a given row.
    Uses only columns already present from enrich_dataframe().
    Returns a dict of feature_name → numeric value (NaN-safe).
    """
    row = df.iloc[idx]
    prev = df.iloc[idx - 1] if abs(idx) < len(df) else row

    def g(col, default=0.0):
        val = row.get(col, default)
        try:
            v = float(val)
            return v if not (v != v) else default  # NaN check
        except Exception:
            return default

    def gp(col, default=0.0):
        val = prev.get(col, default)
        try:
            v = float(val)
            return v if not (v != v) else default
        except Exception:
            return default

    rsi = g('RSI', 50)
    rsi_prev = gp('RSI', 50)
    rsi_prev2 = float(df['RSI'].iloc[idx - 2]) if len(df) > 2 and 'RSI' in df.columns else rsi_prev

    macd = g('MACD')
    macd_sig = g('MACD_Signal')
    macd_hist = g('MACD_Hist')
    macd_hist_prev = gp('MACD_Hist')

    price = g('Close', 1.0)
    prev_close = gp('Close', price)
    pos_idx = idx if idx >= 0 else len(df) + idx
    prev2_close = float(df['Close'].iloc[pos_idx - 2]) if pos_idx >= 2 else prev_close

    ma10 = g('MA10', price)
    ma20 = g('MA20', price)
    ma50 = g('MA50', price)
    ma100 = g('MA100', price)
    ma200 = g('MA200', price)

    atr = g('ATR14', 1.0)
    atr_slope = g('ATR14_Slope', 0.0)

    cloud_top = g('CloudTop', price)
    cloud_bot = g('CloudBottom', price)
    tenkan = g('Tenkan', price)
    kijun = g('Kijun', price)
    kijun65 = g('Kijun65', price)

    oct_a1 = g('OCT_A1', 0.0)
    oct_a1_prev = gp('OCT_A1', 0.0)

    banker = g('MCDX_Banker', 10.0)
    hot_money = g('MCDX_HotMoney', 10.0)
    banker_ma = g('MCDX_Banker_MA', 10.0)

    vol = g('Volume', 0.0)
    avg_vol20 = g('AvgVolume20', 1.0)

    # OCT color numeric
    oct_color_raw = str(row.get('OCT_Color', ''))
    oct_color_num = (1.0 if '#00FF00' in oct_color_raw
                     else 0.5 if '#008000' in oct_color_raw
                     else -0.5 if '#FF69B4' in oct_color_raw
                     else -1.0)

    # HA color
    ha_color_raw = str(row.get('HA_Color', 'Red'))
    ha_color_num = 1.0 if 'Green' in ha_color_raw else -1.0

    # HK trend
    hk_trend = g('HK_Trend', 0.0)

    # 2Trend states
    t2_sma_score = g('T2_SMA_Score', 0.0)
    t2_st_score = g('T2_ST_Score', 0.0)

    # ADX + DI+/DI-
    adx = g('ADX', 0.0)
    di_plus = g('DI_Plus', 0.0)
    di_minus = g('DI_Minus', 0.0)
    adx_raw = str(row.get('ADX_Color', 'ORANGE')).upper()
    adx_num = (1.0 if adx_raw == 'WHITE' else
               0.5 if adx_raw == 'GREEN' else
               -1.0 if adx_raw == 'RED' else 0.0)

    # Chikou (26 bars ahead comparison – approximate)
    chikou_val = float(df['Close'].iloc[idx - 26]) if len(df) > abs(idx) + 26 else price
    chikou_pos = 1.0 if price > chikou_val else -1.0

    # RSI position bracket
    if rsi < 30:
        rsi_zone = -2.0
    elif rsi < 50:
        rsi_zone = -1.0
    elif rsi < 70:
        rsi_zone = 1.0
    else:
        rsi_zone = 2.0

    # Price vs cloud
    if price > cloud_top:
        price_vs_cloud = 1.0
    elif price >= cloud_bot:
        price_vs_cloud = 0.0
    else:
        price_vs_cloud = -1.0

    safe_atr = max(atr, 0.0001)
    dist_cloud_top_atr = (price - cloud_top) / safe_atr
    dist_kijun_atr = (price - kijun) / safe_atr
    dist_tenkan_atr = (price - tenkan) / safe_atr
    dist_kijun65_atr = (price - kijun65) / safe_atr
    dist_ma10_atr = (price - ma10) / safe_atr
    dist_ma20_atr = (price - ma20) / safe_atr
    dist_ma50_atr = (price - ma50) / safe_atr

    ma_10_vs_20 = 1.0 if ma10 > ma20 else -1.0
    ma_20_vs_50 = 1.0 if ma20 > ma50 else -1.0
    ma_50_vs_100 = 1.0 if ma50 > ma100 else -1.0
    ma_100_vs_200 = 1.0 if ma100 > ma200 else -1.0

    price_vs_tenkan = 1.0 if price > tenkan else -1.0
    price_vs_kijun = 1.0 if price > kijun else -1.0

    # Slope signals
    rsi_slope = rsi - rsi_prev
    rsi_accel = (rsi - rsi_prev) - (rsi_prev - rsi_prev2)
    macd_hist_slope = macd_hist - macd_hist_prev

    # MACD cross signal
    macd_cross = 1.0 if (macd > macd_sig and gp('MACD', 0) <= gp('MACD_Signal', 0)) else 0.0

    # Volume signals
    rel_vol = vol / max(avg_vol20, 1.0)
    vol_spike = 1.0 if rel_vol > 1.5 else 0.0
    vol_dry = 1.0 if rel_vol < 0.7 else 0.0

    # Banker signals
    banker_vs_ma = banker - banker_ma

    # TK cross
    tk_cross = 1.0 if (tenkan > kijun and gp('Tenkan', tenkan) <= gp('Kijun', kijun)) else 0.0

    col_arrays = _build_col_arrays(df)

    res = {
        # RSI
        "rsi": rsi / 100.0,
        "rsi_zone": rsi_zone / 2.0,
        "rsi_slope": np.clip(rsi_slope / 20.0, -1, 1),
        "rsi_accel": np.clip(rsi_accel / 10.0, -1, 1),

        # MACD
        "macd_hist": np.clip(macd_hist / max(abs(macd_hist) + 0.001, 1.0), -1, 1),
        "macd_hist_slope": np.clip(macd_hist_slope / max(abs(macd_hist_slope) + 0.001, 1.0), -1, 1),
        "macd_vs_signal": np.clip((macd - macd_sig) / safe_atr, -2, 2),
        "macd_cross": macd_cross,

        # MCDX / Banker
        "banker_norm": banker / 20.0,
        "hot_money_norm": hot_money / 20.0,
        "banker_vs_ma": np.clip(banker_vs_ma / 10.0, -1, 1),

        # Ichimoku
        "price_vs_cloud": price_vs_cloud,
        "dist_cloud_top": np.clip(dist_cloud_top_atr / 5.0, -2, 2),
        "dist_kijun": np.clip(dist_kijun_atr / 5.0, -2, 2),
        "dist_tenkan": np.clip(dist_tenkan_atr / 5.0, -2, 2),
        "price_vs_tenkan": price_vs_tenkan,
        "price_vs_kijun": price_vs_kijun,
        "tk_cross": tk_cross,
        "chikou_pos": chikou_pos,
        "cloud_thickness_pct": np.clip((cloud_top - cloud_bot) / max(price, 1.0) * 10.0, 0, 2),

        # Volume / Volatility
        "rel_vol": np.clip(rel_vol / 3.0, 0, 1),
        "vol_spike": vol_spike,
        "vol_dry": vol_dry,
        "atr_slope_sign": np.clip(atr_slope / safe_atr, -1, 1),

        # Heikin / 2Trend / TrendColor
        "ha_color": ha_color_num,
        "hk_trend": float(hk_trend),
        "t2_sma_score": np.clip(t2_sma_score / 50.0, -1, 1),
        "t2_st_score": np.clip(t2_st_score / 50.0, -1, 1),

        # Octopus
        "oct_color": oct_color_num,
        "oct_a1_sign": 1.0 if oct_a1 > 0 else -1.0,
        "oct_expanding": 1.0 if oct_a1 > oct_a1_prev else -1.0,

        # ADX + DI+/DI- relationship
        "adx_norm": np.clip(adx / 50.0, 0, 1),
        "adx_color": adx_num,
        "adx_vs_diplus": np.clip((adx - di_plus) / 50.0, -1, 1),
        "adx_vs_diminus": np.clip((adx - di_minus) / 50.0, -1, 1),
        "di_dominance": np.clip((di_plus - di_minus) / max(di_plus + di_minus + 0.001, 1.0), -1, 1),

        "dist_kijun65": np.clip(dist_kijun65_atr / 5.0, -2, 2),
        "dist_ma10": np.clip(dist_ma10_atr / 5.0, -2, 2),
        "dist_ma20": np.clip(dist_ma20_atr / 5.0, -2, 2),
        "dist_ma50": np.clip(dist_ma50_atr / 5.0, -2, 2),
        "ma_10_vs_20": ma_10_vs_20,
        "ma_20_vs_50": ma_20_vs_50,
        "ma_50_vs_100": ma_50_vs_100,
        "ma_100_vs_200": ma_100_vs_200,

        # Short-term momentum trend (1-2 sessions)
        "price_slope_1d": np.clip((price - prev_close) / safe_atr / 1.5, -1.0, 1.0),
        "price_slope_2d": np.clip((prev_close - prev2_close) / safe_atr / 1.5, -1.0, 1.0),
        "macd_slope": np.clip((macd - gp('MACD', macd)) / safe_atr * 5.0, -1.0, 1.0),
    }

    res.update(_calc_dynamic_features(col_arrays, idx, safe_atr))
    return res
def _vectorize(
    sv: dict,
    weight_config: dict[str, float] | None = None,
    feature_history: dict[str, np.ndarray] | None = None,
    idx: int | None = None,
) -> np.ndarray:
    """Convert state dict to numpy array with weight configuration and anomaly detection override."""
    if weight_config is None:
        weight_config = DEFAULT_WEIGHT_CONFIG

    anomalous = _detect_anomalous_features(sv, feature_history, idx, weight_config)

    # Maintain sorted key order
    keys = sorted(sv.keys())

    values = []
    for key in keys:
        raw = sv[key]

        if raw is None or (isinstance(raw, float) and raw != raw):
            raw = 0.0

        weight = FALLBACK_WEIGHT if key in anomalous else weight_config.get(key, 1.0)
        values.append(float(raw) * weight)

    return np.array(values, dtype=np.float64)
def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ─────────────────────────────────────────────────────────────
# PHASE 3 – SUPPORT / RESISTANCE ZONE ENGINE
# ─────────────────────────────────────────────────────────────

def detect_sr_zones(df: pd.DataFrame, n_recent: int = 250) -> list:
    """
    Detect Support/Resistance zones from the enriched DataFrame.
    Uses SwingHigh / SwingLow + MA levels + Ichimoku levels.
    Returns list of dicts sorted by price:
      {price, type, confidence, label, tolerance}
    """
    recent = df.tail(n_recent).copy()
    price = float(df['Close'].iloc[-1])
    atr = float(df['ATR14'].iloc[-1]) if 'ATR14' in df.columns else price * 0.01
    tolerance = max(atr * 0.5, price * 0.005)

    candidates = []

    # 1. SwingHigh → Resistance (Weight 2 for swing points)
    if 'SwingHigh' in recent.columns:
        sh = recent[recent['SwingHigh'] > 0]['SwingHigh'].values
        for v in sh:
            candidates.append({'price': float(v), 'type': 'resistance', 'hits': 2})

    # 2. SwingLow → Support (Weight 2 for swing points)
    if 'SwingLow' in recent.columns:
        sl = recent[recent['SwingLow'] > 0]['SwingLow'].values
        for v in sl:
            candidates.append({'price': float(v), 'type': 'support', 'hits': 2})

    # 3. Key MA levels with weights
    # Long-term (3): MA200, Kijun65
    # Medium-term (2): MA100, MA50, Kijun, CloudTop, CloudBottom
    # Short-term (1): MA20, Tenkan
    ma_weights = {
        'MA200': 3, 'Kijun65': 3,
        'MA100': 2, 'MA50': 2, 'Kijun': 2, 'CloudTop': 2, 'CloudBottom': 2,
        'MA20': 1, 'Tenkan': 1
    }

    for col, lbl in [('MA20', 'MA20'), ('MA50', 'MA50'), ('MA100', 'MA100'),
                     ('MA200', 'MA200'), ('Kijun', 'Kijun'), ('Kijun65', 'Kijun65'),
                     ('CloudTop', 'Cloud Top'), ('CloudBottom', 'Cloud Bottom'),
                     ('Tenkan', 'Tenkan')]:
        if col in df.columns:
            v = float(df[col].iloc[-1])
            if v > 0:
                t = 'resistance' if v > price else 'support'
                w = ma_weights.get(col, 1)
                candidates.append({'price': v, 'type': t, 'hits': w, 'label_override': lbl})

    # Cluster nearby candidates
    if not candidates:
        return []

    candidates.sort(key=lambda x: x['price'])
    zones = []
    used = [False] * len(candidates)

    for i, c in enumerate(candidates):
        if used[i]:
            continue
        cluster_prices = [c['price']]
        cluster_hits = c.get('hits', 1)
        cluster_type = c['type']
        label_override = c.get('label_override', '')

        for j in range(i + 1, len(candidates)):
            if used[j]:
                continue
            if abs(candidates[j]['price'] - c['price']) <= tolerance * 2:
                cluster_prices.append(candidates[j]['price'])
                cluster_hits += candidates[j].get('hits', 1)
                used[j] = True
                if candidates[j].get('label_override'):
                    label_override = candidates[j]['label_override']

        used[i] = True
        zone_price = float(np.mean(cluster_prices))
        confidence = min(100, cluster_hits * 12)  # Adjust scaling for new weights
        is_confluence = cluster_hits >= 3

        zones.append({
            'price': zone_price,
            'type': cluster_type,
            'confidence': confidence,
            'tolerance': round(tolerance, 2),
            'label': label_override or (f"S/R {zone_price:.1f}"),
            'hits': cluster_hits,
            'is_confluence': is_confluence,
        })

    # Separate and re-assign type by proximity to current price
    for z in zones:
        z['type'] = 'resistance' if z['price'] > price else 'support'
        z['distance_pct'] = round((z['price'] - price) / price * 100, 2)

    zones.sort(key=lambda x: x['price'])
    return zones


# ─────────────────────────────────────────────────────────────
# PHASE 4 + 5 – HISTORICAL ANALOG + STATE MATCHING
# ─────────────────────────────────────────────────────────────

def build_state_vector_fast(col_arrays: dict, idx: int, n: int) -> dict:
    if idx < 0:
        idx = n + idx
    
    prev_idx = idx - 1 if idx > 0 else idx
    prev2_idx = idx - 2 if idx > 1 else prev_idx
    chikou_idx = idx - 26 if idx >= 26 else idx

    def g(col, default=0.0):
        val = col_arrays[col][idx]
        if val != val or val is None:
            return default
        return float(val)

    def gp(col, default=0.0):
        val = col_arrays[col][prev_idx]
        if val != val or val is None:
            return default
        return float(val)

    rsi = g('RSI', 50.0)
    rsi_prev = gp('RSI', 50.0)
    rsi_prev2 = float(col_arrays['RSI'][prev2_idx]) if prev2_idx >= 0 else rsi_prev

    macd = g('MACD')
    macd_sig = g('MACD_Signal')
    macd_hist = g('MACD_Hist')
    macd_hist_prev = gp('MACD_Hist')

    price = g('Close', 1.0)
    prev_close = gp('Close', price)
    prev2_close = float(col_arrays['Close'][prev2_idx]) if prev2_idx >= 0 else prev_close

    ma10 = g('MA10', price)
    ma20 = g('MA20', price)
    ma50 = g('MA50', price)
    ma100 = g('MA100', price)
    ma200 = g('MA200', price)

    atr = g('ATR14', 1.0)
    atr_slope = g('ATR14_Slope', 0.0)

    cloud_top = g('CloudTop', price)
    cloud_bot = g('CloudBottom', price)
    tenkan = g('Tenkan', price)
    kijun = g('Kijun', price)
    kijun65 = g('Kijun65', price)

    oct_a1 = g('OCT_A1', 0.0)
    oct_a1_prev = gp('OCT_A1', 0.0)

    banker = g('MCDX_Banker', 10.0)
    hot_money = g('MCDX_HotMoney', 10.0)
    banker_ma = g('MCDX_Banker_MA', 10.0)

    vol = g('Volume', 0.0)
    avg_vol20 = g('AvgVolume20', 1.0)

    oct_color_raw = str(col_arrays['OCT_Color'][idx])
    oct_color_num = (1.0 if '#00FF00' in oct_color_raw
                     else 0.5 if '#008000' in oct_color_raw
                     else -0.5 if '#FF69B4' in oct_color_raw
                     else -1.0)

    ha_color_raw = str(col_arrays['HA_Color'][idx])
    ha_color_num = 1.0 if 'Green' in ha_color_raw else -1.0

    hk_trend = g('HK_Trend', 0.0)

    t2_sma_score = g('T2_SMA_Score', 0.0)
    t2_st_score = g('T2_ST_Score', 0.0)

    adx = g('ADX', 0.0)
    di_plus = g('DI_Plus', 0.0)
    di_minus = g('DI_Minus', 0.0)
    adx_raw = str(col_arrays['ADX_Color'][idx]).upper()
    adx_num = (1.0 if adx_raw == 'WHITE' else
               0.5 if adx_raw == 'GREEN' else
               -1.0 if adx_raw == 'RED' else 0.0)

    chikou_val = float(col_arrays['Close'][chikou_idx])
    chikou_pos = 1.0 if price > chikou_val else -1.0

    if rsi < 30:
        rsi_zone = -2.0
    elif rsi < 50:
        rsi_zone = -1.0
    elif rsi < 70:
        rsi_zone = 1.0
    else:
        rsi_zone = 2.0

    if price > cloud_top:
        price_vs_cloud = 1.0
    elif price >= cloud_bot:
        price_vs_cloud = 0.0
    else:
        price_vs_cloud = -1.0

    safe_atr = max(atr, 0.0001)
    dist_cloud_top_atr = (price - cloud_top) / safe_atr
    dist_kijun_atr = (price - kijun) / safe_atr
    dist_tenkan_atr = (price - tenkan) / safe_atr
    dist_kijun65_atr = (price - kijun65) / safe_atr
    dist_ma10_atr = (price - ma10) / safe_atr
    dist_ma20_atr = (price - ma20) / safe_atr
    dist_ma50_atr = (price - ma50) / safe_atr

    ma_10_vs_20 = 1.0 if ma10 > ma20 else -1.0
    ma_20_vs_50 = 1.0 if ma20 > ma50 else -1.0
    ma_50_vs_100 = 1.0 if ma50 > ma100 else -1.0
    ma_100_vs_200 = 1.0 if ma100 > ma200 else -1.0

    price_vs_tenkan = 1.0 if price > tenkan else -1.0
    price_vs_kijun = 1.0 if price > kijun else -1.0

    rsi_slope = rsi - rsi_prev
    rsi_accel = (rsi - rsi_prev) - (rsi_prev - rsi_prev2)
    macd_hist_slope = macd_hist - macd_hist_prev

    gp_macd = gp('MACD', 0)
    gp_macd_sig = gp('MACD_Signal', 0)
    macd_cross = 1.0 if (macd > macd_sig and gp_macd <= gp_macd_sig) else 0.0

    rel_vol = vol / max(avg_vol20, 1.0)
    vol_spike = 1.0 if rel_vol > 1.5 else 0.0
    vol_dry = 1.0 if rel_vol < 0.7 else 0.0

    banker_vs_ma = banker - banker_ma

    tk_cross = 1.0 if (tenkan > kijun and gp('Tenkan', tenkan) <= gp('Kijun', kijun)) else 0.0

    res = {
        "rsi": rsi / 100.0,
        "rsi_zone": rsi_zone / 2.0,
        "rsi_slope": np.clip(rsi_slope / 20.0, -1, 1),
        "rsi_accel": np.clip(rsi_accel / 10.0, -1, 1),
        "macd_hist": np.clip(macd_hist / max(abs(macd_hist) + 0.001, 1.0), -1, 1),
        "macd_hist_slope": np.clip(macd_hist_slope / max(abs(macd_hist_slope) + 0.001, 1.0), -1, 1),
        "macd_vs_signal": np.clip((macd - macd_sig) / safe_atr, -2, 2),
        "macd_cross": macd_cross,
        "banker_norm": banker / 20.0,
        "hot_money_norm": hot_money / 20.0,
        "banker_vs_ma": np.clip(banker_vs_ma / 10.0, -1, 1),
        "price_vs_cloud": price_vs_cloud,
        "dist_cloud_top": np.clip(dist_cloud_top_atr / 5.0, -2, 2),
        "dist_kijun": np.clip(dist_kijun_atr / 5.0, -2, 2),
        "dist_tenkan": np.clip(dist_tenkan_atr / 5.0, -2, 2),
        "price_vs_tenkan": price_vs_tenkan,
        "price_vs_kijun": price_vs_kijun,
        "tk_cross": tk_cross,
        "chikou_pos": chikou_pos,
        "cloud_thickness_pct": np.clip((cloud_top - cloud_bot) / max(price, 1.0) * 10.0, 0, 2),
        "rel_vol": np.clip(rel_vol / 3.0, 0, 1),
        "vol_spike": vol_spike,
        "vol_dry": vol_dry,
        "atr_slope_sign": np.clip(atr_slope / safe_atr, -1, 1),
        "ha_color": ha_color_num,
        "hk_trend": float(hk_trend),
        "t2_sma_score": np.clip(t2_sma_score / 50.0, -1, 1),
        "t2_st_score": np.clip(t2_st_score / 50.0, -1, 1),
        "oct_color": oct_color_num,
        "oct_a1_sign": 1.0 if oct_a1 > 0 else -1.0,
        "oct_expanding": 1.0 if oct_a1 > oct_a1_prev else -1.0,
        "adx_norm": np.clip(adx / 50.0, 0, 1),
        "adx_color": adx_num,
        "adx_vs_diplus": np.clip((adx - di_plus) / 50.0, -1, 1),
        "adx_vs_diminus": np.clip((adx - di_minus) / 50.0, -1, 1),
        "di_dominance": np.clip((di_plus - di_minus) / max(di_plus + di_minus + 0.001, 1.0), -1, 1),
        "dist_kijun65": np.clip(dist_kijun65_atr / 5.0, -2, 2),
        "dist_ma10": np.clip(dist_ma10_atr / 5.0, -2, 2),
        "dist_ma20": np.clip(dist_ma20_atr / 5.0, -2, 2),
        "dist_ma50": np.clip(dist_ma50_atr / 5.0, -2, 2),
        "ma_10_vs_20": ma_10_vs_20,
        "ma_20_vs_50": ma_20_vs_50,
        "ma_50_vs_100": ma_50_vs_100,
        "ma_100_vs_200": ma_100_vs_200,
        "price_slope_1d": np.clip((price - prev_close) / safe_atr / 1.5, -1.0, 1.0),
        "price_slope_2d": np.clip((prev_close - prev2_close) / safe_atr / 1.5, -1.0, 1.0),
        "macd_slope": np.clip((macd - gp('MACD', macd)) / safe_atr * 5.0, -1.0, 1.0),
    }

    res.update(_calc_dynamic_features(col_arrays, idx, safe_atr))
    return res
def _select_diverse_matches(tiers: dict[int, list]) -> list:
    """
    Select matches with temporal diversity.
    Ensures we don't pick adjacent historical sessions (from the same historical trend period).
    
    Pass 1: Go through Tiers 1, 2, 3 (already sorted descending by similarity).
            Pick matches that are at least MIN_MATCH_GAP_SESSIONS (5) sessions apart
            from already selected matches. Stop if we reach MAX_MATCHES_RETURN (30).
    Pass 2: If we have fewer than MIN_MATCHES_TARGET (20) matches, fill from the remaining
            non-selected candidates in Tiers 1, 2, 3 (relaxed gap requirement) in descending similarity.
            Stop if we reach MIN_MATCHES_TARGET.
    Pass 3 (Tier 4): If still fewer than MIN_MATCHES_TARGET, fill from Tier 4 candidates.
            First apply the gap constraint.
            If still fewer than MIN_MATCHES_TARGET, relax the gap constraint for Tier 4.
    """
    selected = []
    selected_indices = set()

    def is_far_enough(idx):
        for s_idx in selected_indices:
            if abs(idx - s_idx) < MIN_MATCH_GAP_SESSIONS:
                return False
        return True

    # Ensure all lists are sorted descending by similarity
    for t in tiers:
        tiers[t].sort(key=lambda x: x['similarity'], reverse=True)

    # Pass 1: Tiers 1, 2, 3 with gap constraint
    remaining_t123 = []
    for t in [1, 2, 3]:
        for m in tiers[t]:
            if is_far_enough(m['idx']):
                selected.append(m)
                selected_indices.add(m['idx'])
                if len(selected) >= MAX_MATCHES_RETURN:
                    break
            else:
                remaining_t123.append(m)
        if len(selected) >= MAX_MATCHES_RETURN:
            break

    # Pass 2: Relaxed fill for Tiers 1, 2, 3
    if len(selected) < MIN_MATCHES_TARGET:
        for m in remaining_t123:
            if len(selected) >= MIN_MATCHES_TARGET:
                break
            selected.append(m)
            selected_indices.add(m['idx'])

    # Pass 3: Tier 4 with gap constraint first, then relaxed
    if len(selected) < MIN_MATCHES_TARGET:
        remaining_t4 = []
        for m in tiers[4]:
            if is_far_enough(m['idx']):
                selected.append(m)
                selected_indices.add(m['idx'])
                if len(selected) >= MIN_MATCHES_TARGET:
                    break
            else:
                remaining_t4.append(m)
        
        # If still short, relax gap for Tier 4
        if len(selected) < MIN_MATCHES_TARGET:
            for m in remaining_t4:
                if len(selected) >= MIN_MATCHES_TARGET:
                    break
                selected.append(m)
                selected_indices.add(m['idx'])

    # Keep descending similarity order
    selected.sort(key=lambda x: x['similarity'], reverse=True)
    return selected


def _calc_temporal_diversity(matches: list) -> dict:
    """
    Evaluate how temporally diverse the matches are.
    Returns a dict with:
      - num_clusters: number of unique historical episodes/clusters (grouping matches with idx within 10 sessions).
      - span_sessions: max(idx) - min(idx)
      - diversity_score: num_clusters / len(matches) if matches else 1.0
      - warning: warning message if diversity is low (e.g. fewer than 3 unique clusters)
    """
    if not matches:
        return {
            'num_clusters': 0,
            'span_sessions': 0,
            'diversity_score': 1.0,
            'warning': None
        }
    
    indices = sorted([m['idx'] for m in matches if 'idx' in m])
    if not indices:
        return {
            'num_clusters': 0,
            'span_sessions': 0,
            'diversity_score': 1.0,
            'warning': None
        }
    
    # Cluster matching indices with a gap of <= 10 sessions
    clusters = 0
    last_idx = -9999
    for idx in indices:
        if idx - last_idx > 10:
            clusters += 1
        last_idx = idx
        
    span = indices[-1] - indices[0]
    div_score = round(clusters / len(matches), 2)
    
    warning = None
    if clusters < 3:
        warning = f"Độ đa dạng lịch sử thấp: chỉ khớp với {clusters} giai đoạn lịch sử khác nhau. Kết quả có thể bị thiên kiến."
        
    return {
        'num_clusters': clusters,
        'span_sessions': span,
        'diversity_score': div_score,
        'warning': warning
    }


def find_historical_matches(df: pd.DataFrame,
                             current_vec: np.ndarray,
                             lookback_warmup: int = 100,
                             top_n: int = 30,
                             target_idx: int = -1,
                             all_state_vectors: list = None,
                             feature_history: dict = None,
                             col_arrays: dict = None,
                             strict_cloud: bool = True,
                             all_hist_vec_combined: list = None) -> list:
    """
    Compare current state vector against ALL historical rows.
    Returns top_n most similar historical periods with their outcomes.

    Each match: {date, similarity, idx, future_3, future_5, future_10}
    future_N = % change of Close after N sessions from match point
    """
    if len(df) < lookback_warmup + 5:
        return []

    matches = []
    all_candidates_raw = []
    n = len(df)

    if target_idx == -1:
        target_idx = n - 1

    # We need at least 20 bars ahead for outcome
    max_idx = target_idx - 21
    if max_idx < lookback_warmup:
        max_idx = target_idx - 11

    # Build col_arrays ONCE
    if col_arrays is None:
        col_arrays = _build_col_arrays(df)

    # Generate all state vectors first to build feature_history
    if all_state_vectors is None:
        all_state_vectors = [build_state_vector_fast(col_arrays, i, n) for i in range(n)]

    if feature_history is None:
        feature_history = {}
        for key in DEFAULT_WEIGHT_CONFIG:
            feature_history[key] = np.array([sv.get(key, np.nan) for sv in all_state_vectors], dtype=np.float64)

    # Build current trajectory state vectors with correct feature history & idx
    if all_hist_vec_combined is not None:
        curr_vec_combined = all_hist_vec_combined[target_idx]
    else:
        curr_vec_0 = _vectorize(all_state_vectors[target_idx], feature_history=feature_history, idx=target_idx)
        curr_vec_1 = _vectorize(all_state_vectors[target_idx - 1], feature_history=feature_history, idx=target_idx - 1) if target_idx >= 1 else curr_vec_0
        curr_vec_2 = _vectorize(all_state_vectors[target_idx - 2], feature_history=feature_history, idx=target_idx - 2) if target_idx >= 2 else curr_vec_1
        curr_vec_combined = np.concatenate([curr_vec_0, curr_vec_1, curr_vec_2])

    # ── Tính 1 lần trước vòng lặp ───────────────────────────────────
    def get_order(p, m1, m2):
        return (p > m1, m1 > m2, p > m2)

    curr_price_vs_cloud = all_state_vectors[target_idx]['price_vs_cloud']
    _curr_atr = float(col_arrays['ATR14'][target_idx])
    _safe_curr_atr = _curr_atr if _curr_atr == _curr_atr and _curr_atr > 0 else 1.0
    _curr_close     = float(col_arrays['Close'][target_idx])
    _curr_cloud_top    = float(col_arrays['CloudTop'][target_idx])
    _curr_cloud_bottom = float(col_arrays['CloudBottom'][target_idx])
    _dist_curr_cloud = min(
        abs(_curr_close - _curr_cloud_top),
        abs(_curr_close - _curr_cloud_bottom)
    ) / _safe_curr_atr
    curr_in_transition = _dist_curr_cloud <= 0.5

    curr_price   = float(col_arrays['Close'][target_idx])
    curr_kijun   = float(col_arrays['Kijun'][target_idx])
    curr_kijun65 = float(col_arrays['Kijun65'][target_idx])
    curr_ma20    = float(col_arrays['MA20'][target_idx])
    curr_ma50    = float(col_arrays['MA50'][target_idx])
    curr_k_order  = get_order(curr_price, curr_kijun, curr_kijun65)
    curr_ma_order = get_order(curr_price, curr_ma20, curr_ma50)
    # ────────────────────────────────────────────────────────────────

    for i in range(lookback_warmup, max_idx):
        try:
            # Trajectory matching: get vectors for day i, i-1, and i-2 with correct idx & history
            if all_hist_vec_combined is not None:
                hist_vec_combined = all_hist_vec_combined[i]
            else:
                hist_vec_0 = _vectorize(all_state_vectors[i], feature_history=feature_history, idx=i)
                hist_vec_1 = _vectorize(all_state_vectors[i - 1], feature_history=feature_history, idx=i - 1) if i >= 1 else hist_vec_0
                hist_vec_2 = _vectorize(all_state_vectors[i - 2], feature_history=feature_history, idx=i - 2) if i >= 2 else hist_vec_1
                hist_vec_combined = np.concatenate([hist_vec_0, hist_vec_1, hist_vec_2])

            # Combined trajectory similarity (Concatenated 3-session vector)
            sim = _cosine_sim(curr_vec_combined, hist_vec_combined)

            base_price = float(col_arrays['Close'][i])
            if base_price <= 0:
                continue

            # ── Check same state price vs cloud ──────────────────────────────
            hist_price_vs_cloud = all_state_vectors[i]['price_vs_cloud']
            is_same_cloud_state = False
            if hist_price_vs_cloud == curr_price_vs_cloud:
                is_same_cloud_state = True
            else:
                _hist_atr = float(col_arrays['ATR14'][i])
                _safe_hist_atr = _hist_atr if _hist_atr == _hist_atr and _hist_atr > 0 else 1.0
                _hist_close       = float(col_arrays['Close'][i])
                _hist_cloud_top    = float(col_arrays['CloudTop'][i])
                _hist_cloud_bottom = float(col_arrays['CloudBottom'][i])
                _dist_hist_cloud = min(
                    abs(_hist_close - _hist_cloud_top),
                    abs(_hist_close - _hist_cloud_bottom)
                ) / _safe_hist_atr
                hist_in_transition = _dist_hist_cloud <= 0.5
                if curr_in_transition and hist_in_transition:
                    is_same_cloud_state = True


            all_candidates_raw.append({
                'idx': i,
                'sim': sim,
                'base_price': base_price
            })

            tier = _classify_tier(sim)
            if tier is None:
                continue

            # ── Hard Criteria: MA/Kijun order ───────────────────────────────
            kijun_i   = float(col_arrays['Kijun'][i])
            kijun65_i = float(col_arrays['Kijun65'][i])
            ma20_i    = float(col_arrays['MA20'][i])
            ma50_i    = float(col_arrays['MA50'][i])

            hist_k_order  = get_order(base_price, kijun_i, kijun65_i)
            hist_ma_order = get_order(base_price, ma20_i, ma50_i)

            if (hist_k_order != curr_k_order) and (hist_ma_order != curr_ma_order):
                continue


            def future_ret(days):
                target_idx = i + days
                if target_idx >= n:
                    return None
                fp = float(col_arrays['Close'][target_idx])
                return round((fp - base_price) / base_price * 100, 2)

            try:
                date_val = df['Date'].iloc[i]
                date_str = (date_val.strftime('%Y-%m-%d')
                            if hasattr(date_val, 'strftime') else str(date_val))
            except Exception:
                date_str = str(i)

            # Weight based on similarity, recency, and tier multiplier
            dist = n - 1 - i
            w_sim = np.exp((sim - 1.0) / 0.1)
            w_rec = np.exp(-dist / 1000)
            tier_mult = TIER_MULTIPLIERS[tier]
            weight = float(w_sim * w_rec * tier_mult)
            if is_same_cloud_state:
                weight = weight * KUMO_SAME_STATE_BOOST

            matches.append({
                'date': date_str,
                'idx': i,
                'similarity': round(sim, 4),
                'future_3': future_ret(3),
                'future_5': future_ret(5),
                'future_10': future_ret(10),
                'base_price': round(base_price, 2),
                'weight': round(weight, 6),
                'tier': tier,
                'tier_label': TIER_LABELS[tier]
            })
        except Exception:
            continue

    if len(matches) < 3:
        if not strict_cloud and all_candidates_raw:
            matches = [] # Clear existing to replace with top 3 raw
            all_candidates_raw.sort(key=lambda x: x['sim'], reverse=True)
            for cand in all_candidates_raw[:3]:
                i = cand['idx']
                sim = cand['sim']
                base_price = cand['base_price']
                tier = 4
                
                def future_ret_fallback(days):
                    t_idx = i + days
                    if t_idx >= n:
                        return None
                    fp = float(col_arrays['Close'][t_idx])
                    return round((fp - base_price) / base_price * 100, 2)
                    
                try:
                    date_val = df['Date'].iloc[i]
                    date_str = (date_val.strftime('%Y-%m-%d')
                                if hasattr(date_val, 'strftime') else str(date_val))
                except Exception:
                    date_str = str(i)
                    
                # ── Check same state price vs cloud for fallback ───────────────────
                hist_price_vs_cloud = all_state_vectors[i]['price_vs_cloud']
                is_same_cloud_state = False
                if hist_price_vs_cloud == curr_price_vs_cloud:
                    is_same_cloud_state = True
                else:
                    _hist_atr = float(col_arrays['ATR14'][i])
                    _safe_hist_atr = _hist_atr if _hist_atr == _hist_atr and _hist_atr > 0 else 1.0
                    _hist_close       = float(col_arrays['Close'][i])
                    _hist_cloud_top    = float(col_arrays['CloudTop'][i])
                    _hist_cloud_bottom = float(col_arrays['CloudBottom'][i])
                    _dist_hist_cloud = min(
                        abs(_hist_close - _hist_cloud_top),
                        abs(_hist_close - _hist_cloud_bottom)
                    ) / _safe_hist_atr
                    hist_in_transition = _dist_hist_cloud <= 0.5
                    if curr_in_transition and hist_in_transition:
                        is_same_cloud_state = True

                dist = n - 1 - i
                w_sim = np.exp((sim - 1.0) / 0.1)
                w_rec = np.exp(-dist / 1000)
                tier_mult = TIER_MULTIPLIERS[tier]
                weight = float(w_sim * w_rec * tier_mult)
                if is_same_cloud_state:
                    weight = weight * KUMO_SAME_STATE_BOOST
                
                matches.append({
                    'date': date_str,
                    'idx': i,
                    'similarity': round(sim, 4),
                    'future_3': future_ret_fallback(3),
                    'future_5': future_ret_fallback(5),
                    'future_10': future_ret_fallback(10),
                    'base_price': round(base_price, 2),
                    'weight': round(weight, 6),
                    'tier': tier,
                    'tier_label': TIER_LABELS[tier]
                })
        else:
            return matches

    # 2. Separate by tier
    tiers = {t: [] for t in [1, 2, 3, 4]}
    for m in matches:
        tiers[m['tier']].append(m)

    # 3. Select matches using diversity-aware selection
    result = _select_diverse_matches(tiers)

    return result
def calculate_outcome_distribution(matches: list) -> dict:
    """
    Given top historical matches, calculate the ACTUAL distribution of
    price changes after 3, 5, 10, 20 sessions.
    Uses weight coefficients for matches.

    Returns per-horizon stats: mean, median, std, pct_positive, pct_negative,
    pct_sideways, percentiles.
    Sideways = within ±0.2% of base price.
    """
    result = {}
    
    # Calculate tier summary once
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for m in matches:
        t = m.get('tier')
        if t in counts:
            counts[t] += 1
    used_tiers = [t for t, c in counts.items() if c > 0]
    dominant_tier = max(used_tiers) if used_tiers else 4
    avg_sim = float(np.mean([m['similarity'] for m in matches])) if matches else 0.0
    
    temporal_div = _calc_temporal_diversity(matches)
    
    warnings_list = []
    best_tier = min(used_tiers) if used_tiers else 4
    num_high_quality = sum(1 for m in matches if m.get('tier', 4) <= 3)
    num_tier12 = sum(1 for m in matches if m.get('tier', 4) <= 2)

    if len(matches) < 10 or num_tier12 < 2:
        warnings_list.append("Mức độ tin cậy thấp: Số phiên tương đồng (>75%) ít hơn 10 phiên HOẶC số phiên tương đồng cao (>80%) ít hơn 2 phiên.")
    if temporal_div.get('warning'):
        warnings_list.append(temporal_div['warning'])
        
    warning_str = " | ".join(warnings_list) if warnings_list else None

    tier_summary = {
        'dominant_tier': dominant_tier,
        'confidence_label': CONFIDENCE_LABELS[dominant_tier],
        'tier_1_count': counts[1],
        'tier_2_count': counts[2],
        'tier_3_count': counts[3],
        'tier_4_count': counts[4],
        'avg_similarity': round(avg_sim, 4),
        'should_trust': dominant_tier <= 2,
        'warning': warning_str,
        'temporal_diversity': temporal_div
    }

    for horizon_key in ['future_3', 'future_5', 'future_10']:
        label_map = {
            'future_3': '3 phiên',
            'future_5': '5 phiên',
            'future_10': '10 phiên',
        }
        pairs = [(m[horizon_key], m.get('weight', 1.0)) for m in matches if m.get(horizon_key) is not None]
        if not pairs:
            result[horizon_key] = {'label': label_map[horizon_key], 'n': 0, 'tier_summary': tier_summary}
            continue

        arr = np.array([p[0] for p in pairs])
        weights = np.array([p[1] for p in pairs])
        sum_weights = np.sum(weights)
        if sum_weights <= 0:
            weights = np.ones_like(weights)
            sum_weights = np.sum(weights)

        threshold = 0.2  # ±0.2% considered sideways
        pos_mask = arr > threshold
        neg_mask = arr < -threshold
        sum_w_pos = np.sum(weights[pos_mask])
        sum_w_neg = np.sum(weights[neg_mask])

        w_mean_up = round(float(np.sum(arr[pos_mask] * weights[pos_mask]) / sum_w_pos), 2) if sum_w_pos > 0 else 0.0
        w_mean_down = round(float(np.sum(arr[neg_mask] * weights[neg_mask]) / sum_w_neg), 2) if sum_w_neg > 0 else 0.0

        pct_up = round(float(np.sum(weights[pos_mask]) / sum_weights * 100), 1)
        pct_down = round(float(np.sum(weights[neg_mask]) / sum_weights * 100), 1)
        pct_side = round(100.0 - pct_up - pct_down, 1)

        # Weighted bracket percentages
        bracket_huge_up = round(float(np.sum(weights[arr > 10.0]) / sum_weights * 100), 1)
        bracket_up = round(float(np.sum(weights[(arr >= 3.0) & (arr <= 10.0)]) / sum_weights * 100), 1)
        bracket_sideways = round(float(np.sum(weights[(arr > -3.0) & (arr < 3.0)]) / sum_weights * 100), 1)
        bracket_down = round(float(np.sum(weights[(arr >= -10.0) & (arr <= -3.0)]) / sum_weights * 100), 1)
        bracket_huge_down = round(float(np.sum(weights[arr < -10.0]) / sum_weights * 100), 1)

        # Weighted mean
        w_mean = round(float(np.sum(arr * weights) / sum_weights), 2)

        # Weighted percentiles
        def get_w_percentile(pct):
            sorter = np.argsort(arr)
            s_arr = arr[sorter]
            s_w = weights[sorter]
            cum_w = np.cumsum(s_w)
            cum_w /= cum_w[-1]
            return round(float(np.interp(pct / 100.0, cum_w, s_arr)), 2)

        w_median = get_w_percentile(50)
        w_p10 = get_w_percentile(10)
        w_p25 = get_w_percentile(25)
        w_p75 = get_w_percentile(75)
        w_p90 = get_w_percentile(90)

        # Weighted standard deviation
        mean_diff = arr - (np.sum(arr * weights) / sum_weights)
        w_std = round(float(np.sqrt(np.sum(weights * (mean_diff ** 2)) / sum_weights)), 2)

        result[horizon_key] = {
            'label': label_map[horizon_key],
            'n': len(pairs),
            'mean': w_mean,
            'median': w_median,
            'std': w_std,
            'pct_up': pct_up,
            'pct_down': pct_down,
            'pct_sideways': pct_side,
            'mean_up': w_mean_up,
            'mean_down': w_mean_down,
            'bracket_huge_up': bracket_huge_up,
            'bracket_up': bracket_up,
            'bracket_sideways': bracket_sideways,
            'bracket_down': bracket_down,
            'bracket_huge_down': bracket_huge_down,
            'p10': w_p10,
            'p25': w_p25,
            'p75': w_p75,
            'p90': w_p90,
            'best': round(float(np.max(arr)), 2),
            'worst': round(float(np.min(arr)), 2),
            'values': arr.tolist(),
            'tier_summary': tier_summary
        }
    return result
def analyze_sr_reactions(df: pd.DataFrame, zones: list) -> list:
    """
    For each zone, analyze historical behavior when price approached the zone.
    Approach = price comes within tolerance of zone price.

    Returns zones with added reaction stats:
      {bounce_pct, break_pct, false_break_pct, n_tests}
    """
    enriched_zones = []
    n = len(df)
    close_arr = df['Close'].values
    high_arr = df['High'].values
    low_arr = df['Low'].values

    for zone in zones:
        z_price = zone['price']
        z_tol = zone['tolerance']
        z_type = zone['type']

        tests = []
        i = 20  # skip warmup
        while i < n - 5:
            price_i = close_arr[i]
            touched = False

            if z_type == 'support':
                # Price approached from above
                touched = (low_arr[i] <= z_price + z_tol) and (close_arr[max(0, i-2)] > z_price + z_tol)
            else:
                # Price approached from below
                touched = (high_arr[i] >= z_price - z_tol) and (close_arr[max(0, i-2)] < z_price - z_tol)

            if touched:
                # Outcome after 3 sessions
                future_close = close_arr[min(i + 3, n - 1)]
                if z_type == 'support':
                    if future_close > z_price + z_tol:
                        outcome = 'bounce'
                    elif future_close < z_price - z_tol:
                        outcome = 'break'
                    else:
                        outcome = 'false_break'
                else:
                    if future_close > z_price + z_tol:
                        outcome = 'break'
                    elif future_close < z_price - z_tol:
                        outcome = 'reject'
                    else:
                        outcome = 'stall'

                tests.append(outcome)
                i += 5  # skip overlap
            else:
                i += 1

        n_tests = len(tests)
        if n_tests > 0:
            if zone['type'] == 'support':
                bounce_pct = round(tests.count('bounce') / n_tests * 100, 1)
                break_pct = round(tests.count('break') / n_tests * 100, 1)
                false_pct = round(tests.count('false_break') / n_tests * 100, 1)
                reaction = {'bounce_pct': bounce_pct, 'break_pct': break_pct,
                            'false_break_pct': false_pct, 'n_tests': n_tests}
            else:
                reject_pct = round(tests.count('reject') / n_tests * 100, 1)
                break_pct = round(tests.count('break') / n_tests * 100, 1)
                stall_pct = round(tests.count('stall') / n_tests * 100, 1)
                reaction = {'reject_pct': reject_pct, 'break_pct': break_pct,
                            'stall_pct': stall_pct, 'n_tests': n_tests}
        else:
            reaction = {'n_tests': 0}

        enriched_zones.append({**zone, **reaction})

    return enriched_zones


# ─────────────────────────────────────────────────────────────
# PHASE 8 – WHAT-IF SCENARIO TREE
# ─────────────────────────────────────────────────────────────

def build_scenario_tree(current_price: float,
                        zones: list,
                        dist: dict) -> dict:
    """
    Construct a dynamic What-If Scenario Tree mapping Main (consensus) and
    Alternative paths and their branching decisions based on nearby Support/Resistance zones.
    """
    # Separate zones
    supports = sorted([z for z in zones if z['type'] == 'support'], key=lambda x: x['price'], reverse=True)
    resistances = sorted([z for z in zones if z['type'] == 'resistance'], key=lambda x: x['price'])

    # Primary direction from 5-session distribution (analog matching outcomes)
    consensus = calculate_consensus_direction(dist)
    main_down = not consensus['is_bullish']
    d5 = dist.get('future_5', {})
    pct_up_5   = d5.get('pct_up', 50)
    pct_down_5 = d5.get('pct_down', 50)
    main_prob  = max(pct_up_5, pct_down_5)

    # Nearest S/R
    nearest_support = supports[0] if supports else None
    second_support = supports[1] if len(supports) > 1 else None
    nearest_resistance = resistances[0] if resistances else None
    second_resistance = resistances[1] if len(resistances) > 1 else None

    # Helper zone label
    def _zone_label(z):
        if not z:
            return "Vùng trống"
        lbl = z.get('label', '')
        if 'S/R' in lbl:
            return f"vùng {lbl}"
        return lbl

    def _zone_price(z, fallback):
        return round(z['price'], 2) if z else round(fallback, 2)

    if not main_down:
        # Main Path: bullish expansion
        main_confidence = round(pct_up_5, 1)
        main_direction = "Tăng hướng lên"
        main_target = nearest_resistance

        # Branching at resistance
        if nearest_resistance:
            break_p_res = nearest_resistance.get('break_pct', 45)
            reject_p_res = nearest_resistance.get('reject_pct', 40)
            branch_break_res = {
                'condition': f"Nếu VƯỢT vùng {_zone_label(nearest_resistance)}",
                'probability': round((main_confidence * break_p_res) / 100.0, 1),
                'direction': 'Tăng tiếp',
                'target': _zone_label(second_resistance),
                'target_price': _zone_price(second_resistance, current_price * 1.08),
            }
            branch_reject_res = {
                'condition': f"Nếu BỊ CHẶN tại {_zone_label(nearest_resistance)}",
                'probability': round((main_confidence * reject_p_res) / 100.0, 1),
                'direction': 'Điều chỉnh về',
                'target': _zone_label(nearest_support),
                'target_price': _zone_price(nearest_support, current_price * 0.96),
            }
        else:
            branch_break_res = branch_reject_res = None

        main_path = {
            'probability': main_confidence,
            'direction': main_direction,
            'target': _zone_label(main_target),
            'target_price': _zone_price(main_target, current_price * 1.04),
            'branches': [b for b in [branch_break_res, branch_reject_res] if b],
        }

        # Alt Path: pullback
        alt_prob = round(pct_down_5, 1)
        if nearest_support:
            bounce_p = nearest_support.get('bounce_pct', 55)
            break_p = nearest_support.get('break_pct', 30)
            branch_hold = {
                'condition': f"Nếu GIỮ vùng {_zone_label(nearest_support)}",
                'probability': round((alt_prob * bounce_p) / 100.0, 1),
                'direction': 'Bật lại lên',
                'target': _zone_label(nearest_resistance),
                'target_price': _zone_price(nearest_resistance, current_price * 1.04),
            }
            branch_break = {
                'condition': f"Nếu PHÁ vùng {_zone_label(nearest_support)}",
                'probability': round((alt_prob * break_p) / 100.0, 1),
                'direction': 'Rơi tiếp',
                'target': _zone_label(second_support),
                'target_price': _zone_price(second_support, current_price * 0.92),
            }
            alt_branches = [branch_hold, branch_break]
        else:
            alt_branches = []

        alt_path = {
            'probability': alt_prob,
            'direction': 'Điều chỉnh về',
            'target': _zone_label(nearest_support),
            'target_price': _zone_price(nearest_support, current_price * 0.96),
            'branches': alt_branches,
        }

    else:
        # Main Path: bearish breakdown
        main_confidence = round(pct_down_5, 1)
        main_direction = "Điều chỉnh về"
        main_target = nearest_support

        # Branching at support
        if nearest_support:
            bounce_p_sup = nearest_support.get('bounce_pct', 55)
            break_p_sup = nearest_support.get('break_pct', 35)
            branch_hold_sup = {
                'condition': f"Nếu GIỮ vùng {_zone_label(nearest_support)}",
                'probability': round((main_confidence * bounce_p_sup) / 100.0, 1),
                'direction': 'Bật lại lên',
                'target': _zone_label(nearest_resistance),
                'target_price': _zone_price(nearest_resistance, current_price * 1.04),
            }
            branch_break_sup = {
                'condition': f"Nếu PHÁ vùng {_zone_label(nearest_support)}",
                'probability': round((main_confidence * break_p_sup) / 100.0, 1),
                'direction': 'Rơi tiếp',
                'target': _zone_label(second_support),
                'target_price': _zone_price(second_support, current_price * 0.92),
            }
        else:
            branch_hold_sup = branch_break_sup = None

        main_path = {
            'probability': main_confidence,
            'direction': main_direction,
            'target': _zone_label(main_target),
            'target_price': _zone_price(main_target, current_price * 0.96),
            'branches': [b for b in [branch_hold_sup, branch_break_sup] if b],
        }

        # Alt Path: breakout
        alt_prob = round(pct_up_5, 1)
        if nearest_resistance:
            break_p = nearest_resistance.get('break_pct', 40)
            reject_p = nearest_resistance.get('reject_pct', 45)
            branch_break_res = {
                'condition': f"Nếu VƯỢT vùng {_zone_label(nearest_resistance)}",
                'probability': round((alt_prob * break_p) / 100.0, 1),
                'direction': 'Tăng tiếp',
                'target': _zone_label(second_resistance),
                'target_price': _zone_price(second_resistance, current_price * 1.08),
            }
            branch_reject_res = {
                'condition': f"Nếu BỊ CHẶN tại {_zone_label(nearest_resistance)}",
                'probability': round((alt_prob * reject_p) / 100.0, 1),
                'direction': 'Điều chỉnh về',
                'target': _zone_label(nearest_support),
                'target_price': _zone_price(nearest_support, current_price * 0.96),
            }
            alt_branches = [branch_break_res, branch_reject_res]
        else:
            alt_branches = []

        alt_path = {
            'probability': alt_prob,
            'direction': 'Tăng hướng lên',
            'target': _zone_label(nearest_resistance),
            'target_price': _zone_price(nearest_resistance, current_price * 1.04),
            'branches': alt_branches,
        }

    return {
        'current_price': current_price,
        'main_path': main_path,
        'alt_path': alt_path,
        'n_matches': dist.get('future_5', {}).get('n', 0),
        'consensus': consensus,
    }
def project_targets(df: pd.DataFrame, zones: list) -> dict:
    """
    Project targets using ATR, Measured Move, and Structure Projection.
    """
    price = float(df['Close'].iloc[-1])
    atr = float(df['ATR14'].iloc[-1]) if 'ATR14' in df.columns else price * 0.01

    # ATR projections
    atr_up_1 = round(price + 1.5 * atr, 2)
    atr_up_2 = round(price + 2.5 * atr, 2)
    atr_down_1 = round(price - 1.5 * atr, 2)
    atr_down_2 = round(price - 2.5 * atr, 2)

    # Measured Move – from recent swing low to swing high
    recent = df.tail(120)
    sh = recent[recent['SwingHigh'] > 0]['SwingHigh'] if 'SwingHigh' in recent.columns else pd.Series(dtype=float)
    sl = recent[recent['SwingLow'] > 0]['SwingLow'] if 'SwingLow' in recent.columns else pd.Series(dtype=float)

    measured_up = None
    measured_down = None

    if len(sh) > 0 and len(sl) > 0:
        last_high = float(sh.iloc[-1])
        last_low = float(sl.iloc[-1])
        swing_range = abs(last_high - last_low)

        if price > last_high:
            # Breakout above → measured move up
            measured_up = round(price + swing_range, 2)
        elif price < last_low:
            # Breakdown below → measured move down
            measured_down = round(price - swing_range, 2)
        else:
            measured_up = round(last_high + swing_range, 2)
            measured_down = round(last_low - swing_range, 2)

    # Confidence based on ATR stability
    atr14 = float(df['ATR14'].iloc[-1]) if 'ATR14' in df.columns else 0
    atr30 = float(df['ATR30'].iloc[-1]) if 'ATR30' in df.columns else atr14
    atr_ratio = atr14 / max(atr30, 0.001)
    confidence = "Cao" if 0.8 <= atr_ratio <= 1.2 else "Trung bình" if atr_ratio < 1.5 else "Thấp (Biến động)"

    return {
        'current_price': round(price, 2),
        'atr': round(atr, 2),
        'atr_up_1x5': atr_up_1,
        'atr_up_2x5': atr_up_2,
        'atr_down_1x5': atr_down_1,
        'atr_down_2x5': atr_down_2,
        'measured_move_up': measured_up,
        'measured_move_down': measured_down,
        'confidence': confidence,
    }

# ─────────────────────────────────────────────────────────────
# PREREQUISITE GUARD
# ─────────────────────────────────────────────────────────────

def ensure_whatif_ready(df: pd.DataFrame) -> pd.DataFrame:
    """
    Đảm bảo df có đủ các cột cần thiết cho what-if analysis.
    Nếu thiếu, tự gọi enrich_dataframe để bổ sung.
    Trả về df đã enriched (hoặc df gốc nếu đã đủ).
    """
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing or '_ENRICHED' not in df.columns:
        try:
            from tinvest.data_loader import enrich_dataframe
            df = enrich_dataframe(df)
            logger.info(f"[ensure_whatif_ready] enriched df, missing cols were: {missing[:5]}")
        except Exception as e:
            logger.warning(f"[ensure_whatif_ready] enrich_dataframe failed: {e}")
    return df


# ─────────────────────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────────────────────

def run_whatif_analysis(ticker: str, df: pd.DataFrame,
                         top_n: int = 30,
                         compute_forecast_series: bool = False,
                         forecast_days: int = 90,
                         cached_forecast_series: list = None) -> dict:
    """
    Master What-If analysis function.
    Runs all phases and returns a comprehensive result dict.
    """
    if df is None or len(df) < 100:
        return {'error': f'Không đủ dữ liệu cho {ticker} (cần ≥100 phiên)'}

    # C1+C2: Đảm bảo df đã enriched đầy đủ trước khi chạy
    df = ensure_whatif_ready(df)

    # Check 10-session average volume: must be > 100,000 (except index codes)
    ticker_upper = ticker.upper()
    is_index = ('INDEX' in ticker_upper) or ('VN30' in ticker_upper) or ('HNX' in ticker_upper) or ('UPCOM' in ticker_upper)

    if 'Volume' in df.columns:
        avg_vol_10 = float(df['Volume'].tail(10).mean())
        if not is_index and avg_vol_10 <= 100000:
            return {
                'error': f'Bỏ qua phân tích What-If cho {ticker} do khối lượng trung bình 10 phiên ({avg_vol_10:,.0f}) dưới 100,000',
                'ticker': ticker
            }

    try:
        price = float(df['Close'].iloc[-1])
        try:
            date_val = df['Date'].iloc[-1]
            date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)
        except Exception:
            date_str = 'N/A'

        # Phase 2: State vector for current bar
        logger.info(f"[What-If] {ticker}: Building state vector...")
        current_sv = build_state_vector(df, idx=-1)
        current_vec = _vectorize(current_sv)

        # Phase 3: S/R zones
        logger.info(f"[What-If] {ticker}: Detecting S/R zones...")
        zones_raw = detect_sr_zones(df)

        # Phase 7: S/R reactions
        logger.info(f"[What-If] {ticker}: Analyzing S/R reactions...")
        zones = analyze_sr_reactions(df, zones_raw)

        # Pre-compute to save time for both main match and forecast series
        col_arrays = _build_col_arrays(df)
        n_df = len(df)
        
        all_state_vectors = [build_state_vector_fast(col_arrays, i, n_df) for i in range(n_df)]
        
        feature_history = {}
        for key in DEFAULT_WEIGHT_CONFIG:
            feature_history[key] = np.array([sv.get(key, np.nan) for sv in all_state_vectors], dtype=np.float64)

        all_vectorized_states = [_vectorize(all_state_vectors[i], feature_history=feature_history, idx=i) for i in range(n_df)]
            
        all_hist_vec_combined = []
        for i in range(n_df):
            v0 = all_vectorized_states[i]
            v1 = all_vectorized_states[i-1] if i >= 1 else v0
            v2 = all_vectorized_states[i-2] if i >= 2 else v1
            all_hist_vec_combined.append(np.concatenate([v0, v1, v2]))

        # Phase 4+5: Historical matches
        logger.info(f"[What-If] {ticker}: Finding historical analogs (top {top_n})...")
        matches = find_historical_matches(
            df, current_vec=current_vec, top_n=top_n, target_idx=-1,
            all_state_vectors=all_state_vectors, feature_history=feature_history, col_arrays=col_arrays,
            all_hist_vec_combined=all_hist_vec_combined
        )
        warning = None

        # Phase 6: Outcome distribution
        logger.info(f"[What-If] {ticker}: Calculating outcome distribution...")
        distribution = calculate_outcome_distribution(matches)

        # Phase 8: Scenario tree
        logger.info(f"[What-If] {ticker}: Building scenario tree...")
        scenario_tree = build_scenario_tree(price, zones, distribution)

        # Phase 9: Target projection
        logger.info(f"[What-If] {ticker}: Projecting targets...")
        targets = project_targets(df, zones)

        # Match quality summary
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for m in matches:
            t = m.get('tier')
            if t in counts:
                counts[t] += 1
        used_tiers = [t for t, c in counts.items() if c > 0]
        dominant_tier = max(used_tiers) if used_tiers else 4
        avg_sim = float(np.mean([m['similarity'] for m in matches])) if matches else 0.0
        
        temporal_div = _calc_temporal_diversity(matches)
        
        # Build custom warning based on user rules
        warnings_list = []
        if warning:
            warnings_list.append(warning)
            
        best_tier = min(used_tiers) if used_tiers else 4
        num_high_quality = sum(1 for m in matches if m.get('tier', 4) <= 3)
        num_tier12 = sum(1 for m in matches if m.get('tier', 4) <= 2)
        
        if len(matches) < 7 or num_tier12 < 2:
            warnings_list.append("Mức độ tin cậy thấp: Cần ít nhất 7 phiên tương đồng (>75%) và 2 phiên độ tương đồng cao (>80%).")
        if temporal_div.get('warning'):
            warnings_list.append(temporal_div['warning'])
            
        if not warnings_list:
            final_warning = None
        else:
            final_warning = " | ".join(warnings_list)

        match_quality = {
            'dominant_tier': dominant_tier,
            'confidence_label': CONFIDENCE_LABELS[dominant_tier],
            'tier_1_count': counts[1],
            'tier_2_count': counts[2],
            'tier_3_count': counts[3],
            'tier_4_count': counts[4],
            'avg_similarity': round(avg_sim, 4),
            'should_trust': dominant_tier <= 2,
            'warning': final_warning
        }

        forecast_series = []
        if compute_forecast_series:
            logger.info(f"[What-If] {ticker}: Computing EV forecast series (ev10 + MA3) for the last {forecast_days} days...")

            # Dùng cache nếu có
            cached_map = {}
            if cached_forecast_series:
                for item in cached_forecast_series:
                    cached_map[item['date']] = item

            ev10_buffer: list[float] = []
            ev10_ma5_buffer: list[float] = []

            start_idx = max(100, n_df - forecast_days)
            WARMUP = 5
            warmup_start = max(100, start_idx - WARMUP)
            
            for target_idx in range(warmup_start, n_df):
                date_val = df['Date'].iloc[target_idx]
                d_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)
                close_val = float(col_arrays['Close'][target_idx])
                
                # Ưu tiên lấy từ cache nếu không phải là phiên hiện tại (để đề phòng thay đổi giá intraday)
                if target_idx < n_df - 1 and d_str in cached_map:
                    ev10_price = cached_map[d_str]['ev10']
                else:
                    day_matches = find_historical_matches(
                        df, current_vec=None, top_n=top_n, target_idx=target_idx,
                        all_state_vectors=all_state_vectors, feature_history=feature_history, col_arrays=col_arrays,
                        all_hist_vec_combined=all_hist_vec_combined
                    )
                    day_dist = calculate_outcome_distribution(day_matches)
                    ev10_pct = day_dist.get('future_10', {}).get('mean', 0.0) or 0.0
                    ev10_price = close_val * (1 + ev10_pct / 100)

                # Buffer 3
                ev10_buffer.append(ev10_price)
                if len(ev10_buffer) > 3:
                    ev10_buffer.pop(0)
                ev10_ma3_price = float(sum(ev10_buffer) / len(ev10_buffer))

                # Buffer 5
                ev10_ma5_buffer.append(ev10_price)
                if len(ev10_ma5_buffer) > 5:
                    ev10_ma5_buffer.pop(0)
                ev10_ma5_price = float(sum(ev10_ma5_buffer) / len(ev10_ma5_buffer))

                if target_idx >= start_idx:
                    forecast_series.append({
                        'date': d_str,
                        'price': close_val,
                        'ev10': ev10_price,
                        'ev10_ma3': ev10_ma3_price,
                        'ev10_ma5': ev10_ma5_price,
                    })

        return {
            'ticker': ticker.upper(),
            'price': round(price, 2),
            'date': date_str,
            'n_history': len(df),
            'state_vector': current_sv,
            'zones': zones,
            'matches': matches,
            'distribution': distribution,
            'scenario_tree': scenario_tree,
            'targets': targets,
            'match_quality': match_quality,
            'temporal_diversity': temporal_div,
            'forecast_series': forecast_series,
            'error': None,
        }

    except Exception as e:
        logger.error(f"[What-If] Error analyzing {ticker}: {e}", exc_info=True)
        return {'error': f'Lỗi phân tích {ticker}: {e}', 'ticker': ticker}