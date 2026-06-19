#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import matplotlib
# Use Agg backend for headless environments to prevent display server errors on GitHub
matplotlib.use('Agg')

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding='utf-8')
import logging
import warnings
# Suppress Pandas FutureWarnings to keep logs clean
warnings.simplefilter(action='ignore', category=FutureWarning)
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set base path to import local modules
base_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_path)

from tinvest.storage_manager import StorageManager
from tinvest.vietstock_client import VietstockClient
from tinvest.data_loader import enrich_dataframe
from tinvest.analyzer import format_report, evaluate_heatmap
from tinvest.chart_exporter import export_ticker_history_json
from AICcode import (
    analyze_ticker_worker,
    analyze_batch_worker,
    CUSTOM_RULES,
    check_rsi_bullish_divergence,
    check_macd_bullish_divergence,
    check_macd_hist_bullish_divergence,
    check_accumulation_breakout
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(base_path, "headless_update.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("HeadlessUpdate")

def run_sync_and_update():
    logger.info("==================================================")
    logger.info("🚀 BẮT ĐẦU CẬP NHẬT DỮ LIỆU TỰ ĐỘNG (HEADLESS)")
    logger.info("==================================================")
    
    # 1. Initialize Storage & Client
    storage = StorageManager()
    client = VietstockClient()
    
    # 2. Check Session Status
    logger.info("[*] Đang kiểm tra phiên làm việc với Vietstock...")
    status = client.check_session_status()
    logger.info(f"[*] Trạng thái phiên làm việc: {status}")
    
    if status in ["LIMITED", "ERROR", "NO_DATA"]:
        logger.warning("⚠️ Phiên làm việc bị hạn chế hoặc lỗi. Đang kích hoạt Selenium để làm mới...")
        refreshed = client.config_mgr.refresh_token()
        if refreshed:
            logger.info("✅ Đã làm mới token thành công! Thiết lập lại client...")
            client.refresh_from_config()
            status = client.check_session_status()
            logger.info(f"[*] Trạng thái phiên làm việc sau khi refresh: {status}")
        else:
            logger.error("❌ Không thể làm mới token bằng Selenium.")
            # We still proceed with the existing credentials/bypass small paging as a fallback
    
    # 3. Detect Missing Dates (SSoT)
    last_date = storage.get_last_date()
    logger.info(f"[*] Ngày cuối cùng có dữ liệu trong storage: {last_date}")
    
    missing_dates = client.get_missing_dates(last_date)
    
    # Integrity check: Last 3 trading days
    check_dates = []
    current = last_date or datetime.now()
    while len(check_dates) < 3 and current is not None:
        if current.weekday() < 5:
            check_dates.append(current.strftime("%Y-%m-%d"))
        current -= timedelta(days=1)
        
    if check_dates:
        logger.info(f"[*] Đang quét tính toàn vẹn 3 ngày gần nhất: {', '.join(check_dates)}...")
        ticker_counts = storage.get_ticker_counts_for_dates(check_dates)
        
        # Smart integrity check based on active registry size to avoid deleting index-only imports
        registry_size = len(storage.get_active_registry() or [])
        if registry_size >= 1200:
            min_required = min(1200, int(registry_size * 0.85))
            bad_dates = [d for d, count in ticker_counts.items() if count > 0 and count < min_required]
        else:
            bad_dates = []
            
        if bad_dates:
            logger.warning(f"⚠️ Phát hiện {len(bad_dates)} ngày bị thiếu mã (yêu cầu >= {min_required} mã): {', '.join(bad_dates)}")
            logger.info("[*] Đang xóa dữ liệu lỗi để tải lại...")
            storage.delete_specific_dates(bad_dates)
            missing_dates = sorted(list(set(missing_dates) | set(bad_dates)))

    # Force update current trading day
    now = datetime.now()
    effective_today = now.date()
    if now.weekday() == 5: effective_today -= timedelta(days=1)
    elif now.weekday() == 6: effective_today -= timedelta(days=2)
    eff_today_str = effective_today.strftime("%Y-%m-%d")
    
    if eff_today_str not in missing_dates:
        missing_dates.append(eff_today_str)
        missing_dates = sorted(missing_dates)
        
    logger.info(f"[*] Danh sách các ngày cần tải dữ liệu: {', '.join(missing_dates)}")
    
    affected_tickers = set()
    
    # 4. Ingest Price Data
    for i, d in enumerate(missing_dates):
        day_total = []
        logger.info(f"\n--- [Ngày {i+1}/{len(missing_dates)}] TẢI DỮ LIỆU: {d} ---")
        
        # HOSE=1, HNX=2, UPCOM=3
        is_any_limited = False
        for cat_id, cat_name in [(1, "HSX"), (2, "HNX"), (3, "UPCOM")]:
            try:
                logger.info(f"   [+] Đang nạp sàn {cat_name}...")
                raw, is_limited = client.fetch_market_day(cat_id, d)
                if is_limited:
                    is_any_limited = True
                if raw:
                    day_total.extend(raw)
                    logger.info(f"   ---> ✅ Đã tải: {len(raw)} mã {cat_name}")
            except Exception as e:
                logger.error(f"   ! Lỗi tải sàn {cat_name} ngày {d}: {e}")
                
        if is_any_limited:
            logger.error("❌ THẤT BẠI: Phát hiện token/cookie Vietstock bị giới hạn hoặc hết hạn. Vui lòng cập nhật cURL mới!")
            sys.exit(1)
            
        if day_total:
            total_raw = len(day_total)
            df_day = client.format_to_df(day_total)
            
            # Skip if total rows is too low
            if total_raw < 1300:
                logger.error(f"❌ HỦY BỎ ngày {d}: Chỉ có {total_raw} mã (Yêu cầu >= 1300).")
                logger.error("Dữ liệu thô thiếu hụt nghiêm trọng, nghi ngờ phiên kết nối không hợp lệ.")
                sys.exit(1)
                
            # Stagnant Bluechips check
            if 'MarketCap' in df_day.columns:
                top50 = df_day.sort_values('MarketCap', ascending=False).head(50)
                is_stagnant_top50 = (top50['Open'] == top50['High']) & \
                                    (top50['Open'] == top50['Low']) & \
                                    (top50['Open'] == top50['Close'])
                if is_stagnant_top50.all():
                    logger.error(f"❌ HỦY BỎ ngày {d}: Phát hiện 50 mã Bluechips đều đứng im.")
                    continue
                    
            logger.info(f"   [DONE] Kiểm tra toàn vẹn OK. Lưu dữ liệu...")
            
            # Update Active Registry on the last day
            if d == missing_dates[-1]:
                all_tickers = df_day['Ticker'].unique().tolist()
                # Filter out covered warrants (keep only 3-letter alphanumeric tickers)
                all_tickers = [t for t in all_tickers if len(t) == 3 and t.isalnum()]
                storage.save_active_registry(all_tickers)
                logger.info(f"   [*] Đã cập nhật Registry: {len(all_tickers)} mã niêm yết.")
                
            # Sync stock prices
            for idx, (ticker, group) in enumerate(df_day.groupby("Ticker")):
                try:
                    t_min = storage.sync_prices(ticker, group, source='API')
                    if t_min is not None:
                        affected_tickers.add(ticker)
                except Exception as ex:
                    pass
                    
        # Fetch Indices (VNINDEX=1, HNX-INDEX=2)
        indices = [("VNINDEX", 1, -19), ("HNX-INDEX", 2, -18)]
        for ticker, tid, sid in indices:
            try:
                idx_raw = client.fetch_index_day(ticker, tid, sid, d)
                if idx_raw:
                    day_idx = client.format_to_df(idx_raw)
                    t_min = storage.sync_prices(ticker, day_idx, source='API')
                    if t_min is not None:
                        affected_tickers.add(ticker)
                    logger.info(f"   ---> Xong Index: {ticker} ({d})")
            except Exception as e:
                logger.error(f"   ! Lỗi Index {ticker}: {e}")
                
    # 5. Compute indicators & export
    compute_and_export_dashboard(storage, affected_tickers, vietstock_status=status)

def format_index_report(name, res_dict, prefix=""):
    if not res_dict or res_dict['regime']['regime'] == "UNKNOWN":
        return f"\n--- TỔNG QUAN {name}: Không tìm thấy dữ liệu."
    
    res = res_dict['regime']
    mom = res_dict['momentum']
    ichi = res_dict['ichi']
    vsa = res_dict['vsa']
    ma = res_dict['ma']
    sr = res_dict.get('sr', {'s1':0, 's2':0, 'r1':0, 'r2':0})
    sr_source = res_dict.get('sr_source', 'PIVOT')
    sr_label = "Dựa trên tín hiệu mua" if sr_source == "SIGNAL" else "Dựa trên đỉnh/đáy lịch sử"
    
    regime_labels = {
        "UPTREND": "📈 UPTREND (Tăng giá xác nhận)",
        "UPTREND_UNDER_PRESSURE": "⚠️ UPTREND RỦI RO (Suy yếu/Phân phối)",
        "STABLE_RECOVERY": "🔵 HỒI PHỤC ỔN ĐỊNH (Trên MA20/Kijun)",
        "RECOVERY": "🟡 HỒI PHỤC (FTD và trên MA10)",
        "WEAK_RECOVERY": "⚪ HỒI PHỤC YẾU (Có RA Day 3+)",
        "SIDEWAY": "↔️ SIDEWAY (Đi ngang quanh MA50)",
        "MARKET_WEAKENING": "📉 SUY YẾU (Giá dưới MA50)",
        "DOWNTREND": "🔴 DOWNTREND (Thị trường giảm giá)",
        "UNKNOWN": "❓ CHƯA XÁC ĐỊNH"
    }
    regime_label = regime_labels.get(res['regime'], res['regime'])
    
    txt = f"\n{prefix}THỊ TRƯỜNG {name} ({res['date']})"
    txt += f"\n * CHỈ SỐ: {res['price']:,.0f}"
    txt += f"\n * TRẠNG THÁI: {regime_label}"
    txt += f"\n * HÀNH ĐỘNG: {res['action']}"
    if 'r3' in sr and sr['r3'] > 0:
        txt += f"\n * KHÁNG CỰ (R): {sr['r1']:,.0f} | {sr['r2']:,.0f} | {sr['r3']:,.0f}"
    else:
        txt += f"\n * KHÁNG CỰ (R): {sr['r1']:,.0f} | {sr['r2']:,.0f}" if sr['r1'] > 0 else "\n * KHÁNG CỰ (R): N/A"
    txt += f"\n * HỖ TRỢ (S): {sr['s1']:,.0f} | {sr['s2']:,.0f}" if sr['s1'] > 0 else "\n * HỖ TRỢ (S): N/A"
    txt += f"\n   (S/R: {sr_label})"
    
    if res['ftd_active']: 
        ftd_str = res.get('ftd_date', 'N/A')
        txt += f"\n   - XÁC NHẬN FTD: Đang Kích Hoạt (Từ phiên {ftd_str} - {res.get('ftd_quality', 'N/A')})"
    txt += f"\n   - Nỗ lực hồi phục (RA) : Ngày thứ {res['ra_day']}" if res['ra_day'] > 0 else ""
    txt += f"\n   - Ngày Phân Phối      : {res['distribution_count']} ngày\n"
    
    diag = res_dict.get('valuation', {}).get('tech_health', {}).get('diagnostics', {})
    if diag:
        ma_d = diag.get('ma', {})
        ichi_d = diag.get('ichimoku', {})
        rsi_d = diag.get('rsi', {})
        macd_d = diag.get('macd', {})
        adx_d = diag.get('adx', {})
        
        txt += "\n [2.1 CHẨN ĐOÁN CHỈ BÁO THỊ TRƯỜNG]"
        txt += f"\n   ● [MA] {ma_d.get('status', '')}"
        txt += f"\n   ● [MA Hành động] {ma_d.get('action', '')}"
        txt += f"\n   ● [Ichimoku] {ichi_d.get('status', '')}"
        txt += f"\n   ● [RSI Setup] {rsi_d.get('status', '')}"
        txt += f"\n   [MACD Setup] {macd_d.get('status', '')}"
        txt += f"\n   ● [ADX Setup] {adx_d.get('status', '')}"
        
        txt += f"\n\n [2.2 ĐÁNH GIÁ NẾN NHIỆT & ELLIOTT]"
        txt += f"\n   ● Heatmap: {res_dict.get('heatmap_eval', 'N/A')}"
        txt += f"\n   ● Elliott: {res_dict.get('elliott_eval', 'N/A')}\n"
        
        mcdx = res_dict.get('mcdx_eval', {})
        if mcdx:
            txt += f"\n [CHỈ BÁO DÒNG TIỀN TẠO LẬP - MCDX]"
            txt += f"\n   ● Trạng thái : {mcdx.get('status', 'N/A')}"
            txt += f"\n   ● Hành động  : {mcdx.get('action', 'N/A')}"
            txt += f"\n   ● Chi tiết   : {mcdx.get('details', 'N/A')}\n"
    else:
        txt += f"\n * VSA: {vsa['dominant']} | Ichi: {ichi['trend']} | MA: {ma['trend_label']}"
        txt += f"\n * RSI: {mom['rsi_val']} | MACD: {mom['macd_val']}\n"
    
    sigs = res_dict.get('signals', {})
    if sigs and sigs.get('entry_type') != "NONE":
        txt += f"\n 🔥 TÍN HIỆU: {sigs['entry_type']} ({sigs['confidence']})"
        
    st = res_dict.get('state_rules', {})
    alloc = "10-30%"
    alloc_note = "Chưa xác định rõ"
    if st:
        pri_map = {"UPTREND": "Sóng Tăng mạnh", "DOWNTREND": "Sóng Giảm mạnh", "UPTREND_START": "Vừa bứt phá vào sóng Tăng", "DOWNTREND_START": "Vừa gãy nền vào sóng Giảm", "WEAK_UPTREND": "Tăng nhưng yếu dần", "WEAK_DOWNTREND": "Giảm nhẹ (đà rơi chậm lại)", "RECOVERY": "Giai đoạn HỒI PHỤC", "RANGE": "Đi biên ngang", "SQUEEZE": "Nén chặt biên hẹp", "NEUTRAL": "Trạng thái Trung tính", "SIDEWAY": "Đi ngang"}
        sec_map = {"PULLBACK": "Nhịp kéo ngược (chỉnh lành mạnh)", "FAILED_PULLBACK": "Kéo ngược thất bại (thủng nền)", "EXHAUSTION": "Đuối sức (nguy cơ đảo chiều)", "REVERSAL_BUILD": "Xây nền đảo chiều đáy", "ROLL_OVER": "Xác nhận gãy", "ACCUMULATION": "Gom hàng bám nền", "DISTRIBUTION": "Phân phối", "TRAP": "Bẫy giá (lùa gà)", "UNDER_PRESSURE": "Áp lực bán (Tiệm cận hỗ trợ)", "NORMAL": "Bình thường"}
        sig_map = {"BREAKOUT_BUY": "MUA BREAKOUT", "PULLBACK_BUY": "MUA PULLBACK", "TREND_FOLLOW": "ÔM TIẾP", "REVERSAL_BUY": "MUA BẮT ĐÁY", "TAKE_PROFIT": "CHỐT LÃI", "EXIT_OR_SHORT": "THOÁT HÀNG", "EXIT_FAST": "CHẠY NGAY", "SHORT": "Đứng ngoài", "NO_TRADE": "Hạn chế mua mới", "NONE": "Chưa có tín hiệu"}
        
        st_pri = pri_map.get(st.get('primary', ''), st.get('primary', 'N/A'))
        st_sec = sec_map.get(st.get('secondary', ''), st.get('secondary', 'N/A'))
        st_sig = sig_map.get(st.get('signal', ''), st.get('signal', 'N/A'))
        st_pri_raw = st.get('primary', '')
        if st.get('signal') == "NO_TRADE":
            if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                st_sig = "Ưu tiên nắm giữ (Đợi chỉnh để mua)"
            else:
                st_sig = "Cần thận trọng (Chưa có điểm mua)"
        
        st_conf = int(st.get('confidence', 0))
        st_avoid = st.get('avoid_entry', False)
        
        if st_conf >= 3: st_win = "Tốt (>= 70%)"
        elif st_conf == 2: st_win = "Khá (~ 60%)"
        elif st_conf >= 0: st_win = "Trung bình (~ 50%)"
        else: st_win = "Thấp (< 50%)"
        
        ftd_on = res['ftd_active']
        dist_n = res.get('distribution_count', 0)
        
        if st_pri_raw in ['UPTREND', 'UPTREND_START']:
            if ftd_on and dist_n <= 2:
                alloc = "80-100%"
                alloc_note = "Xu hướng mạnh, FTD xác nhận, phân phối ít -> ALL IN được"
            elif ftd_on and dist_n > 2:
                alloc = "60-80%"
                alloc_note = "Xu hướng tăng nhưng phân phối đang tăng -> vẫn giữ tỷ trọng cao nhưng sẵn sàng hạ"
            else:
                alloc = "60-80%"
                alloc_note = "Xu hướng tăng nhưng chưa có FTD xác nhận -> chưa nên full"
        elif st_pri_raw == 'WEAK_UPTREND':
            if ftd_on:
                alloc = "50-70%"
                alloc_note = "Tăng yếu dần nhưng FTD còn sống -> canh giữ, giảm dần nếu chớm gãy"
            else:
                alloc = "30-50%"
                alloc_note = "Tăng yếu dần, không có FTD -> cẩn thận chuyển giao"
        elif st_pri_raw in ['RANGE', 'SQUEEZE', 'SIDEWAY', 'NEUTRAL']:
            if ftd_on:
                alloc = "50-70%"
                alloc_note = "Đang tích lũy/chuyển giao trong nhịp hồi có FTD -> ưu tiên nắm giữ cổ phiếu Leader"
            else:
                alloc = "20-40%"
                alloc_note = "Chưa rõ xu hướng, đang tích lũy/trung tính -> giữ tiền mặt chờ xác nhận"
        elif st_pri_raw == 'WEAK_DOWNTREND':
            if ftd_on:
                alloc = "40-60%"
                alloc_note = "Nhịp điều chỉnh/nghỉ chân trong đà hồi phục có FTD -> CƠ HỘI GOM HÀNG"
            elif dist_n >= 3:
                alloc = "0-15%"
                alloc_note = "Giảm nhẹ + phân phối nhiều -> RỦI RO CAO, BÁN HẠ TỶ TRỌNG gấp"
            else:
                alloc = "15-30%"
                alloc_note = "Điều chỉnh bình thường -> giữ ít, chờ xem có giữ nền không"
        elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START']:
            # Kiểm tra: FTD còn sống + regime đang RECOVERY → đây là nền MA giảm dài hạn,
            # không phải gãy trend mới. Chỉ bán sạch khi FTD đã bị hủy.
            _reg_now = res.get('regime', 'UNKNOWN')
            if ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']:
                alloc = "30-50%"
                alloc_note = "Nền MA dài hạn còn giảm nhưng FTD đang kích hoạt + regime RECOVERY -> Thăm dò, KHÔNG bán sạch"
            else:
                alloc = "0-10%"
                alloc_note = "Gãy xu hướng xác nhận (không có FTD bảo vệ) -> BÁN SẠCH, RA NGOÀI"
        elif st_pri_raw == 'RECOVERY':
            if ftd_on:
                alloc = "50-75%"
                alloc_note = "Hồi phục ổn định có FTD -> ưu tiên nắm giữ & quan sát điểm gia tăng"
            else:
                alloc = "20-40%"
                alloc_note = "Hồi phục kỹ thuật, chưa có FTD -> chỉ nên test tỷ trọng nhỏ"
        else:
            reg = res['regime']
            if reg == "STABLE_RECOVERY":
                alloc, alloc_note = "50-75%", "Hồi phục ổn định trên MA20"
            elif reg == "RECOVERY":
                alloc, alloc_note = "30-50%", "Đang nỗ lực hồi phục"
            else:
                alloc = "10-30%"
                alloc_note = "Chưa xác định rõ -> giữ ít phòng thủ"
        
        if st_avoid:
            if st_pri_raw in ['UPTREND', 'UPTREND_START'] and ftd_on:
                if alloc == "80-100%": alloc = "60-80%"
                elif alloc == "60-80%": alloc = "40-60%"
                alloc_note = "⚠️ CẢNH BÁO: Trạng thái quá nhiệt / MCDX phân phối -> Ưu tiên nắm giữ, hạn chế mua đuổi"
            elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START', 'MARKET_WEAKENING']:
                # Chỉ bán sạch nếu không có FTD bảo vệ; nếu FTD còn sống trong RECOVERY thì giữ nguyên alloc
                _reg_now = res.get('regime', 'UNKNOWN')
                if not (ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']):
                    alloc = "0-10%"
                    alloc_note = "Bộ Lọc Rủi Ro đang BẬT + không có FTD -> CẤM MUA MỚI"
            elif st_pri_raw in ['RECOVERY', 'WEAK_DOWNTREND'] and ftd_on:
                # Đang hồi phục có FTD: không ép xuống 10-20%, hạ nhẹ thôi
                if alloc not in ['0-10%', '10-20%']:
                    # Hạ xuống một bậc thay vì về 10-20%
                    alloc_note = "⚠️ Bộ lọc rủi ro bật nhưng FTD còn sống -> Giữ thận trọng, hạn chế mua thêm"
            else:
                alloc = "10-20%"
                alloc_note = "Thị trường lưỡng lự, bộ lọc rủi ro đang bật -> Tỷ trọng thấp"
        
        m = st.get('metrics', {})
        txt += "\n\n [2.3 ĐẶC ĐIỂM TRẠNG THÁI THỊ TRƯỜNG (ROBOT)]"
        txt += f"\n   ● Xu Hướng Cốt Lõi    : {st_pri}"
        txt += f"\n   ● Hành Vi Vận Động     : {st_sec}"
        txt += f"\n   ● Tín Hiệu Khuyến Nghị: {st_sig}"
        txt += f"\n   ● Xác Suất Thắng      : {st_win} (Hệ số: {st_conf})"
        txt += f"\n   ● Tỷ Trọng Khuyên     : {alloc} cổ phiếu ({alloc_note})"
        if m:
            txt += f"\n   ● ADX: {m.get('adx',0):.1f} | MACD Hist: {m.get('hist',0):.2f} | Vol Spike: {m.get('vol_spike', False)} | Trend Bias: {m.get('trend_bias', 0)}"
            
    txt += "\n\n 🎯 TỔNG KẾT CHIẾN LƯỢC TỪ AI:"
    mcdx = res_dict.get('mcdx_eval', {})
    if mcdx:
        txt += f"\n  💰 DÒNG TIỀN TẠO LẬP (MCDX - Tham khảo): {mcdx.get('status', 'N/A')} -> {mcdx.get('action', 'N/A')}"
        
    reg = res['regime']
    s1_val = f"{sr['s1']:,.0f}" if sr['s1'] > 0 else 'N/A'
    s2_val = f"{sr['s2']:,.0f}" if sr['s2'] > 0 else 'N/A'
    r1_val = f"{sr['r1']:,.0f}" if sr['r1'] > 0 else 'N/A'
    r2_val = f"{sr['r2']:,.0f}" if sr['r2'] > 0 else 'N/A'
    dist_count = res.get('distribution_count', 0)
    ra_day = res.get('ra_day', 0)
    ftd_quality = res.get('ftd_quality', 'N/A')
    sl_idx = f"{sr['s1'] * 0.99:,.0f}" if sr['s1'] > 0 else 'N/A'
    
    if res['ftd_active']:
        if reg in ["UPTREND", "STABLE_RECOVERY"]:
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD XÁC NHẬN + ĐỒNG THUẬN TĂNG. MÔI TRƯỜNG THUẬN LỢI."
            txt += f"\n     - Phân Bổ Tỷ Trọng      : Duy trì {alloc} cổ phiếu. Ưu tiên mã đang dẫn dắt (Leader)."
            txt += f"\n     - 🛒 Vùng Mua Gia Tăng   : Nhặt thêm hàng khi Index test lại hỗ trợ {s1_val}. Mạnh dạn gom nếu về {s2_val}."
            txt += f"\n     - 🎯 Vùng Chốt Một Phần  : Tỉa lộc khi Index chạm cản {r1_val} - {r2_val}. Không bán sạch khi trend còn sống."
            txt += f"\n     - ✂ Báo Động Đỏ Khi Nào? : Nếu Index đóng cửa thủng hỗ trợ {s1_val} kèm Volume lớn -> Hạ về 50% tiền mặt ngay."
        elif reg == "UPTREND_UNDER_PRESSURE":
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - CÓ FTD NHƯNG ÁP LỰC BÁN ĐANG TĂNG ({dist_count} phiên phân phối)."
            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : BÁN BỚT HÀNG YẾU NGAY HÔM NAY. Không chờ hồi lên cản mới bán!"
            txt += f"\n     - Cơ Cấu Danh Mục        : Loại bỏ ngay các mã gãy MA20 / mã thua lỗ nhiều. Chỉ giữ {alloc} cổ phiếu Leader khỏe."
            txt += f"\n     - 🛡️ Phòng Thủ Khi Thủng S1: Nếu Index thủng hỗ trợ {s1_val} nhưng FTD chưa hỏng -> Hạ tỷ trọng về 50% cổ phiếu."
            txt += f"\n     - ⚠️ Gãy Trend Xác Nhận   : Nếu FTD bị hủy (thủng đáy cũ) hoặc gãy xu hướng -> Nâng TIỀN MẶT lên 70%+, chỉ giữ 10-30% hoặc thoát sạch."
            txt += f"\n     - 🛒 Mua Mới Được Không?  : CẤM FOMO. Chỉ test lượng nhỏ nếu Index đạp chuẩn về sâu {s2_val} rồi nảy lên giữ được."
            txt += f"\n     - 📌 FTD Còn Sống Không?  : FTD ({ftd_quality}) sẽ BỊ HỦY nếu Index đóng cửa dưới mốc FTD cũ. Lúc đó -> chuyển sang DOWNTREND."
        elif reg == "RECOVERY":
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD VỪA KÍCH HOẠT, MỚI VƯỢT MA10. CÒN SỚM ĐỂ BẮT ĐÁY MẠNH."
            txt += f"\n     - Phân Bổ Tỷ Trọng      : Giữ {alloc} cổ phiếu. Test hàng nhỏ ở mã Leader."
            txt += f"\n     - 🛒 Mua Ở Đâu?          : Chỉ nhặt khi Index duy trì trên {s1_val}. Nếu xé rào vượt {r1_val} kèm vol -> tăng lên 50%."
            txt += f"\n     - ✂ Stoploss Cho Cả Port : Rút về 10% cổ phiếu nếu Index quay đầu thủng {sl_idx}."
        else:
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD CÓ NHƯNG XUNG LỰC CHƯA RÕ. MÔI TRƯỜNG TRUNG TÍNH."
            txt += f"\n     - Mua Dò Đường           : Giải ngân {alloc} test vị thế nhỏ khi Index nén quanh {s1_val}."
            txt += f"\n     - Chờ Xác Nhận           : Chỉ tăng tỷ trọng lên 50%+ khi Index vượt {r1_val} kèm thanh khoản rõ ràng."
            txt += f"\n     - ✂ Rút Lui Nếu          : Index đóng cửa dưới {sl_idx} -> xoá vị thế test, giữ tiền mặt chờ."
    else:
        if ra_day > 0:
            txt += f"\n  👉 THỊ TRƯỜNG [ĐANG NỖ LỰC HỒI PHỤC - RA Ngày {ra_day}] - CHỜ XÁC NHẬN FTD."
            txt += f"\n     - Tình Trạng             : Thị trường đang cố ngưng rơi nhưng CHƯA CÓ FTD. Mọi nhịp hồi đều có thể là bẫy."
            txt += f"\n     - Tỷ Trọng Khuyên        : Giữ {alloc} cổ phiếu (toàn mã cực khỏe)."
            txt += f"\n     - 🛒 Canh Mua Test        : Mua mồi 10% ở mã Leader nền đẹp khi Index đang test hỗ trợ {s1_val}."
            txt += f"\n     - ⚡ Khi Nào Tăng Tỷ Trọng: Chờ FTD xuất hiện (Volume bùng nổ > TB20 + Close tăng > 1.5%). Khi đó mới nâng lên 40%."
            txt += f"\n     - ✂ Đổ Máu Khi Nào?      : Nếu Index thủng đáy cũ {s2_val} -> BÁN SẠCH, RA NGOÀI HOÀN TOÀN."
        elif reg == "MARKET_WEAKENING":
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐÀ TĂNG CHẤM DỨT, BẮT ĐẦU SUY YẾU."
            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : Cắt bỏ mã yếu NGAY LẬP TỨC. Không đợi hồi, không gồng."
            txt += f"\n     - Tỷ Trọng Phòng Thủ     : Tối đa {alloc} cổ phiếu. Chỉ giữ mã còn trên MA50."
            txt += f"\n     - 🔪 Người Kẹp Hàng Nặng : Canh bất kỳ nhịp kéo ảo nào chạm gần {r1_val} -> BÁN XẢ giảm tải. Đừng hy vọng."
            txt += f"\n     - 🛒 Mua Lại Khi Nào?    : Chỉ khi Index đạp rã thật sâu về tận {s2_val} + xuất hiện FTD mới."
        elif reg == "SIDEWAY":
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐI NGANG BIÊN HẸP, KHÔNG CÓ XU HƯỚNG RÕ."
            txt += f"\n     - Chiến Lược             : SWING TRADE biên. Mua sát {s1_val}, bán sát {r1_val}."
            txt += f"\n     - Tỷ Trọng               : {alloc} cổ phiếu, ưu tiên mã có câu chuyện riêng."
            txt += f"\n     - ✂ Rào Chắn             : Thủng {s2_val} -> chuyển sang phòng thủ 100% tiền mặt."
        else:
            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - DOWNTREND / RỦI RO LỚN. ƯU TIÊN ÔM TIỀN MẶT."
            txt += f"\n     - ⛔ LỆNH CẤM             : TUYỆT ĐỐI KHÔNG BẮT ĐÁY. Mọi nhịp hồi đều là bẫy Bull Trap."
            txt += f"\n     - ✂ Cắt Lỗ Kỷ Luật       : Bán tháo toàn bộ mã yếu, mã thua lỗ. Không ngoại lệ."
            txt += f"\n     - 🔪 Canh Xả Hàng Kẹp    : Nếu có nhịp Bull Trap nảy lên sát {r1_val} -> thoát sạch. Đây là CƠ HỘI VÀNG để chạy."
            txt += f"\n     - 🛒 Vùng Cứu Trợ        : Chỉ quay lại thị trường khi Index đạp cạn kiệt về tận {s2_val} + FTD mới xác nhận."
            
    if st:
        txt += f"\n\n  📊 ĐÁNH GIÁ TỔNG HỢP TỪ ROBOT:"
        txt += f"\n     Xu hướng: {st_pri} | Hành vi: {st_sec} | Tín hiệu: {st_sig}"
        txt += f"\n     Xác suất tiếp diễn xu hướng hiện tại: {st_win}"
        txt += f"\n     ➡️ TỶ TRỌNG KHUYẾN NGHỊ: NẮM GIỮ {alloc} CỔ PHIẾU."
        if st_avoid:
            if st_pri_raw in ['UPTREND', 'UPTREND_START'] and ftd_on:
                txt += f"\n     ⚠️ CẢNH BÁO: Trạng thái quá nhiệt / Phân kỳ âm -> Ưu tiên bảo vệ thành quả, CHỐT LỜI DẦN."
            else:
                txt += f"\n     ⛔ BỘ LỌC RỦI RO: ĐANG BẬT - TUYỆT ĐỐI KHÔNG MUA MỚI."
    return txt


def check_mark_minervini(df):
    """
    Mark Minervini Filter criteria.
    """
    required_cols = ['Close', 'MA50', 'MA100', 'MA200', 'High52', 'Low52', 'AvgVolume10', 'AvgVolume20', 'AvgVolume60', 'SlopeMA200', 'ATR10', 'ATR30']
    if not all(col in df.columns for col in required_cols) or len(df) < 2:
        return False
    try:
        return (
            df['Close'].iloc[-1] > df['MA50'].iloc[-1] > df['MA100'].iloc[-1] > df['MA200'].iloc[-1] and
            df['Close'].iloc[-1] > 0.85 * df['High52'].iloc[-1] and
            df['Close'].iloc[-1] >= 1.3 * df['Low52'].iloc[-1] and
            df['AvgVolume20'].iloc[-1] > df['AvgVolume60'].iloc[-1] and
            df['AvgVolume10'].iloc[-1] < 0.9 * df['AvgVolume20'].iloc[-1] and
            df['SlopeMA200'].iloc[-1] > 0 and
            df['ATR10'].iloc[-1] < df['ATR30'].iloc[-1]
        )
    except Exception:
        return False


def compute_and_export_dashboard(storage, affected_tickers, vietstock_status=None):
    # Rule 2: Kiểm tra hủy niêm yết (10 phiên không giao dịch) và cập nhật registry
    current_reg = storage.get_active_registry()
    if current_reg:
        delisted_tickers = storage.identify_delisted_tickers(days_threshold=10)
        if delisted_tickers:
            logger.info(f"[*] Rule 2: Phát hiện {len(delisted_tickers)} mã không giao dịch 10 phiên (hủy niêm yết/ngừng hoạt động).")
            storage.remove_from_registry(delisted_tickers)

    # Load existing analysis results if file exists to merge instead of overwrite
    existing_tickers_analysis = {}
    existing_market_indices = {}
    existing_market_breadth = {}
    existing_vietstock_status = None
    
    output_dir = os.path.join(base_path, "Output")
    output_file = os.path.join(output_dir, "analysis_results.json")
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                if isinstance(old_data, dict):
                    for r in old_data.get("tickers_analysis", []):
                        if isinstance(r, dict) and "Ticker" in r:
                            existing_tickers_analysis[r["Ticker"]] = r
                    existing_market_indices = old_data.get("market_indices", {})
                    existing_market_breadth = old_data.get("market_breadth", {})
                    existing_vietstock_status = old_data.get("vietstock_status", None)
            logger.info(f"💾 Đã tải {len(existing_tickers_analysis)} mã từ file analysis_results.json hiện tại để hợp nhất.")
        except Exception as e_load:
            logger.warning(f"⚠️ Không thể đọc file analysis_results.json cũ: {e_load}. Sẽ tạo mới.")

    # Use existing status if not provided and it was saved previously
    if vietstock_status is None:
        vietstock_status = existing_vietstock_status or "UNKNOWN"

    # 5. Determine which tickers need recalculation
    current_reg = storage.get_active_registry()
    if not current_reg:
        logger.warning("⚠️ Registry is empty or missing! Rebuilding from existing analysis or storage files...")
        fallback_tickers = set(existing_tickers_analysis.keys())
        
        # Look at prices folder
        prices_path = os.path.join(base_path, "data_storage", "prices")
        if os.path.exists(prices_path):
            for fname in os.listdir(prices_path):
                if fname.endswith(".parquet"):
                    symbol = fname[:-8].upper()
                    if len(symbol) == 3 and symbol.isalnum():
                        fallback_tickers.add(symbol)
        
        if fallback_tickers:
            current_reg = sorted(list(fallback_tickers))
            storage.save_active_registry(current_reg)
            current_reg = set(current_reg)
            logger.info(f"✅ Rebuilt active registry with {len(current_reg)} symbols.")
        else:
            current_reg = set()
    else:
        current_reg = set(current_reg)
        
    active_set = current_reg
    
    # Self-healing: identify tickers in active_registry but missing from analysis results or history files
    missing_tickers = set()
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)
    
    for t in active_set:
        in_analysis = (t in existing_tickers_analysis)
        history_file_exists = os.path.exists(os.path.join(history_dir, f"{t}.json"))
        if not in_analysis or not history_file_exists:
            missing_tickers.add(t)
            
    new_price_count = len(affected_tickers)
    has_new_price_data = new_price_count > 0

    if missing_tickers:
        logger.info(f"🔍 Phát hiện {len(missing_tickers)} mã trong Registry bị thiếu kết quả phân tích hoặc file lịch sử. Thêm vào danh sách cập nhật...")
        affected_tickers = set(affected_tickers) | missing_tickers

    if new_price_count > 10:
        logger.info(f"🔄 Có {new_price_count} mã thay đổi giá (> 10). Tự động cập nhật phân tích cho TOÀN BỘ hệ thống...")
        affected_tickers = affected_tickers.union(active_set)
        affected_tickers.add("VNINDEX")
        affected_tickers.add("HNX-INDEX")
    else:
        logger.info("ℹ️ Ít hơn 10 mã thay đổi giá. Tính toán cho VNINDEX, HNX-INDEX và các mã có thanh khoản > 100,000...")
        affected_tickers.add("VNINDEX")
        affected_tickers.add("HNX-INDEX")
        
        for t in active_set:
            try:
                df_t = storage.load_ticker_data(t)
                if df_t is not None and not df_t.empty and 'Volume' in df_t.columns:
                    avg_vol_10 = df_t['Volume'].tail(10).mean()
                    if avg_vol_10 > 100000:
                        affected_tickers.add(t)
            except Exception:
                pass

    logger.info(f"--- ĐANG TÍNH TOÁN CHỈ BÁO VÀ PHÂN TÍCH CHO {len(affected_tickers)} MÃ ---")

    
    data_dict = {}
    analysis_cache = {}
    items_to_recompute = []
    
    # Load historical data for affected tickers
    for t in affected_tickers:
        df_full = storage.load_ticker_data(t)
        if df_full is not None:
            data_dict[t] = df_full
            items_to_recompute.append((t, df_full))
            
    # Đảm bảo luôn có VNINDEX và HNX-INDEX để xuất biểu đồ và tính chỉ báo đầy đủ
    for idx_symbol in ["VNINDEX", "HNX-INDEX"]:
        if idx_symbol not in data_dict:
            idx_df = storage.load_ticker_data(idx_symbol)
            if idx_df is not None:
                data_dict[idx_symbol] = idx_df
            
    total = len(items_to_recompute)
    if total > 0:
        batch_size = 10
        batches = [items_to_recompute[i:i + batch_size] for i in range(0, total, batch_size)]
        num_workers = min((os.cpu_count() or 4) * 2, 16)
        
        logger.info(f"[*] Khởi chạy ThreadPoolExecutor với {num_workers} workers...")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(analyze_batch_worker, b) for b in batches]
            completed_count = 0
            for future in as_completed(futures):
                batch_results = future.result()
                for ticker, res in batch_results:
                    if res:
                        analysis_cache[ticker] = res
                        if 'df' in res:
                            data_dict[ticker] = res['df']
                        storage.save_indicators(ticker, res['df'])
                        storage.save_analysis(ticker, res)
                completed_count += len(batch_results)
                if completed_count % 200 == 0 or completed_count == total:
                    logger.info(f"      ... Tiến độ: {completed_count}/{total} mã...")
                    
    # 6. Post-Integrity Check (Hậu Kiểm)
    missing_after = []
    for t in affected_tickers:
        df_check = data_dict.get(t)
        if df_check is not None and ('HK_NW' not in df_check.columns or 'T2_SMA' not in df_check.columns):
            missing_after.append(t)
            
    if missing_after:
        logger.warning(f"⚠️ HẬU KIỂM: Phát hiện {len(missing_after)} mã thiếu Trending. Đang xử lý bù...")
        for t in missing_after:
            try:
                df_final = enrich_dataframe(data_dict[t])
                data_dict[t] = df_final
                storage.save_indicators(t, df_final)
            except Exception as ex:
                pass
        logger.info("✅ Hậu kiểm hoàn tất.")
    else:
        logger.info("✅ Tuyệt vời! 100% mã đã đầy đủ chỉ số Trending.")

    # 7. Calculate Market Breadth (Time-series)
    is_failed_data = vietstock_status in ["LIMITED", "ERROR", "NO_DATA"]
    if not is_failed_data:
        logger.info("📊 Đang tính toán dữ liệu Độ rộng Thị trường...")
        full_data_dict = data_dict.copy()
        missing_from_cache = [t for t in current_reg if t not in full_data_dict]
        if missing_from_cache:
            logger.info(f"📊 Đang tải thêm {len(missing_from_cache)} mã từ storage để tính toán độ rộng...")
            def load_one(t):
                df = storage.load_ticker_data(t)
                return t, df
            with ThreadPoolExecutor(max_workers=16) as executor:
                results = executor.map(load_one, missing_from_cache)
                for t, df in results:
                    if df is not None:
                        full_data_dict[t] = df
        market_breadth_data = compute_market_breadth(full_data_dict)
    else:
        logger.info("📊 Dữ liệu đầu vào bị lỗi/thiếu. Giữ nguyên dữ liệu Độ rộng Thị trường cũ để tránh sai sót.")
        market_breadth_data = existing_market_breadth
    
    # 8. Filter Tickers & Build Output Structure
    logger.info("🔍 Đang tổng hợp các bộ lọc và luật tùy chỉnh...")
    tickers_analysis = []
    
    categories_meta = {
        "ACCUMULATION": "Tích lũy",
        "PERFECT_MA": "Perfect MA (Xu hướng tăng mạnh)",
        "HEIKIN_BUY": "Heikin Buy (Tín hiệu mua Heikin Ashi)",
        "UPCLOUD": "UpCloud (Xu hướng tăng trên mây)",
        "WHITE_ADX": "ADX Trắng (Đầu chu kỳ xu hướng)",
        "MARK_MINERVINI": "Mark Minervini (MINERVINI)",
        "EARLY": "Điểm mua EARLY (Mua sớm)",
        "ADD_1": "Điểm mua gia tăng 1 (ADD_1)",
        "ADD_2": "Điểm mua gia tăng 2 (ADD_2)",
        "STRONG": "Điểm mua MẠNH (STRONG)"
    }
    
    rules_meta = {k: v["label"] for k, v in CUSTOM_RULES.items()}
    
    # Pre-compiled list of tickers for simple category views
    filtered_results = {cat: [] for cat in categories_meta.keys()}
    for rule_key in rules_meta.keys():
        filtered_results[rule_key] = []
        
    df_vn = data_dict.get("VNINDEX")
    df_vn_indexed = df_vn.set_index('Date') if df_vn is not None and not df_vn.empty else None

    for ticker, data in list(analysis_cache.items()):
        df = data.get("df")
        if df is None or df.empty:
            continue
            
        # Calculate RS14 and RS52 against VNINDEX
        if df_vn_indexed is not None and 'Date' in df.columns:
            try:
                bench_close = df['Date'].map(df_vn_indexed['Close']).ffill().bfill()
                rs_raw = df['Close'] / (bench_close + 1e-10)
                
                # RS52: 52 weeks = 260 bars
                rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
                rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
                df['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)
                
                # RS14: 14 weeks = 70 bars
                rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
                rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
                df['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)
            except Exception as e_rs:
                logger.warning(f"Error calculating RS for {ticker}: {e_rs}")
            
        # Get price indicators
        current_vol = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
        # Allow low-volume stocks on web search as requested by user
        # if current_vol < 20000:
        #     continue
            
        res = data.get("adv") or {}
        accum = data.get("accum") or {}
        ma_trend = data.get("ma_trend") or {}
        val = data.get("valuation") or {}
        
        current_p = float(df['Close'].iloc[-1]) * 1000
        ep = val.get("price", 0)
        tp = val.get("tp1", 0)
        tp2 = val.get("tp2", 0)
        sl = val.get("cutloss_partial", 0)
        rr_ratio = val.get("rr_ratio", 0)
        val_score = val.get("risk_score", 0)
        risk_pct = val.get("risk_pct", 0)
        action = val.get("action", "WAIT")
        
        # Evaluate matched categories
        matched_categories = []
        
        if accum.get("is_accumulation", False):
            matched_categories.append("ACCUMULATION")
            
        if ma_trend.get("is_perfect_uptrend", False):
            matched_categories.append("PERFECT_MA")
            
        # Heikin Buy
        buy_2 = False
        if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
            buy_2 = df.get('HK_BuySignal', pd.Series([False])).tail(2).any() or df.get('HK_BuyManh', pd.Series([False])).tail(2).any()
        if buy_2:
            matched_categories.append("HEIKIN_BUY")
            
        # UpCloud
        if len(df) > 0 and 'High' in df.columns and 'Low' in df.columns:
            last = df.iloc[-1]
            current_price = last['Close']
            span_a = last.get('SpanA', 0)
            span_b = last.get('SpanB', 0)
            tenkan = last.get('Tenkan', 0)
            kijun = last.get('Kijun', 0)
            ma10 = last.get('MA10', 0)
            ma20 = last.get('MA20', 0)
            
            future_span_a = (tenkan + kijun) / 2
            h52 = df['High'].iloc[-52:].max() if len(df) >= 52 else df['High'].max()
            l52 = df['Low'].iloc[-52:].min() if len(df) >= 52 else df['Low'].min()
            future_span_b = (h52 + l52) / 2
            
            c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
            c2 = (future_span_a > future_span_b)
            c3 = (tenkan > kijun)
            c4 = (ma10 > ma20)
            if c1 and c2 and c3 and c4:
                matched_categories.append("UPCLOUD")
                
        # White ADX
        adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
        if adx_color == "WHITE":
            matched_categories.append("WHITE_ADX")
            
        # Mark Minervini
        if check_mark_minervini(df):
            matched_categories.append("MARK_MINERVINI")
            
        # Entry Type (EARLY, ADD_1, ADD_2, STRONG)
        entry_type = res.get("entry_type")
        if entry_type in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
            matched_categories.append(entry_type)
            
        # Evaluate matched custom rules
        matched_rules = []
        for rule_key, r_def in CUSTOM_RULES.items():
            try:
                if r_def["func"](df):
                    matched_rules.append(rule_key)
            except Exception:
                pass
                
        # VSA Analysis – đọc từ cache đã tính trong worker (không tính lại)
        vsa_res = analysis_cache.get(ticker, {}).get("vsa_cached") or analysis_cache.get(ticker, {}).get("vsa") or {}
        if not vsa_res:
            from tinvest.vsa_engine import analyze_vsa
            vsa_res = analyze_vsa(df)
        vsa_dominant = vsa_res.get("dominant", "neutral")
        vsa_score = vsa_res.get("score", 0)

        # MCDX Analysis – đọc từ cache đã tính trong worker (không tính lại)
        mcdx_eval = analysis_cache.get(ticker, {}).get("mcdx_eval_cached") or {}
        if not mcdx_eval:
            from tinvest.mcdx_engine import evaluate_mcdx_rules
            mcdx_eval = evaluate_mcdx_rules(df)
        
        banker_val = float(df['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df.columns else 0.0
        hot_val = float(df['MCDX_HotMoney'].iloc[-1]) if 'MCDX_HotMoney' in df.columns else 0.0
        
        banker_aligned = banker_val
        hot_aligned = min(20.0 - banker_aligned, hot_val)
        retailer_aligned = max(0.0, 20.0 - banker_aligned - hot_val)
        
        banker_pct = round((banker_aligned / 20.0) * 100, 1)
        hot_pct = round((hot_aligned / 20.0) * 100, 1)
        retailer_pct = round((retailer_aligned / 20.0) * 100, 1)
        
        # History (last 30 trading days) for mini charts
        recent_df = df.tail(30)
        history = {
            "dates": [pd.to_datetime(d).strftime("%Y-%m-%d") if not pd.isna(d) else "N/A" for d in recent_df['Date']],
            "closes": [float(c) * 1000 for c in recent_df['Close']],
            "volumes": [int(v) for v in recent_df['Volume']]
        }

        # Generate detailed text report
        try:
            close_26 = df['Close'].iloc[-26] if len(df) > 26 else df['Close'].iloc[0]
            heatmap_eval_val = evaluate_heatmap(df)
            
            report_input = {
                "ticker": ticker.upper(),
                "price": float(df['Close'].iloc[-1]),
                "date": pd.to_datetime(df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(df['Date'].iloc[-1]) else "N/A",
                "ichi": data.get("ichi"),
                "vsa": data.get("vsa"),
                "ma_trend": data.get("ma_trend"),
                "adv": data.get("adv"),
                "accum": data.get("accum"),
                "valuation": val,
                "state_rules": data.get("state_rules"),
                "close_26": float(close_26),
                "ma20": float(df['MA20'].iloc[-1]) if 'MA20' in df.columns else float(df['Close'].rolling(20).mean().iloc[-1]),
                "ma50": float(df['MA50'].iloc[-1]) if 'MA50' in df.columns else float(df['Close'].rolling(50).mean().iloc[-1]),
                "heatmap_eval": heatmap_eval_val,
                "mcdx_eval": mcdx_eval
            }
            report_text = format_report(report_input)
        except Exception as e_rep:
            logger.warning(f"⚠️ Không thể sinh báo cáo chi tiết cho mã {ticker}: {e_rep}")
            report_text = f"Không có báo cáo chi tiết cho mã {ticker}."

        # Portfolio Engine compatibility indicators
        mcdx_banker = float(df['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df.columns else 10
        prev_mcdx_banker = float(df['MCDX_Banker'].iloc[-2]) if len(df) > 1 and 'MCDX_Banker' in df.columns else mcdx_banker
        adx = float(df['ADX'].iloc[-1]) if 'ADX' in df.columns else 20
        ha_color = str(df['HA_Color'].iloc[-1]) if 'HA_Color' in df.columns else 'Green'
        ma20 = float(df['MA20'].iloc[-1]) if 'MA20' in df.columns else current_p / 1000
        vol = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
        vol_avg = float(df['AvgVolume20'].iloc[-1]) if 'AvgVolume20' in df.columns else vol
        
        mcdx_weak = (mcdx_banker < prev_mcdx_banker) and (mcdx_banker < 15)
        adx_low = adx < 20
        heikin_red = (ha_color.lower() == 'red')
        price_below_ma20 = (current_p / 1000) < ma20
        tech_weak = mcdx_weak or adx_low or heikin_red or price_below_ma20
        
        sideways_near_res = False
        p_res_vnd = float(val.get('r1', 0)) * 1000
        if len(df) >= 4 and p_res_vnd > 0:
            recent_highs = df['High'].iloc[-4:].max() * 1000
            recent_lows = df['Low'].iloc[-4:].min() * 1000
            recent_vols = df['Volume'].iloc[-4:].mean()
            if recent_highs >= p_res_vnd * 0.98 and (recent_highs - recent_lows)/recent_lows < 0.05 and recent_vols > vol_avg:
                sideways_near_res = True
                
        # Determine State Signal
        state_val = val.get("state", "NONE")
        sig_map = {
            "STRONG": "Mua mạnh (Trend Leader)", 
            "ADD_2": "Gia tăng vị thế 2 (Confirm)",
            "ADD_1": "Gia tăng vị thế 1 (Pullback)", 
            "EARLY": "Mua sớm (Thăm dò)", 
            "NONE": "Chưa có tín hiệu dứt khoát"
        }
        holding_sig = sig_map.get(state_val, "Chưa có tín hiệu dứt khoát")
        
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
        realtime_sig = rt_sig_map.get(data.get("state_rules", {}).get("signal", ""), "")
        state_signal = (realtime_sig if realtime_sig else holding_sig).upper()

        # Safely handle NaN values for integers
        safe_int = lambda x: int(x) if (x is not None and not pd.isna(x)) else 0
        
        avg_vol_raw = df['AvgVolume10'].iloc[-1] if 'AvgVolume10' in df.columns else (df['Volume'].rolling(10).mean().iloc[-1] if len(df) >= 10 else current_vol)

        # Create ticker record
        ticker_record = {
            "Ticker": ticker,
            "Price": safe_int(current_p),
            "Volume": safe_int(current_vol),
            "AvgVolume10": safe_int(avg_vol_raw),
            "Entry": int(ep * 1000) if ep > 0 else None,
            "Target": int(tp * 1000) if tp > 0 else None,
            "Target2": int(tp2 * 1000) if tp2 > 0 else None,
            "ReportText": report_text,
            "StopLoss": int(sl * 1000) if sl > 0 else None,
            "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",
            "RiskScore": int(val_score),
            "RiskPct": float(risk_pct),
            "Action": action,
            "Categories": matched_categories,
            "Rules": matched_rules,
            
            # Extended attributes for lookup
            "CutlossFull": int(val.get("cutloss_full", 0) * 1000) if val.get("cutloss_full", 0) > 0 else None,
            "TrailingStop": int(val.get("trailing_stop", 0) * 1000) if val.get("trailing_stop", 0) > 0 else None,
            "OpportunityScore": int(val.get("opp_score", 0)),
            "OpportunityDesc": str(val.get("opp_desc", "N/A")),
            "SafetyRating": int(val.get("topup_safety", 0)),
            "TopupPrice": int(val.get("topup_price", 0) * 1000) if val.get("topup_price", 0) > 0 else None,
            "TopupDesc": str(val.get("topup_desc", "N/A")),
            "AccumulationQuality": str(accum.get("base_quality", "NONE")),
            "AccumulationNotes": accum.get("notes", []),
            "AccumulationRangePct": float(accum.get("range_pct", 0.0)),
            "ReadyToBreak": bool(accum.get("ready_to_break", False)),
            
            # Portfolio Engine helpers
            "Support1": int(val.get("s1", 0) * 1000) if val.get("s1", 0) > 0 else None,
            "Support2": int(val.get("s2", 0) * 1000) if val.get("s2", 0) > 0 else None,
            "Resistance1": int(val.get("r1", 0) * 1000) if val.get("r1", 0) > 0 else None,
            "Resistance2": int(val.get("r2", 0) * 1000) if val.get("r2", 0) > 0 else None,
            "TrendStatus": str(ma_trend.get("trend_status", "Sideway")),
            "TechWeak": bool(tech_weak),
            "SidewaysNearRes": bool(sideways_near_res),
            "StateSignal": state_signal,
            "AntiTrap": bool(data.get("state_rules", {}).get("metrics", {}).get("anti_trap_block", False)),
            "AvoidEntry": bool(data.get("state_rules", {}).get("avoid_entry", False)),
            
            # MCDX Cash Flow
            "MCDX": {
                "banker_pct": banker_pct,
                "hot_pct": hot_pct,
                "retailer_pct": retailer_pct,
                "status": str(mcdx_eval.get("status", "N/A")),
                "action": str(mcdx_eval.get("action", "N/A")),
                "details": str(mcdx_eval.get("details", "N/A"))
            },
            
            # Technical Diagnostics Table
            "Diagnostics": {
                "rsi": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("status", "N/A")), 
                        "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("action", "N/A"))},
                "macd": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("status", "N/A")), 
                         "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("action", "N/A"))},
                "adx": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("status", "N/A")), 
                        "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("action", "N/A"))},
                "ichimoku": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("status", "N/A")), 
                             "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("action", "N/A"))},
                "ma": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("status", "N/A")), 
                       "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("action", "N/A"))},
                "vsa": {"status": f"VSA Dominant: {vsa_dominant.upper()}", 
                        "action": f"VSA Score: {vsa_score}/4"}
            },
            
            # History for Chart.js
            "History": history
        }
        
        tickers_analysis.append(ticker_record)

    # Merge existing and newly analyzed
    merged_tickers_analysis = existing_tickers_analysis.copy()
    for record in tickers_analysis:
        merged_tickers_analysis[record["Ticker"]] = record
        
    # Remove recalculated tickers that were filtered out or failed
    newly_analyzed_symbols = {r["Ticker"] for r in tickers_analysis}
    for t in affected_tickers:
        if t not in newly_analyzed_symbols and t in merged_tickers_analysis:
            del merged_tickers_analysis[t]
            
    # Final sorted tickers list (only active registry tickers, excluding delisted/warrants)
    current_reg = storage.get_active_registry() or set()
    tickers_analysis = [r for r in merged_tickers_analysis.values() if r["Ticker"] in current_reg]
    tickers_analysis.sort(key=lambda x: (
        1 if x.get("Action") == "BUY" else (2 if x.get("Action") == "WAIT" else 3),
        x.get("Ticker", "")
    ))
    
    # Rebuild pre-compiled categories/rules lists
    filtered_results = {cat: [] for cat in categories_meta.keys()}
    for rule_key in rules_meta.keys():
        filtered_results[rule_key] = []
        
    for r in tickers_analysis:
        t_symbol = r["Ticker"]
        for cat in r.get("Categories", []):
            if cat in filtered_results:
                filtered_results[cat].append(t_symbol)
        for rule in r.get("Rules", []):
            if rule in filtered_results:
                filtered_results[rule].append(t_symbol)

    # Calculate Market Indices Analysis
    market_indices = existing_market_indices.copy()
    breadth_ma20 = 50.0
    breadth_ma50 = 50.0
    if market_breadth_data and "MA20" in market_breadth_data and market_breadth_data["MA20"]:
        breadth_ma20 = market_breadth_data["MA20"][-1]
    if market_breadth_data and "MA50" in market_breadth_data and market_breadth_data["MA50"]:
        breadth_ma50 = market_breadth_data["MA50"][-1]

    for index_ticker in ["VNINDEX", "HNX-INDEX"]:
            
        idx_df = data_dict.get(index_ticker)
        if idx_df is not None and not idx_df.empty:
            try:
                from tinvest.market_engine import analyze_market_index, analyze_momentum_divergence
                from tinvest.ichimoku_engine import analyze_ichimoku
                from tinvest.vsa_engine import analyze_vsa
                from tinvest.ma_engine import analyze_ma_trend
                from tinvest.data_loader import enrich_dataframe
                from tinvest.advanced_entry import classify_entry
                from tinvest.valuation_engine import evaluate_stock_valuation
                from tinvest.state_engine import evaluate_state_rules
                from tinvest.mcdx_engine import evaluate_mcdx_rules
                
                df_rich = enrich_dataframe(idx_df.copy())
                mom = analyze_momentum_divergence(idx_df)
                signals = classify_entry(df_rich)
                val = evaluate_stock_valuation("INDEX", df_rich, signals)
                sr = {"s1": float(val.get("s1", 0)), "s2": float(val.get("s2", 0)),
                      "r1": float(val.get("r1", 0)), "r2": float(val.get("r2", 0))}
                if "r3" in val:
                    sr["r3"] = float(val["r3"])
                
                state_rules = evaluate_state_rules(df_rich)
                heatmap_eval = evaluate_heatmap(df_rich)
                mcdx_eval = evaluate_mcdx_rules(df_rich)
                
                res_regime = analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
                
                # Save computed indicators to storage and cache so it is available for chart exporter
                data_dict[index_ticker] = df_rich
                storage.save_indicators(index_ticker, df_rich)
                analysis_cache[index_ticker] = {'df': df_rich}
                
                st_pri_raw = state_rules.get('primary', '')
                ftd_on = res_regime.get('ftd_active', False)
                dist_n = res_regime.get('distribution_count', 0)
                
                alloc = "10-30%"
                alloc_note = "Chưa xác định rõ"
                
                if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                    if ftd_on and dist_n <= 2:
                        alloc = "80-100%"
                        alloc_note = "Xu hướng mạnh, FTD xác nhận, phân phối ít -> ALL IN được"
                    elif ftd_on and dist_n > 2:
                        alloc = "60-80%"
                        alloc_note = "Xu hướng tăng nhưng phân phối đang tăng -> vẫn giữ tỷ trọng cao nhưng sẵn sàng hạ"
                    else:
                        alloc = "60-80%"
                        alloc_note = "Xu hướng tăng nhưng chưa có FTD xác nhận -> chưa nên full"
                elif st_pri_raw == 'WEAK_UPTREND':
                    if ftd_on:
                        alloc = "50-70%"
                        alloc_note = "Tăng yếu dần nhưng FTD còn sống -> canh giữ, giảm dần nếu chớm gãy"
                    else:
                        alloc = "30-50%"
                        alloc_note = "Tăng yếu dần, không có FTD -> cẩn thận chuyển giao"
                elif st_pri_raw in ['RANGE', 'SQUEEZE', 'SIDEWAY', 'NEUTRAL']:
                    if ftd_on:
                        alloc = "50-70%"
                        alloc_note = "Đang tích lũy/chuyển giao trong nhịp hồi có FTD -> ưu tiên nắm giữ cổ phiếu Leader"
                    else:
                        alloc = "20-40%"
                        alloc_note = "Chưa rõ xu hướng, đang tích lũy/trung tính -> giữ tiền mặt chờ xác nhận"
                elif st_pri_raw == 'WEAK_DOWNTREND':
                    if ftd_on:
                        alloc = "40-60%"
                        alloc_note = "Nhịp điều chỉnh/nghỉ chân trong đà hồi phục có FTD -> CƠ HỘI GOM HÀNG"
                    elif dist_n >= 3:
                        alloc = "0-15%"
                        alloc_note = "Giảm nhẹ + phân phối nhiều -> RỦI RO CAO, BÁN HẠ TỶ TRỌNG gấp"
                    else:
                        alloc = "15-30%"
                        alloc_note = "Điều chỉnh bình thường -> giữ ít, chờ xem có giữ nền không"
                elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START']:
                    # Kiểm tra: FTD còn sống + regime đang RECOVERY → đây là nền MA giảm dài hạn,
                    # không phải gãy trend mới. Chỉ bán sạch khi FTD đã bị hủy.
                    _reg_now = res_regime.get('regime', 'UNKNOWN')
                    if ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']:
                        alloc = "30-50%"
                        alloc_note = "Nền MA dài hạn còn giảm nhưng FTD đang kích hoạt + regime RECOVERY -> Thăm dò, KHÔNG bán sạch"
                    else:
                        alloc = "0-10%"
                        alloc_note = "Gãy xu hướng xác nhận (không có FTD bảo vệ) -> BÁN SẠCH, RA NGOÀI"
                elif st_pri_raw == 'RECOVERY':
                    if ftd_on:
                        alloc = "50-75%"
                        alloc_note = "Hồi phục ổn định có FTD -> ưu tiên nắm giữ & quan sát điểm gia tăng"
                    else:
                        alloc = "20-40%"
                        alloc_note = "Hồi phục kỹ thuật, chưa có FTD -> chỉ nên test tỷ trọng nhỏ"
                else:
                    reg_str = res_regime.get('regime', 'UNKNOWN')
                    if reg_str == "STABLE_RECOVERY":
                        alloc, alloc_note = "50-75%", "Hồi phục ổn định trên MA20"
                    elif reg_str == "RECOVERY":
                        alloc, alloc_note = "30-50%", "Đang nỗ lực hồi phục"
                    else:
                        alloc = "10-30%"
                        alloc_note = "Chưa xác định rõ -> giữ ít phòng thủ"
                        
                st_avoid = state_rules.get('avoid_entry', False)
                if st_avoid:
                    if st_pri_raw in ['UPTREND', 'UPTREND_START', 'WEAK_UPTREND', 'RECOVERY'] and ftd_on:
                        if alloc == "80-100%": alloc = "60-80%"
                        elif alloc == "60-80%": alloc = "40-60%"
                        elif alloc == "50-70%": alloc = "30-50%"
                        elif alloc == "50-75%": alloc = "40-60%"
                        alloc_note = "⚠️ CẢNH BÁO: Thị trường quá nhiệt / MCDX phân phối -> Ưu tiên nắm giữ, hạn chế mua đuổi"
                    elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START', 'MARKET_WEAKENING']:
                        # Chỉ bán sạch nếu không có FTD bảo vệ; nếu FTD còn sống trong RECOVERY thì giữ nguyên alloc
                        _reg_now = res_regime.get('regime', 'UNKNOWN')
                        if not (ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']):
                            alloc = "0-10%"
                            alloc_note = "Bộ Lọc Rủi Ro đang BẬT + không có FTD -> CẤM MUA MỚI"
                    elif st_pri_raw in ['RECOVERY', 'WEAK_DOWNTREND'] and ftd_on:
                        # Đang hồi phục có FTD: không ép xuống 10-20%, hạ nhẹ thôi
                        if alloc not in ['0-10%', '10-20%']:
                            alloc_note = "⚠️ Bộ lọc rủi ro bật nhưng FTD còn sống -> Giữ thận trọng, hạn chế mua thêm"
                    else:
                        alloc = "10-20%"
                        alloc_note = "Thị trường lưỡng lự, bộ lọc rủi ro đang bật -> Tỷ trọng thấp"

                cleaned_sr = {k: float(v) for k, v in sr.items()}
                
                # Generate index report text
                try:
                    res_dict = {
                        "regime": {
                            "regime": str(res_regime.get("regime", "UNKNOWN")),
                            "action": str(res_regime.get("action", "WAIT")),
                            "price": float(idx_df['Close'].iloc[-1]),
                            "date": pd.to_datetime(idx_df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(idx_df['Date'].iloc[-1]) else "N/A",
                            "ftd_active": bool(res_regime.get("ftd_active", False)),
                            "ftd_date": str(res_regime.get("ftd_date", "N/A")),
                            "ftd_quality": str(res_regime.get("ftd_quality", "N/A")),
                            "ra_day": int(res_regime.get("ra_day", 0)),
                            "distribution_count": int(res_regime.get("distribution_count", 0)),
                        },
                        "momentum": mom,
                        "ichi": analyze_ichimoku(df_rich),
                        "vsa": analyze_vsa(df_rich),
                        "ma": analyze_ma_trend(df_rich),
                        "sr": cleaned_sr,
                        "sr_source": "SIGNAL" if (signals.get('entry_type', 'NONE') != 'NONE') else "PIVOT",
                        "signals": signals,
                        "valuation": val,
                        "state_rules": state_rules,
                        "heatmap_eval": heatmap_eval,
                        "elliott_eval": "N/A",
                        "mcdx_eval": mcdx_eval,
                        "date": pd.to_datetime(idx_df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(idx_df['Date'].iloc[-1]) else "N/A"
                    }
                    report_text = format_index_report(index_ticker, res_dict, prefix="")
                except Exception as e_idx_rep:
                    logger.warning(f"⚠️ Không thể sinh báo cáo chi tiết cho index {index_ticker}: {e_idx_rep}")
                    report_text = f"Không có báo cáo chi tiết cho index {index_ticker}."

                market_indices[index_ticker] = {
                    "price": float(idx_df['Close'].iloc[-1]),
                    "ReportText": report_text,
                    "date": pd.to_datetime(idx_df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(idx_df['Date'].iloc[-1]) else "N/A",
                    "regime": str(res_regime.get("regime", "UNKNOWN")),
                    "action": str(res_regime.get("action", "WAIT")),
                    "ftd_active": bool(res_regime.get("ftd_active", False)),
                    "ftd_date": str(res_regime.get("ftd_date", "N/A")),
                    "ftd_quality": str(res_regime.get("ftd_quality", "N/A")),
                    "ra_day": int(res_regime.get("ra_day", 0)),
                    "distribution_count": int(res_regime.get("distribution_count", 0)),
                    "support_resistance": cleaned_sr,
                    "alloc": str(alloc),
                    "alloc_note": str(alloc_note),
                    "diagnostics": {
                        "ma": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("status", "N/A")), 
                               "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("action", "N/A"))},
                        "ichimoku": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("status", "N/A")), 
                                     "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("action", "N/A"))},
                        "rsi": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("status", "N/A")), 
                                "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("action", "N/A"))},
                        "macd": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("status", "N/A")), 
                                 "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("action", "N/A"))},
                        "adx": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("status", "N/A")), 
                                "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("action", "N/A"))}
                    },
                    "heatmap_eval": str(heatmap_eval),
                    "mcdx_eval": {
                        "status": str(mcdx_eval.get("status", "N/A")),
                        "action": str(mcdx_eval.get("action", "N/A")),
                        "details": str(mcdx_eval.get("details", "N/A")),
                        "banker_pct": float(df_rich['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df_rich.columns else 0.0,
                        "hot_pct": float(df_rich['MCDX_Hot'].iloc[-1]) if 'MCDX_Hot' in df_rich.columns else 0.0,
                        "retailer_pct": float(df_rich['MCDX_Retailer'].iloc[-1]) if 'MCDX_Retailer' in df_rich.columns else 0.0
                    },
                    "state_rules": {
                        "primary": str(state_rules.get('primary', 'N/A')),
                        "secondary": str(state_rules.get('secondary', 'N/A')),
                        "signal": str(state_rules.get('signal', 'N/A')),
                        "regime": str(state_rules.get('regime', 'N/A')),
                        "confidence": int(state_rules.get('confidence', 0)),
                        "avoid_entry": bool(state_rules.get('avoid_entry', False)),
                        "adx": float(state_rules.get('metrics', {}).get('adx', 0.0)),
                        "macd_hist": float(state_rules.get('metrics', {}).get('hist', 0.0)),
                        "trend_bias": float(state_rules.get('metrics', {}).get('trend_bias', 0.0)),
                        "vol_spike": bool(state_rules.get('metrics', {}).get('vol_spike', False)),
                        "vol_dry": bool(state_rules.get('metrics', {}).get('vol_dry', False)),
                        "strong_trend": bool(state_rules.get('metrics', {}).get('strong_trend', False)),
                        "breakout_up": bool(state_rules.get('metrics', {}).get('breakout_up', False)),
                        "dist_ma20": float(state_rules.get('metrics', {}).get('dist_ma20', 0.0)),
                        "rsi": float(state_rules.get('metrics', {}).get('rsi', 50.0))
                    },
                    "alloc_note": str(alloc_note)
                }
            except Exception as e_idx:
                logger.error(f"⚠️ Lỗi phân tích Index {index_ticker}: {e_idx}")

    # 9. Output to JSON file
    output_dir = os.path.join(base_path, "Output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "analysis_results.json")
    
    # ICT current time format
    from datetime import timezone
    ict_time = datetime.now(timezone.utc) + timedelta(hours=7)
    last_update_str = ict_time.strftime("%Y-%m-%d %H:%M:%S")

    # Đếm số mã có dữ liệu thực (có giá close hợp lệ)
    stocks_updated_count = sum(
        1 for v in tickers_analysis
        if isinstance(v, dict) and v.get("Price") not in (None, 0, "")
    )
    
    final_output = {
        "last_update": last_update_str,
        "vietstock_status": vietstock_status,
        "stocks_updated_count": stocks_updated_count,
        "market_breadth": market_breadth_data,
        "market_indices": market_indices,
        "categories_meta": categories_meta,
        "rules_meta": rules_meta,
        "tickers_analysis": tickers_analysis,
        "filtered_results": filtered_results
    }
    
    def clean_nans(obj):
        import math
        if isinstance(obj, dict):
            return {k: clean_nans(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_nans(x) for x in obj]
        elif isinstance(obj, float):
            return 0.0 if (math.isnan(obj) or math.isinf(obj) or obj != obj) else obj
        try:
            import numpy as np
            if isinstance(obj, (np.floating, np.float32, np.float64)):
                if np.isnan(obj) or np.isinf(obj):
                    return 0.0
                return float(obj)
            elif isinstance(obj, (np.integer, np.int32, np.int64)):
                return int(obj)
        except ImportError:
            pass
        return obj

    final_output = clean_nans(final_output)

    logger.info(f"[*] Đang xuất file kết quả ra: {output_file}...")
    import tempfile
    temp_fd, temp_path = tempfile.mkstemp(dir=output_dir, prefix="analysis_results_tmp_")
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
        if os.path.exists(output_file):
            os.replace(temp_path, output_file)
        else:
            os.rename(temp_path, output_file)
    except Exception as e_write:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
        raise e_write
        
    logger.info(f"✅ HOÀN TẤT CẬP NHẬT! Đã xuất {len(tickers_analysis)} mã cổ phiếu.")
    
    # 10. Export History JSON for each ticker (used by web charts — replaces PNG exports)
    logger.info("📊 Đang xuất dữ liệu lịch sử JSON cho Web Dashboard (thay thế xuất ảnh PNG)...")
    export_ticker_history_json(data_dict, analysis_cache, output_dir)
    
    logger.info("==================================================")



def run_csv_import(csv_paths):

    from pathlib import Path
    from tinvest.data_loader import _normalize_columns, _clean_dataframe
    
    logger.info("==================================================")
    logger.info("🚀 BẮT ĐẦU NẠP DỮ LIỆU TỪ FILE CSV")
    logger.info("==================================================")
    
    storage = StorageManager()
    
    # 1. Thu thập tất cả các file CSV
    files_to_process = []
    for path in csv_paths:
        p = Path(path)
        if p.is_dir():
            # Quét tất cả file .csv trong thư mục
            files_to_process.extend(list(p.glob("**/*.csv")) + list(p.glob("*.csv")))
        elif p.is_file() and p.suffix.lower() == ".csv":
            files_to_process.append(p)
        else:
            # Check if it matches a wildcard or is just a path string
            import glob
            matched = glob.glob(path)
            for m in matched:
                mp = Path(m)
                if mp.is_file() and mp.suffix.lower() == ".csv":
                    files_to_process.append(mp)
                    
    # Loại bỏ trùng lặp và giữ thứ tự
    seen = set()
    unique_files = []
    for f in files_to_process:
        abs_path = f.resolve()
        if abs_path not in seen:
            seen.add(abs_path)
            unique_files.append(f)
            
    if not unique_files:
        logger.error("❌ Không tìm thấy file CSV hợp lệ nào để xử lý.")
        sys.exit(1)

    # Sort files chronologically so that newer files are processed last (overwriting older values in drop_duplicates)
    def get_file_sort_key(p):
        import re
        import os
        m = re.search(r"Upto(\d{2})\.(\d{2})\.(\d{4})", p.name, re.IGNORECASE)
        if m:
            day, month, year = map(int, m.groups())
            return (1, year, month, day)
        try:
            return (0, os.path.getmtime(str(p)))
        except:
            return (0, 0)

    unique_files.sort(key=get_file_sort_key)
        
    logger.info(f"[*] Tìm thấy {len(unique_files)} file CSV để xử lý...")
    
    ticker_dfs = {}
    skipped_3char = 0
    
    for f in unique_files:
        try:
            df_raw = pd.read_csv(f)
            df_norm = _normalize_columns(df_raw)
            
            # Tên file suy luận mã nếu không có cột Ticker
            if "Ticker" not in df_norm.columns:
                potential_ticker = f.stem.upper().split('_')[0].split(' ')[0]
                is_idx = ("VNINDEX" in potential_ticker) or ("HNX" in potential_ticker) or ("HAINDEX" in potential_ticker)
                if (len(potential_ticker) == 3 and potential_ticker.isalnum()) or is_idx:
                    df_norm["Ticker"] = potential_ticker
                    logger.info(f"   + Nhận diện mã '{potential_ticker}' từ tên file: {f.name}")
                else:
                    logger.warning(f"   ! Tên file '{f.name}' không phải mã cổ phiếu hợp lệ (3 ký tự hoặc Index). Bỏ qua.")
                    continue
            
            # Xử lý gộp theo nhóm Ticker vào dictionary
            grouped = df_norm.groupby("Ticker")
            for ticker_val, group in grouped:
                t = str(ticker_val).upper().strip()
                
                # Bộ lọc 3 ký tự (hoặc index)
                is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
                if not (len(t) == 3 and t.isalnum()) and not is_idx:
                    skipped_3char += 1
                    continue
                    
                sub_df = group.drop(columns=["Ticker"]).copy()
                if t not in ticker_dfs:
                    ticker_dfs[t] = []
                ticker_dfs[t].append(sub_df)
                    
        except Exception as e:
            logger.error(f"   ! Lỗi đọc/chuẩn hóa file {f.name}: {e}")
            
    affected_tickers = set()
    skipped_old = 0
    loaded_count = 0
    
    logger.info(f"[*] Đang xử lý và gộp dữ liệu cho {len(ticker_dfs)} mã cổ phiếu...")
    
    for t, dfs in ticker_dfs.items():
        try:
            # Gộp tất cả các DataFrame của mã t
            combined_df = pd.concat(dfs, ignore_index=True)
            is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
            
            try:
                date_series = combined_df["Date"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                parsed = pd.Series(pd.NaT, index=combined_df.index)
                
                # Parse 8-digit YYYYMMDD values
                mask_8d = date_series.str.match(r"^\d{8}$") == True
                if mask_8d.any():
                    parsed[mask_8d] = pd.to_datetime(date_series[mask_8d], format="%Y%m%d", errors="coerce")
                    
                # Parse other valid date formats
                mask_other = ~mask_8d & (date_series.notna()) & (date_series != "") & (date_series.str.lower() != "nan")
                if mask_other.any():
                    parsed[mask_other] = pd.to_datetime(date_series[mask_other], format='mixed', dayfirst=False, errors="coerce")
                    
                combined_df["Date"] = parsed
                
                # Loại bỏ các dòng có Date lỗi (NaT)
                combined_df = combined_df.dropna(subset=["Date"])
                
                # Sắp xếp theo ngày tăng dần
                combined_df = combined_df.sort_values("Date").reset_index(drop=True)
                
                # Loại bỏ các dòng trùng lặp ngày, giữ lại dòng cuối cùng
                combined_df = combined_df.drop_duplicates(subset=["Date"], keep="last")
                
                # Làm sạch dữ liệu
                clean_sub = _clean_dataframe(combined_df, ticker=t)
                
                # Bộ lọc 30 ngày tương tự AICcode
                last_date = clean_sub['Date'].max()
                if (datetime.now() - last_date).days > 30 and not is_idx:
                    skipped_old += 1
                    continue
                    
                # Đồng bộ giá vào Storage
                storage.sync_prices(t, clean_sub, source='CSV')
                affected_tickers.add(t)
                loaded_count += 1
            except Exception as ex:
                logger.error(f"   ! Lỗi xử lý chi tiết mã {t}: {ex}")
                
        except Exception as e:
            logger.error(f"   ! Lỗi gộp dữ liệu mã {t}: {e}")
            
    if skipped_3char > 0:
        logger.info(f"[*] Đã bỏ qua {skipped_3char} mã không hợp lệ (không phải 3 ký tự hoặc Index).")
    if skipped_old > 0:
        logger.info(f"[*] Đã bỏ qua {skipped_old} mã có dữ liệu quá cũ (> 30 ngày không giao dịch).")
        
    if not affected_tickers:
        logger.error("❌ Không nạp được mã cổ phiếu hợp lệ nào từ CSV.")
        sys.exit(1)
        
    logger.info(f"✅ Hoàn tất nạp dữ liệu! Đã đồng bộ {loaded_count} mã vào Storage.")
    
    # Cập nhật Registry các mã hoạt động
    storage.save_active_registry(list(affected_tickers))
    
    # Tính toán toàn bộ chỉ báo và vẽ biểu đồ
    compute_and_export_dashboard(storage, affected_tickers, vietstock_status="CSV_MODE")

def compute_market_breadth(data_dict):
    """Ported market breadth computation from TinvestApp._update_breadth_from_cache."""
    if len(data_dict) < 5:
        logger.warning("⚠️ Không đủ dữ liệu để tính độ rộng (cần ít nhất 5 mã).")
        return {}
        
    # Get reference dates from VNINDEX
    vn_key = next((k for k in data_dict.keys() if "VNINDEX" in k), "VNINDEX")
    idx_df = data_dict.get(vn_key)
    if idx_df is None or idx_df.empty:
        logger.warning("⚠️ Không tìm thấy VNINDEX để làm mốc thời gian.")
        return {}
        
    all_dates = pd.to_datetime(idx_df['Date']).sort_values().unique()
    ref_date = all_dates[-1]
    
    breadth_dfs = []
    processed_count = 0
    
    for ticker, df_sub in data_dict.items():
        if ticker in ["VNINDEX", "HNXINDEX", "UPCOM", "VN30", "HNX30", "HAINDEX", "UPCOM-INDEX", "HNX-INDEX"]:
            continue
        if len(df_sub) < 50:
            continue
            
        try:
            if df_sub is None or df_sub.empty:
                continue
                
            # Skip if delisted/suspended > 30 days
            last_ticker_date = pd.to_datetime(df_sub['Date'].iloc[-1])
            if (ref_date - last_ticker_date).days > 30:
                continue
                
            df_sub_clean = df_sub.drop_duplicates(subset=['Date']).copy()
            df_sub_clean['Date'] = pd.to_datetime(df_sub_clean['Date'])
            df_sub_clean = df_sub_clean.sort_values('Date').reset_index(drop=True)
            
            ma10 = df_sub_clean['MA10'] if 'MA10' in df_sub_clean.columns else df_sub_clean['Close'].rolling(10).mean()
            ma20 = df_sub_clean['MA20'] if 'MA20' in df_sub_clean.columns else df_sub_clean['Close'].rolling(20).mean()
            ma50 = df_sub_clean['MA50'] if 'MA50' in df_sub_clean.columns else df_sub_clean['Close'].rolling(50).mean()
            
            tenkan = df_sub_clean['Tenkan'] if 'Tenkan' in df_sub_clean.columns else (df_sub_clean['High'].rolling(9).max() + df_sub_clean['Low'].rolling(9).min()) / 2
            kijun = df_sub_clean['Kijun'] if 'Kijun' in df_sub_clean.columns else (df_sub_clean['High'].rolling(26).max() + df_sub_clean['Low'].rolling(26).min()) / 2
            spana = df_sub_clean['SpanA'] if 'SpanA' in df_sub_clean.columns else ((tenkan + kijun) / 2).shift(26)
            spanb = df_sub_clean['SpanB'] if 'SpanB' in df_sub_clean.columns else ((df_sub_clean['High'].rolling(52).max() + df_sub_clean['Low'].rolling(52).min()) / 2).shift(26)
            
            raw_temp = pd.DataFrame()
            raw_temp['Date'] = df_sub_clean['Date']
            raw_temp['Close'] = df_sub_clean['Close']
            raw_temp['MA10'] = ma10
            raw_temp['MA20'] = ma20
            raw_temp['MA50'] = ma50
            raw_temp['Tenkan'] = tenkan
            raw_temp['Kijun'] = kijun
            raw_temp['SpanA'] = spana
            raw_temp['SpanB'] = spanb
            
            raw_temp = raw_temp.set_index('Date')
            
            temp = pd.DataFrame(index=all_dates)
            temp.index.name = 'Date'
            
            temp = temp.join(raw_temp, how='left')
            temp = temp.ffill()
            
            temp['Valid'] = temp['Close'].notna().astype(int)
            temp['>MA10'] = (temp['Valid'] & (temp['Close'] > temp['MA10']) & temp['MA10'].notna()).astype(int)
            temp['>MA20'] = (temp['Valid'] & (temp['Close'] > temp['MA20']) & temp['MA20'].notna()).astype(int)
            temp['>MA50'] = (temp['Valid'] & (temp['Close'] > temp['MA50']) & temp['MA50'].notna()).astype(int)
            
            kumo_top = temp[['SpanA', 'SpanB']].max(axis=1)
            temp['>CLOUD'] = (temp['Valid'] & (temp['Close'] > kumo_top) & temp['SpanA'].notna() & temp['SpanB'].notna()).astype(int)
            temp['>TENKAN'] = (temp['Valid'] & (temp['Close'] > temp['Tenkan']) & temp['Tenkan'].notna()).astype(int)
            temp['>KIJUN'] = (temp['Valid'] & (temp['Close'] > temp['Kijun']) & temp['Kijun'].notna()).astype(int)
            
            temp = temp.reset_index()
            breadth_dfs.append(temp)
            processed_count += 1
        except Exception as e:
            pass
            
    if breadth_dfs:
        all_breadth = pd.concat(breadth_dfs)
        grouped = all_breadth.groupby('Date').sum()
        valid_counts = grouped['Valid'].replace(0, 1)
        
        mb = pd.DataFrame()
        mb['%MA10'] = (grouped['>MA10'] / valid_counts) * 100
        mb['%MA20'] = (grouped['>MA20'] / valid_counts) * 100
        mb['%MA50'] = (grouped['>MA50'] / valid_counts) * 100
        mb['%ICHI_CLOUD'] = (grouped['>CLOUD'] / valid_counts) * 100
        mb['%ICHI_TENKAN'] = (grouped['>TENKAN'] / valid_counts) * 100
        mb['%ICHI_KIJUN'] = (grouped['>KIJUN'] / valid_counts) * 100
        mb = mb.sort_index()
        
        # Align VNINDEX Closes
        vn_closes = []
        vn_key = next((k for k in data_dict.keys() if "VNINDEX" in k), "VNINDEX")
        df_vn = data_dict.get(vn_key)
        if df_vn is not None and not df_vn.empty:
            df_vn_aligned = df_vn.copy()
            df_vn_aligned['Date'] = pd.to_datetime(df_vn_aligned['Date'])
            df_vn_aligned = df_vn_aligned.set_index('Date')
            
            for d in mb.index:
                if d in df_vn_aligned.index:
                    vn_closes.append(float(df_vn_aligned.loc[d, 'Close']))
                else:
                    vn_closes.append(vn_closes[-1] if vn_closes else 0.0)
        else:
            vn_closes = [0.0] * len(mb)

        logger.info(f"✅ Tính xong Độ rộng từ {processed_count} mã cổ phiếu.")
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in mb.index],
            "MA10": mb['%MA10'].round(2).tolist(),
            "MA20": mb['%MA20'].round(2).tolist(),
            "MA50": mb['%MA50'].round(2).tolist(),
            "ICHI_CLOUD": mb['%ICHI_CLOUD'].round(2).tolist(),
            "ICHI_TENKAN": mb['%ICHI_TENKAN'].round(2).tolist(),
            "ICHI_KIJUN": mb['%ICHI_KIJUN'].round(2).tolist(),
            "VNINDEX_Closes": vn_closes
        }
    return {}

def run_clear_cache():
    import shutil
    logger.info("==================================================")
    logger.info("🧹 BẮT ĐẦU XÓA TOÀN BỘ DỮ LIỆU CŨ (CLEAR DATA CACHE)")
    logger.info("==================================================")
    
    storage = StorageManager()
    count = storage.clear_computed_data()
    logger.info(f"✅ Đã xóa sạch {count} files trong data_storage.")
    
    # Clean Output directory
    output_dir = os.path.join(base_path, "Output")
    analysis_file = os.path.join(output_dir, "analysis_results.json")
    history_dir = os.path.join(output_dir, "history")
    
    deleted_output_files = 0
    if os.path.exists(analysis_file):
        try:
            os.remove(analysis_file)
            deleted_output_files += 1
            logger.info("   🗑️ Đã xóa Output/analysis_results.json")
        except Exception as e:
            logger.error(f"   ! Lỗi khi xóa {analysis_file}: {e}")
            
    if os.path.exists(history_dir):
        try:
            shutil.rmtree(history_dir)
            os.makedirs(history_dir, exist_ok=True)
            deleted_output_files += 1
            logger.info("   🗑️ Đã xóa thư mục Output/history/")
        except Exception as e:
            logger.error(f"   ! Lỗi khi xóa thư mục {history_dir}: {e}")
            
    logger.info(f"✅ Hoàn tất dọn dẹp {deleted_output_files} mục trong Output.")
    logger.info("==================================================")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hệ thống cập nhật dữ liệu tự động cho AIC PRO")
    parser.add_argument("--import-csv", nargs="+", help="Đường dẫn đến một hoặc nhiều file/thư mục CSV chứa dữ liệu lịch sử ban đầu")
    parser.add_argument("--clear-cache", action="store_true", help="Xóa sạch toàn bộ dữ liệu lưu trữ cũ và kết quả tính toán")
    args = parser.parse_args()
    
    if args.clear_cache:
        run_clear_cache()
    elif args.import_csv:
        run_csv_import(args.import_csv)
    else:
        run_sync_and_update()
