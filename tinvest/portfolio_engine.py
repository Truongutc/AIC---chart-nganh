import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _calc_buy_qty_risk_based(q_curr: float, p_avg_vnd: float, p_buy_vnd: float,
                              cutloss_vnd: float, risk_budget: float) -> float:
    """
    Tính số cổ tối đa có thể mua thêm sao cho sau khi mua,
    nếu giá hit SL (cutloss_vnd) thì tổng lỗ ≤ risk_budget (VND).

    Công thức rút ra từ phương trình rủi ro tổng:
        q_curr × (p_avg - sl) + q_add × (p_buy - sl) = risk_budget
    → q_add = (risk_budget − q_curr × max(0, p_avg − sl)) / (p_buy − sl)

    Trả về 0 nếu không thể mua thêm (giá mua ≤ SL, hoặc hết ngân sách).
    """
    if p_buy_vnd <= cutloss_vnd:
        return 0.0  # Mua dưới SL → tuyệt đối không mua
    current_risk = q_curr * max(0.0, p_avg_vnd - cutloss_vnd)
    remaining = risk_budget - current_risk
    if remaining <= 0:
        return 0.0  # Ngân sách rủi ro đã cạn
    return remaining / (p_buy_vnd - cutloss_vnd)


def analyze_portfolio(portfolio_params: dict, tickers_data: list, storage) -> str:
    """
    Phân tích danh mục đầu tư dựa trên bộ công thức quản trị rủi ro.

    portfolio_params: {
        'nav_total': float,
        'w_target': float, # % (ví dụ: 100 cho 100%)
        'n_tickers': int,
        'r_cl': float # % cutloss mặc định (ví dụ: 7)
    }

    tickers_data: list of dict, each dict: {
        'ticker': str,
        'quantity': float,
        'avg_price': float
    }

    storage: StorageManager instance to load data
    """

    try:
        cash_on_hand = float(portfolio_params['nav_total'])
        w_target = float(portfolio_params['w_target']) / 100.0
        n_tickers = int(portfolio_params['n_tickers'])
        r_cl = float(portfolio_params['r_cl']) / 100.0
    except Exception as e:
        return f"Lỗi tham số đầu vào danh mục: {e}"

    if n_tickers <= 0:
        return "Số lượng mã phải lớn hơn 0."

    report_lines = []
    report_lines.append("BÁO CÁO ĐÁNH GIÁ DANH MỤC ĐẦU TƯ\n" + "=" * 50)

    total_market_value = 0
    total_cost_value = 0

    pre_results = []

    from tinvest.analyzer import analyze_stock

    for item in tickers_data:
        ticker = item['ticker'].upper().strip()
        q_i = float(item['quantity'])
        p_avg_input = float(item['avg_price'])

        df = storage.load_ticker_data(ticker)
        if df is None or len(df) < 20:
            pre_results.append({'ticker': ticker, 'valid': False,
                                 'msg': f"Không đủ dữ liệu cho {ticker}. Vui lòng update."})
            continue

        analysis = analyze_stock(ticker, df)
        if not analysis:
            pre_results.append({'ticker': ticker, 'valid': False,
                                 'msg': f"Không thể phân tích {ticker}."})
            continue

        val = analysis.get('valuation', {})
        if not val or not val.get('is_valid'):
            pre_results.append({'ticker': ticker, 'valid': False,
                                 'msg': f"Lỗi Valuation cho {ticker}."})
            continue

        # Prices from system are in thousands (e.g. 27.5). Convert to VND.
        p_now_vnd = float(val.get('price', 0)) * 1000
        p_sup_vnd = float(val.get('s1', 0)) * 1000
        if p_sup_vnd == 0:
            p_sup_vnd = p_now_vnd * 0.95
        p_res_vnd = float(val.get('r1', 0)) * 1000
        if p_res_vnd == 0:
            p_res_vnd = p_now_vnd * 1.05
        p_ts_vnd = float(val.get('trailing_stop', p_sup_vnd / 1000)) * 1000

        # SL kỹ thuật thật (cutloss_partial) — dùng để tính rủi ro thực tế
        cutloss_real_vnd = float(val.get('cutloss_partial', 0)) * 1000
        if cutloss_real_vnd <= 0:
            cutloss_real_vnd = p_ts_vnd * 0.97  # fallback

        # Normalize p_avg_input to VND
        p_avg_vnd = p_avg_input * 1000 if p_avg_input < 1000 else p_avg_input

        # Determine Trend
        ma_trend = analysis.get('ma_trend', {})
        trend_status = ma_trend.get('trend_status', 'Sideway')
        trend_i = 0
        if "Uptrend" in trend_status:
            trend_i = 1
        elif "Downtrend" in trend_status:
            trend_i = -1

        market_val = q_i * p_now_vnd
        cost_val = q_i * p_avg_vnd

        total_market_value += market_val
        total_cost_value += cost_val

        pre_results.append({
            'ticker': ticker, 'valid': True, 'q': q_i, 'p_avg_vnd': p_avg_vnd, 'p_now_vnd': p_now_vnd,
            'p_sup_vnd': p_sup_vnd, 'p_res_vnd': p_res_vnd, 'p_ts_vnd': p_ts_vnd,
            'cutloss_real_vnd': cutloss_real_vnd,
            'trend': trend_i, 'trend_desc': trend_status,
            'market_val': market_val, 'cost_val': cost_val, 'df': df, 'val': val, 'analysis': analysis
        })

    # ── True NAV ────────────────────────────────────────────────────────────
    nav_current = cash_on_hand + total_market_value
    if nav_current <= 0:
        return "Tổng tài sản (Tiền mặt + Cổ phiếu) phải lớn hơn 0."

    v_max_i = (nav_current * w_target) / n_tickers   # Giá trị tối đa mỗi mã
    risk_max_nav = 0.03 * nav_current                 # Ngân sách rủi ro 3% NAV / mã
    portfolio_risk_total = 0
    results = []

    # ── Metric pass (tính pl_pct, w_curr, tech_weak ...) ───────────────────
    for item in pre_results:
        if not item['valid']:
            results.append(item)
            continue

        ticker = item['ticker']
        q_i = item['q']
        p_avg_vnd = item['p_avg_vnd']
        p_now_vnd = item['p_now_vnd']
        p_sup_vnd = item['p_sup_vnd']
        p_res_vnd = item['p_res_vnd']
        p_ts_vnd = item['p_ts_vnd']
        cutloss_real_vnd = item['cutloss_real_vnd']
        df = item['df']

        pl_pct = (p_now_vnd - p_avg_vnd) / p_avg_vnd if p_avg_vnd > 0 else 0
        w_curr = item['market_val'] / nav_current

        last_row = df.iloc[-1]
        mcdx_banker = float(last_row.get('Banker', 0)) if 'Banker' in df.columns else 10
        prev_mcdx_banker = float(df.iloc[-2].get('Banker', mcdx_banker)) if len(df) > 1 and 'Banker' in df.columns else mcdx_banker
        adx = float(last_row.get('ADX', 20))
        # Dùng HK_BarColor (màu nến Heikin-Ashi THẬT hiển thị trên biểu đồ,
        # hệ Flower/2Trend) thay vì HA_Color (Heikin-Ashi cổ điển, không có
        # trạng thái trung tính) để cờ "xấu" khớp đúng màu nến thật.
        hk_bar_color = str(last_row.get('HK_BarColor', 'white')) if 'HK_BarColor' in df.columns else 'white'
        ma20 = float(last_row.get('MA20', p_now_vnd / 1000))
        vol = float(last_row.get('Volume', 0))
        vol_avg = float(last_row.get('AvgVolume20', vol))

        mcdx_weak = (mcdx_banker < prev_mcdx_banker) and (mcdx_banker < 15)
        adx_low = adx < 20
        heikin_red = (hk_bar_color.lower() == 'red')
        price_below_ma20 = (p_now_vnd / 1000) < ma20
        tech_weak = mcdx_weak or adx_low or heikin_red or price_below_ma20

        sideways_near_res = False
        if len(df) >= 4:
            recent_highs = df['High'].iloc[-4:].max() * 1000
            recent_lows = df['Low'].iloc[-4:].min() * 1000
            recent_vols = df['Volume'].iloc[-4:].mean()
            if recent_highs >= p_res_vnd * 0.98 and (recent_highs - recent_lows) / recent_lows < 0.05 and recent_vols > vol_avg:
                sideways_near_res = True

        # SL dùng để trigger cảnh báo (trailing_stop từ hệ thống)
        p_sl_vnd = p_ts_vnd if p_ts_vnd > 0 else p_sup_vnd * 0.97
        sl_source = "Hệ thống tư vấn"

        current_risk_amt = q_i * (p_avg_vnd - p_sl_vnd) if p_avg_vnd > p_sl_vnd else 0
        portfolio_risk_total += current_risk_amt

        results.append({
            'ticker': ticker, 'valid': True, 'q': q_i, 'p_avg_vnd': p_avg_vnd, 'p_now_vnd': p_now_vnd,
            'p_sup_vnd': p_sup_vnd, 'p_res_vnd': p_res_vnd, 'p_ts_vnd': p_ts_vnd,
            'cutloss_real_vnd': cutloss_real_vnd,
            'trend': item['trend'], 'trend_desc': item['trend_desc'],
            'pl_pct': pl_pct, 'w_curr': w_curr, 'm_val': item['market_val'],
            'tech_weak': tech_weak, 'sideways_near_res': sideways_near_res,
            'current_risk': current_risk_amt, 'p_sl_vnd': p_sl_vnd, 'sl_source': sl_source,
            'val': item['val'], 'analysis': item['analysis']
        })

    # ── Portfolio summary ───────────────────────────────────────────────────
    report_lines.append("1. ĐÁNH GIÁ CHẤT LƯỢNG TÀI SẢN (TỔNG QUAN)")
    report_lines.append(f"- Tổng Tài Sản Hiện Tại (NAV): {nav_current:,.0f} VND")
    report_lines.append(f"  + Tiền mặt đang có: {cash_on_hand:,.0f} VND ({(cash_on_hand / nav_current) * 100:.1f}%)")
    report_lines.append(f"  + Giá trị cổ phiếu: {total_market_value:,.0f} VND ({(total_market_value / nav_current) * 100:.1f}%)")
    report_lines.append(f"- Tổng Giá Vốn Cổ Phiếu: {total_cost_value:,.0f} VND")

    total_profit = total_market_value - total_cost_value
    total_profit_pct = (total_profit / total_cost_value * 100) if total_cost_value > 0 else 0
    sign = "+" if total_profit > 0 else ""
    report_lines.append(f"- Lợi Nhuận Trạng Thái Cổ Phiếu: {sign}{total_profit:,.0f} VND ({sign}{total_profit_pct:.1f}%)")
    report_lines.append(f"- Tổng rủi ro tiềm ẩn (Số tiền mất nếu hit SL): {portfolio_risk_total:,.0f} VND ({(portfolio_risk_total / nav_current) * 100:.1f}% NAV)")

    report_lines.append("\nNhận xét cân đối:")
    if (total_market_value / nav_current) > w_target:
        report_lines.append(f"  [!] QUÁ TỶ TRỌNG CỔ PHIẾU: Tỷ trọng hiện tại ({(total_market_value / nav_current) * 100:.1f}%) vượt mức khuyến cáo ({w_target * 100:.0f}%). Cần chốt lời/hạ tỷ trọng.")
    else:
        report_lines.append(f"  [v] TỶ TRỌNG AN TOÀN: Tỷ lệ phân bổ cổ phiếu ({(total_market_value / nav_current) * 100:.1f}%) đang nằm trong mức khuyến cáo ({w_target * 100:.0f}%).")

    if portfolio_risk_total > risk_max_nav:
        report_lines.append("  [!] CẢNH BÁO RỦI RO: Rủi ro tổng đang VƯỢT QUÁ 3% NAV. Ưu tiên số 1 là giảm tỷ trọng các mã vi phạm hoặc cắt lỗ ngay lập tức để bảo vệ vốn.")
    else:
        report_lines.append("  [v] RỦI RO KIỂM SOÁT TỐT: Rủi ro tổng trong tầm kiểm soát (< 3% NAV).")

    valid_tickers_count = len([r for r in results if r['valid']])
    if valid_tickers_count > n_tickers:
        report_lines.append(f"  [!] DANH MỤC DÀN TRẢI: Bạn đang cầm {valid_tickers_count} mã, vượt quá số lượng tối ưu là {n_tickers} mã. Khuyên dùng: Tỉa cỏ trồng hoa, bán bớt các mã gãy trend/yếu.")

    # ══════════════════════════════════════════════════════════════════════════
    # PASS 1 — Xác định SELL / REDUCE / HOLD (không cần biết tiền mặt khả dụng)
    # ══════════════════════════════════════════════════════════════════════════
    sell_proceeds = 0.0  # Tiền thu về từ tất cả lệnh bán/hạ

    for res in results:
        if not res['valid']:
            continue

        ticker = res['ticker']
        q_i = res['q']
        p_avg_vnd = res['p_avg_vnd']
        p_now_vnd = res['p_now_vnd']
        p_sup_vnd = res['p_sup_vnd']
        p_res_vnd = res['p_res_vnd']
        w_curr = res['w_curr']
        pl_pct = res['pl_pct']
        cutloss_real_vnd = res['cutloss_real_vnd']

        val_res = res['val']
        an_core = res['analysis']
        val_core = an_core.get('valuation', {})
        state_rules = an_core.get('state_rules', {})
        m = state_rules.get('metrics', {})

        h_rating = val_res.get('tech_health', {}).get('health_rating', 'N/A')
        h_score = val_res.get('tech_health', {}).get('health_score', 0)

        # ── Tín hiệu AI ───────────────────────────────────────────────────
        state = val_core.get('state', 'NONE')
        sig_map = {
            'STRONG': 'Mua mạnh (Trend Leader)', 'ADD_2': 'Gia tăng vị thế 2 (Confirm)',
            'ADD_1': 'Gia tăng vị thế 1 (Pullback)', 'EARLY': 'Mua sớm (Thăm dò)',
            'NONE': 'Chưa có tín hiệu dứt khoát'
        }
        holding_sig = sig_map.get(state, 'Chưa có tín hiệu dứt khoát')
        rt_sig_map = {
            'BREAKOUT_BUY': 'MUA BREAKOUT (Tiền tấn công)', 'PULLBACK_BUY': 'MUA PULLBACK (Tiền gốc)',
            'RETEST_BUY': 'MUA RETEST (Điểm Giàu)', 'CONTINUATION_BUY': 'GIA TĂNG (Trend Confirm)',
            'TREND_FOLLOW': 'ÔM TIẾP (Theo sóng)', 'TAKE_PROFIT': 'CHỐT LÃI (Canh nhả hàng)',
            'EXIT_OR_SHORT': 'THOÁT HÀNG (Rủi ro)', 'EXIT_FAST': 'CHẠY NGAY (Bẫy giá)',
            'SHORT': 'Đứng ngoài hoàn toàn'
        }
        realtime_sig = rt_sig_map.get(state_rules.get('signal', ''), '')
        sr_signal = realtime_sig if realtime_sig else holding_sig

        avoid_entry = state_rules.get('avoid_entry', False)
        if avoid_entry and (sr_signal.upper().startswith('MUA') or sr_signal.upper().startswith('GIA TĂNG')):
            if m.get('anti_trap_block'):
                sr_signal = 'BLOCK (Rủi ro Fomo: Đợi chỉnh)'

        _rs = val_core.get('risk_score', 50)
        anti_trap = m.get('anti_trap_block', False)
        sig_upper = sr_signal.upper()
        ai_good = state in ('STRONG', 'ADD_2', 'ADD_1') and _rs <= 75 and not anti_trap

        # Trạng thái tỷ trọng
        status_desc = val_res.get('tech_health', {}).get('health_rating', 'BT')
        if w_curr > w_target / n_tickers:
            status_desc = 'Quá Tỷ Trọng'
        elif pl_pct < -0.05:
            status_desc = 'Đang Lỗ/Yếu'

        action = '_BUY_CANDIDATE'  # Mặc định: sẽ xử lý ở Pass 2
        q_action = 0
        p_action_vnd = 0
        reason = ''

        # Lấy trạng thái MA để check gãy trend cho Quy tắc 3
        # Dùng field boolean is_break_confirmed từ ma_rules thay vì string matching trên status text.
        # Lý do: string matching 'GÃY' bắt cả cảnh báo sớm lẫn xác nhận hoàn toàn.
        # Chỉ gãy trend ĐÃ XÁC NHẬN (break_confirmed_1/2) mới đủ cơ sở bán hàng.
        # Nếu giá còn trên MA10, is_break_confirmed = False hoàn toàn an toàn.
        ma_diag = val_res.get('tech_health', {}).get('diagnostics', {}).get('ma', {})
        is_trend_broken = bool(ma_diag.get('is_break_confirmed', False))

        # ── Quy tắc 1: Trailing_stop bị chạm ─────────────────────────────
        if p_now_vnd < res['p_sl_vnd']:
            sl_src = res['sl_source']
            if ai_good and p_now_vnd >= cutloss_real_vnd:
                # Giá giữa trailing_stop và SL thật: AI vẫn tốt → chỉ cảnh báo HOLD
                action = 'HOLD (Cảnh báo SL)'
                q_action = 0
                reason = (
                    f"Chạm trailing_stop ({sl_src}), AI ({state}) vẫn tốt. "
                    f"SL thật {cutloss_real_vnd/1000:.2f} chưa bị thủng — tiếp tục theo dõi."
                )
            else:
                # AI xấu hoặc thủng SL thật → bán hết
                action = 'BÁN HẾT (100%)'
                q_action = q_i
                p_action_vnd = p_now_vnd
                if p_now_vnd < cutloss_real_vnd:
                    reason = f"Thủng SL kỹ thuật thật {cutloss_real_vnd/1000:.2f}. Cắt lỗ bảo vệ vốn."
                else:
                    reason = f"Vi phạm cắt lỗ/chặn lãi ({sl_src})."

        # ── Quy tắc 2: Tín hiệu Chốt Lời / Thoát từ AI ──────────────────
        # Lưu ý: Tín hiệu CHỐT LÃI chỉ áp dụng khi đang LÃNH (pl_pct >= 0).
        # Nếu đang lỗ mà AI nói CHỐT LÃI → không có gì để chốt, chỉ HOLD đến SL.
        # EXIT_FAST / EXIT_OR_SHORT (CHẠY/THOÁT) thì bán bất kể lãi/lỗ.
        elif ('CHỐT' in sig_upper or 'THOÁT' in sig_upper or 'CHẠY' in sig_upper or 'BLOCK' in sig_upper) \
                and not ai_good:
            _is_panic_exit = 'CHẠY' in sig_upper or 'EXIT_FAST' in sig_upper or 'THOÁT HÀNG (RỦI RO)' in sig_upper
            if pl_pct < 0 and not _is_panic_exit:
                # Đang lỗ + tín hiệu CHỐT LÃI thông thường:
                # Không có lãi nào để chốt. HOLD đến khi hit SL mới thoát.
                action = '_BUY_CANDIDATE'  # Chuyển sang Pass 2 để đánh giá theo % lỗ và hỗ trợ
                reason = ''
            elif 'BLOCK' in sig_upper or '50%' in sig_upper:
                action = 'CHỐT LỜI (50%)'
                q_action = q_i * 0.5
                p_action_vnd = p_now_vnd
                reason = f"Đồng bộ AI lõi: {sr_signal}."
            else:
                action = 'CHỐT LỜI/THOÁT' if pl_pct >= 0 else 'THOÁT HÀNG (Cắt lỗ)'
                q_action = q_i
                p_action_vnd = p_now_vnd
                reason = f"Đồng bộ AI lõi: {sr_signal}."

        # ── Quy tắc 3: Gãy Trend / Downtrend ─────────────────────────────
        # Chỉ kích hoạt khi AI lõi cũng xác nhận xấu (not ai_good),
        # tránh override tín hiệu ADD_1/ADD_2/STRONG của AI.
        # Nếu lỗ nhỏ (> -5%) và chưa hit SL → cảnh báo HOLD thay vì bán ngay.
        #
        # QUAN TRỌNG: is_trend_broken CHỈ dùng ma_status_str (kết quả từ ma_rules).
        # KHÔNG dùng sig_upper vì sig_upper có thể chứa 'ĐỨNG NGOÀI' khi state_engine
        # trả về signal='SHORT' → gây false positive cho mọi cổ đang đi ngang/yếu.
        elif is_trend_broken and not ai_good:
            sl_not_hit = p_now_vnd >= res['p_sl_vnd']
            minor_loss = -0.05 < pl_pct < 0
            if minor_loss and sl_not_hit:
                # Lỗ nhỏ, chưa hit SL, trend yếu → cảnh báo nhưng chưa cần bán gấp
                action = 'HOLD (Cảnh báo Trend Yếu)'
                q_action = 0
                reason = (
                    f"Kỹ thuật yếu (h_score={h_score}đ), nhưng lỗ chỉ {pl_pct*100:.1f}% "
                    f"và SL {res['p_sl_vnd']/1000:.2f} chưa bị chạm. Theo dõi chặt."
                )
            else:
                action = 'CẮT LỖ (Gãy Trend)' if pl_pct < 0 else 'CHỐT LỜI/THOÁT'
                q_action = q_i
                p_action_vnd = p_now_vnd
                reason = ('Cổ phiếu gãy trend/Downtrend. Cắt bỏ dứt khoát.' if pl_pct < 0
                          else 'Trend đảo chiều xấu, ưu tiên chốt lãi bảo vệ vốn.')

        # ── Quy tắc 4: Quản trị tỷ trọng (vượt ngưỡng 5% dung sai) ──────
        elif w_curr > w_target / n_tickers + 0.05:
            action = 'HẠ TỶ TRỌNG'
            excess_value = (q_i * p_now_vnd) - v_max_i
            q_action = excess_value / p_now_vnd
            p_action_vnd = p_now_vnd
            near_res = p_now_vnd >= p_res_vnd * 0.97
            if ai_good and near_res:
                reason = (
                    f"Tỷ trọng ({w_curr*100:.1f}%) vượt ngưỡng, giá gần kháng cự {p_res_vnd/1000:.2f}. "
                    f"Hạ tỷ trọng chốt lời — nhưng nhớ MUA LẠI vì cổ ({state}) vẫn còn dư địa tăng."
                )
            elif ai_good:
                reason = (
                    f"Cổ ({state}) khỏe nhưng tỷ trọng ({w_curr*100:.1f}%) vượt ngưỡng an toàn. "
                    f"Hạ bớt — cân nhắc mua lại khi giá điều chỉnh về {p_sup_vnd/1000:.2f}."
                )
            else:
                reason = f"Tỷ trọng hiện tại ({w_curr*100:.1f}%) vượt quá mức an toàn."

        # Lưu trạng thái trung gian vào res
        res['action'] = action
        res['q_action'] = q_action
        res['p_action_vnd'] = p_action_vnd
        res['reason'] = reason
        res['status_desc'] = status_desc
        res['state_sig'] = sr_signal.upper()
        res['state'] = state
        res['sig_upper'] = sig_upper
        res['_rs'] = _rs
        res['anti_trap'] = anti_trap
        res['ai_good'] = ai_good
        res['h_score'] = h_score
        res['h_rating'] = h_rating

        # Cộng dồn tiền thu về từ các lệnh bán
        _is_sell = action not in ('HOLD', 'HOLD (Cảnh báo SL)', '_BUY_CANDIDATE',
                                   'CHỜ ĐỢI', 'CHỜ VỀ HỖ TRỢ', 'KHÔNG TBG')
        if _is_sell and q_action > 0:
            sell_proceeds += q_action * p_now_vnd

    # ══════════════════════════════════════════════════════════════════════════
    # Tiền khả dụng thực tế = tiền mặt hiện có + tiền thu về từ lệnh bán
    # ══════════════════════════════════════════════════════════════════════════
    available_cash = cash_on_hand + sell_proceeds

    # ══════════════════════════════════════════════════════════════════════════
    # PASS 2 — Xác định BUY / TBG / HOLD cho các mã chưa có quyết định
    # Ưu tiên theo chất lượng tín hiệu: STRONG > ADD_2 > ADD_1 > EARLY
    # ══════════════════════════════════════════════════════════════════════════
    _state_priority = {'STRONG': 0, 'ADD_2': 1, 'ADD_1': 2, 'EARLY': 3, 'NONE': 9}
    buy_candidates = [r for r in results if r.get('action') == '_BUY_CANDIDATE' and r['valid']]
    buy_candidates.sort(key=lambda r: _state_priority.get(r.get('state', 'NONE'), 9))

    for res in buy_candidates:
        q_i = res['q']
        p_avg_vnd = res['p_avg_vnd']
        p_now_vnd = res['p_now_vnd']
        p_sup_vnd = res['p_sup_vnd']
        p_res_vnd = res['p_res_vnd']
        w_curr = res['w_curr']
        pl_pct = res['pl_pct']
        state = res['state']
        sig_upper = res['sig_upper']
        _rs = res['_rs']
        anti_trap = res['anti_trap']
        ai_good = res['ai_good']
        h_score = res['h_score']
        cutloss_real_vnd = res['cutloss_real_vnd']

        action = 'HOLD'
        q_action = 0
        p_action_vnd = 0
        reason = ''

        # ── Quy tắc 5: Đang lỗ — xét TBG hoặc cắt bật ───────────────────────────────────
        # Ngưỡng lỗ căn cứ vào khoảng cách thực tế tới SL, không dùng % cứng tùy tiện.
        # sl_proximity = tỷ lệ đã đi qua trên đoạn giá vốn → SL (0.0 = mới mua, 1.0 = hit SL).
        # "Vùng nguy hiểm" = đã qua 60%+ đường xuống SL.
        if pl_pct < 0:
            sl_vnd = res['p_sl_vnd']
            full_range = p_avg_vnd - sl_vnd          # khoảng cách tối đa giá vốn → SL
            already_lost = p_avg_vnd - p_now_vnd     # đã giảm bao nhiêu từ giá vốn
            sl_proximity = (already_lost / full_range) if full_range > 0 else 0.0
            in_danger_zone = sl_proximity >= 0.60    # đã qua 60% đường xuống SL
            if in_danger_zone or (p_now_vnd > 0 and (p_now_vnd - p_sup_vnd) / p_now_vnd > 0.10):
                # Lỗ nặng hoặc xa hỗ trợ — cắt bớt nếu AI xấu, giữ nếu AI tốt
                if not ai_good:
                    action = 'CẮT LỖ BỚT'
                    q_action = q_i * 0.5
                    p_action_vnd = p_now_vnd
                    reason = f'Lỗ {pl_pct*100:.1f}% / xa hỗ trợ >10%, AI xấu. Cắt bớt 50% bảo vệ vốn.'
                else:
                    action = 'HOLD (Theo dõi)'
                    reason = (
                        f'Lỗ {pl_pct*100:.1f}% (cách SL {sl_proximity*100:.0f}%), AI ({state}) vẫn tốt. '
                        f'Chờ nhúng về hỗ trợ {p_sup_vnd/1000:.2f} để xem xét TBG.'
                    )

            elif p_now_vnd <= p_sup_vnd * 1.02 and ai_good:
                # Về vùng hỗ trợ + AI tốt → tính TBG bằng công thức risk-based
                # Guard: h_rating "Yếu" → KHÔNG TBG vào cổ kỹ thuật yếu, dù AI state tốt.
                # Nhất quán với Rule 6. Phải đợi h_rating >= "Trung bình".
                h_rating_val = res.get('h_rating', '')
                if h_rating_val == 'Yếu':
                    action = 'KHÔNG TBG (KT Yếu)'
                    reason = (
                        f'Về hỗ trợ {p_sup_vnd/1000:.2f} nhưng kỹ thuật "{h_rating_val}" '
                        f'(opp_score={h_score}đ < 40). Không TBG vào cổ yếu. '
                        f'Đợi h_rating >= "Trung bình" mới xem xét.'
                    )
                else:
                    p_buy = p_sup_vnd if p_sup_vnd > cutloss_real_vnd else p_now_vnd
                    if p_buy <= cutloss_real_vnd:
                        action = 'KHÔNG TBG'
                        reason = f'Hỗ trợ {p_buy/1000:.2f} ≤ SL {cutloss_real_vnd/1000:.2f}. Không TBG.'
                    else:
                        q_add = _calc_buy_qty_risk_based(q_i, p_avg_vnd, p_buy, cutloss_real_vnd, risk_max_nav)
                        # Giới hạn bởi tỷ trọng tối đa và tiền khả dụng
                        q_max_w = max(0.0, (v_max_i - q_i * p_now_vnd) / p_buy) if p_buy > 0 else 0
                        q_add = min(q_add, q_max_w)
                        if available_cash > 0:
                            q_add = min(q_add, available_cash / p_buy)
                        else:
                            q_add = 0
                        q_add = round(q_add / 100) * 100

                        if q_add >= 100:
                            action = 'MUA TBG XUỐNG'
                            q_action = q_add
                            p_action_vnd = p_buy
                            available_cash -= q_add * p_buy
                            new_total = q_i + q_add
                            new_avg = (q_i * p_avg_vnd + q_add * p_buy) / new_total if new_total > 0 else p_avg_vnd
                            reason = (
                                f'Về hỗ trợ {p_buy/1000:.2f}, AI ({state}) tốt. '
                                f'Mua thêm {int(q_add):,} cp → Giá vốn mới ≈ {new_avg/1000:.2f}. '
                                f'Nếu hit SL {cutloss_real_vnd/1000:.2f}: lỗ ≤ 3% NAV.'
                            )
                        elif available_cash <= 0:
                            action = 'CHỜ ĐỢI'
                            reason = f'Về hỗ trợ, AI tốt nhưng hết tiền khả dụng. Chờ khi có tiền.'
                        else:
                            action = 'KHÔNG TBG'
                            reason = 'Lỗ hiện tại đã gần hết ngân sách rủi ro 3% NAV.'

            elif p_now_vnd <= p_sup_vnd * 1.02 and not ai_good:
                action = 'CHỜ ĐỢI'
                reason = f'Về hỗ trợ nhưng AI xấu (h_rating={res.get("h_rating","")}, h_score={h_score}đ). Không TBG, rủi ro thủng nền cao.'


            else:
                action = 'CHỜ VỀ HỖ TRỢ'
                reason = f'Đang lơ lửng, chờ nhúng về vùng {p_sup_vnd/1000:.2f}.'

        # ── Quy tắc 6: Tín hiệu AI tốt (STRONG/ADD_2/ADD_1) ─────────────
        elif ai_good:
            # Guard: kỹ thuật "Yếu" (h_rating = opp_desc từ valuation_engine, opp_col < 40).
            # Dùng nhãn ngữ nghĩa trực tiếp, không số tùy tiện.
            h_rating_val = res.get('h_rating', '')
            if h_rating_val == 'Yếu':
                action = 'HOLD (Theo dõi)'
                reason = (
                    f'AI ({state}) có tín hiệu gia tăng nhưng kỹ thuật "{h_rating_val}" '
                    f'(opp_score={h_score}đ < 40). Không mua thêm khi sức khoẻ Yếu. '
                    f'Đợi h_rating cải thiện lên "Trung bình" trở lên.'
                )
            else:
                p_buy = p_now_vnd
                q_add = _calc_buy_qty_risk_based(q_i, p_avg_vnd, p_buy, cutloss_real_vnd, risk_max_nav)
                # Giới hạn bởi tỷ trọng tối đa và tiền khả dụng
                q_max_w = max(0.0, (v_max_i - q_i * p_now_vnd) / p_now_vnd) if p_now_vnd > 0 else 0
                q_add = min(q_add, q_max_w)
                if available_cash > 0:
                    q_add = min(q_add, available_cash / p_now_vnd)
                else:
                    q_add = 0
                q_add = round(q_add / 100) * 100

                can_add_weight = w_curr < (w_target / n_tickers) * 0.95
                if q_add >= 100 and can_add_weight:
                    action = 'MUA GIA TĂNG'
                    q_action = q_add
                    p_action_vnd = p_now_vnd
                    available_cash -= q_add * p_now_vnd
                    reason = (
                        f'AI ({state}) tốt, còn dư địa tỷ trọng ({w_curr*100:.1f}% < {(w_target/n_tickers)*100:.0f}%). '
                        f'Mua {int(q_add):,} cp tại {p_now_vnd/1000:.2f}. '
                        f'Nếu hit SL: lỗ ≤ 3% NAV. Tiền còn lại: {available_cash:,.0f} VND.'
                    )
                else:
                    action = 'HOLD'
                    if not can_add_weight:
                        reason = f'AI ({state}) tốt, đã đủ tỷ trọng ({w_curr*100:.1f}%). Gồng lãi.'
                    elif available_cash <= 0:
                        reason = f'AI ({state}) tốt nhưng hết tiền khả dụng. Gồng lãi.'
                    else:
                        reason = f'AI ({state}) tốt — ngân sách rủi ro gần cạn, giữ nguyên vị thế.'

        # ── Quy tắc 7: Tín hiệu AI lõi fallback ─────────────────────────
        elif 'MUA' in sig_upper or 'GIA TĂNG' in sig_upper:
            can_add_weight = w_curr < (w_target / n_tickers) * 0.8
            if available_cash > 0 and can_add_weight:
                p_buy = p_sup_vnd if p_now_vnd > p_sup_vnd * 1.05 else p_now_vnd
                if p_buy > cutloss_real_vnd:
                    q_add = _calc_buy_qty_risk_based(q_i, p_avg_vnd, p_buy, cutloss_real_vnd, risk_max_nav)
                    q_add = min(q_add, available_cash / p_buy) if p_buy > 0 else 0
                    q_add = round(q_add / 100) * 100
                    if q_add >= 100:
                        action = 'MUA GIA TĂNG'
                        q_action = q_add
                        p_action_vnd = p_buy
                        available_cash -= q_add * p_buy
                        reason = (
                            f'AI lõi: {res["state_sig"]}. Mua {int(q_add):,} cp tại {p_buy/1000:.2f}. '
                            f'Nếu hit SL: lỗ ≤ 3% NAV.'
                        )
                    else:
                        action = 'HOLD'
                        reason = f'Tín hiệu {res["state_sig"]} — ngân sách rủi ro gần cạn, theo dõi thêm.'
                else:
                    action = 'HOLD'
                    reason = f'Tín hiệu mua nhưng giá mua ≤ SL kỹ thuật. Chờ điều chỉnh.'
            else:
                action = 'HOLD'
                reason = ('Tín hiệu mua nhưng đã đủ tỷ trọng. Gồng lãi.' if not can_add_weight
                          else 'Tín hiệu mua nhưng hết tiền khả dụng. Gồng lãi.')

        else:
            action = 'HOLD'
            reason = 'Duy trì vị thế, tiếp tục theo dõi.'

        if not reason:
            reason = 'Duy trì vị thế hiện tại, theo dõi thêm.'

        res['action'] = action
        res['q_action'] = q_action
        res['p_action_vnd'] = p_action_vnd
        res['reason'] = reason

    # ══════════════════════════════════════════════════════════════════════════
    # PASS 3 — In mô tả chi tiết từng mã
    # ══════════════════════════════════════════════════════════════════════════
    report_lines.append("\n2. ĐÁNH GIÁ CHI TIẾT TỪNG MÃ (Tư duy xử lý)")
    for res in results:
        if not res['valid']:
            continue
        t = res['ticker']
        pl_sign = "+" if res['pl_pct'] > 0 else ""
        h_rating = res.get('h_rating', 'N/A')
        h_score = res.get('h_score', 0)
        sr_signal = res.get('state_sig', 'N/A')
        action = res['action']
        reason = res['reason']

        desc = (
            f"- {t}: Đang chiếm {res['w_curr']*100:.1f}% NAV. "
            f"Lãi/lỗ: {pl_sign}{res['pl_pct']*100:.1f}%. "
            f"Chất lượng KT: {h_rating} ({h_score}đ). Tín hiệu AI: {sr_signal}. "
            f"Hướng xử lý chiến lược: {action} ({reason})."
        )
        report_lines.append(desc)

    # ── Bảng tư vấn ACTION ─────────────────────────────────────────────────
    report_lines.append("\n3. BẢNG TƯ VẤN KIẾN NGHỊ XỬ LÝ (ACTION)")
    report_lines.append("-" * 125)
    header = (f"| {'Mã':<6} | {'Lãi/Lỗ %':<9} | {'Trạng Thái':<12} | {'Khuyến Nghị':<20} "
              f"| {'KL Hiện Tại':<12} | {'KL Khuyến Nghị':<15} | {'Giá Bán/Mua':<12} | {'Lý do Kỹ thuật'}")
    report_lines.append(header)
    report_lines.append("-" * 125)

    for res in results:
        if not res['valid']:
            row = (f"| {res['ticker']:<6} | {'-':<9} | {'Lỗi Dữ Liệu':<12} | {'Bỏ qua':<20} "
                   f"| {'-':<12} | {'-':<15} | {'-':<12} | {res['msg']}")
            report_lines.append(row)
            continue

        ticker = res['ticker']
        q_i = res['q']
        pl_pct = res['pl_pct']
        status_desc = res['status_desc']
        action = res['action']
        q_action = res['q_action']
        p_action_vnd = res['p_action_vnd']
        reason = res['reason']

        pl_str = f"{pl_pct*100:+.1f}%"
        q_curr_str = f"{int(q_i):,}"
        q_action_rounded = round(q_action / 100) * 100 if q_action else 0
        q_str = f"{int(q_action_rounded):,}" if q_action_rounded else "-"
        p_str = f"{p_action_vnd/1000:.1f}" if p_action_vnd else "-"

        row = (f"| {ticker:<6} | {pl_str:<9} | {status_desc:<12} | {action:<20} "
               f"| {q_curr_str:<12} | {q_str:<15} | {p_str:<12} | {reason}")
        report_lines.append(row)

    report_lines.append("-" * 125)

    # Tóm tắt tiền khả dụng cuối cùng
    report_lines.append(f"\n💰 TIỀN KHẢ DỤNG SAU KHI THỰC HIỆN: {available_cash:,.0f} VND")
    report_lines.append("\nQUY TẮC BẢO VỆ (Vô hiệu hóa khuyến nghị)")
    report_lines.append("- Nếu thị trường chung (VN-INDEX) xác nhận gãy Trend hoặc rủi ro vĩ mô đột biến, HỦY TOÀN BỘ LỆNH MUA.")
    report_lines.append("- Các mức hỗ trợ/kháng cự có thể thay đổi sau phiên giao dịch. Không mua mù quáng nếu cổ phiếu thủng hỗ trợ với Vol lớn.")

    return "\n".join(report_lines)
