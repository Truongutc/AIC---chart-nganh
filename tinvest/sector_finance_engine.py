"""
Tổng hợp dữ liệu tài chính (VCSH, LNST) theo NGÀNH từ bảng dữ liệu theo mã
(tinvest/finance_workbook.py), tính ROE, tăng trưởng LNST YoY theo quý, và
P/E, P/B theo ngày (kết hợp vốn hóa hàng ngày với dữ liệu tài chính quý mới
nhất đã biết tại thời điểm đó).

Quy ước công thức (đã thống nhất với người dùng):
  - ROE(quý) = TTM_LNST(quý) / VCSH(quý hiện tại)  [VCSH quý hiện tại, không
    phải bình quân — khớp đúng quy ước của P/B bên dưới]
  - P/E(ngày) = Vốn hóa(ngày) / TTM_LNST(quý đã công bố gần nhất)
  - P/B(ngày) = Vốn hóa(ngày) / VCSH(quý đã công bố gần nhất)
  - Tăng trưởng LNST YoY(quý) = (LNST(quý) - LNST(quý cùng kỳ năm trước)) / |LNST(quý cùng kỳ năm trước)|

Quý "đã công bố" — 2 QUY TẮC KHÁC NHAU tuỳ mục đích, dùng 2 hàm riêng biệt
(quyết định rõ ràng với người dùng, không gộp làm 1 để tránh thay đổi ngoài ý
muốn số liệu P/E, P/B LỊCH SỬ đã hiển thị từ trước tới nay):

  1. DỮ LIỆU SỐNG (P/E, P/B hôm nay + ROE/tăng trưởng LNST theo quý) — dùng
     target_quarter_for_date()/effective_quarter_for_live_date(): quý mục
     tiêu LUÔN LUÔN là quý liền TRƯỚC quý dương lịch hiện tại, KHÔNG chờ thêm
     ngày nào — VD sang ngày 1/7 (vừa bước sang Q3) thì quý mục tiêu là Q2
     ngay, dù Q2 gần như chưa mã nào kịp công bố. Mã NÀO CHƯA công bố quý đó
     thì tạm lấy số liệu quý TRƯỚC của CHÍNH mã đó bù vào (xem
     carry_forward_missing_quarter(), ghi placeholder=True), rồi tự thay thế
     bằng số thật ngay khi mã công bố xong (những lần chạy Update finance
     vietcap sau) — thay vì cả hệ thống cùng chờ 1 mốc thời gian cố định rồi
     mới tính, chấp nhận vài quý có mẫu quá thiếu (từng gây ROE ảo 750%).

  2. LỊCH SỬ (backfill_daily_sector_finance_history, chỉ chạy khi Import
     Finance tính lại TOÀN BỘ chuỗi P/E, P/B quá khứ) — VẪN giữ nguyên quy
     tắc cũ, dùng effective_quarter_for_date(..., lag_days=LAG_DAYS): quý
     gần nhất mà (ngày kết thúc quý + 45 ngày) <= ngày giao dịch đó. Giữ
     nguyên có chủ đích — đổi sang quy tắc (1) cho cả lịch sử sẽ làm lệch lại
     P/E, P/B của MỌI lần chuyển quý đã từng xảy ra (quyết định của người
     dùng: giữ nguyên lịch sử, chỉ áp quy tắc mới cho dữ liệu hiện tại).
"""

import json
import os
from datetime import date, timedelta, datetime

import pandas as pd

from tinvest.finance_workbook import quarter_sort_key

LAG_DAYS = 45  # giả định độ trễ công bố BCTC hợp nhất (ngày) — CHỈ còn dùng cho backfill lịch sử, xem docstring ở trên

QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _as_date(d):
    """Chuẩn hoá str/datetime/date về đúng kiểu date — dùng chung cho mọi hàm
    nhận tham số ngày ở module này."""
    if isinstance(d, str):
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    if hasattr(d, "date") and not isinstance(d, date):
        return d.date()
    return d


# ── Tiện ích số học theo quý ──

def quarter_shift(label, n):
    """Dịch nhãn quý đi n quý (âm = lùi về quá khứ). 'Q3-2024' dịch -4 ->
    'Q3-2023' (đúng quý cùng kỳ năm trước)."""
    year, q = quarter_sort_key(label)
    total = year * 4 + (q - 1) + n
    new_year, new_q0 = divmod(total, 4)
    return f"Q{new_q0 + 1}-{new_year}"


def quarter_end_date(label):
    year, q = quarter_sort_key(label)
    month, day = QUARTER_END_MONTH_DAY[q]
    return date(year, month, day)


def effective_quarter_for_date(trading_date, available_quarters, lag_days=LAG_DAYS):
    """Quý tài chính mới nhất đã "công bố" tính đến 1 ngày giao dịch bất kỳ,
    theo quy tắc trễ lag_days ngày sau ngày kết thúc quý. Trả về None nếu
    chưa có quý nào đủ điều kiện (VD ngày quá sớm, trước cả quý đầu tiên)."""
    if isinstance(trading_date, str):
        trading_date = datetime.strptime(trading_date[:10], "%Y-%m-%d").date()
    elif hasattr(trading_date, "date") and not isinstance(trading_date, date):
        trading_date = trading_date.date()

    best = None
    for q in sorted(available_quarters, key=quarter_sort_key):
        disclosure_date = quarter_end_date(q) + timedelta(days=lag_days)
        if disclosure_date <= trading_date:
            best = q
        else:
            break
    return best


