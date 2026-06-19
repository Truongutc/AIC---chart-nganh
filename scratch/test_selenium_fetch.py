import json
import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Force UTF-8 for output
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_selenium_fetch():
    print("--- Test: Fetch API Data using Browser Context ---")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.set_script_timeout(30) # Important for async scripts
    
    try:
        # 1. Warm up session
        url_land = "https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia"
        print(f"Navigating to: {url_land}")
        driver.get(url_land)
        time.sleep(8)
        
        # 2. Extract Token
        try:
            token = driver.find_element("xpath", "//input[@name='__RequestVerificationToken']").get_attribute("value")
            print(f"Token extracted: {token[:20]}...")
        except:
            print("Failed to find token on page. Checking Cookies...")
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            token = cookies.get("__RequestVerificationToken", "")
            print(f"Token from cookie: {token[:20]}...")

        if not token:
            print("ERROR: No token found. Aborting.")
            return

        # 3. Perform POST using JS fetch inside the browser
        payload = {
            "page": 1,
            "pageSize": 50,
            "catID": 1,
            "date": "2026-04-17",
            "__RequestVerificationToken": token
        }
        
        js_script = """
        var callback = arguments[arguments.length - 1];
        var url = '/data/KQGDThongKeGiaPaging';
        var payload = arguments[0];
        
        var body = [];
        for (var property in payload) {
            body.push(encodeURIComponent(property) + "=" + encodeURIComponent(payload[property]));
        }
        body = body.join("&");

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01'
            },
            body: body
        })
        .then(response => {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.text();
        })
        .then(data => callback(data))
        .catch(error => callback("ERROR: " + error.message));
        """
        
        print("Executing POST from browser context...")
        response_text = driver.execute_async_script(js_script, payload)
        
        if response_text.startswith("ERROR:"):
            print(f"❌ Fetch Error: {response_text}")
        elif response_text.strip().startswith("<!DOCTYPE"):
            print("❌ Received HTML instead of JSON. Browser is also blocked!")
            with open("debug_selenium_fetch_fail.html", "w", encoding="utf-8") as f:
                f.write(response_text)
        else:
            print("✅ SUCCESS! JSON data received.")
            print(f"Length: {len(response_text)} bytes")
            print(f"Preview: {response_text[:200]}")
            
    except Exception as e:
        print(f"Execution failed: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    test_selenium_fetch()
