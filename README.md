# TINVEST – Trading Analysis System

Python package for systematic stock analysis using **Ichimoku**, **VSA**, and **AIC** methodology.

---

## Installation

```powershell
# Sử dụng môi trường ảo (khuyến nghị)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Quick Start

### 1. Analyze a Single Stock

```python
from tinvest.data_loader import load_data
from tinvest.analyzer    import analyze_stock, format_report

df     = load_data("your_data.csv")
result = analyze_stock("VNM", df)
print(format_report(result))
```

Sample output:
```
══════════════════════════════════════════════════════════
  📊  TINVEST – PHÂN TÍCH CỔ PHIẾU: VNM
══════════════════════════════════════════════════════════
  Giá đóng cửa   : 80,250.00
  Xu hướng        : UP

  ĐIỂM TỔNG: 9/11  [█████████░]   →  STRONG BUY
...
```

### 2. Scan Multiple Stocks

```python
from tinvest.data_loader import load_data
from tinvest.scanner     import scan_stocks

# CSV must have a "Ticker" column
data_dict = load_data("multi_ticker.csv")
result_df = scan_stocks(data_dict)
print(result_df.to_string(index=False))
```

Output DataFrame (Score ≥ 8 only):

| Ticker | Price | Trend | MoneyFlow | Trigger | Score | Classification | Action      |
|--------|-------|-------|-----------|---------|-------|----------------|-------------|
| HPG    | 27.50 | UP    | Bullish   | A       | 10    | STRONG BUY     | MUA MẠNH (A) |
| VNM    | 82.10 | UP    | Bullish   | B       | 8     | BUY            | MUA (B)      |

---

## CSV Format

**Single Ticker:**
```csv
Date,Open,High,Low,Close,Volume
2024-01-02,50.1,51.5,49.8,51.0,2500000
...
```

**Multi Ticker:**
```csv
Ticker,Date,Open,High,Low,Close,Volume
VNM,2024-01-02,80.0,81.5,79.5,81.0,1500000
HPG,2024-01-02,25.0,25.8,24.7,25.5,5000000
...
```

> **Minimum 200 rows per ticker required.**

---

## Module Architecture

```
tinvest/
├── data_loader.py        # Module 1: Load & normalize OHLCV CSV
├── ichimoku_engine.py    # Module 2: Ichimoku trend analysis  (score 0–3)
├── vsa_engine.py         # Module 3: Volume Spread Analysis   (score 0–4)
├── aic_engine.py         # Module 4: AIC entry setup A/B/C    (score 0–4)
├── scoring_engine.py     # Module 5: Aggregate scoring & classification
├── decision_engine.py    # Module 6: Opportunity & risk signals
├── scanner.py            # Module 7: Multi-ticker scanner
└── analyzer.py           # Module 8: Single-stock full analysis + report
```

### Score Thresholds

| Total Score | Classification |
|-------------|---------------|
| ≥ 9         | STRONG BUY    |
| 7 – 8       | BUY           |
| 5 – 6       | WATCH         |
| < 5         | AVOID         |

---

## Running Tests

```powershell
# From d:/Github/Codeinvest/
python tests/generate_sample.py   # generate test CSV files
pytest tests/ -v
```