def calendar_quarter_label(d):
    """Nhãn quý dương lịch CHỨA ngày d (không liên quan gì đến việc đã công
    bố BCTC hay chưa) — VD 2026-07-22 -> 'Q3-2026'."""
    q_num = (d.month - 1) // 3 + 1
    return f"Q{q_num}-{d.year}"


def target_quarter_for_date(today=None):
    """Quý tài chính CẦN có dữ liệu tính đến `today`, cho DỮ LIỆU SỐNG (xem
    quy tắc (1) ở docstring đầu module) — LUÔN LUÔN là quý liền TRƯỚC quý
    dương lịch đang chứa `today`, KHÔNG cộng thêm độ trễ chờ công bố nào
    nữa. VD hôm nay là bất kỳ ngày nào trong Q3 (dù mới 1/7 hay đã 30/9) thì
    quý cần dữ liệu luôn là Q2 — vì Q3 chưa kết thúc nên chắc chắn chưa thể
    có báo cáo Q3. Mã nào CHƯA công bố xong quý mục tiêu được xử lý riêng ở
    carry_forward_missing_quarter() (tạm lấy số quý trước của chính mã đó bù
    vào), không phải bằng cách lùi cả hệ thống thêm 1 quý như LAG_DAYS cũ.

    Thay thế hoàn toàn current_expected_quarter() (đã xoá) — dùng cho
    tickers_needing_update() và quarter_due gate của
    compute_sector_quarterly_summary()."""
    today = _as_date(today) if today is not None else date.today()
    return quarter_shift(calendar_quarter_label(today), -1)


def _latest_quarter_at_or_before(target_quarter, available_quarters):
    """Quý mới nhất trong available_quarters mà <= target_quarter (theo thứ
    tự thời gian), hoặc None nếu không quý nào đủ điều kiện."""
    target_key = quarter_sort_key(target_quarter)
    best = None
    for q in sorted(available_quarters, key=quarter_sort_key):
        if quarter_sort_key(q) <= target_key:
            best = q
        else:
            break
    return best


def effective_quarter_for_live_date(trading_date, available_quarters):
    """Quý hiệu lực cho DỮ LIỆU SỐNG (P/E, P/B của ngày đang chạy — xem quy
    tắc (1) ở docstring đầu module) — KHÁC effective_quarter_for_date() (quy
    tắc (2), vẫn giữ độ trễ 45 ngày cũ, CHỈ dùng cho
    backfill_daily_sector_finance_history) ở chỗ không chờ thêm ngày nào,
    dựa thẳng vào target_quarter_for_date()."""
    trading_date = _as_date(trading_date)
    target = target_quarter_for_date(trading_date)
    return _latest_quarter_at_or_before(target, available_quarters)


def carry_forward_missing_quarter(vcsh_df, lnst_df, vcsh_placeholder_df, lnst_placeholder_df,
                                   universe, target_quarter):
    """Với ĐÚNG 1 quý `target_quarter` (quý vừa kết thúc, đang cần dữ liệu) —
    KHÔNG đụng tới bất kỳ quý nào khác (tránh vô tình sửa lại các khoảng
    trống lịch sử cũ không liên quan) — với mọi mã trong `universe` chưa có
    số liệu THẬT cho quý này (kể cả sau khi đã merge dữ liệu mới nhất từ
    Vietcap): tạm lấy số liệu của quý LIỀN TRƯỚC (target_quarter lùi 1) của
    CHÍNH mã đó áp vào, đánh dấu placeholder=True. Mã đã có số thật
    (placeholder=False) cho quý này thì giữ nguyên, không đụng vào. Mã không
    có cả số liệu quý trước để mà lấy (VD mã mới niêm yết) thì để nguyên
    thiếu — không có gì để bù, giống hệt hành vi hiện tại cho các mã đó.

    Sửa TRỰC TIẾP (mutate) cả 4 DataFrame truyền vào, đồng thời trả về chúng
    cho tiện dùng luôn kết quả. Phải gọi SAU merge_new_quarters() (để không
    ghi đè số liệu mới thật vừa cào về) và TRƯỚC
    compute_per_ticker_roe_and_growth()/save_workbook_to_path() (để ROE/G và
    file Excel đều phản ánh đúng số liệu đã bù)."""
    prev_q = quarter_shift(target_quarter, -1)
    for df, ph in ((vcsh_df, vcsh_placeholder_df), (lnst_df, lnst_placeholder_df)):
        if target_quarter not in df.columns:
            df[target_quarter] = float("nan")
        if target_quarter not in ph.columns:
            ph[target_quarter] = False
        for t in universe:
            if t not in df.index:
                continue
            cur_val = df.at[t, target_quarter]
            cur_is_placeholder = bool(ph.at[t, target_quarter]) if t in ph.index else False
            cur_is_real = pd.notna(cur_val) and not cur_is_placeholder
            if cur_is_real:
                continue
            if prev_q in df.columns and t in df.index and pd.notna(df.at[t, prev_q]):
                df.at[t, target_quarter] = df.at[t, prev_q]
                ph.at[t, target_quarter] = True
            # else: quý trước cũng không có gì để bù — để nguyên thiếu.
    return vcsh_df, lnst_df, vcsh_placeholder_df, lnst_placeholder_df


