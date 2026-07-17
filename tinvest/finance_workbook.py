"""
Đọc/ghi/merge file Excel (.xlsx) lưu trên Google Drive — dữ liệu tài chính
quý (mặc định 2019 -> hiện tại) của 302 mã cổ phiếu trong sector_groups.json.

CHỈ CÓ 1 WORKBOOK DUY NHẤT (WORKBOOK_NAME) trên Drive, được cập nhật liên tục
tại chỗ:
  - "Update finance vietcap" cào dữ liệu quý mới từ Vietcap cho các mã còn
    thiếu, gộp thêm cột/ô còn trống vào workbook này (merge_new_quarters),
    rồi ghi đè lại đúng file đó trên Drive.
  - "Import Finance" KHÔNG cào Vietcap — chỉ tải THẲNG workbook này về, tính
    lại toàn bộ ROE/tăng trưởng LNST + tổng hợp ngành + backfill lịch sử P/E,
    P/B từ chính nó. Dùng để build lại nhanh sau khi chạy "Clear Finance"
    (chỉ xoá JSON, giữ nguyên workbook) mà không phải cào lại từ đầu. Lần đầu
    tiên (chưa từng có workbook nào trên Drive), người dùng tự chuẩn bị và
    tải lên 1 file .xlsx đúng tên WORKBOOK_NAME, đúng shape wide bên dưới.

Workbook có 4 sheet: "VCSH", "LNST" (dữ liệu gốc, merge/ghi đè bởi Update
finance vietcap), "ROE", "LNST_YOY" (tính từ 2 sheet gốc, xem
tinvest/sector_finance_engine.py compute_per_ticker_roe_and_growth — luôn
tính lại mới hoàn toàn mỗi lần chạy Import Finance / Update finance vietcap,
không bao giờ đọc lại làm input merge).

Schema (mỗi sheet): cột đầu "Ticker" (mã, viết hoa) làm hàng, các cột sau là
nhãn quý dạng "Qn-YYYY" (VD "Q1-2019", "Q2-2019", ...), sắp xếp tăng dần theo
thời gian trái->phải, mỗi dòng đúng 1 mã. VCSH/LNST = VNĐ thô; ROE = tỷ lệ
thập phân; LNST_YOY = tỷ lệ thập phân (tăng trưởng YoY).
"""

import io
import re

import pandas as pd

QUARTER_RE = re.compile(r"^Q([1-4])-(\d{4})$")
INDEX_NAME = "Ticker"
WORKBOOK_NAME = "sector_finance_ticker_data.xlsx"
ALL_SHEET_NAMES = ("VCSH", "LNST", "ROE", "LNST_YOY")


def quarter_sort_key(label):
    """'Q3-2024' -> (2024, 3). Raise nếu nhãn sai định dạng (lỗi sớm khi
    merge, không âm thầm sắp xếp sai)."""
    m = QUARTER_RE.match(str(label))
    if not m:
        raise ValueError(f"Nhãn quý không hợp lệ: {label!r} (cần dạng 'Qn-YYYY')")
    return int(m.group(2)), int(m.group(1))


def _with_ticker_index_name(df):
    df.index.name = INDEX_NAME
    return df


def new_empty_workbook(tickers=None):
    """Tạo 2 sheet rỗng (chưa có cột quý nào), sẵn hàng cho các mã đã biết."""
    index = pd.Index(sorted(set(tickers or [])), name=INDEX_NAME)
    return {
        "VCSH": pd.DataFrame(index=index),
        "LNST": pd.DataFrame(index=index),
    }


