"""
Client lấy dữ liệu Báo cáo tài chính (VCSH, LNST) theo quý từ API Vietcap IQ,
cho pipeline tính P/E, P/B, ROE, tăng trưởng LNST theo ngành.

Endpoint đã xác nhận sống (kiểm tra thật, không suy đoán từ tài liệu):
  GET https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{TICKER}/financial-statement?section={SECTION}
  SECTION = BALANCE_SHEET | INCOME_STATEMENT — 1 lần gọi trả về TOÀN BỘ lịch
  sử quý (không cần phân trang/tham số ngày).

Field code đã xác nhận đúng qua số liệu thật (đối chiếu với dự án
D:\\Github\\Phan-tich-FA, đồng thời tự gọi API kiểm tra lại):
  bsa78 = VCSH tổng (gồm cổ đông thiểu số), bsa210 = phần thiểu số (NCI)
    -> VCSH cổ đông công ty mẹ = bsa78 - bsa210
  isa22 = LNST của cổ đông công ty mẹ (dùng thẳng, không cần trừ)
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

VIETCAP_BASE = "https://iq.vietcap.com.vn/api/iq-insight-service/v1"

# Header đầy đủ giống Phan-tich-FA/fetch_data.py — Vietcap chặn User-Agent mặc
# định của thư viện requests, cần giả UA trình duyệt thật mới qua được WAF.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}

TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5  # giây, nhân dần theo số lần thử lại


def _get_with_retry(url, retries=MAX_RETRIES):
    last_error = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            raise  # lỗi 4xx/5xx không có lợi gì khi thử lại
        except Exception as e:
            last_error = e
            wait = RETRY_DELAY * (attempt + 1)
            time.sleep(wait)
    raise Exception(f"Thất bại sau {retries} lần thử: {last_error}")


def fetch_ticker_section(ticker, section):
    """Trả về list bản ghi quý thô (data['quarters']) cho 1 mã + 1 section
    (BALANCE_SHEET/INCOME_STATEMENT). KHÔNG BAO GIỜ raise ra ngoài — lỗi thì
    trả [] và log, để 1 mã lỗi không làm hỏng cả batch 302 mã."""
    url = f"{VIETCAP_BASE}/company/{ticker}/financial-statement?section={section}"
    try:
        result = _get_with_retry(url)
        data = result.get("data") or {}
        return data.get("quarters") or []
    except Exception as e:
        print(f"[VietcapFinance] Lỗi lấy {section} cho {ticker}: {e}")
        return []


def _quarter_label(rec):
    """Nhãn quý dạng 'Qn-YYYY' (Quý-Năm) — khớp định dạng cột trong file
    Excel VCSH/LNST trên Drive, xem tinvest/finance_workbook.py."""
    year = rec.get("yearReport")
    length = rec.get("lengthReport")
    if year is None or length is None or length not in (1, 2, 3, 4):
        return None
    return f"Q{length}-{year}"


def fetch_ticker_finance(ticker, years_back=None):
    """Trả về {'VCSH': {quý: giá_trị}, 'LNST': {quý: giá_trị}} cho 1 mã, quét
    toàn bộ lịch sử quý Vietcap có. Bỏ qua các bản ghi lengthReport=5 (báo cáo
    năm, nằm trong data['years'] chứ không phải nhu cầu ở đây).

    years_back (tùy chọn): CHỈ giữ lại các quý trong N năm gần nhất tính từ
    năm hiện tại — dùng cho Update Finance Vietcap để tránh phải cào lại toàn
    bộ lịch sử (VD chạy năm 2029 mà vẫn cố lấy về tận 2019 là quá xa và không
    cần thiết). Không set (None) = lấy toàn bộ lịch sử Vietcap có, dùng cho
    trường hợp cần đầy đủ nhất có thể."""
    from datetime import date
    min_year = (date.today().year - years_back) if years_back else None

    vcsh = {}
    lnst = {}

    for rec in fetch_ticker_section(ticker, "BALANCE_SHEET"):
        year = rec.get("yearReport")
        if min_year is not None and year is not None and year < min_year:
            continue
        label = _quarter_label(rec)
        if not label:
            continue
        bsa78 = rec.get("bsa78")
        if bsa78 is None:
            continue
        bsa210 = rec.get("bsa210") or 0.0
        vcsh[label] = bsa78 - bsa210

    for rec in fetch_ticker_section(ticker, "INCOME_STATEMENT"):
        year = rec.get("yearReport")
        if min_year is not None and year is not None and year < min_year:
            continue
        label = _quarter_label(rec)
        if not label:
            continue
        isa22 = rec.get("isa22")
        if isa22 is None:
            continue
        lnst[label] = isa22

    return {"VCSH": vcsh, "LNST": lnst}


def fetch_all_tickers_finance(tickers, max_workers=6, years_back=None):
    """Lấy dữ liệu tài chính cho nhiều mã song song (giới hạn số luồng để
    tránh bị Vietcap chặn vì gọi quá dồn dập). Mã nào lỗi thì log & bỏ qua,
    không phá vỡ cả batch. Trả về {ticker: {'VCSH': {...}, 'LNST': {...}}}.
    years_back: xem fetch_ticker_finance()."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_ticker_finance, t, years_back): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                out[ticker] = future.result()
            except Exception as e:
                print(f"[VietcapFinance] Bỏ qua {ticker} do lỗi: {e}")
    return out