# ── Phân giải danh sách mã theo ngành (đảm bảo KHÔNG đếm trùng mã) ──

def get_finance_ticker_universe(sector_groups):
    """Tập hợp (khử trùng) toàn bộ mã trong các ngành TĨNH (không có
    'dynamic') của sector_groups.json — đây là "toàn bộ cổ phiếu trên thị
    trường" theo phạm vi đã chốt cho tính năng tài chính (302 mã), tách biệt
    hoàn toàn với vũ trụ mã của VNINDEX (không VIN) dùng cho phân tích kỹ
    thuật (~1500+ mã, xem tinvest/sector_index_engine.py)."""
    universe = set()
    for code, group_def in sector_groups.items():
        if group_def.get("dynamic"):
            continue
        universe |= set(group_def.get("tickers", []))
    return universe


def resolve_finance_sector_tickers(code, group_def, sector_groups):
    """Danh sách mã (đã khử trùng, sắp xếp) dùng để tổng hợp tài chính cho 1
    ngành. 'financeUniverse' là field RIÊNG của module này (sector_index_engine.py
    không đọc field này, nên không ảnh hưởng cách tính giá/kỹ thuật):
      - "ALL"        -> toàn bộ 302 mã (VNINDEX)
      - "ALL_EXCEPT" -> 302 mã trừ đi group_def['exclude'] (VNINDEX_NONVIN, trừ họ VIN)
      - không có     -> đúng group_def['tickers'] của chính ngành đó (BANK, BANK_NHO, ...)
    Luôn trả về set đã sort — 1 mã dù xuất hiện ở nhiều ngành con (VD NAB ở cả
    BANK và BANK_NHO) cũng chỉ xuất hiện 1 lần trong danh sách trả về, tránh
    đếm trùng khi tổng hợp cho VNINDEX/VNINDEX_NONVIN."""
    finance_universe = group_def.get("financeUniverse")
    if finance_universe == "ALL":
        tickers = get_finance_ticker_universe(sector_groups)
    elif finance_universe == "ALL_EXCEPT":
        exclude = set(group_def.get("exclude", []))
        tickers = get_finance_ticker_universe(sector_groups) - exclude
    else:
        tickers = set(group_def.get("tickers", []))
    return sorted(tickers)


# ── Tổng hợp theo ngành mỗi quý ──

def sector_quarter_present_tickers(ticker_df, tickers, quarter):
    """Danh sách con của `tickers` có giá trị hợp lệ (không NaN) tại `quarter`
    trong `ticker_df`. Dùng để biết CHÍNH XÁC tập mã đã đóng góp vào 1 tổng
    ngành (sector_quarter_sum) — cần thiết để đối chiếu lại với tập mã dùng
    tính vốn hóa (sector_market_cap), tránh lệch tập mã giữa tử số/mẫu số
    P/E, P/B (xem sector_quarter_sum, compute_sector_quarterly_summary)."""
    if ticker_df is None or ticker_df.empty or quarter not in ticker_df.columns:
        return []
    return [t for t in tickers if t in ticker_df.index and pd.notna(ticker_df.at[t, quarter])]


def sector_quarter_sum(ticker_df, tickers, quarter):
    """Tổng giá trị 1 quý của 1 ngành, cộng qua các mã có dữ liệu (bỏ qua mã
    thiếu). Trả về (None, 0) nếu KHÔNG mã nào trong ngành có dữ liệu quý đó."""
    present = sector_quarter_present_tickers(ticker_df, tickers, quarter)
    if not present:
        return None, 0
    return sum(float(ticker_df.at[t, quarter]) for t in present), len(present)


def yoy_growth(this_q_sum, last_year_q_sum):
    if this_q_sum is None or last_year_q_sum is None or last_year_q_sum == 0:
        return None
    return (this_q_sum - last_year_q_sum) / abs(last_year_q_sum)


def sector_roe(ttm_lnst, current_q_vcsh_sum):
    if ttm_lnst is None or current_q_vcsh_sum is None or current_q_vcsh_sum == 0:
        return None
    return ttm_lnst / current_q_vcsh_sum


def sector_pe(market_cap, ttm_lnst):
    if not market_cap or ttm_lnst is None or ttm_lnst == 0:
        return None
    return market_cap / ttm_lnst


def sector_pb(market_cap, current_q_vcsh_sum):
    if not market_cap or current_q_vcsh_sum is None or current_q_vcsh_sum == 0:
        return None
    return market_cap / current_q_vcsh_sum


def per_ticker_ttm_lnst(lnst_df, ticker, quarter):
    """TTM LNST của 1 mã tại 1 quý — None nếu thiếu bất kỳ quý nào trong 4
    quý liền trước (kể cả quý hiện tại), hoặc mã/quý không có trong lnst_df.
    Dùng chung cho cả sheet ROE theo mã (compute_per_ticker_roe_and_growth)
    và P/E theo mã hàng ngày (compute_and_append_daily_sector_finance)."""
    if lnst_df is None or lnst_df.empty or ticker not in lnst_df.index or quarter is None:
        return None
    total = 0.0
    for q in (quarter_shift(quarter, -i) for i in range(4)):
        if q not in lnst_df.columns:
            return None
        v = lnst_df.at[ticker, q]
        if v is None or v != v:  # NaN
            return None
        total += float(v)
    return total


