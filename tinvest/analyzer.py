"""
Module 8 – Single Stock Analyzer
==================================
Runs the full TINVEST pipeline on a single ticker and produces a conversational, actionable report.
"""

import logging
import pandas as pd
import numpy as np

from .ichimoku_engine import analyze_ichimoku
from .vsa_engine       import analyze_vsa
from .ma_engine        import analyze_ma_trend
from .advanced_entry   import classify_entry
from .accumulation_engine import analyze_accumulation
from .valuation_engine import evaluate_stock_valuation
from .data_loader import enrich_dataframe
from .state_engine import evaluate_state_rules
from .mcdx_engine import evaluate_mcdx_rules

logger = logging.getLogger(__name__)


def evaluate_heatmap(df: pd.DataFrame) -> str:
    """Evaluate heatmap candle color transitions in the last 3-5 sessions."""
    if 'HM_Flower_Open' not in df.columns or 'HM_MoneyFlow' not in df.columns:
        return "N/A (Chưa nạp dữ liệu Heatmap)"
    
    last_n = 5
    sub = df.tail(last_n).copy()
    if len(sub) < 2: return "Trung tính"
    
    f_o, f_c = sub['HM_Flower_Open'], sub['HM_Flower_Close']
    mf = sub['HM_MoneyFlow']
    
    # Map colors: 1=White, -1=Red, 0=Yellow
    colors = []
    for i in range(len(sub)):
        o, c, m = f_o.iloc[i], f_c.iloc[i], mf.iloc[i]
        if c >= o and m == 1:
            colors.append("White")
        elif c < o and m == -1:
            colors.append("Red")
        else:
            colors.append("Yellow")
            
    current = colors[-1]
    prev = colors[-2]
    
    # 1. Chuyển từ vàng sang trắng là tăng tốt
    if prev == "Yellow" and current == "White":
        return "TĂNG TỐT (Nến chuyển Vàng -> Trắng)"
    # 2. Từ vàng sang đỏ là yếu
    if prev == "Yellow" and current == "Red":
        return "YẾU (Nến chuyển Vàng -> Đỏ)"
    # 3. Nến đỏ liên tiếp là đang đà giảm
    if all(c == "Red" for c in colors[-3:]):
        return "ĐANG ĐÀ GIẢM (Nến Đỏ liên tiếp)"
    # 4. Từ trắng sang vàng là cảnh báo đảo chiều ngắn hạn
    if prev == "White" and current == "Yellow":
        return "CẢNH BÁO ĐẢO CHIỀU NGẮN HẠN (Trắng -> Vàng)"
    # 5. Từ đỏ sang vàng hoặc từ đỏ sang trắng là có thể đảo chiều tăng
    if prev == "Red" and (current == "Yellow" or current == "White"):
        return "CÓ THỂ ĐẢO CHIỀU TĂNG (Đỏ -> Vàng/Trắng)"
        
    color_map = {"White": "Trắng (Tích cực)", "Red": "Đỏ (Tiêu cực)", "Yellow": "Vàng (Lưỡng lự)"}
    return f"Trạng thái: {color_map.get(current, current)}"






