"""
Tính chỉ số ngành theo 2 bước:
1. Chỉ số phụ (Paux): trung bình cộng Open/High/Low/Close, tổng Volume của các
   mã thành viên có dữ liệu trong ngày đó (thành viên động theo ngày, không cần
   chờ đủ mã — mã mới gia nhập/hủy niêm yết chỉ làm đổi số mã chia trung bình).
2. Chỉ số chính thức: kỳ gốc (ngày đầu tiên nhóm có dữ liệu) = giá đóng cửa
   VNINDEX tại đúng ngày gốc đó (không phải mốc 100 cố định) — để chỉ số ngành
   nằm cùng thang điểm và so sánh công bằng được với VNINDEX thật.

   CHỈ cộng dồn (chain) một chuỗi duy nhất làm gốc — Close — theo tỷ lệ biến
   động ngày-qua-ngày của chỉ số phụ:
       Index_Close(t) = Index_Close(t-1) * Paux_Close(t) / Paux_Close(t-1)
   Open/High/Low mỗi ngày được suy ra từ Index_Close(t) theo đúng tỷ lệ trong
   ngày hôm đó so với chỉ số phụ (giữ nguyên hình dạng nến thực tế), KHÔNG
   cộng dồn độc lập từng chuỗi:
       Index_X(t) = Index_Close(t) * Paux_X(t) / Paux_Close(t)   (X = Open/High/Low)
   Nếu cộng dồn 4 chuỗi O/H/L/C độc lập với nhau, sau nhiều năm chúng sẽ trôi
   dạt (drift) khác nhau và có thể bị chéo nhau (High < Low) — đã gặp lỗi này
   và sửa lại theo cách neo O/H/L vào Close mỗi ngày như trên.

Danh sách ngành đọc từ sector_groups.json ở gốc dự án.
"""
import os
import json
import logging
import pandas as pd

logger = logging.getLogger(__name__)

base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTOR_GROUPS_PATH = os.path.join(base_path, "sector_groups.json")


