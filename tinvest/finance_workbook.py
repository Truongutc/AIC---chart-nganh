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

Workbook có 6 sheet: "VCSH", "LNST" (dữ liệu gốc, merge/ghi đè bởi Update
finance vietcap), "VCSH_PLACEHOLDER", "LNST_PLACEHOLDER" (cờ bool cùng shape
với VCSH/LNST — True = ô đó đang là số liệu quý TRƯỚC được lấy TẠM để bù cho
quý mới chưa công bố, không phải số thật, xem sector_finance_engine.py
carry_forward_missing_quarter()), "ROE", "LNST_YOY" (tính từ VCSH/LNST, xem
tinvest/sector_finance_engine.py compute_per_ticker_roe_and_growth — luôn
tính lại mới hoàn toàn mỗi lần chạy Import Finance / Update finance vietcap,
không bao giờ đọc lại làm input merge).

Schema (mỗi sheet): cột đầu "Ticker" (mã, viết hoa) làm hàng, các cột sau là
nhãn quý dạng "Qn-YYYY" (VD "Q1-2019", "Q2-2019", ...), sắp xếp tăng dần theo
thời gian trái->phải, mỗi dòng đúng 1 mã. VCSH/LNST = VNĐ thô; ROE = tỷ lệ
thập phân; LNST_YOY = tỷ lệ thập phân (tăng trưởng YoY); VCSH_PLACEHOLDER/
LNST_PLACEHOLDER = bool (True/False).
"""

import io
import re

import pandas as pd

QUARTER_RE = re.compile(r"^Q([1-4])-(\d{4})$")
INDEX_NAME = "Ticker"
WORKBOOK_NAME = "sector_finance_ticker_data.xlsx"
ALL_SHEET_NAMES = ("VCSH", "LNST", "VCSH_PLACEHOLDER", "LNST_PLACEHOLDER", "ROE", "LNST_YOY")
PLACEHOLDER_SHEET_NAMES = ("VCSH_PLACEHOLDER", "LNST_PLACEHOLDER")


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
    """Tạo 4 sheet rỗng (chưa có cột quý nào), sẵn hàng cho các mã đã biết —
    2 sheet giá trị (VCSH/LNST) + 2 sheet cờ placeholder tương ứng (rỗng, coi
    như "chưa có gì để đánh dấu placeholder", đúng nghĩa khi chưa có dữ liệu)."""
    index = pd.Index(sorted(set(tickers or [])), name=INDEX_NAME)
    return {
        "VCSH": pd.DataFrame(index=index),
        "LNST": pd.DataFrame(index=index),
        "VCSH_PLACEHOLDER": pd.DataFrame(index=index),
        "LNST_PLACEHOLDER": pd.DataFrame(index=index),
    }


def _normalize_placeholder_df(ph_df, value_df):
    """Đưa 1 sheet cờ placeholder về ĐÚNG shape (index/columns) với sheet giá
    trị đi kèm (VCSH hoặc LNST) — reindex (điền False cho hàng/cột mới xuất
    hiện), fillna(False), ép kiểu bool. PHẢI gọi hàm này mỗi khi đọc/merge/tra
    cứu 1 sheet placeholder — đảm bảo không bao giờ lệch shape (KeyError) và
    không bao giờ có NaN lẫn vào cột bool (bool dtype có NaN sẽ tự ép lên
    object dtype, khiến so sánh/truth-value không còn đáng tin cậy)."""
    if ph_df is None:
        ph_df = pd.DataFrame()
    ph = ph_df.reindex(index=value_df.index, columns=value_df.columns, fill_value=False)
    ph = ph.fillna(False).astype(bool)
    _with_ticker_index_name(ph)
    return ph


def load_workbook_from_bytes(xlsx_bytes):
    """Đọc 2 sheet VCSH/LNST (+ 2 sheet cờ placeholder đi kèm) từ nội dung
    .xlsx (bytes, VD tải về từ Drive). Trả về workbook rỗng nếu bytes là None
    (chưa từng có file trên Drive) HOẶC
    nếu file tồn tại nhưng thiếu sheet VCSH/LNST — VD file placeholder rỗng
    người dùng tự tạo để né lỗi storageQuotaExceeded của Service Account (xem
    gdrive_client.upload_file: Service Account không tạo file mới được, chỉ
    update file đã có sẵn tên đúng) — không bao giờ raise ra ngoài, coi các
    trường hợp này tương đương "chưa có dữ liệu gì".

    2 sheet cờ placeholder (VCSH_PLACEHOLDER/LNST_PLACEHOLDER) được đọc ở 1
    try/except HOÀN TOÀN RIÊNG, KHÔNG được gộp chung vào cùng 1 lệnh
    pd.read_excel(sheet_name=[...]) với VCSH/LNST — nếu gộp chung, ngay lần
    chạy ĐẦU TIÊN sau khi triển khai tính năng này, workbook thật trên Drive
    (chưa hề có 2 sheet placeholder) sẽ khiến pd.read_excel raise vì thiếu
    sheet, và nhánh except phía trên sẽ hiểu nhầm là "chưa có dữ liệu gì" rồi
    XOÁ SẠCH toàn bộ VCSH/LNST nhiều năm đang có — 1 lỗi mất dữ liệu nghiêm
    trọng. Workbook cũ (chưa có sheet placeholder) phải được hiểu đúng là
    "chưa từng có ô nào được đánh dấu placeholder" (mọi số liệu hiện có đều là
    số thật), không phải "không có dữ liệu gì"."""
    if not xlsx_bytes:
        return new_empty_workbook()
    try:
        sheets = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=["VCSH", "LNST"], index_col=0, engine="openpyxl")
    except ValueError as e:
        print(f"[FinanceWorkbook] File trên Drive thiếu sheet VCSH/LNST ({e}) — coi như chưa có dữ liệu, "
              f"sẽ tạo đầy đủ 6 sheet khi ghi lại lần này.")
        return new_empty_workbook()
    for name, df in sheets.items():
        df.index = df.index.astype(str).str.upper()
        df.columns = df.columns.astype(str)
        _with_ticker_index_name(df)

    try:
        ph_sheets = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=list(PLACEHOLDER_SHEET_NAMES),
                                   index_col=0, engine="openpyxl")
        for name, df in ph_sheets.items():
            df.index = df.index.astype(str).str.upper()
            df.columns = df.columns.astype(str)
    except ValueError:
        # Workbook cũ chưa có 2 sheet này — không phải lỗi, chỉ là chưa từng
        # có ô nào carry-forward trước khi tính năng này tồn tại.
        ph_sheets = {"VCSH_PLACEHOLDER": pd.DataFrame(), "LNST_PLACEHOLDER": pd.DataFrame()}
    sheets["VCSH_PLACEHOLDER"] = _normalize_placeholder_df(ph_sheets["VCSH_PLACEHOLDER"], sheets["VCSH"])
    sheets["LNST_PLACEHOLDER"] = _normalize_placeholder_df(ph_sheets["LNST_PLACEHOLDER"], sheets["LNST"])
    return sheets


def load_workbook_from_path(path):
    with open(path, "rb") as f:
        return load_workbook_from_bytes(f.read())


def save_workbook_to_path(sheets, path):
    """Ghi tối đa 6 sheet (xem ALL_SHEET_NAMES) ra file .xlsx, cột luôn
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


