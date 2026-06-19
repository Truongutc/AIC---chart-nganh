import json
import requests
from pathlib import Path

def test_ticker(ticker, cat_id, date_str):
    with open("config.json", "r") as f:
        config = json.load(f)
    
    url = "https://finance.vietstock.vn/data/KQGDThongKeGiaPaging"
    headers = config.get("headers", {})
    cookies = config.get("cookies", {})
    token = config.get("payload_token")
    
    payload = {
        "page": 1,
        "pageSize": 1000,
        "catID": cat_id,
        "date": date_str,
        "__RequestVerificationToken": token
    }
    
    print(f"[*] Testing {ticker} (Cat {cat_id}) for date {date_str}...")
    response = requests.post(url, data=payload, headers=headers, cookies=cookies)
    
    if response.status_code == 200:
        data = response.json()
        if len(data) >= 3:
            stocks = data[2]
            print(f"Total stocks found in response: {len(stocks)}")
            found = [s for s in stocks if s.get("StockCode") == ticker]
            if found:
                print(f"[OK] Found {ticker}: {found[0]}")
            else:
                print(f"[FAIL] {ticker} NOT found in first {len(stocks)} items of Cat {cat_id}")
                if stocks:
                    print(f"   First 5 tickers: {[s.get('StockCode') for s in stocks[:5]]}")
                    # Print one sample to check date
                    print(f"   Sample TradingDate: {stocks[0].get('TradingDate')}")
        else:
            print(f"[FAIL] Unexpected structure (len={len(data)}): {data}")
    else:
        print(f"[FAIL] HTTP {response.status_code}: {response.text[:200]}")

if __name__ == "__main__":
    # Test MBB (HOSE) for 27-03 and 30-03
    test_ticker("MBB", 1, "2026-03-27")
    test_ticker("MBB", 1, "2026-03-30")
    
    # Test VGI (UPCOM) for 27-03 and 30-03
    test_ticker("VGI", 3, "2026-03-27")
    test_ticker("VGI", 3, "2026-03-30")