def analyze_stock(ticker: str, df: pd.DataFrame) -> dict:
    logger.info(f"Analyzing {ticker} ...")
    
    # 1. Enrich data 1 lần duy nhất (tất cả MA, ATR, Ichimoku, HA, VSA)
    df_rich = enrich_dataframe(df.copy())
    
    # 2. Call engines — đọc từ columns đã có sẵn, không tính lại
    ichi = analyze_ichimoku(df_rich)
    vsa = analyze_vsa(df_rich)
    ma_trend = analyze_ma_trend(df_rich)
    adv = classify_entry(df_rich)
    accum = analyze_accumulation(df_rich)
    
    last = df_rich.iloc[-1]
    
    # 3. Valuation & Risk Management (AIC Style)
    valuation = evaluate_stock_valuation(ticker, df_rich, adv)
    
    # 4. Master State Engine (Rule Trạng Thái)
    state_rules = evaluate_state_rules(df_rich)
    
    # Store close_26 for Chikou analysis in report
    close_26 = df_rich['Close'].iloc[-26] if len(df_rich) > 26 else df_rich['Close'].iloc[0]

    heatmap_eval = evaluate_heatmap(df_rich)
    mcdx_eval = evaluate_mcdx_rules(df_rich)
    
    return {
        "ticker": ticker.upper(),
        "price": float(last["Close"]),
        "date": str(last["Date"].date()) if hasattr(last["Date"], "date") else str(last["Date"]),
        "ichi": ichi,
        "vsa": vsa,
        "ma_trend": ma_trend,
        "adv": adv,
        "accum": accum,
        "valuation": valuation,
        "state_rules": state_rules,
        "close_26": float(close_26),
        "ma20": float(df_rich['MA20'].iloc[-1]),
        "ma50": float(df_rich['MA50'].iloc[-1]),
        "heatmap_eval": heatmap_eval,
        "mcdx_eval": mcdx_eval
    }


