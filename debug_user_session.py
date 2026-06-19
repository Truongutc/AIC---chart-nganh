import requests
import re

# The user's curl parameters
url = 'https://finance.vietstock.vn/data/KQGDThongKeGiaPaging'
headers = {
    'Accept': '*/*',
    'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://finance.vietstock.vn',
    'Referer': 'https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'sec-ch-ua': '"Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

cookies_str = 'language=vi-VN; Theme=Light; AnonymousNotification=; isShowLogin=true; packName=Basic; qPerDay=0; qPerMonth=0; vst_isShowTourGuid=true; _gid=GA1.2.1631650041.1774845802; ASP.NET_SessionId=eog4j2b3imffj21a2ixwotsw; __RequestVerificationToken=VjVCW7YdoJOsNFEXfV_08l4qHuxP-f1khJw4i0FctjkyGKxNo9H1Gh4avrWpVd3rOao3_gKE4_4_sjROa-H7-N--_Ns_FkDi-4FBuwQQ5AQ1; CookieLogin=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoiaHV1dHJ1b25ndXRjQGdtYWlsLmNvbSIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL2hhc2giOiJzay1oNHp5T0NoVTJScHBVeUVYNHJhSGlnIiwiaHR0cDovL3NjaGVtYXMueG1sc29hcC5vcmcvd3MvMjAwNS8wNS9pZGVudGl0eS9jbGFpbXMvbmFtZWlkZW50aWZpZXIiOiJodXV0cnVvbmd1dGNAZ21haWwuY29tIiwiZXhwIjoxNzc3NTM0MTQ3LCJpc3MiOiIudmlldHN0b2NrLnZuIiwiYXVkIjoiLnZpZXRzdG9jay52biJ9.N9R_QEQMVJmB8Pc9vlKWKHIeLknPGhmZ8cFGD-OHss8; vst_usr_lg_token=R1iAdNLItU6TFbsybjOzxQ==; _ga_EXMM0DKVEX=GS2.1.s1774941513$o140$g1$t1774942136$j47$l0$h0; _ga=GA1.2.1417740156.1752282620'
cookies = {c.split('=')[0].strip(): c.split('=')[1].strip() for c in cookies_str.split(';') if '=' in c}

data = {
    'page': '1',
    'pageSize': '1000', # Request a lot to see if it's truncated
    'catID': '1',
    'date': '2026-03-31',
    '__RequestVerificationToken': 'DNUXE643YJqyQ65FQ9GG_3mjBGgFAeEu-tRaSWJcIw8AIc_yLSqd17XoUqaGuGcywSjQLeIyN7OjKZ5eeqHjO14Q48cuRJG_SOItoAREhbrRNZGLCsJ5je9IfYR3uabxKcAQTyNqBiyLm888oHJENw2'
}

print("Checking session status with user's credentials...")
import json
resp = requests.post(url, headers=headers, cookies=cookies, data=data)

if resp.status_code == 200:
    print(f"Response status: 200")
    try:
        json_data = resp.json()
        if isinstance(json_data, list) and len(json_data) >= 3:
            tickers = json_data[2]
            print(f"Total tickers (pageSize=1000): {len(tickers)}")
            
            if len(tickers) == 200:
                print(">>> STATUS: LIMITED. Testing bypass (pageSize=50)...")
                data['pageSize'] = '50'
                data['page'] = '5' # Should be tickers 201-250 if bypass works
                resp_p5 = requests.post(url, headers=headers, cookies=cookies, data=data)
                if resp_p5.status_code == 200:
                    json_p5 = resp_p5.json()
                    tickers_p5 = json_p5[2]
                    print(f"Total tickers on page 5 (pageSize=50): {len(tickers_p5)}")
                    if len(tickers_p5) > 0:
                        first_stock = tickers_p5[0].get('StockCode')
                        row_num = tickers_p5[0].get('ROW')
                        print(f"First ticker on page 5: {first_stock} (ROW: {row_num})")
                        if row_num > 200:
                            print(">>> BYPASS WORKING! Can access records beyond 200.")
                        else:
                            print(">>> BYPASS FAILED. Still seeing same records.")
                else:
                    print(f"Bypass test failed with status {resp_p5.status_code}")
        else:
            print("Response structure unexpected.")
    except Exception as e:
        print(f"JSON Parse Error: {e}")
else:
    print(f"Request failed with status {resp.status_code}")
