---
name: Vietcap API Engine
description: Guidelines and code patterns for accessing, caching, and mapping financial data from the Vietcap IQ Insight API.
---

# Vietcap API Engine Custom Skill

This skill documents how to interact with the Vietcap (Vietcap Securities / IQ Insight) APIs to fetch and map company metadata, financial statements (Income Statement, Balance Sheet, Cash Flow), and historical valuation ratios (P/E, P/B, ROE, etc.).

## 1. Connection & Session Setup

Vietcap APIs require specific headers to bypass request filtering. Use a session and configure the headers as follows:

- **Base URL**: `https://iq.vietcap.com.vn/api/iq-insight-service/v1` or `https://trading.vietcap.com.vn/api/iq-insight-service/v1`
- **Referer**: `https://trading.vietcap.com.vn/`
- **Origin**: `https://trading.vietcap.com.vn`
- **User-Agent**: Standard modern browser agent string.

### Python Connection Example
```python
import requests

def create_vietcap_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://trading.vietcap.com.vn",
        "Referer": "https://trading.vietcap.com.vn/",
    })
    # Warm up session with a get request
    try:
        s.get("https://trading.vietcap.com.vn/iq/company?ticker=HPG", timeout=10)
    except Exception:
        pass
    return s
```

---

## 2. Key API Endpoints

### A. Company Details
* **URL**: `https://trading.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker={ticker}`
* **Response fields**:
  - `currentPrice`: Current stock price
  - `numberOfSharesMktCap`: Total shares outstanding (used to calculate Market Cap fallback)
  - `marketCap`: Market Capitalization (in VND, divide by `1e9` for billions)
  - `enOrganName` / `viOrganName`: Company name
  - `sector`: Industrial sector
  - `targetPrice` / `upsideToTargetPercent`
  - `freeFloatPercentage` / `foreignerPercentage`

### B. Financial Statements
* **URL**: `https://trading.vietcap.com.vn/api/iq-insight-service/v1/company/{ticker}/financial-statement?section={SECTION}&quarterly={quarterly}`
* **Parameters**:
  - `SECTION`: `INCOME_STATEMENT`, `BALANCE_SHEET`, or `NOTE`
  - `quarterly`: `true` (for quarters) or `false` (for years)
* **Response structure**:
  - `r.json()["data"]["years"]` or `r.json()["data"]["quarters"]`

### C. Statistics & Valuation Ratios
* **URL**: `https://trading.vietcap.com.vn/api/iq-insight-service/v1/company/{ticker}/statistics-financial`
* **Response fields**: List of records containing fields like `pe`, `pb`, `evToEbitda`, `roe`, `year`, `quarter`.

---

## 3. Data Field Mappings

### A. General Corporations (Non-financials / Manufacturing / Utilities)

#### Income Statement (`INCOME_STATEMENT`)
- **Revenue**: `isa3` (Doanh thu thuần)
- **COGS**: `isa4` (Giá vốn hàng bán)
- **Gross Profit**: `isa5` (Lợi nhuận gộp)
- **Financial Income**: `isa6` (Doanh thu tài chính)
- **Financial Expense**: `isa7` (Chi phí tài chính)
- **Interest Expense**: `isa8` (Chi phí lãi vay)
- **SG&A Sales**: `isa9` (Chi phí bán hàng) -> *Caution: often saved as a negative number in Vietcap*
- **SG&A Admin**: `isa10` (Chi phí quản lý doanh nghiệp) -> *Caution: often saved as a negative number in Vietcap*
- **PBT (Profit Before Tax)**: `isa16` (Lợi nhuận trước thuế)
- **NPAT (Net Profit After Tax)**: `isa20` (LNST)
- **Parent NPAT**: `isa22` (LNST công ty mẹ)
- **Basic EPS**: `isa23`

#### Balance Sheet (`BALANCE_SHEET`)
- **Cash**: `bsa2` (Tiền & tương đương tiền)
- **Total Assets**: `bsa53`
- **Total Liabilities**: `bsa54`
- **Short-term Borrowings**: `bsa56`
- **Long-term Borrowings**: `bsa71`
- **Total Equity**: `bsa78` (including Minority Interest)
- **Charter Capital**: `bsa80` (Vốn điều lệ)
- **Minority Interest (NCI)**: `bsa210`

#### Cash Flow (`NOTE`)
- **Depreciation**: `cfa2` (Khấu hao TSCĐ)
- **CAPEX**: `cfa19` (Tiền chi mua sắm/xây dựng TSCĐ - negative value)
- **Dividends Paid**: `cfa32` (Cổ tức đã trả - negative value)

---

### B. Securities Companies (CTCK)

#### Specialized Income Statement (Segment / Operating Revenue)
- **Brokerage Revenue**: `iss42` (Doanh thu môi giới)
- **Brokerage Cost**: `iss133` (Chi phí môi giới - negative)
- **Margin Revenue**: `iss120` (Lãi cho vay & phải thu)
- **FVTPL Gain**: `iss115` (Lãi tài sản tài chính FVTPL)
- **FVTPL Loss**: `iss124` (Lỗ tài sản tài chính FVTPL - negative)
- **FVTPL Cost**: `iss132` (Chi phí tự doanh - negative)
- **AFS Gain**: `iss121` (Lãi tài sản tài chính AFS)
- **IB Underwriting Revenue**: `iss44` (Bảo lãnh phát hành)
- **IB Advisory Revenue**: `iss46`
- **Total Revenue**: `isa1`
- **Total Cost**: `isa4`
- **Gross Profit**: `isa5`
- **SG&A Admin**: `isa10` (Chi phí quản lý)
- **PBT**: `isa16`
- **NPAT**: `isa20`

#### Specialized Balance Sheet
- **FVTPL Portfolio**: `bsa6`
- **AFS Portfolio**: `bsa14`
- **HTM Portfolio**: `bsa10`
- **Margin Loans**: `bsa18` (Các khoản cho vay)

---

## 4. Key Implementation Traps

1. **Negative Signs**:
   Some cost items (like SG&A or CAPEX/Dividends) are already saved as negative numbers in the Vietcap response database. Check the sign before adding/subtracting them.
   - Example: `operating_result` calculations should add the SG&A fields if they are negative, or use `abs()` to handle them cleanly.
2. **Missing Field Fallbacks**:
   - If a company details request fails, always provide sensible fallbacks (e.g., standard defaults for beta, market cap, and outstanding shares) to avoid script crashes.
3. **Vietcap API Inaccuracies**:
   - Vietcap sometimes mislabels tags internally (e.g. labeling `isa16` as tax but it is mathematically PBT). Always map by the correct key code (e.g., `isa16`, `isa20`) verified from the database structure rather than text labels.