def _combine_metric_with_placeholder(existing_df, existing_ph_df, new_df):
    """Gộp 1 sheet (VCSH hoặc LNST) CÓ XÉT cờ placeholder — khác combine_first
    thường ở chỗ: 1 ô đang carry-forward (có giá trị, nhưng placeholder=True,
    xem carry_forward_missing_quarter() ở sector_finance_engine.py) KHÔNG được
    coi là "đã có giá trị thật", nên vẫn phải nhường chỗ cho dữ liệu mới nếu
    Vietcap đã có số thật — combine_first thường (chỉ phân biệt NaN/không-NaN)
    không thể diễn đạt điều này, vì ô carry-forward không hề là NaN.

    Quy tắc mỗi ô: existing thắng CHỈ KHI nó là số thật (không NaN VÀ không bị
    đánh dấu placeholder) — giữ nguyên hành vi "bất khả xâm phạm" cũ cho số
    liệu đã xác nhận. Ngược lại (đang thiếu hoặc đang placeholder): nếu new_df
    có giá trị thì lấy giá trị mới, đánh dấu placeholder=False (Vietcap chỉ
    trả về số đã công bố thật, không bao giờ là số bù); nếu new_df cũng không
    có gì, giữ nguyên trạng thái cũ (để carry_forward_missing_quarter() xử lý
    tiếp sau).

    Trả về (merged_df, merged_ph_df, set_cột_MỚI_XUẤT_HIỆN_lần_đầu)."""
    if existing_df is None:
        existing_df = pd.DataFrame()
    if new_df is None:
        new_df = pd.DataFrame()

    new_cols = set(new_df.columns) - set(existing_df.columns)

    if new_df.empty:
        merged_df = existing_df.copy()
        merged_ph = _normalize_placeholder_df(existing_ph_df, merged_df)
    else:
        idx = existing_df.index.union(new_df.index)
        cols = existing_df.columns.union(new_df.columns)

        existing_aligned = existing_df.reindex(index=idx, columns=cols)
        new_aligned = new_df.reindex(index=idx, columns=cols)
        ph_aligned = _normalize_placeholder_df(existing_ph_df, existing_aligned)

        existing_real = existing_aligned.notna() & (~ph_aligned)
        new_has_value = new_aligned.notna()
        take_new = (~existing_real) & new_has_value

        merged_df = existing_aligned.mask(take_new, new_aligned)
        merged_ph = ph_aligned.mask(take_new, False)

    if len(merged_df.columns) > 0:
        merged_df = merged_df.reindex(columns=sorted(merged_df.columns, key=quarter_sort_key))
        merged_ph = merged_ph.reindex(columns=merged_df.columns)
    merged_df = merged_df.sort_index()
    merged_ph = merged_ph.reindex(index=merged_df.index)
    merged_ph = merged_ph.fillna(False).astype(bool)
    _with_ticker_index_name(merged_df)
    _with_ticker_index_name(merged_ph)
    return merged_df, merged_ph, new_cols