def load_workbook_from_bytes(xlsx_bytes):
    """Đọc 2 sheet VCSH/LNST từ nội dung .xlsx (bytes, VD tải về từ Drive).
    Trả về workbook rỗng nếu bytes là None (chưa từng có file trên Drive) HOẶC
    nếu file tồn tại nhưng thiếu sheet VCSH/LNST — VD file placeholder rỗng
    người dùng tự tạo để né lỗi storageQuotaExceeded của Service Account (xem
    gdrive_client.upload_file: Service Account không tạo file mới được, chỉ
    update file đã có sẵn tên đúng) — không bao giờ raise ra ngoài, coi các
    trường hợp này tương đương "chưa có dữ liệu gì"."""
    if not xlsx_bytes:
        return new_empty_workbook()
    try:
        sheets = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=["VCSH", "LNST"], index_col=0, engine="openpyxl")
    except ValueError as e:
        print(f"[FinanceWorkbook] File trên Drive thiếu sheet VCSH/LNST ({e}) — coi như chưa có dữ liệu, "
              f"sẽ tạo đầy đủ 4 sheet khi ghi lại lần này.")
        return new_empty_workbook()
    for name, df in sheets.items():
        df.index = df.index.astype(str).str.upper()
        df.columns = df.columns.astype(str)
        _with_ticker_index_name(df)
    return sheets


def load_workbook_from_path(path):
    with open(path, "rb") as f:
        return load_workbook_from_bytes(f.read())


def save_workbook_to_path(sheets, path):
    """Ghi tối đa 4 sheet (VCSH, LNST, ROE, LNST_YOY) ra file .xlsx, cột luôn
    sắp xếp tăng dần theo quý, cột đầu luôn có tiêu đề rõ ràng "Ticker"."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name in ALL_SHEET_NAMES:
            df = sheets.get(name)
            if df is None:
                df = pd.DataFrame()
            if len(df.columns) > 0:
                df = df.reindex(columns=sorted(df.columns, key=quarter_sort_key))
            df = df.sort_index()
            _with_ticker_index_name(df)
            df.to_excel(writer, sheet_name=name)


def _combine_metric(existing_df, new_df):
    """Gộp 1 sheet (VCSH hoặc LNST): combine_first (existing luôn thắng, chỉ
    điền ô NaN / thêm cột quý mới), sort cột theo quý, sort index. Trả về
    (merged_df, set_cột_MỚI_XUẤT_HIỆN_lần_đầu)."""
    if existing_df is None:
        existing_df = pd.DataFrame()
    if new_df is None:
        new_df = pd.DataFrame()

    if existing_df.empty:
        merged_df = new_df
        new_cols = set(new_df.columns)
    elif new_df.empty:
        merged_df = existing_df
        new_cols = set()
    else:
        new_cols = set(new_df.columns) - set(existing_df.columns)
        # combine_first: giá trị của existing_df được ưu tiên tuyệt đối,
        # new_df chỉ điền vào đúng những ô đang là NaN (thiếu dữ liệu) —
        # không bao giờ ghi đè ô đã có giá trị.
        merged_df = existing_df.combine_first(new_df)

    if len(merged_df.columns) > 0:
        merged_df = merged_df.reindex(columns=sorted(merged_df.columns, key=quarter_sort_key))
    merged_df = merged_df.sort_index()
    _with_ticker_index_name(merged_df)
    return merged_df, new_cols


def merge_new_quarters(existing_sheets, new_data):
    """Gộp dữ liệu mới (dạng row-dict, từ Vietcap) vào workbook hiện có —
    CHỈ thêm cột quý mới bên phải và điền các ô còn thiếu (NaN), KHÔNG BAO
    GIỜ ghi đè 1 ô (ticker, quý) đã có sẵn giá trị thật.

    new_data: {ticker: {'VCSH': {quý: giá_trị}, 'LNST': {quý: giá_trị}}}
              (đúng shape trả về từ vietcap_finance_client.fetch_all_tickers_finance).

    Trả về (merged_sheets, danh_sách_quý_MỚI_XUẤT_HIỆN_lần_đầu — để biết cần
    backfill lịch sử P/E, P/B cho những quý nào)."""
    merged = {}
    all_new_quarters = set()

    for metric in ("VCSH", "LNST"):
        existing_df = existing_sheets.get(metric)

        rows = {}
        for ticker, metrics in new_data.items():
            qvals = metrics.get(metric) or {}
            if qvals:
                rows[str(ticker).upper()] = qvals
        new_df = pd.DataFrame.from_dict(rows, orient="index")

        merged_df, new_cols = _combine_metric(existing_df, new_df)
        merged[metric] = merged_df
        all_new_quarters |= new_cols

    return merged, sorted(all_new_quarters, key=quarter_sort_key)


