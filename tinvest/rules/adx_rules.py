import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# AIC ADX RULES — Full System
# Based on AIC-ADX PineScript indicator + Combo doctrine
#
# TRIẾT LÝ CỐT LÕI:
#   ADX chỉ trả lời 1 câu: "Có trend không?"
#   → Dùng để CHỌN CHIẾN LƯỢC, không dùng để vào/ra lệnh trực tiếp.
#
# ADX COLOR SYSTEM (theo PineScript AIC-ADX):
#   ORANGE : ADX <= 20 (Level Range)          → Sideway, no trend
#   WHITE  : ADX > 20, đang tăng, DI+ >= DI− → Trend đang mạnh dần (BUY zone)
#   GREEN  : ADX > 20, không tăng, DI+ >= DI− → Trend tăng nhưng đà yếu dần
#   RED    : ADX > 20, DI− > DI+             → Trend giảm
#
# ENTRY CONDITIONS (từ PineScript):
#   entryLong    : ADX>20, DI+≥DI−, ADX đang tăng, DI+ mới cắt lên DI−
#   entryShort   : ADX>20, DI−>DI+, ADX đang tăng, DI− mới cắt lên DI+
#   entryLongStr : ADX>20, DI+≥DI−, ADX đang tăng, DI+ >= Level_Trend (35)
#   entryShortSt : ADX>20, DI−>DI+, ADX đang tăng, DI− >= Level_Trend (35)
#   exitLong     : DI cắt nhau (DI+ đang giảm) HOẶC ADX quay về ≤20
#   exitShort    : DI cắt nhau (DI− đang giảm) HOẶC ADX quay về ≤20
# ─────────────────────────────────────────────────────────────────────────────

HL_RANGE = 20   # ADX threshold: sideway boundary
HL_TREND = 35   # ADX threshold: strong trend (DI level)


def _get_adx_color(adx: float, adx_prev: float, di_plus: float, di_minus: float) -> str:
    """
    Xác định màu ADX theo logic PineScript AIC-ADX:
      ORANGE : hlRange (ADX <= HL_RANGE)
      WHITE  : ADX đang tăng + DI+ >= DI−  (C_White)
      GREEN  : ADX không tăng + DI+ >= DI− (C_GREENLIGHT)
      RED    : DI− > DI+                   (C_REDLIGHT)
    """
    hl_range = adx <= HL_RANGE
    sig_up = adx > adx_prev
    di_up = di_plus >= di_minus

    if hl_range:
        return "ORANGE"
    if sig_up and di_up:
        return "WHITE"
    if not sig_up and di_up:
        return "GREEN"
    # sigUp + diDn or not sigUp + diDn → đều là RED
    return "RED"


def _get_condition_signal(adx: float, adx_prev: float,
                           di_plus: float, di_minus: float,
                           di_plus_prev: float, di_minus_prev: float) -> str:
    """
    Ánh xạ state machine condition từ PineScript:
      +1    : entryLongStr  (Trend tăng cực mạnh, DI+ >= HL_TREND)
      -1    : entryShortSt  (Trend giảm cực mạnh, DI− >= HL_TREND)
      +0.5  : entryLong     (Trend tăng thường, DI+ mới cắt qua DI−)
      -0.5  : entryShort    (Trend giảm thường)
       0    : exit/neutral
    """
    hl_range = adx <= HL_RANGE
    sig_up = adx > adx_prev
    di_up = di_plus >= di_minus
    di_dn = di_minus > di_plus
    di_up_up = di_plus >= HL_TREND
    di_dn_dn = di_minus >= HL_TREND

    # DI mới cắt nhau so với phiên trước
    di_up_prev = di_plus_prev >= di_minus_prev

    entry_long_str = (not hl_range) and di_up and sig_up and di_up_up
    entry_short_str = (not hl_range) and di_dn and sig_up and di_dn_dn
    entry_long = (not hl_range) and di_up and sig_up and (not di_up_prev)
    entry_short = (not hl_range) and di_dn and sig_up and di_up_prev

    cross_di = (di_up and not di_up_prev) or (di_dn and di_up_prev)
    exit_long = (cross_di and di_up_prev) or (hl_range)
    exit_short = (cross_di and not di_up_prev) or (hl_range)

    if entry_long_str:
        return "LONG_STRONG"
    if entry_short_str:
        return "SHORT_STRONG"
    if entry_long:
        return "LONG"
    if entry_short:
        return "SHORT"
    if exit_long or exit_short:
        return "EXIT"
    return "HOLD"