def compute_per_ticker_roe_and_growth(vcsh_df, lnst_df):
    """Tính ROE và tăng trưởng LNST YoY THEO TỪNG MÃ (không phải theo ngành),
    cùng công thức đã thống nhất ở mức ngành:
      ROE(mã,q) = TTM_LNST(mã,q) / VCSH(mã,q)  (None nếu thiếu 1 trong 4 quý
                  TTM hoặc thiếu VCSH quý đó)
      YoY(mã,q) = (LNST(mã,q) - LNST(mã,q-4)) / |LNST(mã,q-4)|
    Trả về (roe_df, growth_df) — 2 DataFrame Ticker × Qn-YYYY, cùng shape với
    VCSH/LNST, dùng để ghi làm 2 sheet mới "ROE"/"LNST_YOY" của workbook
    (xem tinvest/finance_workbook.py)."""
    all_quarters = sorted(set(vcsh_df.columns) | set(lnst_df.columns), key=quarter_sort_key)
    all_tickers = sorted(set(vcsh_df.index) | set(lnst_df.index))

    roe_rows = {}
    growth_rows = {}
    for t in all_tickers:
        roe_row = {}
        growth_row = {}
        for q in all_quarters:
            ttm = per_ticker_ttm_lnst(lnst_df, t, q)
            vcsh_now = None
            if t in vcsh_df.index and q in vcsh_df.columns:
                v = vcsh_df.at[t, q]
                vcsh_now = float(v) if pd.notna(v) else None
            roe_row[q] = sector_roe(ttm, vcsh_now)

            lnst_now = None
            if t in lnst_df.index and q in lnst_df.columns:
                v = lnst_df.at[t, q]
                lnst_now = float(v) if pd.notna(v) else None
            prev_q = quarter_shift(q, -4)
            lnst_prev = None
            if t in lnst_df.index and prev_q in lnst_df.columns:
                v = lnst_df.at[t, prev_q]
                lnst_prev = float(v) if pd.notna(v) else None
            growth_row[q] = yoy_growth(lnst_now, lnst_prev)
        roe_rows[t] = roe_row
        growth_rows[t] = growth_row

    roe_df = pd.DataFrame.from_dict(roe_rows, orient="index")
    growth_df = pd.DataFrame.from_dict(growth_rows, orient="index")
    if len(roe_df.columns) > 0:
        roe_df = roe_df.reindex(columns=sorted(roe_df.columns, key=quarter_sort_key))
    if len(growth_df.columns) > 0:
        growth_df = growth_df.reindex(columns=sorted(growth_df.columns, key=quarter_sort_key))
    roe_df.index.name = "Ticker"
    growth_df.index.name = "Ticker"
    return roe_df, growth_df


UNIT_SCALE = 1_000_000  # xem giải thích quy ước đơn vị ở ticker_market_cap()


def ticker_market_cap(close, shares):
    """Vốn hóa 1 mã (VNĐ thô) tại 1 ngày, None nếu thiếu giá hoặc số CP.

    Lưu ý quy ước đơn vị lưu trữ nội bộ (đã kiểm tra thật qua data_storage/):
      - Close trong data_storage/prices/*.parquet lưu theo NGHÌN đồng (VD 33.75
        nghĩa là 33.750 VNĐ).
      - shares_outstanding.json (storage.get_shares_outstanding(), ghi bởi
        run_headless_update.py từ MarketCap(triệu đồng, theo Vietstock)/Close)
        lưu theo NGHÌN cổ phiếu.
    => VNĐ thô = Close(nghìn đồng) x Shares(nghìn CP) x 1_000_000
    (nghìn x nghìn = triệu, nhân thêm 1000 nữa mới ra đơn vị đồng thô)."""
    if close and shares and close > 0 and shares > 0:
        return close * shares * UNIT_SCALE
    return None


def sector_market_cap(closes_today, shares_outstanding, tickers):
    """Tổng vốn hóa ngành hôm nay (VNĐ thô) — tổng ticker_market_cap() qua
    các mã có đủ dữ liệu giá + số CP, bỏ qua mã thiếu."""
    total = 0.0
    for t in tickers:
        mc = ticker_market_cap(closes_today.get(t), shares_outstanding.get(t))
        if mc:
            total += mc
    return total


