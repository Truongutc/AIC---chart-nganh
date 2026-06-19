import requests
import json
import os
from tinvest.config_manager import ConfigManager

cfg = ConfigManager()
headers = cfg.get("headers")
cookies = cfg.get("cookies")
token = cfg.get("payload_token")

payload = {
    "page": 1,
    "pageSize": 30,
    "catID": 1,
    "date": "2026-04-17",
    "__RequestVerificationToken": token
}

print(f"URL: https://finance.vietstock.vn/data/KQGDThongKeGiaPaging")
print(f"Payload: {payload}")

try:
    r = requests.post("https://finance.vietstock.vn/data/KQGDThongKeGiaPaging", headers=headers, cookies=cookies, data=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = json.loads(r.content.decode('utf-8-sig'))
        print(f"Full Length: {len(data)}")
        for i, val in enumerate(data):
            if i == 2:
                print(f"Element {i}: (list of {len(val)} items)")
            else:
                print(f"Element {i}: {val}")
    else:
        print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
