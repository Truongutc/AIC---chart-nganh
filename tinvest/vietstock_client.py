import requests
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import re
import re
import ssl
from collections import OrderedDict
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from tinvest.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class VietstockClient:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.base_url = "https://finance.vietstock.vn"
        self.stats_api_url = self.config_mgr.get("vietstock_api_url")
        self.index_api_url = self.config_mgr.get("vietstock_index_url")
        self.stocklist_api_url = self.config_mgr.get("stocklist_api_url")
        
        self.session_limited = False # Track if current token is restricted to 200 items
        self.session = requests.Session()
        
        # Enable Legacy SSL support for Machine 2 (OpenSSL 3+ compatibility)
        try:
            class LegacyAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    ctx = create_urllib3_context()
                    # Enable legacy server connect (needed for some older TLS servers on OpenSSL 3.0+)
                    ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
                    kwargs['ssl_context'] = ctx
                    return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)
            
            adapter = LegacyAdapter()
            self.session.mount("https://", adapter)
            logger.info("Enabled Legacy SSL Adapter for compatibility.")
        except Exception as e:
            logger.warning(f"Could not enable Legacy SSL Adapter: {e}")

        self.api_url = "https://finance.vietstock.vn/data/KQGDThongKeGiaPaging"
        self.token = None
        self.refresh_from_config()

    def refresh_from_config(self):
        """Update session headers and cookies from config (Mirror Mode)."""
        # Reload config from disk
        self.config_mgr = ConfigManager()
        conf_headers = self.config_mgr.get("headers") or {}
        conf_cookies = self.config_mgr.get("cookies") or {}
        
        # 1. Start with a clean slate to mirror browser exactly
        self.session.headers.clear()
        
        ua = conf_headers.get("User-Agent") or conf_headers.get("user-agent")
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            
        # 2. Build Ordered Headers (Chrome-like Fingerprint)
        ordered_headers = OrderedDict()
        ordered_headers["sec-ch-ua"] = self.config_mgr._sanitize_string(conf_headers.get("sec-ch-ua", '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"'))
        ordered_headers["sec-ch-ua-mobile"] = "?0"
        ordered_headers["User-Agent"] = ua
        ordered_headers["sec-ch-ua-platform"] = '"Windows"'
        ordered_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        ordered_headers["X-Requested-With"] = "XMLHttpRequest"
        ordered_headers["Sec-Fetch-Site"] = "same-origin"
        ordered_headers["Sec-Fetch-Mode"] = "cors"
        ordered_headers["Sec-Fetch-Dest"] = "empty"
        
        # Referer and Origin
        ref = conf_headers.get("Referer") or f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia"
        ordered_headers["Referer"] = self.config_mgr._sanitize_string(ref)
        ordered_headers["Origin"] = "https://finance.vietstock.vn"
        ordered_headers["Accept-Encoding"] = "gzip, deflate" # Standard requests support
        ordered_headers["Accept-Language"] = "vi,en-US;q=0.9,en;q=0.8"
        
        self.session.headers.update(ordered_headers)
        
        # 3. Clear and update cookies (Mirror Mode)
            
        # 3. Clear and update cookies
        self.session.cookies.clear()
        if conf_cookies:
            self.session.cookies.update(conf_cookies)

        # 4. Sync tokens and status
        self.manual_token = self.config_mgr.get("payload_token")
        self.session_limited = False
        logger.info(f"Mirror Mode Active: Headers synced (UA: {ua[:30]}...)")

    def ensure_valid_session(self):
        """Visit landing page to get fresh ASP.NET_SessionId and __RequestVerificationToken cookies."""
        try:
            url = f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia"
            # We use a clean GET to the landing page to populate cookies
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                # Save captured cookies back to config manager for persistence
                current_cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
                if current_cookies:
                    self.config_mgr.set("cookies", current_cookies)
                    logger.info(f"Automatically captured {len(current_cookies)} cookies.")
                return True
        except Exception as e:
            logger.error(f"Failed to ensure valid session: {e}")
        return False

    def check_session_status(self, date_str=None):
        """Perform a small probe to check if the session is currently limited."""
        # 1. Warm up session (Establish SSL/TLS and landing cookies)
        try:
            logger.info("[*] Warming up session...")
            self.session.get(f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia", timeout=20)
        except Exception as e:
            logger.warning(f"Session warming failed: {e}")
            
        if not date_str:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            # Weekend handling
            if now.weekday() == 5: date_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            elif now.weekday() == 6: date_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")
            
        try:
            # OPTIMIZED PROBE: Request exactly 201 items.
            # If server returns 200 or less, it's suspiciously limited.
            raw = self._fetch_page(1, date_str, page=1, page_size=201)
            if not raw or not isinstance(raw, list) or len(raw) < 3:
                return "ERROR"
            
            stocks = raw[2]
            if not stocks: return "NO_DATA"
            
            # If we requested 201 but got exactly 200 or 50 or something smaller, it's LIMITED
            if len(stocks) <= 200:
                self.session_limited = True
                
                # TEST BYPASS: Explicitly try to fetch a different page
                bypass_size = self.config_mgr.get("bypass_pageSize") or 50
                if bypass_size >= 200: bypass_size = 50
                
                # Try fetching page 2 with bypass size
                test_raw = self._fetch_page(1, date_str, page=2, page_size=bypass_size)
                if test_raw and isinstance(test_raw, list) and len(test_raw) >= 3 and test_raw[2]:
                     return "LIMITED_BYPASSED" # Bypass works!
                else:
                     return "LIMITED" # TRULY BLOCKED.
            
            self.session_limited = False
            return "VALID"
        except Exception as e:
            logger.error(f"check_session_status critical error: {e}")
            return "ERROR"

    def get_token(self):
        """Fetch __RequestVerificationToken from Vietstock landing page."""
        try:
            url = f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia"
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                token_input = soup.find('input', {'name': '__RequestVerificationToken'})
                if token_input:
                    self.token = token_input.get('value')
                    return self.token
        except Exception as e:
            logger.error(f"Error fetching Vietstock token: {e}")
        return None

    def get_stock_list(self, cat_id):
        """Fetch full symbol mapping for a category (1:HOSE, 2:HNX, 3:UPCOM)."""
        params = {"catID": cat_id}
        try:
            response = self.session.get(self.stocklist_api_url, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching stock list for cat {cat_id}: {e}")
        return []

    def _is_json(self, text):
        try:
            json.loads(text)
            return True
        except:
            return False

    def _fetch_page(self, cat_id, date_str, page=1, page_size=2000):
        # 1. ALWAYS Refresh from config first to get latest pasted tokens/cookies
        self.refresh_from_config()
        
        # 2. Prevent infinite refresh loops
        if not hasattr(self, '_refreshing'):
            self._refreshing = False
            
        # 3. Determine the correct token to use (Payload token)
        token_to_use = self.manual_token if self.manual_token else self.token
        
        # 4. Standard Vietstock POST Payload
        payload = {
            "page": page,
            "pageSize": page_size,
            "catID": cat_id,
            "date": date_str,
            "__RequestVerificationToken": self.config_mgr._sanitize_string(token_to_use) if token_to_use else ""
        }
        
        try:
            # 5. Mirror RAW Cookie Header via Cookie Jar (Allows session updates)
            raw_cookie_str = self.config_mgr.get("raw_cookie_str")
            if raw_cookie_str:
                # Remove static header to let Jar take over
                if "Cookie" in self.session.headers:
                    del self.session.headers["Cookie"]
                
                # Parse and populate Jar
                cookie_dict = self.config_mgr._parse_cookie_str(raw_cookie_str)
                requests.utils.add_dict_to_cookiejar(self.session.cookies, cookie_dict)
            
            logger.info(f"[*] API POST -> {self.api_url} | Payload: page={page}, pageSize={page_size}, catID={cat_id}")
            self.session.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            
            # CRITICAL: Sanitize ALL headers (keys and values) to ASCII
            clean_headers = OrderedDict()
            for k, v in self.session.headers.items():
                clean_headers[self.config_mgr._sanitize_string(k)] = self.config_mgr._sanitize_string(v)
            
            self.session.headers.clear()
            self.session.headers.update(clean_headers)
            
            response = self.session.post(self.api_url, data=payload, timeout=30)
            logger.info(f"[<] Response: {response.status_code}")

            if response.status_code == 200:
                # Better HTML detection
                content_type = response.headers.get("Content-Type", "")
                is_html = "text/html" in content_type.lower()
                
                if not is_html:
                    # Double check content for HTML tags if content-type is misleading
                    content_preview = response.content[:200].decode('utf-8', errors='ignore').upper()
                    if "<!DOCTYPE HTML>" in content_preview or "<HTML" in content_preview:
                        is_html = True

                if is_html:
                    logger.warning("⚠️ Nhận được trang HTML thay vì JSON. Vietstock có thể đang chặn yêu cầu hoặc Token hết hạn.")
                    
                    if "/Error/Index" in response.text:
                         logger.error("❌ Vietstock trả về trang lỗi hệ thống (/Error/Index). Vui lòng dán lại cURL mới.")
                         # Clear everything to force a clean start
                         self.session.cookies.clear()
                         self.manual_token = None
                    
                    if not self._refreshing:
                        logger.warning("Đang thử tự động làm mới chuẩn (Interactive Refresh)...")
                        self._refreshing = True
                        try:
                            if self.config_mgr.refresh_token():
                                self.refresh_from_config()
                                # Retry once
                                return self._fetch_page(cat_id, date_str, page, page_size)
                        finally:
                            self._refreshing = False
                    
                    # Log error details if still failing
                    logger.error("❌ Không thể kết nối API dù đã thử làm mới. Xem debug_api_error.html để biết chi tiết.")
                    with open("debug_api_error.html", "w", encoding="utf-8") as f:
                        f.write(f"URL: {self.api_url}\nStatus: {response.status_code}\n\n{response.text}")
                    return None
                
                try:
                    # Decode using utf-8-sig to handle possible BOM
                    return json.loads(response.content.decode('utf-8-sig'))
                except json.JSONDecodeError as je:
                    logger.error(f"❌ Lỗi định dạng JSON: {je}. Phản hồi bắt đầu bằng: {response.text[:100]}")
                    return None
            else:
                logger.error(f"❌ API trả về lỗi HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối API: {e}")
        return None

    def is_session_valid(self, raw_data, prev_records=None):
        """
        Validate if the session has real trading data.
        Rejects if all sampled stocks have zero volume or stagnant prices.
        """
        if not raw_data or not isinstance(raw_data, list) or len(raw_data) < 3:
            return False
        
        stocks = raw_data[2]
        if not stocks: return False
        
        # Check top 20 for signs of life
        samples = stocks[:20]
        total_vol = sum(int(s.get('M_TotalVol', 0)) for s in samples)
        if total_vol == 0: return False
        
        return True

    def fetch_market_day(self, cat_id, date_str):
        """Fetch all stocks for a market category with automatic 200-limit bypass."""
        # Safety: Use pageSize=200 which is the most stable authenticated limit.
        default_size = 200
        
        logger.info(f"[*] Đang thực hiện nạp dữ liệu sàn {cat_id} (pageSize=200)...")
        raw_p1 = self._fetch_page(cat_id, date_str, page=1, page_size=default_size)
        
        if not raw_p1 or not isinstance(raw_p1, list) or len(raw_p1) < 3:
            return [], False
            
        if not self.is_session_valid(raw_p1):
            logger.warning(f"⚠️ Phiên làm việc không hợp lệ hoặc không có dữ liệu giao dịch cho ngày {date_str}.")
            return [], False

        all_stocks = []
        stocks_p1 = raw_p1[2]
        
        # 2. Check for the limit restriction (Vietstock Blocking)
        # If the number of stocks returned is magically exactly 200, 50, or any small number
        # when we know the market is likely bigger, we trigger bypass.
        # We also check if 'TotalPages' indicated by Vietstock is > 1.
        total_pages = 1
        try:
            if len(raw_p1) >= 4:
                tp = raw_p1[3]
                if isinstance(tp, list): total_pages = int(tp[0])
                else: total_pages = int(tp)
        except: total_pages = 1

        is_suspiciously_small = (len(stocks_p1) <= 200 and total_pages > 1) or (len(stocks_p1) in [200, 50, 100])
        
        if is_suspiciously_small:
            logger.warning(f"⚠️ Phát hiện Vietstock có dấu hiệu chặn giới hạn ({len(stocks_p1)} mã). Kích hoạt chế độ Auto-Bypass (paging nhỏ)...")
            
            # BYPASS STRATEGY: Use small pageSize (e.g. 50) to crawl multiple pages
            bypass_size = self.config_mgr.get("bypass_pageSize") or 50
            if not bypass_size or bypass_size >= 200: 
                bypass_size = 50 # Default safe value
                
            all_stocks = []
            # We iterate up to 100 pages to catch ~2000 symbols max (if page size is 20)
            max_pages = 41 if bypass_size >= 50 else 101
            for p in range(1, max_pages):
                p_raw = self._fetch_page(cat_id, date_str, page=p, page_size=bypass_size)
                if p_raw and isinstance(p_raw, list) and len(p_raw) >= 3:
                    p_stocks = p_raw[2]
                    if not p_stocks: break # End of data
                    
                    # Merge unique tickers
                    existing = {s.get('StockCode') for s in all_stocks}
                    for s in p_stocks:
                        if s.get('StockCode') not in existing:
                            all_stocks.append(s)
                    
                    if len(p_stocks) < bypass_size: break # Last page
                else:
                    break
                time.sleep(0.3) # Avoid spamming
            
            expected_min = 300 if cat_id in [1, 3] else 150
            is_limited = (len(all_stocks) < expected_min) or (len(all_stocks) == 200)
            return all_stocks, is_limited
        else:
            # Full data received in page 1
            all_stocks.extend(stocks_p1)
            
            total_pages = 1
            try:
                if len(raw_p1) >= 4:
                    tp = raw_p1[3]
                    if isinstance(tp, list): total_pages = int(tp[0])
                    else: total_pages = int(tp)
            except: total_pages = 1
            
            if len(all_stocks) < 100 and total_pages > 1: # Safety check for very small markets
                 logger.info(f"[+] Vietstock báo cáo có {total_pages} trang dữ liệu. Đang tải tiếp...")
                 for p in range(2, total_pages + 1):
                     p_raw = self._fetch_page(cat_id, date_str, page=p, page_size=default_size)
                     if p_raw and len(p_raw) >= 3:
                         all_stocks.extend(p_raw[2])
                     else: break
                     time.sleep(0.3)
                     
            expected_min = 300 if cat_id in [1, 3] else 150
            is_limited = (len(all_stocks) < expected_min)
            return all_stocks, is_limited

    def fetch_index_day(self, ticker, cat_id, stock_id, date_str):
        """Fetch index data for a given date."""
        self.refresh_from_config()
        token_to_use = self.manual_token if self.manual_token else self.token
        if not token_to_use:
             self.get_token()
             token_to_use = self.token
             
        payload = {
            "page": 1,
            "pageSize": 20,
            "catID": cat_id,
            "stockID": stock_id,
            "fromDate": date_str,
            "toDate": date_str,
            "__RequestVerificationToken": token_to_use
        }
        
        try:
            response = self.session.post(self.index_api_url, data=payload, timeout=30)
            if response.status_code == 200:
                # Handle possible BOM in index API response too
                data = json.loads(response.content.decode('utf-8-sig'))
                if data and isinstance(data, list) and len(data) >= 2:
                    records = data[1]
                    formatted = []
                    for r in records:
                        formatted.append({
                            "StockCode": ticker, # Use StockCode so format_to_df renames it correctly
                            "TradingDate": date_str,
                            "OpenPrice": r.get("OpenPrice", 0),
                            "HighestPrice": r.get("HighestPrice", 0),
                            "LowestPrice": r.get("LowestPrice", 0),
                            "ClosePrice": r.get("ClosePrice", 0),
                            "M_TotalVol": int(r.get("TotalVol", 0))
                        })
                    return formatted
        except Exception as e:
            logger.error(f"Error fetching index {ticker}: {e}")
        return []

    def get_missing_dates(self, last_date):
        """Return missing trading dates up to today."""
        now = datetime.now()
        effective_today = now.date()
        if now.weekday() == 5: effective_today -= timedelta(days=1)
        elif now.weekday() == 6: effective_today -= timedelta(days=2)
        
        if not last_date:
            last_date = now - timedelta(days=365)
        
        # If last_date is today (e.g. from a previous partial run), 
        # we still want to re-check today to ensure full data
        missing = []
        curr = (last_date + timedelta(days=1)).date()
        if curr > effective_today:
             return [effective_today.strftime("%Y-%m-%d")]

        while curr <= effective_today:
            if curr.weekday() < 5:
                missing.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)
        return missing

    def format_to_df(self, raw_list):
        if not raw_list: return pd.DataFrame()
        
        df = pd.DataFrame(raw_list)
        if 'StockCode' in df.columns:
            df = df.rename(columns={
                'StockCode': 'Ticker',
                'TradingDate': 'Date',
                'OpenPrice': 'Open',
                'HighestPrice': 'High',
                'LowestPrice': 'Low',
                'ClosePrice': 'Close',
                'M_TotalVol': 'Volume'
            })
            
            # Numeric conversion for prices and volume
            for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'MarketCap', 'TotalVal']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Convert prices to thousands ONLY for stocks. 
            # Indices like VNINDEX/HNX-INDEX are already in the correct unit.
            if not df.empty:
                is_index = df['Ticker'].iloc[0] in ['VNINDEX', 'HNX-INDEX']
                if not is_index:
                    for col in ['Open', 'High', 'Low', 'Close']:
                        if col in df.columns:
                            df[col] = df[col] / 1000.0
            
            def parse_ms_date(d):
                if not isinstance(d, str): return d
                match = re.search(r'\((\d+)\)', d)
                if match:
                    from datetime import timezone
                    ts = int(match.group(1)) / 1000.0
                    # Convert explicitly to ICT (UTC+7) timezone to prevent shift on GitHub Actions (UTC timezone)
                    dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=7)))
                    return dt.strftime("%Y-%m-%d")
                return d
            df['Date'] = df['Date'].apply(parse_ms_date)

        # Preserve MarketCap for integrity checks in AICcode.py
        required = ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'MarketCap', 'TotalVal']
        df = df[[c for c in required if c in df.columns]]
        return df