def evaluate_adx(df: pd.DataFrame, idx: int = -1) -> dict:
    """
    Phân tích toàn diện ADX theo hệ thống AIC ADX:

    1. Phân loại lực xu hướng (5 tầng)
    2. Xác định màu ADX (White/Green/Red/Orange)
    3. Tín hiệu Entry/Exit theo DI crossover
    4. Combo đánh giá với RSI, MA, MACD, Breakout
    5. Cảnh báo sai lầm phổ biến
    """
    min_len = abs(idx) + 15
    if len(df) < min_len:
        return {
            "value": 0, "bias": "UNKNOWN", "is_rising": False,
            "color": "ORANGE", "condition": "EXIT",
            "status": "Không đủ dữ liệu ADX",
            "action": "N/A",
            "combo": {}
        }

    last  = df.iloc[idx]
    prev  = df.iloc[idx - 1]
    prev2 = df.iloc[idx - 2] if len(df) >= abs(idx) + 2 else prev

    adx      = float(last.get('ADX', 0))
    adx_prev = float(prev.get('ADX', 0))

    di_plus       = float(last.get('DI_Plus', 0))
    di_minus      = float(last.get('DI_Minus', 0))
    di_plus_prev  = float(prev.get('DI_Plus', 0))
    di_minus_prev = float(prev.get('DI_Minus', 0))

    ma20 = float(last.get('MA20', last['Close']))
    ma50 = float(last.get('MA50', last['Close']))
    ma20_prev = float(prev.get('MA20', ma20))
    ma50_prev = float(prev.get('MA50', ma50))

    rsi      = float(last.get('RSI', 50))
    macd     = float(last.get('MACD', 0))
    macd_h   = float(last.get('MACD_Hist', 0))
    macd_h_p = float(prev.get('MACD_Hist', 0))
    price    = float(last['Close'])
    open_p   = float(last['Open'])

    is_rising = adx > adx_prev
    is_falling = adx < adx_prev
    di_up = di_plus >= di_minus
    bias = "TĂNG" if di_up else "GIẢM"

    color     = _get_adx_color(adx, adx_prev, di_plus, di_minus)
    condition = _get_condition_signal(adx, adx_prev, di_plus, di_minus,
                                     di_plus_prev, di_minus_prev)

    status = []
    action = []

    # ──────────────────────────────────────────────────────────────
    # TẦNG 1: ADX < 20 — SIDEWAY / NO TREND
    # ──────────────────────────────────────────────────────────────
    if adx < HL_RANGE:
        status.append("ADX < 20: Thị trường SIDEWAY — Không có xu hướng rõ ràng.")
        action.append(
            "Đánh mean reversion (mua thấp bán cao trong biên). "
            "RSI 30–70 hoạt động tốt. "
            "BỎ QUA mọi tín hiệu MACD/MA cắt nhau vì nhiễu cực cao."
        )
        # Fake breakout warning
        if price > prev['Close'] * 1.02:
            status.append("⚠️ Cảnh báo Breakout giả: Giá tăng đột ngột khi ADX thấp — đây là bẫy (trap)!")
        # DI crossover when ADX < 20 = fake
        di_cross = (di_plus >= di_minus) != (di_plus_prev >= di_minus_prev)
        if di_cross:
            status.append("⚠️ DI cắt nhau nhưng ADX < 20 → Fake signal. Bỏ qua hoàn toàn.")

    # ──────────────────────────────────────────────────────────────
    # TẦNG 2: 20 ≤ ADX < 25 — BẮT ĐẦU CÓ TREND
    # ──────────────────────────────────────────────────────────────
    elif HL_RANGE <= adx < 25:
        if is_rising:
            status.append(f"ADX {adx:.1f} (20–25), đang DỐC LÊN: Trend mới BẮT ĐẦU hình thành (bias: {bias}).")
            action.append(f"Theo dõi sát. Chuẩn bị vào lệnh theo hướng {bias} khi ADX vượt 25.")
        else:
            status.append(f"ADX {adx:.1f} (20–25) không có độ dốc: Tín hiệu chưa rõ ràng.")
            action.append("Chờ ADX dốc lên hoặc vượt 25 mới xác nhận trend.")

    # ──────────────────────────────────────────────────────────────
    # TẦNG 3: 25 ≤ ADX < 40 — TREND RÕ RÀNG (vùng VÀNG)
    # ──────────────────────────────────────────────────────────────
    elif 25 <= adx < 40:
        if di_up and ma20 > ma50:
            # Combo MA xác nhận
            if is_rising:
                status.append(f"ADX {adx:.1f} (25–40) DỐC LÊN + MA20>MA50: TREND TĂNG SIÊU KHỎE (màu WHITE).")
                action.append(
                    "HOLD chặt hoặc ADD POSITION. "
                    "Dùng RSI 40–50 để xác nhận điểm mua pullback (KHÔNG dùng RSI 30 nữa). "
                    "RSI 60–70 → cẩn trọng, tránh FOMO."
                )
            else:
                status.append(f"ADX {adx:.1f} (25–40) + MA20>MA50 nhưng ADX phẳng/giảm nhẹ: Trend tăng vẫn vững nhưng đà đang chững.")
                action.append("Tiếp tục HOLD. Chú ý nếu ADX tiếp tục giảm → chuẩn bị thoát dần.")
        elif di_up and ma20 <= ma50:
            status.append(f"ADX {adx:.1f} (25–40), DI+ > DI− nhưng MA20 ≤ MA50: Trend tăng yếu, MA chưa xác nhận.")
            action.append("Giảm size. Chờ MA20 vượt MA50 để xác nhận xu hướng bền vững.")
        elif not di_up:
            status.append(f"ADX {adx:.1f} (25–40), DI− > DI+: Trend GIẢM mạnh đang áp đảo (màu RED).")
            action.append("Không bắt đáy. Trend giảm đang kiểm soát. Đứng ngoài hoặc hạ tỷ trọng.")

    # ──────────────────────────────────────────────────────────────
    # TẦNG 4: 40 ≤ ADX < 60 — TREND RẤT MẠNH (cao trào)
    # ──────────────────────────────────────────────────────────────
    elif 40 <= adx < 60:
        if di_up:
            status.append(f"ADX {adx:.1f} (40–60): TREND TĂNG RẤT MẠNH — giai đoạn cao trào.")
        else:
            status.append(f"ADX {adx:.1f} (40–60): TREND GIẢM RẤT MẠNH — nguy hiểm cực cao.")

        if is_falling:
            action.append(
                "⚠️ ADX ĐÃ ĐẠT ĐỈNH và đang quay xuống: Xung lực bắt đầu chết. "
                "Dời Trailing Stop lên sát. Chuẩn bị THOÁT HÀNG từng phần."
            )
        else:
            action.append(
                "Trend đang cực bốc. Nắm giữ tiếp nhưng KHÔNG MỞ VỊ THẾ MỚI tại đây. "
                "Dời stoploss lên sát giá theo dạng trailing."
            )

    # ──────────────────────────────────────────────────────────────
    # TẦNG 5: ADX ≥ 60 — QUÁ NÓNG / CUỐI TREND
    # ──────────────────────────────────────────────────────────────
    elif adx >= 60:
        status.append(f"ADX {adx:.1f} ≥ 60: TREND {bias} SIÊU NÓNG — thường là cuối xu hướng, dễ đảo chiều.")
        action.append(
            "TUYỆT ĐỐI KHÔNG MỞ VỊ THẾ MUA MỚI. "
            "Canh chốt lời từng phần. Bảo vệ thành quả là ưu tiên số 1."
        )

    # ──────────────────────────────────────────────────────────────
    # TREND TRAJECTORY (Tra cứu lịch sử)
    # ──────────────────────────────────────────────────────────────
    adx_5ago = float(df.iloc[idx - 5].get('ADX', adx)) if len(df) >= abs(idx) + 5 else adx

    if adx > adx_5ago and adx > HL_RANGE:
        status.append(f"📈 ADX tăng từ {adx_5ago:.1f} → {adx:.1f}: Trend ĐANG MẠNH DẦN. Cứ HOLD, đừng chốt sớm.")
    elif adx < adx_5ago and adx_5ago > 30:
        status.append(f"📉 ADX giảm từ {adx_5ago:.1f} → {adx:.1f}: Trend YẾU DẦN. Chuẩn bị thoát.")

    # ──────────────────────────────────────────────────────────────
    # COMBO EVALUATIONS
    # ──────────────────────────────────────────────────────────────
    combo = {}

    # --- COMBO 1: ADX + RSI ---
    if adx < HL_RANGE:
        # Sideway → RSI 30-70 hoạt động tốt
        combo["adx_rsi"] = {
            "valid": True,
            "status": f"ADX Sideway + RSI {rsi:.1f}: Dùng RSI 30–70 để đánh mean reversion.",
            "action": "BUY khi RSI < 35, SELL khi RSI > 65."
        }
    elif adx >= 25:
        # Trend → Đổi ngưỡng RSI
        if rsi <= 50:
            combo["adx_rsi"] = {
                "valid": True,
                "status": f"ADX Trend ({adx:.1f}) + RSI {rsi:.1f} (vùng 40–50): Điểm mua pullback uy tín.",
                "action": "RSI 40–50 trong ADX > 25 = Kèo mua pullback đẹp. Vào hàng."
            }
        elif 50 < rsi <= 70:
            combo["adx_rsi"] = {
                "valid": True,
                "status": f"ADX Trend ({adx:.1f}) + RSI {rsi:.1f} (vùng 60–70): Cẩn trọng, không FOMO.",
                "action": "Trend còn mạnh nhưng giá đã rướn. Giữ hàng, không mua đuổi."
            }
        else:
            combo["adx_rsi"] = {
                "valid": False,
                "status": f"ADX Trend ({adx:.1f}) + RSI {rsi:.1f} > 70: Quá nhiệt!",
                "action": "Không mua mới. Canh chốt lời một phần."
            }

    # --- COMBO 2: ADX + MA ---
    if adx >= 25:
        ma_ok = ma20 > ma50 and di_up
        if ma_ok and is_rising:
            combo["adx_ma"] = {
                "valid": True,
                "status": f"ADX {adx:.1f} + MA20({ma20:.2f}) > MA50({ma50:.2f}) + DI+ > DI−: COMBO TREND CHUẨN BÀI.",
                "action": "Trend rất mạnh, vào được. Đây là setup cực hợp cổ phiếu VN."
            }
        elif ma20 < ma50 and not di_up:
            combo["adx_ma"] = {
                "valid": False,
                "status": f"ADX {adx:.1f} + MA20 < MA50 + DI− > DI+: DOWNTREND xác nhận.",
                "action": "Không mua. Tránh bắt đáy."
            }
        elif ma20 > ma50 and not di_up:
            combo["adx_ma"] = {
                "valid": None,
                "status": f"ADX {adx:.1f}: MA tăng nhưng DI− đang chiếm ưu thế — mâu thuẫn tín hiệu.",
                "action": "Chờ hai chỉ báo đồng thuận mới hành động."
            }
    else:
        combo["adx_ma"] = {
            "valid": None,
            "status": f"ADX {adx:.1f} < 25: Combo MA không đáng tin trong sideway.",
            "action": "Bỏ qua tín hiệu MA."
        }

    # --- COMBO 3: ADX + MACD ---
    macd_cross_up = macd_h > 0 and macd_h_p <= 0
    macd_cross_dn = macd_h < 0 and macd_h_p >= 0
    if adx >= 25:
        if macd_cross_up and di_up:
            combo["adx_macd"] = {
                "valid": True,
                "status": f"ADX Trend ({adx:.1f}) + MACD cắt lên + DI+: TÍN HIỆU MUA RẤT ĐÁNG TIN.",
                "action": "Vào lệnh với confidence cao."
            }
        elif macd_cross_dn and not di_up:
            combo["adx_macd"] = {
                "valid": False,
                "status": f"ADX Trend ({adx:.1f}) + MACD cắt xuống + DI−: Tín hiệu bán/thoát xác nhận.",
                "action": "Thoát vị thế hoặc không mở mới."
            }
        else:
            combo["adx_macd"] = {
                "valid": None,
                "status": f"ADX {adx:.1f}: MACD chưa có tín hiệu giao cắt rõ ràng.",
                "action": "Chờ xác nhận."
            }
    else:
        combo["adx_macd"] = {
            "valid": None,
            "status": f"ADX {adx:.1f} < 20: BỎ QUA toàn bộ tín hiệu MACD — nhiễu loạn.",
            "action": "Không trade theo MACD khi sideway."
        }

    # --- COMBO 4: ADX + Breakout ---
    recent_highs = [h for h in df['SwingHigh'].iloc[max(0, idx - 15):idx] if h > 0]
    breakout_confirmed = False
    if recent_highs and price > recent_highs[-1]:
        if adx >= 25 and is_rising:
            breakout_confirmed = True
            combo["adx_breakout"] = {
                "valid": True,
                "status": f"Giá phá đỉnh ({recent_highs[-1]:.2f}) + ADX {adx:.1f} tăng: BREAKOUT THẬT. Xu hướng xác nhận.",
                "action": "VÀO MẠNH TAY khi đóng cửa trên đỉnh cũ. Volume xác nhận thêm điểm uy tín."
            }
        else:
            combo["adx_breakout"] = {
                "valid": False,
                "status": f"Giá phá đỉnh ({recent_highs[-1]:.2f}) nhưng ADX {adx:.1f} thấp/không tăng: BREAKOUT GIẢ (TRAP).",
                "action": "Không vào. Đây là bẫy lùa gà điển hình."
            }

    # ──────────────────────────────────────────────────────────────
    # ENTRY/EXIT SIGNAL (từ PineScript condition state machine)
    # ──────────────────────────────────────────────────────────────
    entry_action = ""
    if condition == "LONG_STRONG":
        entry_action = f"🔥 ENTRY LONG MẠNH: DI+ ({di_plus:.1f}) ≥ {HL_TREND} + ADX tăng — Trend tăng cực mạnh."
    elif condition == "SHORT_STRONG":
        entry_action = f"💀 ENTRY SHORT MẠNH: DI− ({di_minus:.1f}) ≥ {HL_TREND} + ADX tăng — Trend giảm cực mạnh."
    elif condition == "LONG":
        entry_action = f"✅ ENTRY LONG: DI+ vừa cắt lên DI− + ADX > 20 và tăng — Trend tăng bắt đầu."
    elif condition == "SHORT":
        entry_action = f"⬇️ ENTRY SHORT: DI− vừa cắt lên DI+ + ADX > 20 và tăng — Trend giảm bắt đầu."
    elif condition == "EXIT":
        entry_action = "🚪 EXIT: DI cắt nhau theo chiều ngược lại HOẶC ADX quay về vùng Sideway (≤ 20)."

    if entry_action:
        action.append(entry_action)

    # Fallback nếu không có action
    if not action:
        action.append(f"ADX {adx:.1f} (bias: {bias}). Quan sát thêm diễn biến.")

    return {
        "value": round(adx, 2),
        "bias": bias,
        "is_rising": is_rising,
        "color": color,           # WHITE / GREEN / RED / ORANGE
        "condition": condition,   # LONG_STRONG / SHORT_STRONG / LONG / SHORT / EXIT / HOLD
        "di_plus": round(di_plus, 2),
        "di_minus": round(di_minus, 2),
        "status": " | ".join(status) if status else f"ADX {adx:.1f}: Chưa có tín hiệu đặc biệt.",
        "action": " | ".join(action),
        "combo": combo
    }