def merge_new_quarters(existing_sheets, new_data):
    """Gộp dữ liệu mới (dạng row-dict, từ Vietcap) vào workbook hiện có —
    CHỈ thêm cột quý mới bên phải và điền các ô còn thiếu (NaN hoặc đang
    placeholder), KHÔNG BAO GIỜ ghi đè 1 ô (ticker, quý) đã có sẵn giá trị
    THẬT (xem _combine_metric_with_placeholder).

    new_data: {ticker: {'VCSH': {quý: giá_trị}, 'LNST': {quý: giá_trị}}}
              (đúng shape trả về từ vietcap_finance_client.fetch_all_tickers_finance).

    Trả về (merged_sheets — gồm cả 2 sheet cờ placeholder,
    danh_sách_quý_MỚI_XUẤT_HIỆN_lần_đầu — để biết cần backfill lịch sử P/E,
    P/B cho những quý nào)."""
    merged = {}
    all_new_quarters = set()

    for metric, ph_metric in (("VCSH", "VCSH_PLACEHOLDER"), ("LNST", "LNST_PLACEHOLDER")):
        existing_df = existing_sheets.get(metric)
        existing_ph_df = existing_sheets.get(ph_metric)

        rows = {}
        for ticker, metrics in new_data.items():
            qvals = metrics.get(metric) or {}
            if qvals:
                rows[str(ticker).upper()] = qvals
        new_df = pd.DataFrame.from_dict(rows, orient="index")

        merged_df, merged_ph_df, new_cols = _combine_metric_with_placeholder(existing_df, existing_ph_df, new_df)
        merged[metric] = merged_df
        merged[ph_metric] = merged_ph_df
        all_new_quarters |= new_cols

    return merged, sorted(all_new_quarters, key=quarter_sort_key)