def compute_sector_quarterly_summary(vcsh_df, lnst_df, sector_groups, today=None):
    """Xây dựng toàn bộ nội dung Output/sector_finance_quarterly.json — tổng
    LNST/VCSH, TTM LNST, ROE, tăng trưởng YoY cho MỌI ngành (kể cả VNINDEX,
    VNINDEX_NONVIN) x MỌI quý có trong workbook.

    ROE/yoy_lnst_growth CHỈ được tính cho quý <= target_quarter_for_date(today)
    (quý liền trước quý dương lịch hiện tại — xem docstring đầu module) — quý
    ĐANG DIỄN RA (chưa kết thúc) luôn bị ép None vì chắc chắn chưa thể có báo
    cáo. Từ khi có carry_forward_missing_quarter() (gọi TRƯỚC hàm này, ở
    run_headless_update.py), quý mục tiêu luôn có đủ dữ liệu cho MỌI mã
    (thật hoặc tạm bù từ quý trước) nên không còn rủi ro mẫu quá thiếu như
    trước đây (đã từng gặp thật: VNINDEX Q2-2026 ra roe=7.5,
    yoy_lnst_growth=-0.98 do quý đó chỉ 5/302 mã báo cáo sớm, dưới cơ chế
    LAG_DAYS cũ). lnst_sum/vcsh_sum/ttm_lnst luôn tính cho MỌI quý có trong
    dữ liệu (không gate), chỉ ROE/G bị ép về None cho quý đang diễn ra."""
    if today is None:
        today = date.today()
    target_quarter_key = quarter_sort_key(target_quarter_for_date(today))
    all_quarters = sorted(set(vcsh_df.columns) | set(lnst_df.columns), key=quarter_sort_key)

    sectors_out = {}
    for code, group_def in sector_groups.items():
        tickers = resolve_finance_sector_tickers(code, group_def, sector_groups)
        if not tickers:
            continue

        lnst_sums = {}
        vcsh_sums = {}
        quarterly = {}
        for q in all_quarters:
            lnst_sum, lnst_cov = sector_quarter_sum(lnst_df, tickers, q)
            vcsh_sum, vcsh_cov = sector_quarter_sum(vcsh_df, tickers, q)
            lnst_sums[q] = lnst_sum
            vcsh_sums[q] = vcsh_sum
            quarterly[q] = {
                "lnst_sum": lnst_sum,
                "vcsh_sum": vcsh_sum,
                "coverage_tickers": max(lnst_cov, vcsh_cov),
                "ttm_lnst": None,
                "roe": None,
                "yoy_lnst_growth": None,
            }

        for q in all_quarters:
            trailing = [quarter_shift(q, -3), quarter_shift(q, -2), quarter_shift(q, -1), q]
            trailing_vals = [lnst_sums.get(x) for x in trailing]
            ttm = None if any(v is None for v in trailing_vals) else sum(trailing_vals)
            quarterly[q]["ttm_lnst"] = ttm

            quarter_due = quarter_sort_key(q) <= target_quarter_key
            if quarter_due:
                quarterly[q]["roe"] = sector_roe(ttm, vcsh_sums.get(q))
                quarterly[q]["yoy_lnst_growth"] = yoy_growth(lnst_sums.get(q), lnst_sums.get(quarter_shift(q, -4)))
            else:
                quarterly[q]["roe"] = None
                quarterly[q]["yoy_lnst_growth"] = None

            # Tập mã CHÍNH XÁC đã đóng góp vào ttm_lnst / vcsh_sum ở quý này —
            # dùng để giới hạn lại đúng tập mã khi tính vốn hóa cho P/E, P/B
            # hàng ngày (compute_and_append_daily_sector_finance), tránh lệch
            # tập mã giữa tử số (vốn hóa, tính trên toàn bộ mã có giá) và mẫu
            # số (tổng LNST/VCSH, chỉ tính trên mã có đủ dữ liệu tài chính).
            ttm_tickers = set(tickers)
            for tq in trailing:
                ttm_tickers &= set(sector_quarter_present_tickers(lnst_df, tickers, tq))
            quarterly[q]["ttm_tickers"] = sorted(ttm_tickers)
            quarterly[q]["vcsh_tickers"] = sorted(sector_quarter_present_tickers(vcsh_df, tickers, q))

        sectors_out[code] = {
            "name": group_def.get("name", code),
            "icon": group_def.get("icon", ""),
            "ticker_count": len(tickers),
            "quarterly": quarterly,
        }

    return {
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "quarters": all_quarters,
        "sectors": sectors_out,
    }


# ── Bước hàng ngày: P/E, P/B (gắn vào run_headless_update.py) ──

def _upsert_daily_point(daily, trading_date, values, field_names):
    """Chèn/ghi đè điểm của trading_date vào `daily` (dict với 'dates' +
    field_names, mỗi field 1 mảng song song theo 'dates'), rồi trả về `daily`
    đã sắp xếp lại tăng dần theo ngày. Dùng chung cho cả file theo ngành và
    file theo mã — an toàn tuyệt đối dù gọi không đúng thứ tự thời gian."""
    by_date = {
        d: tuple(daily[f][i] for f in field_names)
        for i, d in enumerate(daily["dates"])
    }
    by_date[trading_date] = tuple(values)
    sorted_dates = sorted(by_date.keys())
    daily["dates"] = sorted_dates
    for idx, f in enumerate(field_names):
        daily[f] = [by_date[d][idx] for d in sorted_dates]
    return daily


_SECTOR_DAILY_FIELDS = ("market_cap", "pe", "pb", "quarter_used")


