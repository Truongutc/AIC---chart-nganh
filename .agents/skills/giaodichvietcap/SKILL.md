---
name: giaodichvietcap
description: Kết nối và lấy dữ liệu giao dịch tự động từ API Vietcap (bao gồm P/E, P/B của VN-Index và dữ liệu khối ngoại, cung cầu của từng mã cổ phiếu/chỉ số).
---

# Hướng dẫn Kết nối & Lấy dữ liệu giao dịch Vietcap IQ

Tài liệu này hướng dẫn cách kết nối trực tiếp đến hệ thống API của Vietcap IQ (`https://trading.vietcap.com.vn` hoặc `https://iq.vietcap.com.vn`) để thu thập các nhóm dữ liệu định giá chỉ số và thông tin chi tiết của cổ phiếu/chỉ số.

---

## 1. Cấu hình Kết nối Chung (Headers & Base URL)
Để kết nối thành công mà không bị máy chủ từ chối (lỗi 400 hoặc 403), tất cả các yêu cầu HTTP GET phải đính kèm header `Referer` và `User-Agent` hợp lệ.

*   **Base URL**: `https://trading.vietcap.com.vn` (hoặc `https://iq.vietcap.com.vn`)
*   **Headers bắt buộc**:
    ```json
    {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://trading.vietcap.com.vn/"
    }
    ```

---

## 2. API lấy P/E và P/B của chỉ số VN-Index

*   **Endpoint**: `/api/iq-insight-service/v1/market-watch/index-valuation`
*   **Tham số truy vấn (Query Params)**:
    *   `type`: `PE` hoặc `PB` (Chữ hoa)
    *   `comGroupCode`: `VNINDEX`
    *   `timeFrame`: `ALL` (lấy toàn bộ) hoặc `YTD` (từ đầu năm).
    *   `fromDate` & `toDate` (Tùy chọn): Lọc theo ngày tùy ý `YYYY-MM-DD`. Nếu truyền ngày, không cần truyền `timeFrame`.
*   **Cấu trúc dữ liệu trả về**:
    *   `values`: Mảng chứa các cặp `{ date, value }`.
    *   `average`: Đường trung bình (Mean).
    *   `plusOneSD` / `plusTwoSD`: Đường +1 / +2 Độ lệch chuẩn.
    *   `minusOneSD` / `minusTwoSD`: Đường -1 / -2 Độ lệch chuẩn.

---

## 3. API lấy dữ liệu Giao dịch Khối ngoại & Cung cầu của Chỉ số (ví dụ: VNINDEX)

*   **Endpoint**: `/api/iq-insight-service/v1/market-indices/history`
*   **Tham số truy vấn (Query Params)**:
    *   `index`: `VNINDEX` (Chỉ số cần tra cứu, bắt buộc).
    *   `page`: Số trang (bắt đầu từ `0`).
    *   `size`: Số lượng bản ghi mỗi trang (Ví dụ: `20`, `50`).
    *   `fromDate` & `toDate` (Tùy chọn): Lọc theo ngày `YYYY-MM-DD`.
*   **Ánh xạ các trường dữ liệu cần thiết** (Nằm trong danh sách `data.content`):
    *   **Giá trị giao dịch ròng khối ngoại**: Trường **`foreignNetValueTotal`** (đơn vị: VND).
    *   **Khối lượng chưa khớp bên mua**: Trường **`totalBuyUnmatchedVolume`**.
    *   **Khối lượng chưa khớp bên bán**: Trường **`totalSellUnmatchedVolume`**.
    *   **KLTB 1 lệnh mua**: Trường **`averageBuyTradeVolume`**.
    *   **KLTB 1 lệnh bán**: Trường **`averageSellTradeVolume`**.

---

## 4. API lấy dữ liệu Giao dịch Khối ngoại & Cung cầu của Cổ phiếu (ví dụ: TCB, HPG)

*   **Endpoint**: `/api/iq-insight-service/v1/company/{ticker}/price-history`
*   **Tham số truy vấn (Query Params)**:
    *   `page`: Số trang (bắt đầu từ `0`).
    *   `size`: Số lượng bản ghi mỗi trang (Ví dụ: `20`, `50`).
    *   `fromDate` & `toDate`: Lọc theo khoảng ngày `YYYY-MM-DD`.
*   **Ánh xạ các trường dữ liệu cần thiết** (Nằm trong danh sách `data.content`):
    *   **Giá trị giao dịch ròng khối ngoại**: Trường **`foreignNetValueTotal`** (đơn vị: VND).
    *   **Khối lượng chưa khớp bên mua**: Trường **`totalBuyUnmatchedVolume`**.
    *   **Khối lượng chưa khớp bên bán**: Trường **`totalSellUnmatchedVolume`**.
    *   **KLTB 1 lệnh mua**: Trường **`averageBuyTradeVolume`**.
    *   **KLTB 1 lệnh bán**: Trường **`averageSellTradeVolume`**.

---

## 5. Code mẫu triển khai nhanh bằng Python

```python
import requests

class VietcapAPIClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://trading.vietcap.com.vn/"
        })
        self.base_url = "https://trading.vietcap.com.vn/api/iq-insight-service/v1"

    def get_vnindex_valuation(self, val_type="PE", from_date=None, to_date=None):
        """Lấy dữ liệu định giá P/E hoặc P/B lịch sử của VNINDEX"""
        url = f"{self.base_url}/market-watch/index-valuation"
        params = {"type": val_type, "comGroupCode": "VNINDEX"}
        if from_date and to_date:
            params["fromDate"] = from_date
            params["toDate"] = to_date
        else:
            params["timeFrame"] = "ALL"
            
        r = self.session.get(url, params=params, timeout=15)
        if r.status_code == 200 and r.json().get("successful"):
            return r.json().get("data")
        return None

    def get_index_history(self, index_name="VNINDEX", from_date=None, to_date=None, page=0, size=50):
        """Lấy lịch sử giao dịch nước ngoài & cung cầu của chỉ số (VN-Index)"""
        url = f"{self.base_url}/market-indices/history"
        params = {
            "index": index_name,
            "page": page,
            "size": size
        }
        if from_date and to_date:
            params["fromDate"] = from_date
            params["toDate"] = to_date
        r = self.session.get(url, params=params, timeout=15)
        if r.status_code == 200 and r.json().get("successful"):
            return r.json().get("data", {}).get("content", [])
        return []

    def get_stock_trade_history(self, ticker, from_date, to_date, page=0, size=50):
        """Lấy lịch sử giao dịch nước ngoài & cung cầu của cổ phiếu"""
        url = f"{self.base_url}/company/{ticker}/price-history"
        params = {
            "page": page,
            "size": size,
            "fromDate": from_date,
            "toDate": to_date
        }
        r = self.session.get(url, params=params, timeout=15)
        if r.status_code == 200 and r.json().get("successful"):
            return r.json().get("data", {}).get("content", [])
        return []
```
