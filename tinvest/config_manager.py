import json
import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.default_config = {
            "vietstock_api_url": "https://finance.vietstock.vn/data/KQGDThongKeGiaPaging",
            "vietstock_index_url": "https://finance.vietstock.vn/data/KQGDThongKeGiaStockPaging",
            "stocklist_api_url": "https://finance.vietstock.vn/data/stocklist",
            "bypass_pageSize": 50,
            "cookies": {},
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive"
            }
        }
        self.config = self._load()

    def _load(self):
        if not self.config_path.exists():
            self._save(self.default_config)
            return self.default_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Merge with defaults to ensure all keys exist
                for k, v in self.default_config.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return self.default_config

    def _save(self, data):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get(self, key):
        return self.config.get(key, self.default_config.get(key))

    def set(self, key, value):
        self.config[key] = value
        self._save(self.config)

    def _sanitize_string(self, val):
        """Ensure string is ASCII-compatible for HTTP headers."""
        if not val or not isinstance(val, str): return val
        # Remove non-ASCII characters that cause latin-1 encoding errors
        return val.encode('ascii', 'ignore').decode('ascii').strip()

    def set_vietstock_url(self, url):
        self.set("vietstock_api_url", url)

    def _sanitize_curl(self, text):
        """Clean up shell artifacts from cURL strings (Windows/Bash)."""
        if not text: return ""
        # 1. Line continuations
        text = text.replace('\\\n', ' ').replace('^ \n', ' ')
        # 2. Caret escapes (Windows CMD)
        text = re.sub(r"\^([=:\s\$])", r"\1", text)
        # 3. Double carets and common Windows escaping artifacts
        text = text.replace('^^', '^').replace('^"', '"')
        # 4. Collapse spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _is_tracked_header(self, name):
        tracked = {
            "user-agent", "referer", "origin", "accept-language", "accept",
            "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
            "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
            "x-requested-with", "content-type", "connection"
        }
        return name.lower() in tracked

    def _should_preserve_case(self, name):
        """Headers starting with sec- should stay lowercase."""
        return name.lower().startswith("sec-")

    def parse_input(self, text):
        """
        Extract cookies, tokens and headers from raw text (cURL or Browser Headers).
        Always returns True if anything was updated.
        """
        if not text: return False
        
        # Cleanup input (remove helper markers and line continuations)
        text = re.sub(r'---.*---', '', text).strip()
        # Handle both Windows (^) and Linux (\) line continuations
        text = text.replace('\\\n', ' ').replace('\\\r\n', ' ').replace('^\n', ' ')
        
        # 1. Handle Multi-cURL paste: Pick the right one (Prioritize Data Paging)
        target_text = text
        if "curl" in text.lower():
            chunks = re.split(r'curl\s+', text, flags=re.IGNORECASE)
            chunks = [c.strip() for c in chunks if c.strip()]
            priority_keywords = ["KQGDThongKeGiaPaging", "KQGDThongKeGiaStockPaging", "stocklist", "finance.vietstock.vn"]
            
            best_chunk = ""
            for kw in priority_keywords:
                for c in chunks:
                    if kw in c:
                        best_chunk = c
                        break
                if best_chunk: break
            
            target_text = "curl " + (best_chunk or chunks[0])

        is_curl = "curl" in target_text.lower()[:50]
        if is_curl:
            target_text = self._sanitize_curl(target_text)
        
        updates = {
            "cookies": {},
            "headers": {}, # We'll populate this with tracked headers
            "vietstock_api_url": None,
            "payload_token": "",
            "bypass_pageSize": None
        }
        
        # Initialize headers with existing ones from config
        old_headers = self.config.get("headers", {})
        for k, v in old_headers.items():
            updates["headers"][k] = v

        # 2. Extract Data from cURL
        if is_curl:
            # A. Extract URL
            url_match = re.search(r"curl\s+['\"]?(https?://[^'\"]+)['\"]?", target_text, re.IGNORECASE)
            if url_match:
                updates["vietstock_api_url"] = url_match.group(1)

            # B. Extract Headers (Robust regex for single/double quotes)
            raw_headers = re.findall(r"(?:-H|--header)\s+(?:'([^']+)'|\"((?:\\\\\"|[^\"])+)\")", target_text, re.IGNORECASE)
            if not raw_headers:
                 # Fallback for simpler formats
                 raw_headers = re.findall(r"-H\s+['\"]([^'\"]+)['\"]", target_text, re.IGNORECASE)

            for h_tuple in raw_headers:
                h = h_tuple if isinstance(h_tuple, str) else (h_tuple[0] or h_tuple[1])
                if h and ":" in h:
                    k, v = h.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k.lower() == "cookie":
                        updates["cookies"].update(self._parse_cookie_str(v))
                        updates["raw_cookie_str"] = v # Capture raw string
                    elif self._is_tracked_header(k):
                        updates["headers"][k] = self._sanitize_string(v)
            
            # B2. Support -b or --cookie flags (common in Edge/Cốc Cốc)
            cookie_flag_match = re.search(r"(?:-b|--cookie)\s+(?:'([^']+)'|\"((?:\\\\\"|[^\"])+)\")", target_text, re.IGNORECASE)
            if cookie_flag_match:
                cookie_str = cookie_flag_match.group(1) or cookie_flag_match.group(2)
                updates["cookies"].update(self._parse_cookie_str(cookie_str))
                updates["raw_cookie_str"] = cookie_str

            # C. Extract Payload (Token)
            data_match = re.search(r"--data(?:-raw|-binary|-ascii)?\s+(?:'([^']+)'|\"((?:\\\\\"|[^\"])+)\")", target_text, re.IGNORECASE)
            if data_match:
                data_val = data_match.group(1) or data_match.group(2)
                params = data_val.split("&")
                for p in params:
                    if "=" in p:
                         t_parts = p.split("=", 1)
                         tk_key, tv_val = t_parts[0].strip(), t_parts[1].strip()
                         if tk_key == "__RequestVerificationToken":
                             updates["payload_token"] = tv_val
                         elif tk_key.lower() == "pagesize":
                             try: updates["bypass_pageSize"] = int(tv_val)
                             except: pass
        else:
            # Format 2: Universal Multi-line Parser (Browsers, URLs, etc.)
            lines = [l.strip() for l in target_text.split("\n") if l.strip()]
            for line in lines:
                if ":" in line and not line.startswith("http"):
                    k, v = line.split(":", 1)
                    self._extract_header_field(k.strip(), v.strip(), updates)
                elif line.startswith("http"):
                    token_match = re.search(r"__RequestVerificationToken[=:\s]+([A-Za-z0-9._-]{50,})", line)
                    if token_match:
                        updates["payload_token"] = token_match.group(1).split("&")[0].strip(";")

        # D. HTML Token Fallback
        if not updates["payload_token"]:
            # Check for token in raw text (source code)
            html_token = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', target_text)
            if html_token:
                updates["payload_token"] = html_token.group(1)

        # E. Dual-token synchronization:
        if not updates["payload_token"]:
            if "__RequestVerificationToken" in updates["cookies"]:
                updates["payload_token"] = updates["cookies"]["__RequestVerificationToken"]

        # E. Capture raw cookie string if missing but cookies are present
        if not updates.get("raw_cookie_str") and updates["cookies"]:
            updates["raw_cookie_str"] = "; ".join([f"{k}={v}" for k, v in updates["cookies"].items()])
        
        if updates.get("raw_cookie_str"):
            updates["raw_cookie_str"] = self._sanitize_string(updates["raw_cookie_str"])

        # Commit updates
        updated = False
        if updates["vietstock_api_url"]:
            self.set("vietstock_api_url", updates["vietstock_api_url"])
            updated = True

        if updates["cookies"]:
            # If we found NEW cookies, we replace the whole cookie dict to avoid mixing sessions
            self.set("cookies", updates["cookies"])
            updated = True
            
        if updates["payload_token"]:
            self.set("payload_token", updates["payload_token"])
            updated = True
            
        if updates["bypass_pageSize"] is not None:
             self.set("bypass_pageSize", updates["bypass_pageSize"])
             updated = True

        if updates.get("raw_cookie_str"):
            self.set("raw_cookie_str", updates["raw_cookie_str"])
            updated = True

        if updates["headers"]:
             current_headers = self.config.get("headers", {})
             new_headers = {}
             
             for k, v in updates["headers"].items():
                 # Filter out restricted headers
                 if k.lower() not in ["content-length", "host", "connection"]:
                     new_headers[k] = v
             
             # Also ensure we remove these if they were previously in config
             for k in ["Host", "Content-Length", "host", "content-length"]:
                 if k in current_headers:
                     del current_headers[k]

             current_headers.update(new_headers)
             self.set("headers", current_headers)
             updated = True
             
        return updated

    def _is_tracked_header(self, k):
        return k.lower() in self._get_tracked_header_list()

    def _get_tracked_header_list(self):
        return ["user-agent", "origin", "referer", "x-requested-with", 
                "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
                "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "accept-language", "accept"]

    def _extract_header_field(self, k, v, updates):
        k_lower = k.lower().rstrip(":")
        
        # If it's a known header, store it in headers
        if self._is_tracked_header(k_lower):
            updates["headers"][k] = v
            return

        # Otherwise, treat it as a potential cookie
        # (We want to keep ALL cookies provided by the user now)
        if k_lower == "cookie":
            updates["cookies"].update(self._parse_cookie_str(v))
        else:
            val = self._sanitize_string(v.strip().strip(";").strip())
            updates["cookies"][k] = val
            logger.info(f"[*] Đã nhận diện Cookie: {k}")

    def refresh_token(self):
        """Force a fresh token acquisition using Selenium with error handling."""
        import os
        if os.environ.get("GITHUB_ACTIONS") == "true":
            logger.error("❌ Selenium token refresh is disabled in GitHub Actions to prevent hanging. Please manually update the VIETSTOCK_CURL secret.")
            return False
            
        try:
            from tinvest.token_refresher import fetch_fresh_token
            result = fetch_fresh_token()
            if result:
                self.config = self._load() # Reload from disk
                return True
        except ImportError:
            logger.error("❌ Lỗi: Thiếu thư viện 'selenium' hoặc 'webdriver-manager'.")
            logger.error("Vui lòng cài đặt bằng lệnh: pip install selenium webdriver-manager")
        except Exception as e:
            logger.error(f"❌ Lỗi không xác định khi làm mới token: {e}")
        return False

    def _parse_cookie_str(self, cookie_str):
        cookies = {}
        if not cookie_str: return cookies
        pairs = cookie_str.split(";")
        for p in pairs:
            if "=" in p:
                parts = p.strip().split("=", 1)
                k = self._sanitize_string(parts[0])
                v = self._sanitize_string(parts[1])
                if k: cookies[k] = v
        return cookies
