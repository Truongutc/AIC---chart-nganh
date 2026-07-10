"""
Tính chỉ số ngành theo 2 bước:
1. Chỉ số phụ (Paux): trung bình Open/High/Low/Close theo TRỌNG SỐ VỐN HÓA
   (CapWeight = số CP lưu hành mới nhất của từng mã, hằng số theo mã — xem
   _load_shares_outstanding) của các mã thành viên có dữ liệu trong ngày đó
   (thành viên động theo ngày, không cần chờ đủ mã — mã mới gia nhập/hủy
   niêm yết chỉ làm đổi tập mã tham gia trung bình). Volume = tổng, chỉ để
   hiển thị. Đây là cách VN-Index thật đang dùng (chỉ số vốn hóa): số CP lưu
   hành lấy từ MarketCap/Close của API Vietstock tại lần Update Stock Data
   gần nhất, áp dụng cho TOÀN BỘ chuỗi giá lịch sử đã điều chỉnh cổ tức/phát
   hành của mã đó (không lưu vốn hóa lịch sử — không cần thiết vì mỗi lần
   tính đều dùng lại đúng 1 số CP lưu hành hiện tại, nhất quán trong 1 lượt
   tính nên không có điểm nối lệch pha).
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


def resolve_group_tickers(group_def, active_registry, storage=None):
    if group_def.get("dynamic") == "ALL_EXCEPT":
        exclude = set(group_def.get("exclude", []))

        # Loại toàn bộ MÃ NGÀNH (khoá trong sector_groups.json) khỏi vũ trụ
        # ứng viên. compute_all_sector_indices() ghi chỉ số ngành đã tính ra
        # ĐÚNG thư mục data_storage/prices/ như cổ phiếu thật (qua
        # storage.sync_prices(group_code, ...)) — nếu 1 mã ngành trùng đúng 3
        # ký tự chữ+số (VD "BDS", "KCN") thì vòng scan bên dưới sẽ hiểu nhầm
        # file đó là 1 mã cổ phiếu thật và đưa NGƯỢC LẠI chỉ số ngành đã cộng
        # dồn (thang điểm ~500-2600, không phải giá cổ phiếu) vào chính phép
        # tính trung bình — gây biến động cực lớn, bất thường (phát hiện
        # 2026-07-10: BDS.parquet khiến VNINDEX_NONVIN nhảy +193% trong 1
        # phiên vì bị tính lẫn như 1 cổ phiếu).
        try:
            exclude |= set(load_sector_groups().keys())
        except Exception:
            pass

        # Dùng TOÀN BỘ mã từng có dữ liệu giá (kể cả mã đã hủy niêm yết), không
        # chỉ mã đang niêm yết hôm nay — nếu chỉ lấy active_registry (registry
        # hiện tại) thì các mã đã hủy niêm yết trong quá khứ sẽ bị loại khỏi
        # TOÀN BỘ lịch sử tính toán (kể cả những năm chúng còn giao dịch), gây
        # sai lệch kiểu "survivorship bias". Mỗi mã tự nhiên chỉ đóng góp vào
        # trung bình ở đúng những ngày nó có dữ liệu giá thật (theo đúng số
        # lượng cổ phiếu tồn tại ở từng thời điểm).
        universe = set()
        if storage is not None:
            try:
                for fname in os.listdir(storage.prices_dir):
                    if fname.endswith(".parquet"):
                        universe.add(fname[:-8].upper())
            except Exception:
                pass
        if not universe:
            universe = set(active_registry or [])

        candidates = {t for t in universe if len(t) == 3 and t.isalnum()}
        return sorted(candidates - exclude)
    return list(group_def.get("tickers", []))


def _load_trading_calendar(storage):
    """
    Lịch giao dịch thật (không có phiên cuối tuần/lễ) — lấy từ toàn bộ ngày
    VNINDEX có dữ liệu, vì VNINDEX luôn có đủ mọi phiên giao dịch thật của thị
    trường. Dùng làm mốc để:
      (a) loại bỏ các dòng dữ liệu rơi vào ngày KHÔNG phải phiên giao dịch
          (lỗi nhập liệu — VD 1 mã ghi nhầm giá vào thứ Bảy);
      (b) lấp các phiên gián đoạn NGẮN HẠN của 1 mã (bị đình chỉ giao dịch vài
          phiên nhưng CHƯA hủy niêm yết, hoặc lỗ hổng dữ liệu) bằng giá đóng
          cửa gần nhất của CHÍNH mã đó, để số mã tham gia tính trung bình mỗi
          ngày không bị chao đảo vì lý do KHÔNG phải niêm yết/hủy niêm yết
          thật sự.
    """
    try:
        vni_df = storage.load_ticker_data('VNINDEX')
        if vni_df is not None and not vni_df.empty:
            return pd.to_datetime(vni_df['Date']).sort_values().unique()
    except Exception as e:
        logger.warning(f"⚠️ Không lấy được lịch giao dịch VNINDEX: {e}")
    return None


def _load_shares_outstanding(storage):
    """
    {ticker: số lượng CP lưu hành mới nhất} — lấy từ storage.get_shares_outstanding()
    (do run_headless_update.py ghi mỗi lần Update Stock Data, tính từ
    MarketCap/Close của API Vietstock, sticky-merge chỉ giữ giá trị mới nhất
    mỗi mã). Dùng làm trọng số vốn hóa: MarketCap_i(t) = Close_i(t) [giá đã
    điều chỉnh cổ tức/phát hành] * Shares_i [hằng số theo mã, KHÔNG đổi theo
    ngày]. Mã không có trong map (VD đã hủy niêm yết, không còn vốn hóa hiện
    tại để suy ngược) sẽ có trọng số = 0 — bị loại khỏi trung bình có trọng số
    (không phải lỗi, là đánh đổi đã chấp nhận vì không có cách suy vốn hóa
    quá khứ cho mã không còn dữ liệu vốn hóa hiện tại).
    """
    try:
        return storage.get_shares_outstanding() or {}
    except Exception as e:
        logger.warning(f"⚠️ Không lấy được dữ liệu số CP lưu hành: {e}")
        return {}


def _chain_linked_close_ratio(combined, dates):
    """
    Tỷ lệ biến động Close ngày-qua-ngày, chỉ tính trên các mã CHUNG có mặt ở
    CẢ ngày t và ngày t-1 (chain-linking) — không lấy trung bình Close của
    TOÀN BỘ thành viên ngày t so với TOÀN BỘ thành viên ngày t-1 như trước.

    Lý do: nếu 1 mã hoàn toàn mới lên sàn hoặc hủy niêm yết đúng vào ngày t,
    việc so trung bình "tập hợp mới" với "tập hợp cũ" trực tiếp sẽ tạo ra
    1 mức nhảy ảo do thay đổi thành viên (không phải biến động giá thật) —
    VD mã VPL (giá ~87) gia nhập nhóm chỉ có VIC (giá ~2.4) làm chỉ số nhảy
    +1510% trong 1 phiên dù không mã nào thực sự biến động giá mạnh vậy.
    Chain-linking cô lập đúng phần biến động giá thật: chỉ so sánh Close của
    những mã có mặt ở CẢ 2 ngày, nên thành viên mới/cũ không làm chỉ số nhảy
    — chỉ ảnh hưởng đến HÌNH DẠNG nến (Open/High/Low) của đúng ngày đó qua
    bước 2b (vẫn dùng trung bình toàn bộ thành viên hiện tại), không ảnh
    hưởng đến MỨC (level) của chuỗi Close đã cộng dồn.

    Trung bình Close 2 vế của tỷ lệ theo TRỌNG SỐ VỐN HÓA (CapWeight = số CP
    lưu hành, hằng số theo mã — đồng nhất với Bước 1, xem _load_shares_outstanding).
    Tỷ lệ Weighted_Close(t)/Weighted_Close(t-1) trên đúng tập mã chung khi đó
    CHÍNH LÀ % thay đổi tổng vốn hóa của rổ mã chung — đúng công thức chain-index
    vốn hóa thật (tương đương kỹ thuật "điều chỉnh Divisor" mà VN-Index/HOSE
    dùng khi rổ đổi thành phần). Nếu tổng CapWeight của các mã chung = 0 ở 1
    trong 2 ngày (VD toàn mã không rõ số CP lưu hành) thì lùi về trung bình
    cộng thường của đúng các mã chung đó.
    """
    close_wide = combined.pivot_table(index='Date', columns='Ticker', values='Close', aggfunc='last')
    close_wide = close_wide.reindex(dates)
    cap_wide = combined.pivot_table(index='Date', columns='Ticker', values='CapWeight', aggfunc='last')
    cap_wide = cap_wide.reindex(index=dates, columns=close_wide.columns).fillna(0.0)

    close_mat = close_wide.to_numpy(dtype=float)
    cap_mat = cap_wide.to_numpy(dtype=float)
    valid = ~pd.isna(close_mat)

    n = len(dates)
    ratio = pd.Series(1.0, index=range(n))
    for t in range(1, n):
        common = valid[t] & valid[t - 1]
        if not common.any():
            continue

        prev_close, curr_close = close_mat[t - 1][common], close_mat[t][common]
        prev_cap, curr_cap = cap_mat[t - 1][common], cap_mat[t][common]
        sum_prev_cap, sum_curr_cap = prev_cap.sum(), curr_cap.sum()

        if sum_prev_cap > 0 and sum_curr_cap > 0:
            prev_val = (prev_close * prev_cap).sum() / sum_prev_cap
            curr_val = (curr_close * curr_cap).sum() / sum_curr_cap
        else:
            prev_val = prev_close.mean()
            curr_val = curr_close.mean()

        if prev_val and not pd.isna(prev_val) and not pd.isna(curr_val):
            ratio.iloc[t] = curr_val / prev_val
    return ratio


def compute_sector_index_df(group_def, storage, active_registry):
    """
    Trả về DataFrame Date/Open/High/Low/Close/Volume cho chỉ số ngành (đã cộng
    dồn về kỳ gốc 100 điểm), hoặc None nếu không có mã nào có dữ liệu.
    """
    tickers = resolve_group_tickers(group_def, active_registry, storage=storage)
    if not tickers:
        return None

    trading_calendar = _load_trading_calendar(storage)
    shares_outstanding = _load_shares_outstanding(storage)

    frames = []
    for ticker in tickers:
        df = storage.load_ticker_data(ticker)
        if df is None or df.empty:
            continue
        cols = [c for c in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
        df = df[cols].copy()
        df['Ticker'] = ticker
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').drop_duplicates(subset='Date', keep='last')

        # Loại dữ liệu lỗi rõ ràng theo bất biến toán học của nến OHLC thật:
        # High phải >= Low, và Open/Close của đúng phiên đó PHẢI nằm trong
        # khoảng [Low, High] của chính phiên đó — không có ngoại lệ. Vi phạm
        # thường do lỗi lệch dấu thập phân ở nguồn dữ liệu cho 1 trường riêng
        # lẻ (VD phát hiện 2026-07-10: hàng loạt mã như BVN có Open=7000.11
        # trong khi High=7.0001/Low=6.398/Close=6.3982 ngày 2014-05-26 — Open
        # sai lệch ~1000 lần so với chính High/Low/Close cùng phiên). Bỏ cả
        # hàng nếu High<Low (hỏng toàn phiên); chỉ xoá riêng Open/Close thành
        # NaN nếu chỉ 1 trong 2 trường đó sai — để bước lấp gián đoạn (b) bên
        # dưới tự thay bằng giá trị hợp lệ gần nhất, thay vì lọt thẳng vào
        # trung bình chỉ số phụ và làm nến chỉ số ngành biến dạng bất thường.
        df = df[df['High'] >= df['Low']]
        # Cho phép dung sai 1% để tránh báo nhầm do làm tròn số ở nguồn dữ
        # liệu (VD Close=9.3023 trong khi High=9.300 — lệch 0.03%, rất phổ
        # biến ở mã thanh khoản thấp — không phải lỗi thật).
        tol = 1.01
        bad_open = (df['Open'] < df['Low'] / tol) | (df['Open'] > df['High'] * tol)
        bad_close = (df['Close'] < df['Low'] / tol) | (df['Close'] > df['High'] * tol)
        df.loc[bad_open, 'Open'] = float('nan')
        df.loc[bad_close, 'Close'] = float('nan')

        # Trọng số = số lượng CP lưu hành (CapWeight) — HẰNG SỐ theo từng mã,
        # KHÔNG đổi theo ngày như khối lượng giao dịch (khối lượng từng bị
        # loại vì quá giật cục: 1 mã có thể đột biến gấp 10-50 lần bình
        # thường rồi tụt ngay hôm sau, VD phiên hoảng loạn 09/4/2025: AAA
        # KL=6.8tr rồi 10/4/2025 tụt còn 555k, khiến tỉ trọng nhảy múa hỗn
        # loạn dù giá không biến động tương xứng). Số CP lưu hành ổn định
        # (chỉ đổi khi doanh nghiệp thật sự phát hành thêm CP), nên
        # Close*CapWeight = đúng vốn hóa doanh nghiệp — đây là cách VN-Index
        # thật đang dùng, không phải trung bình giá hay trọng số khối lượng.
        df['CapWeight'] = shares_outstanding.get(ticker, 0.0)

        if trading_calendar is not None:
            # (a) Bỏ các phiên không nằm trong lịch giao dịch thật
            df = df[df['Date'].isin(trading_calendar)]
            if df.empty:
                continue

            # (b) Lấp phiên gián đoạn ngắn hạn TRONG ĐÚNG vòng đời thật của mã
            # (từ phiên đầu tiên đến phiên cuối cùng nó có dữ liệu) — không
            # suy đoán ra ngoài vòng đời thật (không kéo trước ngày niêm yết
            # đầu tiên / sau ngày có dữ liệu cuối cùng, tức hủy niêm yết).
            #
            # Phân biệt "hủy niêm yết thật" với "lỗi đồng bộ tạm thời" (VD
            # hôm nay VCB bị lỗi số học nên không có dòng giá): active_registry
            # là nguồn ĐỘC LẬP với việc có đồng bộ được giá hay không — một mã
            # chỉ bị gỡ khỏi registry này sau khi identify_delisted_tickers()
            # xác nhận >=10 phiên liên tục khối lượng = 0 (storage_manager.py),
            # không phải do thiếu 1 dòng dữ liệu đơn lẻ. Nếu mã vẫn còn trong
            # registry, coi khoảng trống gần nhất (kể cả đúng phiên mới nhất)
            # là lỗi tạm thời — kéo dài vòng đời lấp gián đoạn tới hết lịch
            # giao dịch hiện có, để tổng số mã & Paux không bị lệch vì lỗi dữ
            # liệu 1 phiên. Nếu mã đã bị gỡ khỏi registry (hủy niêm yết thật),
            # vẫn dừng đúng ở ngày cuối cùng thực sự có giá như trước.
            first_date = df['Date'].min()
            observed_last_date = df['Date'].max()
            if active_registry and ticker in active_registry:
                last_date = trading_calendar[-1]
            else:
                last_date = observed_last_date
            lifetime_dates = trading_calendar[
                (trading_calendar >= first_date) & (trading_calendar <= last_date)
            ]
            df = df.set_index('Date').reindex(lifetime_dates)
            df.index.name = 'Date'
            df[['Open', 'High', 'Low', 'Close', 'CapWeight']] = df[['Open', 'High', 'Low', 'Close', 'CapWeight']].ffill()
            df['Volume'] = df['Volume'].fillna(0.0)
            df['Ticker'] = ticker
            df = df.reset_index()

        frames.append(df)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    combined['Date'] = pd.to_datetime(combined['Date'])

    # Bước 1: chỉ số phụ (Paux) = trung bình O/H/L/C theo TRỌNG SỐ VỐN HÓA
    # (CapWeight = số CP lưu hành, hằng số theo mã, xem _load_shares_outstanding)
    # — mã vốn hóa lớn ảnh hưởng nhiều hơn tới trung bình ngày đó, đúng cách
    # VN-Index thật tính (không phải trung bình giá, không phải theo khối
    # lượng giao dịch). VD 3 mã A(giá=100,Shares=10) B(giá=200,Shares=20)
    # C(giá=500,Shares=5): P = (100*10+200*20+500*5)/(10+20+5) = 214.29
    # Nếu tổng CapWeight trong ngày = 0 (toàn mã không rõ số CP lưu hành, VD
    # đã hủy niêm yết) thì lùi về trung bình cộng thường (equal-weight) để
    # tránh chia cho 0. Volume của chỉ số vẫn là TỔNG khối lượng thật đúng
    # phiên đó — chỉ dùng để hiển thị, không dùng làm trọng số tính giá.
    weighted = combined.copy()
    for c in ['Open', 'High', 'Low', 'Close']:
        weighted[f'_w{c}'] = weighted[c] * weighted['CapWeight']

    grp = weighted.groupby('Date').agg(
        _wOpen=('_wOpen', 'sum'), _wHigh=('_wHigh', 'sum'),
        _wLow=('_wLow', 'sum'), _wClose=('_wClose', 'sum'),
        CapWeight=('CapWeight', 'sum'),
        Volume=('Volume', 'sum'),
        Open_eq=('Open', 'mean'), High_eq=('High', 'mean'),
        Low_eq=('Low', 'mean'), Close_eq=('Close', 'mean'),
    ).reset_index().sort_values('Date').reset_index(drop=True)

    has_cap = grp['CapWeight'] > 0
    aux = grp[['Date', 'Volume']].copy()
    for c in ['Open', 'High', 'Low', 'Close']:
        aux[c] = (grp[f'_w{c}'] / grp['CapWeight']).where(has_cap, grp[f'{c}_eq'])

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
    # ngày-qua-ngày — dùng chain-linking (chỉ so các mã CHUNG giữa 2 ngày) để
    # mã mới lên sàn/hủy niêm yết không tạo ra mức nhảy ảo (xem
    # _chain_linked_close_ratio).
    close_ratio = _chain_linked_close_ratio(combined, aux['Date'])
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
