"""Tiện ích tự động làm mới token và cookie Vietstock bằng Selenium.
Kích hoạt bypass 200 mã bằng cách tương tác thông minh.
"""

import json
import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Không thể đọc config: {e}")
    return {}

def _save_config(data: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Không thể ghi config: {e}")

def fetch_fresh_token():
    """Khởi chạy Chrome headless, tương tác để lấy token và đồng bộ Header."""
    logger.info("Đang khởi tạo Chrome để lấy token mới...")
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Tối ưu hóa: Không đợi tải xong toàn bộ (ngăn chặn timeout)
    options.page_load_strategy = 'eager'
    
    # Chặn các thành phần gây chậm
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_settings.ads": 2
    }
    options.add_experimental_option("prefs", prefs)
    
    # Sử dụng User-Agent từ config nếu có
    cfg = _load_config()
    existing_ua = cfg.get("captured_headers", {}).get("User-Agent")
    chrome_version = "125"
    if existing_ua:
        user_agent = existing_ua
    else:
        user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={user_agent}")
    
    # Ẩn đặc điểm Automation
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(45)
        
        url = "https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia"
        logger.info(f"Đang truy cập: {url}")
        
        try:
            driver.get(url)
        except Exception as te:
            logger.warning(f"Lưu ý: Trang tải chưa xong ({te}), nhưng vẫn tiếp tục...")

        time.sleep(5)
        
        # Thu thập User-Agent thực tế
        actual_ua = driver.execute_script("return navigator.userAgent")
        
        # THAO TÁC 1: Chọn pageSize = 50
        try:
            selectors = ["//select[contains(@class, 'pageSize')]", "//select[@id='pageSize']"]
            for sel in selectors:
                try:
                    from selenium.webdriver.support.ui import Select
                    select_elem = driver.find_element("xpath", sel)
                    if select_elem.is_displayed():
                        Select(select_elem).select_by_value("50")
                        logger.info("✅ Đã chọn pageSize = 50")
                        time.sleep(3)
                        break
                except: continue
        except: pass

        # THAO TÁC 2: Bấm chuyển Trang 2
        try:
            page2_selectors = ["//a[text()='2']", "//li[contains(@class, 'page')]/a[text()='2']"]
            for sel in page2_selectors:
                try:
                    btn = driver.find_element("xpath", sel)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("✅ Đã bấm chuyển sang Trang 2")
                        time.sleep(4)
                        break
                except: continue
        except: pass

        # Lấy token và cookies
        try:
            token_elem = driver.find_element("xpath", "//input[@name='__RequestVerificationToken']")
            token = token_elem.get_attribute("value")
        except:
             token = ""

        selenium_cookies = driver.get_cookies()
        cookies = {c["name"]: c["value"] for c in selenium_cookies}
        
        if not token and "__RequestVerificationToken" in cookies:
            token = cookies["__RequestVerificationToken"]

        if not token:
            logger.error("Không thể lấy __RequestVerificationToken!")
            return None

        result = {
            "payload_token": token,
            "cookies": cookies,
            "bypass_pageSize": 50,
            "captured_headers": {
                "User-Agent": user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive",
                "sec-ch-ua": f"\"Google Chrome\";v=\"{chrome_version}\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"{chrome_version}\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\""
            }
        }
        
        # Cập nhật vào config.json
        cfg = _load_config()
        cfg.update(result)
        _save_config(cfg)
        
        logger.info("Đã làm mới token và đồng bộ Header thành công.")
        return result
        
    except Exception as e:
        logger.error(f"Lỗi khi fetch_fresh_token: {e}")
        return None
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_fresh_token()