def load_sector_groups():
    with open(SECTOR_GROUPS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_group_tickers(group_def, active_registry):
    if group_def.get("dynamic") == "ALL_EXCEPT":
        exclude = set(group_def.get("exclude", []))
        # Loại các chỉ số/registry đặc biệt (VNINDEX, HNX-INDEX...) và mã không
        # phải cổ phiếu thường (3 ký tự chữ+số) khỏi rổ tính trung bình.
        candidates = {
            t for t in (active_registry or [])
            if len(t) == 3 and t.isalnum()
        }
        return sorted(candidates - exclude)
    return list(group_def.get("tickers", []))


def compute_sector_index_df(group_def, storage, active_registry):
    """
    Trả về DataFrame Date/Open/High/Low/Close/Volume cho chỉ số ngành (đã cộng
    dồn về kỳ gốc 100 điểm), hoặc None nếu không có mã nào có dữ liệu.
    """
    tickers = resolve_group_tickers(group_def, active_registry)
    if not tickers:
        return None

    frames = []
    for ticker in tickers:
        df = storage.load_ticker_data(ticker)
        if df is None or df.empty:
            continue
        cols = [c for c in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        frames.append(df[cols])

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    combined['Date'] = pd.to_datetime(combined['Date'])

    # Bước 1: chỉ số phụ (Paux) = trung bình cộng O/H/L/C, tổng Volume theo ngày
    aux = combined.groupby('Date').agg(
        Open=('Open', 'mean'),
        High=('High', 'mean'),
        Low=('Low', 'mean'),
        Close=('Close', 'mean'),
        Volume=('Volume', 'sum'),
    ).reset_index().sort_values('Date').reset_index(drop=True)

    if aux.empty:
        return None

    # Giá trị gốc = Close VNINDEX tại đúng ngày gốc (ngày đầu tiên nhóm có dữ
    # liệu), hoặc phiên gần nhất trước đó nếu không khớp ngày giao dịch. Dùng
    # 100 làm dự phòng nếu không lấy được dữ liệu VNINDEX.
    base_date = aux['Date'].iloc[0]
    base_value = 100.0
    try:
        vnindex_df = storage.load_ticker_data('VNINDEX')
        if vnindex_df is not None and not vnindex_df.empty:
            vnindex_df = vnindex_df.copy()
            vnindex_df['Date'] = pd.to_datetime(vnindex_df['Date'])
            vnindex_df = vnindex_df.sort_values('Date')
            match = vnindex_df[vnindex_df['Date'] <= base_date]
            if not match.empty:
                base_value = float(match['Close'].iloc[-1])
    except Exception as e:
        logger.warning(f"⚠️ Không lấy được Close VNINDEX làm kỳ gốc, dùng 100 mặc định: {e}")

    # Bước 2a: cộng dồn Close về kỳ gốc (base_value) theo tỷ lệ biến động
    # ngày-qua-ngày của chỉ số phụ.
    close_ratio = aux['Close'] / aux['Close'].shift(1)
    close_ratio = close_ratio.replace([float('inf'), float('-inf')], 1.0).fillna(1.0)
    index_close = base_value * close_ratio.cumprod()

    # Bước 2b: Open/High/Low mỗi ngày neo theo đúng tỷ lệ trong ngày so với
    # Close của chỉ số phụ — đảm bảo luôn có High >= Close >= Low như dữ liệu
    # gốc, không bị trôi dạt qua nhiều năm.
    index_df = aux[['Date', 'Volume']].copy()
    index_df['Close'] = index_close
    for col in ['Open', 'High', 'Low']:
        day_ratio = aux[col] / aux['Close']
        day_ratio = day_ratio.replace([float('inf'), float('-inf')], 1.0).fillna(1.0)
        index_df[col] = index_close * day_ratio

    # Chốt an toàn: đảm bảo High/Low luôn đúng quan hệ nến (High = max, Low =
    # min của 4 giá trị) dù dữ liệu gốc của 1 mã thành viên có nhiễu/lỗi ở
    # một vài phiên hiếm gặp (VD thanh khoản quá thấp, giá tham chiếu bất thường).
    ohlc = index_df[['Open', 'High', 'Low', 'Close']]
    index_df['High'] = ohlc.max(axis=1)
    index_df['Low'] = ohlc.min(axis=1)

    return index_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]


def compute_all_sector_indices(storage, active_registry=None):
    """
    Tính chỉ số cho toàn bộ nhóm ngành trong sector_groups.json, lưu qua
    storage.sync_prices(group_code, df, source='COMPUTED').
    Trả về set các group_code đã tính thành công.
    """
    if active_registry is None:
        active_registry = storage.get_active_registry() or set()

    groups = load_sector_groups()
    computed = set()

    for group_code, group_def in groups.items():
        try:
            df = compute_sector_index_df(group_def, storage, active_registry)
            if df is None or df.empty:
                logger.warning(f"⚠️ Ngành {group_code} ({group_def.get('name')}) không có dữ liệu.")
                continue
            storage.sync_prices(group_code, df, source='COMPUTED')

            # Giá chỉ số ngành luôn được TÍNH LẠI TOÀN BỘ lịch sử từ đầu mỗi lần
            # chạy (không phải cập nhật gia tăng như cổ phiếu thật), nên chỉ báo
            # kỹ thuật (Heikin/GreenPink/Octopus/Heatmap...) đã lưu từ lần trước
            # luôn phải coi là lỗi thời — xoá cache để buộc tính lại từ đầu,
            # tránh enrich_dataframe() bỏ qua tính toán do thấy cột _ENRICHED
            # đã đầy đủ (dữ liệu giá cũ đã bị thay hoàn toàn bởi giá mới).
            try:
                indicators_path = storage._get_indicators_path(group_code)
                if indicators_path.exists():
                    indicators_path.unlink()
            except Exception:
                pass

            computed.add(group_code)
        except Exception as e:
            logger.error(f"❌ Lỗi tính chỉ số ngành {group_code}: {e}")

    logger.info(f"✅ Đã tính {len(computed)}/{len(groups)} chỉ số ngành.")
    return computed