def format_report(result: dict) -> str:
    """Format the cumulative results into a professional AIC code report."""
    if not result:
        return "Lỗi: Không có dữ liệu phân tích."

    t = result["ticker"]
    price = result["price"]
    date = result["date"]
    val = result.get("valuation", {})
    adv = result.get("adv", {})
    ichi = result.get("ichi", {})
    ma_trend = result.get("ma_trend", {})
    tech = val.get("tech_health", {})

    # Ichimoku (evaluate_ichimoku) luôn tính lại cho ĐÚNG phiên hôm nay — nếu
    # nó xác nhận STRONG DOWNTREND/REVERSAL (avoid_buy=True) thì phải phủ
    # quyết mọi tín hiệu MUA "đang giữ" (state, có thể cũ tới 150 phiên từ
    # classify_entry) để tránh báo cáo tự mâu thuẫn (VD vừa nói Ichimoku
    # "Tránh mua tuyệt đối" vừa khuyến nghị "Mua Mạnh 70-100%" — phát hiện
    # thực tế ở DAUKHI 2026-07-10). Tính 1 lần, dùng cho cả nhãn CHIẾN LƯỢC
    # CỐT LÕI (sr_signal) lẫn Tỷ trọng khuyến nghị (target_pct) bên dưới.
    ichi_avoid = bool(tech.get('diagnostics', {}).get('ichimoku', {}).get('avoid_buy', False))

    # Extract valuation data
    s1, s2 = val.get("s1", 0), val.get("s2", 0)
    r1, r2 = val.get("r1", 0), val.get("r2", 0)
    tp1, tp2 = val.get("tp1", 0), val.get("tp2", 0)
    sl1, sl2 = val.get("cutloss_partial", 0), val.get("cutloss_full", 0)
    ts = val.get("trailing_stop", 0)
    bb = val.get("break_buy", 0)
    
    rs = val.get("risk_score", 0)
    rd = val.get("risk_desc", "LOW")
    opp = val.get("opp_score", 0)
    opp_desc = val.get("opp_desc", "Trung bình")
    
    rr = val.get("rr_ratio", 0)
    action = val.get("action", "WAIT")
    state = val.get("state", "NONE")
    
    state_rules = result.get("state_rules", {})
    m = state_rules.get("metrics", {})
    
    # Dich thuat
    pri_raw = state_rules.get("primary", "")
    sec_raw = state_rules.get("secondary", "")
    # Mapping nhãn trạng thái (Bỏ hoàn toàn TRANSITION)
    regime = {"TREND": "Có xu hướng Rõ Ràng", "RANGE": "Đang đi biên ngang", "SQUEEZE": "Nén chặt (Chờ nổ)", "SIDEWAY": "Đi ngang"}.get(state_rules.get("regime", ""), state_rules.get("regime", "N/A"))
    primary = {"UPTREND": "Sóng Tăng Uy Tín", "DOWNTREND": "Sóng Giảm Rủi Ro", "UPTREND_START": "Vừa bứt phá vào sóng Tăng", "DOWNTREND_START": "Vừa gãy nền vào sóng Giảm", "WEAK_UPTREND": "Tăng nhưng còn yếu", "WEAK_DOWNTREND": "Giảm yếu (Đà rơi chậm lại)", "RANGE": "Đi biên đi ngang", "SQUEEZE": "Nén chặt biên hẹp", "RECOVERY": "Giai đoạn HỒI PHỤC", "NEUTRAL": "Trạng thái Trung tính"}.get(pri_raw, pri_raw or "N/A")
    secondary = {"PULLBACK": "Nhịp chỉnh lành mạnh (Kéo ngược)", "RETEST": "Kiểm tra lại đỉnh/cản (Retest)", "FAILED_PULLBACK": "Kéo giật thất bại (Thủng nền)", "EXHAUSTION": "Đuối sức (Nguy cơ đảo chiều)", "REVERSAL_BUILD": "Xây nền đảo chiều đáy", "ROLL_OVER": "Xác nhận Rơi / Gãy", "ACCUMULATION": "Gom hàng bám nền", "DISTRIBUTION": "Dấu hiệu phân phối", "TRAP": "Có bẫy giá (Lùa gà nổ Vol)", "UNDER_PRESSURE": "Áp lực bán (Tiệm cận hỗ trợ)", "NORMAL": "Trạng thái bình thường"}.get(state_rules.get("secondary", ""), state_rules.get("secondary", "N/A"))
    
    # Logic cho Tín hiệu (Ưu tiên tín hiệu đang nắm giữ - Holding)
    sig_map = {
        "STRONG": "Mua mạnh (Trend Leader)",
        "ADD_2": "Gia tăng vị thế 2 (Confirm)",
        "ADD_1": "Gia tăng vị thế 1 (Pullback)",
        "EARLY": "Mua sớm (Thăm dò)",
        "NONE": "Chưa có tín hiệu dứt khoát"
    }
    holding_sig = sig_map.get(state, "Chưa có tín hiệu dứt khoát")
    
    # Kết hợp với tín hiệu bùng nổ realtime (nếu có từ Master State Engine)
    rt_sig_map = {
        "BREAKOUT_BUY": "MUA BREAKOUT (Tiền tấn công)", 
        "PULLBACK_BUY": "MUA PULLBACK (Tiền gốc)", 
        "RETEST_BUY": "MUA RETEST (Điểm Giàu)", 
        "CONTINUATION_BUY": "GIA TĂNG (Trend Confirm)", 
        "TREND_FOLLOW": "ÔM TIẾP (Theo sóng)", 
        "TAKE_PROFIT": "CHỐT LÃI (Canh nhả hàng)", 
        "EXIT_OR_SHORT": "THOÁT HÀNG (Rủi ro)", 
        "EXIT_FAST": "CHẠY NGAY (Bẫy giá)", 
        "SHORT": "Đứng ngoài hoàn toàn"
    }
    realtime_sig = rt_sig_map.get(state_rules.get("signal", ""), "")
    
    if realtime_sig:
        sr_signal = realtime_sig
    else:
        sr_signal = holding_sig
    original_sr_signal = sr_signal  # giữ lại tín hiệu gốc để giải thích lý do khi bị phủ quyết (Ichimoku/anti-trap)
    conf = int(state_rules.get("confidence", 0))
    if conf >= 3:
        win_rate = "Tốt (Tỉ lệ thắng >= 70%)"
    elif conf == 2:
        win_rate = "Khá (Tỉ lệ thắng ~ 60%)"
    else:
        win_rate = "Thấp (Nhiều rủi ro < 50%)"

    avoid_entry = state_rules.get("avoid_entry", False)

    # Đè Tín hiệu Mua bằng RISK FILTER (Chặn Ngu)
    if avoid_entry and (sr_signal.startswith("MUA") or sr_signal.startswith("GIA TĂNG")):
        if m.get("anti_trap_block"):
            sr_signal = "BLOCK (Rủi ro Fomo: Đợi chỉnh)"

    # (Nhãn "TRÁNH MUA" do Ichimoku chỉ đè lên sr_signal SAU KHI tính xong
    # Tỷ trọng khuyến nghị bên dưới — chỉ đè khi tỷ trọng thực sự về 0%, để
    # tránh mâu thuẫn kiểu headline nói "TRÁNH MUA" trong khi % vẫn còn
    # 50-70% do Ichimoku chỉ hạ 1 bậc chứ chưa buộc đứng ngoài hoàn toàn.)

    sep = "=" * 70
    sep2 = "-" * 70

    lines = [
        "",
        sep,
        f"  💎 AIC code = AI + cơm! 💎 BÁO CÁO PHÂN TÍCH TỔNG HỢP: {t}",
        f"  Ngày: {date}  |  Giá: {price:,.2f}",
        sep,
        ""
    ]

    # --- 1. PHÂN TÍCH KỸ THUẬT ---
    lines.append("  [1. PHÂN TÍCH CHỈ BÁO & SETUP HÀNH ĐỘNG]")
    if tech:
        lines.append(f"  ● Tổng quan kỹ thuật: {tech.get('health_rating', 'BÌNH THƯỜNG')} (Điểm đánh giá: {tech.get('health_score', 0)}/100)")
        diag = tech.get('diagnostics', {})
        if diag:
            lines.append("\n  [HỆ THỐNG ĐƯỜNG TRUNG BÌNH - MA]")
            ma_d = diag.get('ma', {})
            lines.append(f"  ● Nhận định: {ma_d.get('status', 'N/A')}")
            lines.append(f"  ● Hành động: {ma_d.get('action', 'N/A')}")
            
            lines.append("\n  [HỆ THỐNG MÂY ICHIMOKU]")
            ichi_d = diag.get('ichimoku', {})
            lines.append(f"  ● Nhận định: {ichi_d.get('status', 'N/A')}")
            lines.append(f"  ● Hành động: {ichi_d.get('action', 'N/A')}")
            
            lines.append(f"\n  [CHỈ BÁO ĐỘNG LƯỢNG - RSI ({tech.get('rsi_label', 'N/A')})]")
            rsi_d = diag.get('rsi', {})
            lines.append(f"  ● Setup    : {rsi_d.get('status', 'N/A')}")
            lines.append(f"  ● Khuyến nghị: {rsi_d.get('action', 'N/A')}")
            
            lines.append(f"\n  [CHỈ BÁO DÒNG TIỀN - MACD ({tech.get('macd_label', 'N/A')})]")
            macd_d = diag.get('macd', {})
            lines.append(f"  ● Setup    : {macd_d.get('status', 'N/A')}")
            lines.append(f"  ● Khuyến nghị: {macd_d.get('action', 'N/A')}")
            
            lines.append(f"\n  [XUNG LỰC XU HƯỚNG - ADX ({tech.get('adx_label', 'N/A')})]")
            adx_d = diag.get('adx', {})
            lines.append(f"  ● Setup    : {adx_d.get('status', 'N/A')}")
            lines.append(f"  ● Khuyến nghị: {adx_d.get('action', 'N/A')}")

            # --- NEW: HEATMAP EVALUATIONS ---
            lines.append("\n  [HỆ THỐNG BẢN ĐỒ NHIỆT]")
            lines.append(f"  ● Đánh giá Heatmap: {result.get('heatmap_eval', 'N/A')}")
            
            # --- MCDX EVALUATION ---
            mcdx = result.get('mcdx_eval', {})
            if mcdx:
                lines.append(f"\n  [CHỈ BÁO DÒNG TIỀN TẠO LẬP - MCDX]")
                lines.append(f"  ● Trạng thái : {mcdx.get('status', 'N/A')}")
                lines.append(f"  ● Hành động  : {mcdx.get('action', 'N/A')}")
                lines.append(f"  ● Chi tiết   : {mcdx.get('details', 'N/A')}")
    lines.append("")

    # --- 1.5 CĂN CỨ TÍN HIỆU ---
    if m:
        lines.append("  [1.5 BIỆN LUẬN LÝ DO (TÍN HIỆU CƠ SỞ CHẨN ĐOÁN)]")
        lines.append(f"  ● ADX (Xung lực): {m.get('adx', 0):.2f} (Chop: {m.get('chop', False)}) | Biên độ giá: {m.get('range_width', 0):.2f} / ATR: {m.get('atr', 0):.2f}")
        lines.append(f"  ● Cấu Trúc (S_Bias): {m.get('structure_bias', 0)} | Xu Hướng (T_Bias): {m.get('trend_bias', 0)} (Trend Khoẻ: {m.get('strong_trend', False)})")
        lines.append(f"  ● Động Lượng MACD: {m.get('macd', 0):.2f} | Hist: {m.get('hist', 0):.2f}")
        lines.append(f"  ● Thanh Khoản (Vol): Spike={m.get('vol_spike', False)} | Dry={m.get('vol_dry', False)}")
        lines.append(f"  ● Điểm Nổ Nến: Breakout_Up={m.get('breakout_up', False)} | Nến Lực={m.get('strong_candle', False)}")
        lines.append("")

    # --- 3. MỨC GIÁ QUAN TRỌNG ---
    lines.append("  [3. MỨC GIÁ QUAN TRỌNG - S/R]")
    lines.append(f"  ● Giá hiện tại: {price:,.2f}")
    lines.append(f"  ● Hỗ trợ (S): S1: {s1:,.2f} | S2: {s2:,.2f}")
    lines.append(f"  ● Kháng cự (R): R1: {r1:,.2f} | R2: {r2:,.2f}")
    lines.append("")

    # --- 4. TỔNG KẾT CHIẾN LƯỢC AIC PROFESSIONAL ---
    lines.append(sep2)
    lines.append("  🎯 TỔNG KẾT CHIẾN LƯỢC TỪ AI (AIC PROFESSIONAL):")
    
    s1_val = f"{s1:,.2f}" if s1 > 0 else "N/A"
    r1_val = f"{r1:,.2f}" if r1 > 0 else "N/A"
    bb_val = f"{bb:,.2f}" if bb > 0 else "N/A"
    sl1_val = f"{sl1:,.2f}" if sl1 > 0 else "N/A"
    tp1_val = f"{tp1:,.2f}" if tp1 > 0 else "N/A"
    tp2_val = f"{tp2:,.2f}" if tp2 > 0 else "N/A"

    sig_raw = state_rules.get("signal", "NONE")
    anti_trap = m.get("anti_trap_block", False)
    ts_val = f"{ts:,.2f}" if ts > 0 else "MA20"
    
    # 1. Định nghĩa Tỷ trọng khuyến nghị (Dựa trên Tín hiệu và Sức khỏe kỹ thuật)
    ma_diag = tech.get('diagnostics', {}).get('ma', {})
    # Dùng field boolean is_break_confirmed thay vì string matching 'GÃY'.
    # String matching bắt cả cảnh báo sớm (early warning) → false positive.
    # is_break_confirmed = True chỉ khi gãy trend ĐÃ XÁC NHẬN HOÀN TOÀN.
    is_trend_broken = bool(ma_diag.get('is_break_confirmed', False))

    # (ichi_avoid đã tính ở đầu hàm — dùng lại ở đây cho Tỷ trọng khuyến nghị)

    # Áp lực bán xả (state_rules.secondary = DISTRIBUTION/UNDER_PRESSURE, đã
    # tính sẵn ở Master State Engine) trước đây KHÔNG hề làm giảm tỷ trọng —
    # chỉ có anti_trap gắn thêm nhãn cảnh báo mà giữ nguyên % gốc theo tín
    # hiệu Mua.
    selling_pressure = sec_raw in ("DISTRIBUTION", "UNDER_PRESSURE")
    tier_order = [
        "70–100% (Mua Mạnh/Gồng lãi)", "50–70% (Gia tăng 2)",
        "30–50% (Thăm dò/Gia tăng 1)", "15–25% (Mua sớm)", "0% (Theo dõi thêm)",
    ]

    state_tier = {"STRONG": 0, "ADD_2": 1, "ADD_1": 2, "EARLY": 3}.get(state)

    if state_tier is not None:
        if is_trend_broken:
            # MA đã XÁC NHẬN gãy trend hoàn toàn (is_break_confirmed) là tín
            # hiệu nghiêm trọng nhất, khác hẳn Ichimoku/áp lực bán (cảnh báo
            # mềm hơn) — giữ nguyên override cứng về 0% như thiết kế gốc.
            from_label = tier_order[state_tier].split(" ", 1)[0]
            target_pct = "0% (Đứng ngoài phòng thủ)"
            target_pct += f" | ⚠️ Hạ tỷ trọng từ {from_label} về 0% (MA xác nhận gãy trend)"
        else:
            # Ichimoku/áp lực bán — KHÔNG nhảy thẳng về 0% khi có rủi ro (gây
            # sốc cho người xem báo cáo), mà HẠ DẦN TỪNG BẬC theo tier_order,
            # cộng dồn nếu nhiều tín hiệu cùng lúc, luôn nêu rõ hạ từ đâu về
            # đâu (VD "Hạ tỷ trọng từ 50-70% về 30-50%").
            downgrade_steps = 0
            reasons = []
            if ichi_avoid:
                downgrade_steps += 1
                reasons.append("Ichimoku xác nhận downtrend/đảo chiều")
            if selling_pressure:
                downgrade_steps += 1
                reasons.append("áp lực bán (phân phối)")

            new_tier = min(state_tier + downgrade_steps, len(tier_order) - 1)
            target_pct = tier_order[new_tier]
            if downgrade_steps > 0:
                from_label = tier_order[state_tier].split(" ", 1)[0]
                to_label = target_pct.split(" ", 1)[0]
                target_pct += f" | ⚠️ Hạ tỷ trọng từ {from_label} về {to_label} ({', '.join(reasons)})"
    else:
        # Không có vị thế đang giữ — xét theo sức khỏe kỹ thuật chung.
        # risk_score cao đơn thuần vẫn đủ để đứng ngoài khi KHÔNG có tín hiệu
        # AI bullish nào để cân nhắc (không có bậc nào để hạ dần từ đây).
        if rs > 60:
            target_pct = "0% (Đứng ngoài phòng thủ)"
        elif tech.get('health_score', 0) >= 65:
            target_pct = "20–40% (Giữ vị thế/Chờ điểm nổ)"
        elif tech.get('health_score', 0) >= 45:
            target_pct = "10–20% (Quan sát chặt)"
        else:
            target_pct = "0% (Theo dõi thêm)"

    if anti_trap: target_pct += " | 🛡️ CHẶN MUA ĐUỔI"

    # Đè nhãn headline (sr_signal) sang "TRÁNH MUA" CHỈ KHI tỷ trọng cuối
    # cùng thực sự về 0% — nếu Ichimoku/áp lực bán chỉ hạ 1-2 bậc mà vẫn còn
    # tỷ trọng dương (VD 50-70%), giữ nguyên nhãn tín hiệu gốc để khớp với %,
    # tránh mâu thuẫn kiểu headline "TRÁNH MUA" trong khi vẫn khuyến nghị mua.
    if ichi_avoid and target_pct.startswith("0%") and (
        sr_signal.startswith("Mua") or sr_signal.startswith("Gia tăng")
        or sr_signal.startswith("MUA") or sr_signal.startswith("GIA TĂNG")
    ):
        sr_signal = "TRÁNH MUA (Ichimoku đảo chiều xấu)"

    # 2. Xây dựng Lý do hệ thống
    if anti_trap:
        re_rs = []
        if m.get('rsi', 0) > 75: re_rs.append(f"RSI quá nhiệt ({m.get('rsi'):.1f})")
        if (price - result.get('ma20', price)) / result.get('ma20', 1) > 0.1: re_rs.append("Giá rướn quá xa MA20")
        reason_txt = "⚠️ BỘ LỌC CHẶN MUA: " + ", ".join(re_rs)
    elif ichi_avoid and target_pct.startswith("0%"):
        reason_txt = f"⚠️ ICHIMOKU CHẶN MUA: Xu hướng giảm mạnh/đảo chiều (xem mục Ichimoku). Tín hiệu '{original_sr_signal}' bị vô hiệu để bảo vệ vốn."
    elif ichi_avoid:
        reason_txt = f"⚠️ ICHIMOKU HẠ TỶ TRỌNG: Xu hướng giảm mạnh/đảo chiều (xem mục Ichimoku), nhưng tín hiệu '{sr_signal}' theo giá chưa gãy — chỉ hạ bớt tỷ trọng, chưa đứng ngoài hoàn toàn."
    else:
        # Sử dụng Technical Health thay vì Market State
        reason_txt = f"Sức khoẻ: {tech.get('health_rating', 'N/A')} ({tech.get('health_score', 0)}đ). Tín hiệu: {sr_signal}."

    # 3. Phân rã hướng dẫn theo vị thế
    # ─── Lấy thêm risk/opp để tư vấn kẹp hàng thông minh hơn ───
    _rs  = val.get("risk_score", 50)
    _opp = val.get("opp_score", 0)

    # Dùng sức khỏe kỹ thuật thay cho Market State (pri_raw)
    h_rating = tech.get('health_rating', 'Trung bình')
    
    if _rs > 75: # Rủi ro cực cao (Downtrend start/Panic)
        cash_txt = "TUYỆT ĐỐI ĐỨNG NGOÀI. Không bắt dao rơi khi rủi ro cực đại."
        hold_txt = f"CƠ CẤU THOÁT HÀNG. Canh các nhịp hồi kỹ thuật để hạ tỷ trọng tối đa."
        trap_txt = f"CẮT LỖ DỨT KHOÁT. Nếu thủng {sl1_val} phải thoát hàng ngay để bảo vệ vốn."
    elif anti_trap:
        cash_txt = f"KIÊN NHẪN ĐỢI. Không FOMO. Canh nhặt khi giá lùi về vùng an toàn {s1_val}."
        hold_txt = f"DỪNG MUA GIA TĂNG. Nâng chặn lãi lên {ts_val}. Chủ động chốt lộc 1/2 tại {tp1_val}."
        trap_txt = f"CANH HỒI PHỤC HẠ TỶ TRỌNG. Cơ cấu bớt hàng khi giá hồi về vùng kháng cự {r1_val}."
    elif ichi_avoid:
        cash_txt = "TUYỆT ĐỐI ĐỨNG NGOÀI. Ichimoku đang xác nhận xu hướng giảm mạnh/đảo chiều — không mở vị thế mới."
        hold_txt = f"HẠ TỶ TRỌNG. Ichimoku đã đảo chiều xấu dù tín hiệu Mua cũ ({original_sr_signal}) chưa gãy theo giá — ưu tiên bảo toàn vốn, cân nhắc chốt quanh {sl1_val}."
        trap_txt = f"THẬN TRỌNG, KHÔNG BÌNH QUÂN GIÁ. Chờ Ichimoku xác nhận đảo chiều tăng trở lại trước khi hành động thêm. Chỉ giữ nếu chưa thủng {sl1_val}."
    elif state in ("STRONG", "ADD_2", "ADD_1"):
        cash_txt = f"MỞ VỊ THẾ TẤN CÔNG. Vị thế đang khỏe ({h_rating}). Giải ngân thêm khi vượt {r1_val}."
        hold_txt = f"GIA TĂNG TỶ TRỌNG. Tiếp tục gồng lãi. Mục tiêu kỳ vọng {tp2_val}."
        trap_txt = f"CƠ HỘI ĐẢO NGƯỢC: Cổ đang có tín hiệu tốt. Giữ vị thế và chờ về mốc SL {sl1_val}."
    elif h_rating == "Rất mạnh" or h_rating == "Tốt":
        cash_txt = f"GOM HÀNG KHI HỒI. Sức khoẻ kỹ thuật TỐT. Canh mua thêm khi giá điều chỉnh về {s1_val}."
        hold_txt = f"GIỮ VÀ TIẾP TỤC QUAN SÁT. Mục tiêu gần: {tp1_val}. Gia tăng khi giá xác nhận vượt {r1_val}."
        trap_txt = (
            f"KIÊN NHẪN GIỮ: Xu hướng cơ bản vẫn ổn định. Không vội bán. "
            f"Giá có thể tự phục hồi về {tp1_val}. Chỉ cắt nếu thủng {sl1_val}."
        )
    else:
        # Các trường hợp Trung bình / Yếu
        is_weak = _opp < 40 or _rs > 55
        cash_txt = f"THEO DÕI. Đợi tín hiệu rõ ràng hơn tại vùng {s1_val} hoặc {r1_val}."
        hold_txt = f"QUAN SÁT. Giữ tỷ trọng an toàn. Điểm chốt lời mục tiêu tại {tp1_val}."
        if is_weak:
            trap_txt = (
                f"CÂN NHẮC HẠ TỶ TRỌNG KHI HỒI: Tín hiệu tổng thể yếu (Opp: {int(_opp)}, Risk: {int(_rs)}). "
                f"Nếu có nhịp hồi về {r1_val} thì tranh thủ cơ cấu bớt để giảm áp lực."
            )
        else:
            trap_txt = (
                f"GIỮ VÀ THEO DÕI: Tín hiệu chưa rõ chiều. Không hành động vội. "
                f"Chỉ thoát nếu thủng SL {sl1_val}. Chỉ trung bình khi có tín hiệu rõ hơn."
            )

    # ── Điểm Gia Tăng (Topup) ─────────────────────────────────────────────
    topup_price   = val.get("topup_price", 0)
    topup_desc    = val.get("topup_desc", "")
    topup_has_rest = val.get("topup_has_rest", False)
    adv_type      = adv.get("entry_type", "NONE")

    if topup_price > 0 and adv_type != "NONE":
        topup_price_fmt = f"{topup_price * 1000:,.0f}"
        # Tỷ trọng gợi ý gia tăng theo chất lượng tín hiệu
        if opp >= 75 and conf >= 3:
            add_pct = "lên Full 100%"
        elif opp >= 55:
            add_pct = "thêm 30–50%"
        elif opp >= 40:
            add_pct = "thêm 20–30% (thăm dò)"
        else:
            add_pct = "chưa đủ uy tín, theo dõi thêm"

        topup_safety = val.get("topup_safety", 0)
        topup_line = (
            f"     - 📈 Điểm Gia Tăng (Ngắm trước): "
            f"Gia tăng {add_pct} khi ĐÓNG CỬA vượt {topup_price_fmt} | {topup_desc} | Mức độ an toàn: {topup_safety}%"
        )
    else:
        topup_line = f"     - 📈 Điểm Gia Tăng (Ngắm trước): Chưa xác định (cần tín hiệu mua ban đầu trước)."

    lines.append(f"  👉 CHIẾN LƯỢC CỐT LÕI : {sr_signal.upper()}")
    lines.append(f"     ● Tỷ trọng khuyến nghị : {target_pct}")
    lines.append(f"     - Lý do hệ thống       : {reason_txt}")
    
    mcdx = result.get('mcdx_eval', {})
    if mcdx:
        mcdx_status = mcdx.get('status', 'N/A')
        mcdx_action = mcdx.get('action', 'N/A')
        lines.append(f"     - 💰 Tiền lớn (MCDX)   : {mcdx_status} -> {mcdx_action}")
    lines.append(f"     - 🛡️ Vị thế FULL TIỀN    : {cash_txt}")
    lines.append(f"     - 💎 Vị thế ĐANG CẦM CỔ : {hold_txt}")
    lines.append(f"     - ✂ Vị thế ĐANG KẸP     : {trap_txt}")
    lines.append(topup_line)
    lines.append(f"     - 🎯 Mốc Chốt Lời       : TP1: {tp1_val} | TP2: {tp2_val}")
    lines.append(f"     - 🛑 Mốc Cắt Lỗ (SL)    : {sl1_val} (Thủng là Bán)")
    lines.append(sep)
    lines.append("")

    return "\n".join(lines)
