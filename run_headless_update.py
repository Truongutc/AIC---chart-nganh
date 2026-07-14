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
from AICcode import analyze_batch_worker, CUSTOM_RULES

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
    
    # 3. Detect Missing Dates (SSoT) — bắt kịp MỌI ngày còn thiếu kể từ lần
    # đồng bộ gần nhất (không chỉ đúng 1 phiên), để không bao giờ mất dữ liệu
    # ở giữa nếu action không chạy đều đặn (nghỉ lễ, lỗi kỹ thuật...).
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

            # Cập nhật số lượng CP lưu hành (Shares_i = MarketCap / Close) từng
            # mã — dùng làm trọng số vốn hóa khi tính chỉ số ngành (xem
            # tinvest/sector_index_engine.py). Chỉ lưu giá trị MỚI NHẤT, ghi
            # đè sticky mỗi lần cập nhật (không lưu vốn hóa lịch sử — không
            # cần thiết vì mỗi lần tính chỉ số ngành đều dùng lại đúng 1 giá
            # trị Shares_i hiện tại áp cho toàn bộ chuỗi giá đã điều chỉnh).
            if 'MarketCap' in df_day.columns:
                valid = df_day[(df_day['Close'] > 0) & (df_day['MarketCap'] > 0)]
                shares_map = (valid['MarketCap'] / valid['Close']).groupby(valid['Ticker']).last().to_dict()
                if shares_map:
                    storage.save_shares_outstanding(shares_map)

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
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    # 5. Tính chỉ số ngành (trung bình O/H/L/C, tổng Volume các mã thành viên
    # có dữ liệu trong ngày). Hệ thống không còn phân tích từng mã lẻ — thay vào
    # đó phân tích kỹ thuật đầy đủ (entry/target/stoploss/diagnostics/MCDX/tích lũy...)
    # được chạy trên chuỗi chỉ số ngành tổng hợp, giống hệt cách cổ phiếu đơn lẻ
    # từng được phân tích trước đây.
    from tinvest.sector_index_engine import compute_all_sector_indices, load_sector_groups
    sector_groups = load_sector_groups()
    computed_groups = compute_all_sector_indices(storage, active_registry=active_set)
    logger.info(f"--- ĐÃ TÍNH {len(computed_groups)}/{len(sector_groups)} CHỈ SỐ NGÀNH ---")

    affected_tickers = set(computed_groups) | {"VNINDEX", "HNX-INDEX"}
    logger.info(f"--- ĐANG TÍNH TOÁN CHỈ BÁO VÀ PHÂN TÍCH CHO {len(affected_tickers)} CHỈ SỐ NGÀNH/THỊ TRƯỜNG ---")

    data_dict = {}
    analysis_cache = {}
    items_to_recompute = []

    for t in affected_tickers:
        df_full = storage.load_ticker_data(t)
        if df_full is not None:
            data_dict[t] = df_full
            items_to_recompute.append((t, df_full))

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
                    logger.info(f"      ... Tiến độ: {completed_count}/{total} chỉ số...")

    # Post-Integrity Check (Hậu Kiểm)
    missing_after = []
    for t in affected_tickers:
        df_check = data_dict.get(t)
        if df_check is not None and ('HK_NW' not in df_check.columns or 'T2_SMA' not in df_check.columns):
            missing_after.append(t)

    if missing_after:
        logger.warning(f"⚠️ HẬU KIỂM: Phát hiện {len(missing_after)} chỉ số thiếu Trending. Đang xử lý bù...")
        for t in missing_after:
            try:
                df_final = enrich_dataframe(data_dict[t])
                data_dict[t] = df_final
                storage.save_indicators(t, df_final)
            except Exception as ex:
                pass
        logger.info("✅ Hậu kiểm hoàn tất.")
    else:
        logger.info("✅ Tuyệt vời! 100% chỉ số đã đầy đủ chỉ số Trending.")

    # 6. Calculate Market Breadth (Time-series)
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
    
    # 8. Xây dựng tickers_analysis cho từng chỉ số ngành/thị trường — dùng lại
    # đúng schema (Entry/Target/StopLoss/RR/RiskScore/Diagnostics/MCDX/Tích lũy...)
    # từng dùng cho cổ phiếu đơn lẻ, chỉ khác là "Ticker" giờ là mã ngành.
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

                rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
                rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
                df['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)

                rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
                rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
                df['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)
            except Exception as e_rs:
                logger.warning(f"Error calculating RS for {ticker}: {e_rs}")

        current_vol = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0

        res = data.get("adv") or {}
        accum = data.get("accum") or {}
        ma_trend = data.get("ma_trend") or {}
        val = data.get("valuation") or {}

        # Không nhân 1000 nữa: Close ở đây luôn là chỉ số ngành/thị trường
        # (đã ở đúng thang điểm), không phải giá cổ phiếu tính bằng nghìn đồng.
        current_p = float(df['Close'].iloc[-1])
        ep = val.get("price", 0)
        tp = val.get("tp1", 0)
        tp2 = val.get("tp2", 0)
        sl = val.get("cutloss_partial", 0)
        rr_ratio = val.get("rr_ratio", 0)
        val_score = val.get("risk_score", 0)
        risk_pct = val.get("risk_pct", 0)
        action = val.get("action", "WAIT")

        matched_categories = []

        if accum.get("is_accumulation", False):
            matched_categories.append("ACCUMULATION")

        if ma_trend.get("is_perfect_uptrend", False):
            matched_categories.append("PERFECT_MA")

        buy_2 = False
        if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
            buy_2 = df.get('HK_BuySignal', pd.Series([False])).tail(2).any() or df.get('HK_BuyManh', pd.Series([False])).tail(2).any()
        if buy_2:
            matched_categories.append("HEIKIN_BUY")

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

        adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
        if adx_color == "WHITE":
            matched_categories.append("WHITE_ADX")

        if check_mark_minervini(df):
            matched_categories.append("MARK_MINERVINI")

        entry_type = res.get("entry_type")
        if entry_type in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
            matched_categories.append(entry_type)

        matched_rules = []
        for rule_key, r_def in CUSTOM_RULES.items():
            try:
                if r_def["func"](df):
                    matched_rules.append(rule_key)
            except Exception:
                pass

        vsa_res = analysis_cache.get(ticker, {}).get("vsa_cached") or analysis_cache.get(ticker, {}).get("vsa") or {}
        if not vsa_res:
            from tinvest.vsa_engine import analyze_vsa
            vsa_res = analyze_vsa(df)
        vsa_dominant = vsa_res.get("dominant", "neutral")
        vsa_score = vsa_res.get("score", 0)

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

        recent_df = df.tail(30)
        history = {
            "dates": [pd.to_datetime(d).strftime("%Y-%m-%d") if not pd.isna(d) else "N/A" for d in recent_df['Date']],
            "closes": [float(c) for c in recent_df['Close']],
            "volumes": [int(v) for v in recent_df['Volume']]
        }

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
                "mcdx_eval": mcdx_eval,
                # Dark Color confluence — lấy từ analyze_stock cache (nếu có)
                "confluence_flags": data.get("confluence_flags", {}),
                "confluence_count": data.get("confluence_count", 0),
                "confluence_bad":   data.get("confluence_bad", False),
                "heatmap_is_red":   data.get("heatmap_is_red", False),
                "ha_color":         data.get("ha_color", "Green"),
                "oct_color":        data.get("oct_color", ""),
                "oct_bad":          data.get("oct_bad", False),
            }
            report_text = format_report(report_input)
        except Exception as e_rep:
            logger.warning(f"⚠️ Không thể sinh báo cáo chi tiết cho mã {ticker}: {e_rep}")
            report_text = f"Không có báo cáo chi tiết cho mã {ticker}."

        mcdx_banker = float(df['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df.columns else 10
        prev_mcdx_banker = float(df['MCDX_Banker'].iloc[-2]) if len(df) > 1 and 'MCDX_Banker' in df.columns else mcdx_banker
        adx = float(df['ADX'].iloc[-1]) if 'ADX' in df.columns else 20
        ha_color = str(df['HA_Color'].iloc[-1]) if 'HA_Color' in df.columns else 'Green'
        ma20 = float(df['MA20'].iloc[-1]) if 'MA20' in df.columns else current_p
        vol = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
        vol_avg = float(df['AvgVolume20'].iloc[-1]) if 'AvgVolume20' in df.columns else vol

        mcdx_weak = (mcdx_banker < prev_mcdx_banker) and (mcdx_banker < 15)
        adx_low = adx < 20
        heikin_red = (ha_color.lower() == 'red')
        price_below_ma20 = current_p < ma20
        tech_weak = mcdx_weak or adx_low or heikin_red or price_below_ma20

        sideways_near_res = False
        p_res_vnd = float(val.get('r1', 0))
        if len(df) >= 4 and p_res_vnd > 0:
            recent_highs = df['High'].iloc[-4:].max()
            recent_lows = df['Low'].iloc[-4:].min()
            recent_vols = df['Volume'].iloc[-4:].mean()
            if recent_highs >= p_res_vnd * 0.98 and (recent_highs - recent_lows)/recent_lows < 0.05 and recent_vols > vol_avg:
                sideways_near_res = True

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

        safe_int = lambda x: int(x) if (x is not None and not pd.isna(x)) else 0

        avg_vol_raw = df['AvgVolume10'].iloc[-1] if 'AvgVolume10' in df.columns else (df['Volume'].rolling(10).mean().iloc[-1] if len(df) >= 10 else current_vol)

        group_meta = sector_groups.get(ticker)
        display_name = f"{group_meta['icon']} {group_meta['name']}" if group_meta else ticker

        ticker_record = {
            "Ticker": ticker,
            "DisplayName": display_name,
            "Price": safe_int(current_p),
            "Volume": safe_int(current_vol),
            "AvgVolume10": safe_int(avg_vol_raw),
            "Entry": int(ep) if ep > 0 else None,
            "Target": int(tp) if tp > 0 else None,
            "Target2": int(tp2) if tp2 > 0 else None,
            "ReportText": report_text,
            "StopLoss": int(sl) if sl > 0 else None,
            "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",
            "RiskScore": int(val_score),
            "RiskPct": float(risk_pct),
            "Action": action,
            "Categories": matched_categories,
            "Rules": matched_rules,

            "CutlossFull": int(val.get("cutloss_full", 0)) if val.get("cutloss_full", 0) > 0 else None,
            "TrailingStop": int(val.get("trailing_stop", 0)) if val.get("trailing_stop", 0) > 0 else None,
            "OpportunityScore": int(val.get("opp_score", 0)),
            "OpportunityDesc": str(val.get("opp_desc", "N/A")),
            "SafetyRating": int(val.get("topup_safety", 0)),
            "TopupPrice": int(val.get("topup_price", 0)) if val.get("topup_price", 0) > 0 else None,
            "TopupDesc": str(val.get("topup_desc", "N/A")),
            "AccumulationQuality": str(accum.get("base_quality", "NONE")),
            "AccumulationNotes": accum.get("notes", []),
            "AccumulationRangePct": float(accum.get("range_pct", 0.0)),
            "ReadyToBreak": bool(accum.get("ready_to_break", False)),

            "Support1": int(val.get("s1", 0)) if val.get("s1", 0) > 0 else None,
            "Support2": int(val.get("s2", 0)) if val.get("s2", 0) > 0 else None,
            "Resistance1": int(val.get("r1", 0)) if val.get("r1", 0) > 0 else None,
            "Resistance2": int(val.get("r2", 0)) if val.get("r2", 0) > 0 else None,
            "TrendStatus": str(ma_trend.get("trend_status", "Sideway")),
            "TechWeak": bool(tech_weak),
            "SidewaysNearRes": bool(sideways_near_res),
            "StateSignal": state_signal,
            "AntiTrap": bool(data.get("state_rules", {}).get("metrics", {}).get("anti_trap_block", False)),
            "AvoidEntry": bool(data.get("state_rules", {}).get("avoid_entry", False)),

            "MCDX": {
                "banker_pct": banker_pct,
                "hot_pct": hot_pct,
                "retailer_pct": retailer_pct,
                "status": str(mcdx_eval.get("status", "N/A")),
                "action": str(mcdx_eval.get("action", "N/A")),
                "details": str(mcdx_eval.get("details", "N/A"))
            },

            "Diagnostics": {
                "dark_color": {
                    "count": data.get("confluence_count", 0),
                    "is_bad": data.get("confluence_bad", False),
                    "flags": data.get("confluence_flags", {})
                },
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

            "History": history
        }

        tickers_analysis.append(ticker_record)

    # Merge existing and newly analyzed
    merged_tickers_analysis = existing_tickers_analysis.copy()
    for record in tickers_analysis:
        merged_tickers_analysis[record["Ticker"]] = record

    # Remove recalculated codes that were filtered out or failed
    newly_analyzed_symbols = {r["Ticker"] for r in tickers_analysis}
    for t in affected_tickers:
        if t not in newly_analyzed_symbols and t in merged_tickers_analysis:
            del merged_tickers_analysis[t]

    # Final sorted list — chỉ giữ các chỉ số ngành/thị trường hiện đang quản lý
    tickers_analysis = [r for r in merged_tickers_analysis.values() if r["Ticker"] in affected_tickers]
    tickers_analysis.sort(key=lambda x: (
        1 if x.get("Action") == "BUY" else (2 if x.get("Action") == "WAIT" else 3),
        x.get("Ticker", "")
    ))

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

    # 9. Output to JSON file
    output_dir = os.path.join(base_path, "Output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "analysis_results.json")
    
    # ICT current time format
    from datetime import timezone
    ict_time = datetime.now(timezone.utc) + timedelta(hours=7)
    last_update_str = ict_time.strftime("%Y-%m-%d %H:%M:%S")

    # Đếm số mã cổ phiếu THẬT đang có dữ liệu (không phải số chỉ số ngành) —
    # đây là con số phản ánh chất lượng lần cập nhật giá, quyết định độ chính
    # xác của việc tính chỉ số ngành, nên phải giữ theo số mã cổ phiếu gốc.
    stocks_updated_count = len(active_set)

    final_output = {
        "last_update": last_update_str,
        "vietstock_status": vietstock_status,
        "stocks_updated_count": stocks_updated_count,
        "market_breadth": market_breadth_data,
        "categories_meta": categories_meta,
        "rules_meta": rules_meta,
        "tickers_analysis": tickers_analysis,
        "filtered_results": filtered_results,
        "sector_groups_meta": {code: {"name": g.get("name"), "icon": g.get("icon")} for code, g in sector_groups.items()}
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
        
    logger.info(f"✅ HOÀN TẤT CẬP NHẬT! Đã xuất {len(tickers_analysis)} chỉ số ngành/thị trường.")
    
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

    # Import New Data CHỈ nạp/làm sạch dữ liệu giá (đã xong ở _clean_dataframe:
    # phát hiện & lấp phiên biến động sốc/thiếu giá do lỗi). KHÔNG tính chỉ
    # số ngành/chỉ báo ở đây — vì tính chỉ số ngành theo vốn hóa cần số CP
    # lưu hành (chỉ Update Stock Data mới lấy được, từ MarketCap của API
    # Vietstock), Import New Data không có nguồn đó nên không có gì để tính.
    # Việc tính toán chỉ số ngành + chỉ báo dồn hết vào action Update Stock
    # Data (run_sync_and_update), chạy sau khi đã có đủ số CP lưu hành.
    logger.info("[*] Import New Data hoàn tất — dữ liệu giá đã sẵn sàng. Chạy Update Stock Data để tính chỉ số ngành.")

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
