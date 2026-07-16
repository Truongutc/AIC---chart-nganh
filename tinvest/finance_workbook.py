"""
Đọc/ghi/merge file Excel (.xlsx) 2 sheet "VCSH" và "LNST" lưu trên Google
Drive — dữ liệu tài chính quý (mặc định 2019 -> hiện tại, tùy theo dữ liệu
Import Finance nạp vào) của 302 mã cổ phiếu trong sector_groups.json.

Schema (mỗi sheet): cột đầu "Ticker" (mã, viết hoa) làm hàng, các cột sau là
nhãn quý dạng "Qn-YYYY" (VD "Q1-2019", "Q2-2019", ...), sắp xếp tăng dần theo
thời gian trái->phải, mỗi dòng đúng 1 mã. Giá trị = VNĐ thô.
"""

import io
import re

import pandas as pd

QUARTER_RE = re.compile(r"^Q([1-4])-(\d{4})$")
INDEX_NAME = "Ticker"


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
    Trả về workbook rỗng nếu bytes là None (chưa từng có file trên Drive)."""
    if not xlsx_bytes:
        return new_empty_workbook()
    sheets = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=["VCSH", "LNST"], index_col=0, engine="openpyxl")
    for name, df in sheets.items():
        df.index = df.index.astype(str).str.upper()
        df.columns = df.columns.astype(str)
        _with_ticker_index_name(df)
    return sheets


def load_workbook_from_path(path):
    with open(path, "rb") as f:
        return load_workbook_from_bytes(f.read())


def save_workbook_to_path(sheets, path):
    """Ghi 2 sheet ra file .xlsx, cột luôn sắp xếp tăng dần theo quý, cột đầu
    luôn có tiêu đề rõ ràng "Ticker"."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name in ("VCSH", "LNST"):
            df = sheets.get(name)
            if df is None:
                df = pd.DataFrame()
            if len(df.columns) > 0:
                df = df.reindex(columns=sorted(df.columns, key=quarter_sort_key))
            df = df.sort_index()
            _with_ticker_index_name(df)
            df.to_excel(writer, sheet_name=name)


def merge_new_quarters(existing_sheets, new_data):
    """Gộp dữ liệu mới vào workbook hiện có — CHỈ thêm cột quý mới bên phải
    và điền các ô còn thiếu (NaN), KHÔNG BAO GIỜ ghi đè 1 ô (ticker, quý) đã
    có sẵn giá trị thật.

    new_data: {ticker: {'VCSH': {quý: giá_trị}, 'LNST': {quý: giá_trị}}}
              (đúng shape trả về từ vietcap_finance_client.fetch_all_tickers_finance
              hoặc từ parse_long_format_csv()).

    Trả về (merged_sheets, danh_sách_quý_MỚI_XUẤT_HIỆN_lần_đầu — để biết cần
    backfill lịch sử P/E, P/B cho những quý nào)."""
    merged = {}
    all_new_quarters = set()

    for metric in ("VCSH", "LNST"):
        existing_df = existing_sheets.get(metric)
        if existing_df is None:
            existing_df = pd.DataFrame()

        rows = {}
        for ticker, metrics in new_data.items():
            qvals = metrics.get(metric) or {}
            if qvals:
                rows[str(ticker).upper()] = qvals
        new_df = pd.DataFrame.from_dict(rows, orient="index")

        if existing_df.empty:
            merged_df = new_df
            all_new_quarters |= set(new_df.columns)
        elif new_df.empty:
            merged_df = existing_df
        else:
            new_cols = set(new_df.columns) - set(existing_df.columns)
            all_new_quarters |= new_cols
            # combine_first: giá trị của existing_df được ưu tiên tuyệt đối,
            # new_df chỉ điền vào đúng những ô đang là NaN (thiếu dữ liệu) —
            # không bao giờ ghi đè ô đã có giá trị.
            merged_df = existing_df.combine_first(new_df)

        if len(merged_df.columns) > 0:
            merged_df = merged_df.reindex(columns=sorted(merged_df.columns, key=quarter_sort_key))
        merged_df = merged_df.sort_index()
        _with_ticker_index_name(merged_df)
        merged[metric] = merged_df

    return merged, sorted(all_new_quarters, key=quarter_sort_key)


def parse_long_format_csv(csv_path):
    """Đọc CSV nạp ban đầu (Import Finance) dạng dài: cột Ticker, Year,
    Quarter, VCSH, LNST — mỗi dòng 1 cặp mã-quý. Trả về đúng shape new_data
    mà merge_new_quarters() cần: {ticker: {'VCSH': {quý: giá_trị}, 'LNST': {...}}}."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    required = {"Ticker", "Year", "Quarter", "VCSH", "LNST"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV thiếu cột bắt buộc: {sorted(missing)} (cần đủ {sorted(required)})")

    out = {}
    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        if not ticker or ticker == "NAN":
            continue
        label = f"Q{int(row['Quarter'])}-{int(row['Year'])}"
        entry = out.setdefault(ticker, {"VCSH": {}, "LNST": {}})
        if pd.notna(row["VCSH"]):
            entry["VCSH"][label] = float(row["VCSH"])
        if pd.notna(row["LNST"]):
            entry["LNST"][label] = float(row["LNST"])
    return out