def compute_and_append_daily_sector_finance(storage, sector_groups, output_dir, trading_date=None):
    """Đọc Output/sector_finance_quarterly.json (đã có, do Import Finance /
    Update finance vietcap ghi) + vốn hóa hôm nay, tính P/E, P/B ngày hôm nay
    cho mọi ngành (P/E ngành = tổng vốn hóa CHỈ tính trên tập mã đã đóng góp
    TTM LNST / tổng vốn hóa CHỈ tính trên tập mã có VCSH quý đó — xem
    "ttm_tickers"/"vcsh_tickers" trong compute_sector_quarterly_summary, tránh
    lệch tập mã giữa tử số/mẫu số). Append vào Output/finance/{SECTOR}.json.
    KHÔNG BAO GIỜ raise ra ngoài — nếu chưa có dữ liệu tài chính (chưa chạy
    Import/Update Finance lần nào) thì bỏ qua êm, không được làm hỏng pipeline
    hàng ngày."""
    summary_path = os.path.join(output_dir, "sector_finance_quarterly.json")
    if not os.path.exists(summary_path):
        print("[SectorFinance] Chưa có sector_finance_quarterly.json — bỏ qua bước P/E, P/B hàng ngày.")
        return

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception as e:
        print(f"[SectorFinance] Lỗi đọc sector_finance_quarterly.json: {e} — bỏ qua.")
        return

    quarters_sorted = sorted(summary.get("quarters", []), key=quarter_sort_key)
    if not quarters_sorted:
        return

    if trading_date is None:
        trading_date = datetime.now().strftime("%Y-%m-%d")

    shares_outstanding = storage.get_shares_outstanding() or {}
    finance_dir = os.path.join(output_dir, "finance")
    os.makedirs(finance_dir, exist_ok=True)

    eff_q = effective_quarter_for_live_date(trading_date, quarters_sorted)

    for code, sector_data in summary.get("sectors", {}).items():
        group_def = sector_groups.get(code, {})
        tickers = resolve_finance_sector_tickers(code, group_def, sector_groups)
        if not tickers:
            continue

        closes_today = {}
        for t in tickers:
            try:
                df = storage.load_ticker_data(t)
                if df is not None and not df.empty and "Close" in df.columns:
                    closes_today[t] = float(df.iloc[-1]["Close"])
            except Exception:
                continue

        market_cap = sector_market_cap(closes_today, shares_outstanding, tickers)

        pe = pb = None
        if eff_q:
            q_data = sector_data.get("quarterly", {}).get(eff_q, {})
            ttm_tickers = q_data.get("ttm_tickers") or []
            vcsh_tickers = q_data.get("vcsh_tickers") or []
            mc_for_pe = sector_market_cap(closes_today, shares_outstanding, ttm_tickers)
            mc_for_pb = sector_market_cap(closes_today, shares_outstanding, vcsh_tickers)
            pe = sector_pe(mc_for_pe, q_data.get("ttm_lnst"))
            pb = sector_pb(mc_for_pb, q_data.get("vcsh_sum"))

        finance_path = os.path.join(finance_dir, f"{code}.json")
        if os.path.exists(finance_path):
            try:
                with open(finance_path, "r", encoding="utf-8") as f:
                    fdata = json.load(f)
            except Exception:
                fdata = {}
        else:
            fdata = {}

        daily = fdata.setdefault("daily", {"dates": [], "market_cap": [], "pe": [], "pb": [], "quarter_used": []})
        for fld in _SECTOR_DAILY_FIELDS:
            daily.setdefault(fld, [None] * len(daily["dates"]))
        fdata["sector"] = code
        fdata.setdefault("quarterly", {})

        # Ghi theo kiểu dict-theo-ngày rồi serialize lại ĐÃ SẮP XẾP tăng dần —
        # an toàn tuyệt đối dù hàm được gọi không đúng thứ tự thời gian (VD
        # chạy bù cho 1 ngày trong quá khứ sau khi đã có dữ liệu hôm nay),
        # tránh lặp lại đúng lỗi "time không tăng dần nghiêm ngặt" đã gặp với
        # dữ liệu company-ratio-daily của Vietcap trong tab Thống kê giao dịch.
        _upsert_daily_point(daily, trading_date, (market_cap, pe, pb, eff_q), _SECTOR_DAILY_FIELDS)

        fdata["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(finance_path, "w", encoding="utf-8") as f:
                json.dump(fdata, f, ensure_ascii=False)
        except Exception as e:
            print(f"[SectorFinance] Lỗi ghi {finance_path}: {e}")


def overwrite_quarterly_block(sector_groups, summary, output_dir):
    """Ghi đè CHỈ phần 'quarterly' của Output/finance/{SECTOR}.json cho mọi
    ngành có trong summary — dùng bởi Import Finance / Update finance vietcap.
    KHÔNG đụng tới phần 'daily' (thuộc lãnh địa riêng của bước hàng ngày)."""
    finance_dir = os.path.join(output_dir, "finance")
    os.makedirs(finance_dir, exist_ok=True)

    for code, sector_data in summary.get("sectors", {}).items():
        finance_path = os.path.join(finance_dir, f"{code}.json")
        if os.path.exists(finance_path):
            try:
                with open(finance_path, "r", encoding="utf-8") as f:
                    fdata = json.load(f)
            except Exception:
                fdata = {}
        else:
            fdata = {}

        fdata["sector"] = code
        fdata.setdefault("daily", {"dates": [], "market_cap": [], "pe": [], "pb": [], "quarter_used": []})

        quarters = sector_data.get("quarterly", {})
        labels = sorted(quarters.keys(), key=quarter_sort_key)
        fdata["quarterly"] = {
            "labels": labels,
            "lnst_sum": [quarters[q]["lnst_sum"] for q in labels],
            "vcsh_sum": [quarters[q]["vcsh_sum"] for q in labels],
            "ttm_lnst": [quarters[q]["ttm_lnst"] for q in labels],
            "roe": [quarters[q]["roe"] for q in labels],
            "yoy_lnst_growth": [quarters[q]["yoy_lnst_growth"] for q in labels],
            "ttm_tickers": [quarters[q].get("ttm_tickers", []) for q in labels],
            "vcsh_tickers": [quarters[q].get("vcsh_tickers", []) for q in labels],
        }
        fdata["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(finance_path, "w", encoding="utf-8") as f:
            json.dump(fdata, f, ensure_ascii=False)


def log_finance_coverage_gaps(sector_groups, vcsh_df, lnst_df, expected_quarter):
    """In ra log (GitHub Actions run output) độ phủ dữ liệu VCSH/LNST của
    `expected_quarter` so với TOÀN BỘ vũ trụ mã tài chính (get_finance_ticker_universe)
    — giúp biết Import Finance / Update finance vietcap đã đạt độ phủ đầy đủ
    hay chưa, và mã nào còn thiếu cần chú ý thủ công. Không raise, không ghi
    file — chỉ là chẩn đoán hiển thị trong log chạy Action."""
    if not expected_quarter:
        print("[SectorFinance] Không xác định được quý kỳ vọng — bỏ qua kiểm tra độ phủ.")
        return
    universe = sorted(get_finance_ticker_universe(sector_groups))
    missing_vcsh = [
        t for t in universe
        if not (vcsh_df is not None and t in vcsh_df.index and expected_quarter in vcsh_df.columns
                and pd.notna(vcsh_df.at[t, expected_quarter]))
    ]
    missing_lnst = [
        t for t in universe
        if not (lnst_df is not None and t in lnst_df.index and expected_quarter in lnst_df.columns
                and pd.notna(lnst_df.at[t, expected_quarter]))
    ]
    print(f"[SectorFinance] Độ phủ {expected_quarter}: "
          f"{len(universe) - len(missing_vcsh)}/{len(universe)} có VCSH, "
          f"{len(universe) - len(missing_lnst)}/{len(universe)} có LNST.")
    if missing_vcsh:
        print(f"[SectorFinance] Thiếu VCSH {expected_quarter} ({len(missing_vcsh)} mã): {missing_vcsh}")
    if missing_lnst:
        print(f"[SectorFinance] Thiếu LNST {expected_quarter} ({len(missing_lnst)} mã): {missing_lnst}")


def tickers_needing_update(vcsh_df, lnst_df, tickers, expected_quarter, earliest_quarter=None,
                            vcsh_placeholder_df=None, lnst_placeholder_df=None):
    """Trả về danh sách con của `tickers` CẦN gọi lại Vietcap trong Update
    finance vietcap — thiếu 1 trong 3 điều kiện:
      1. Chưa có VCSH/LNST THẬT (không tính giá trị carry-forward tạm, xem
         carry_forward_missing_quarter()) cho `expected_quarter` (quý mục
         tiêu, target_quarter_for_date()) — mã có tin tức tài chính mới cần
         cập nhật, hoặc đang tạm dùng số bù nên vẫn cần thử lại.
      2. Chưa có đủ VCSH/LNST cho `earliest_quarter` (mốc lịch sử xa nhất
         đang chốt, VD FINANCE_SINCE_YEAR trong run_headless_update.py) —
         mã còn thiếu dữ liệu lịch sử (VD sau khi tăng độ sâu lịch sử cần
         cào, những mã đã có sẵn quý mới nhất vẫn phải cào lại để bổ sung
         phần lịch sử còn thiếu, không thì sẽ bị bỏ sót vĩnh viễn).
      3. (Chỉ khi truyền vcsh_placeholder_df/lnst_placeholder_df) Còn CỜ
         placeholder=True ở BẤT KỲ quý nào trong lịch sử của mã đó — chi phí
         gọi Vietcap là theo MÃ (trả về toàn bộ lịch sử), không theo quý, nên
         tiện thể thử lại luôn cho mọi ô còn đang tạm bù, không chỉ riêng
         quý mục tiêu — tránh 1 mã lỡ bỏ lỡ đúng 1 quý cũ rồi báo cáo lại
         bình thường sau đó bị kẹt vĩnh viễn ở giá trị tạm.
    Mã đã có đủ CẢ 3 mốc thì bỏ qua, không gọi lại API (tiết kiệm request).
    earliest_quarter=None thì bỏ qua điều kiện 2 (giữ hành vi cũ)."""
    need = []
    for t in tickers:
        has_expected = (
            t in vcsh_df.index and expected_quarter in vcsh_df.columns
            and pd.notna(vcsh_df.at[t, expected_quarter])
            and t in lnst_df.index and expected_quarter in lnst_df.columns
            and pd.notna(lnst_df.at[t, expected_quarter])
        )
        if has_expected and vcsh_placeholder_df is not None:
            has_expected = has_expected and not (
                t in vcsh_placeholder_df.index and expected_quarter in vcsh_placeholder_df.columns
                and bool(vcsh_placeholder_df.at[t, expected_quarter])
            )
        if has_expected and lnst_placeholder_df is not None:
            has_expected = has_expected and not (
                t in lnst_placeholder_df.index and expected_quarter in lnst_placeholder_df.columns
                and bool(lnst_placeholder_df.at[t, expected_quarter])
            )

        has_earliest = True
        if earliest_quarter is not None:
            has_earliest = (
                t in vcsh_df.index and earliest_quarter in vcsh_df.columns
                and pd.notna(vcsh_df.at[t, earliest_quarter])
                and t in lnst_df.index and earliest_quarter in lnst_df.columns
                and pd.notna(lnst_df.at[t, earliest_quarter])
            )

        has_no_stale_placeholder = True
        if vcsh_placeholder_df is not None and t in vcsh_placeholder_df.index:
            has_no_stale_placeholder = has_no_stale_placeholder and not bool(vcsh_placeholder_df.loc[t].any())
        if lnst_placeholder_df is not None and t in lnst_placeholder_df.index:
            has_no_stale_placeholder = has_no_stale_placeholder and not bool(lnst_placeholder_df.loc[t].any())

        if not (has_expected and has_earliest and has_no_stale_placeholder):
            need.append(t)
    return need


def backfill_daily_sector_finance_history(storage, sector_groups, output_dir):
    """Tính lại TOÀN BỘ chuỗi P/E, P/B hàng ngày (2019 -> nay) cho mọi ngành,
    dùng bởi Import Finance sau khi nạp dữ liệu ban đầu (lúc đó chưa có điểm
    'daily' nào). Ghi đè hoàn toàn phần 'daily' (không phải append — đây là
    thao tác hiếm, tính lại từ đầu là hợp lý), giữ nguyên phần 'quarterly' đã
    có (do overwrite_quarterly_block() ghi riêng). P/E, P/B ngành dùng đúng
    quy ước tập mã đã thống nhất ở compute_and_append_daily_sector_finance
    (ttm_tickers/vcsh_tickers)."""
    summary_path = os.path.join(output_dir, "sector_finance_quarterly.json")
    if not os.path.exists(summary_path):
        print("[SectorFinance] Chưa có sector_finance_quarterly.json — bỏ qua backfill lịch sử.")
        return

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    quarters_sorted = sorted(summary.get("quarters", []), key=quarter_sort_key)
    if not quarters_sorted:
        return

    shares_outstanding = storage.get_shares_outstanding() or {}

    all_needed_tickers = set()
    for code, group_def in sector_groups.items():
        all_needed_tickers |= set(resolve_finance_sector_tickers(code, group_def, sector_groups))

    # Nạp trước toàn bộ lịch sử giá của mọi mã cần dùng — tra cứu qua dict
    # trong bộ nhớ thay vì đọc lại parquet mỗi ngày (nhanh hơn nhiều với hàng
    # nghìn phiên x hàng trăm mã).
    price_series = {}
    for t in all_needed_tickers:
        df = storage.load_ticker_data(t)
        if df is None or df.empty or "Close" not in df.columns:
            continue
        s = df.set_index(df["Date"].dt.strftime("%Y-%m-%d"))["Close"]
        price_series[t] = s.to_dict()

    vni_df = storage.load_ticker_data("VNINDEX")
    if vni_df is None or vni_df.empty:
        print("[SectorFinance] Không có lịch giao dịch VNINDEX — bỏ qua backfill lịch sử.")
        return
    trading_dates = sorted(vni_df["Date"].dt.strftime("%Y-%m-%d").unique())

    sector_daily = {
        code: {"dates": [], "market_cap": [], "pe": [], "pb": [], "quarter_used": []}
        for code in summary.get("sectors", {})
    }

    for d in trading_dates:
        eff_q = effective_quarter_for_date(d, quarters_sorted)
        closes_today = {t: price_series[t][d] for t in all_needed_tickers if t in price_series and d in price_series[t]}

        for code, sector_data in summary.get("sectors", {}).items():
            group_def = sector_groups.get(code, {})
            tickers = resolve_finance_sector_tickers(code, group_def, sector_groups)
            if not tickers:
                continue
            market_cap = sector_market_cap(closes_today, shares_outstanding, tickers)
            pe = pb = None
            if eff_q:
                q_data = sector_data.get("quarterly", {}).get(eff_q, {})
                ttm_tickers = q_data.get("ttm_tickers") or []
                vcsh_tickers = q_data.get("vcsh_tickers") or []
                mc_for_pe = sector_market_cap(closes_today, shares_outstanding, ttm_tickers)
                mc_for_pb = sector_market_cap(closes_today, shares_outstanding, vcsh_tickers)
                pe = sector_pe(mc_for_pe, q_data.get("ttm_lnst"))
                pb = sector_pb(mc_for_pb, q_data.get("vcsh_sum"))
            sd = sector_daily[code]
            sd["dates"].append(d)
            sd["market_cap"].append(market_cap)
            sd["pe"].append(pe)
            sd["pb"].append(pb)
            sd["quarter_used"].append(eff_q)

    finance_dir = os.path.join(output_dir, "finance")
    os.makedirs(finance_dir, exist_ok=True)
    for code, daily in sector_daily.items():
        finance_path = os.path.join(finance_dir, f"{code}.json")
        fdata = {"sector": code, "daily": daily, "quarterly": {}}
        if os.path.exists(finance_path):
            try:
                with open(finance_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                fdata["quarterly"] = old.get("quarterly", {})
            except Exception:
                pass
        fdata["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(finance_path, "w", encoding="utf-8") as f:
            json.dump(fdata, f, ensure_ascii=False)

    print(f"[SectorFinance] Đã backfill P/E, P/B lịch sử cho {len(sector_daily)} ngành, {len(trading_dates)} phiên.")
