from tinvest.config_manager import ConfigManager
import re

cm = ConfigManager()
user_curl = r"""curl 'https://finance.vietstock.vn/data/KQGDThongKeGiaPaging' \
  -H 'Accept: */*' \
  -H 'Accept-Language: vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Cookie: language=vi-VN; Theme=Light; AnonymousNotification=; isShowLogin=true; packName=Basic; qPerDay=0; qPerMonth=0; vst_isShowTourGuid=true; _gid=GA1.2.1631650041.1774845802; ASP.NET_SessionId=eog4j2b3imffj21a2ixwotsw; __RequestVerificationToken=VjVCW7YdoJOsNFEXfV_08l4qHuxP-f1khJw4i0FctjkyGKxNo9H1Gh4avrWpVd3rOao3_gKE4_4_sjROa-H7-N--_Ns_FkDi-4FBuwQQ5AQ1; CookieLogin=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoiaHV1dHJ1b25ndXRjQGdtYWlsLmNvbSIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL2hhc2giOiJzay1oNHp5T0NoVTJScHBVeUVYNHJhSGlnIiwiaHR0cDovL3NjaGVtYXMueG1sc29hcC5vcmcvd3MvMjAwNS8wNS9pZGVudGl0eS9jbGFpbXMvbmFtZWlkZW50aWZpZXIiOiJodXV0cnVvbmd1dGNAZ21haWwuY29tIiwiZXhwIjoxNzc3NTM0MTQ3LCJpc3MiOiIudmlldHN0b2NrLnZuIiwiYXVkIjoiLnZpZXRzdG9jay52biJ9.N9R_QEQMVJmB8Pc9vlKWKHIeLknPGhmZ8cFGD-OHss8; vst_usr_lg_token=R1iAdNLItU6TFbsybjOzxQ==; _ga_EXMM0DKVEX=GS2.1.s1774941513$o140$g1$t1774942136$j47$l0$h0; _ga=GA1.2.1417740156.1752282620' \
  -H 'Origin: https://finance.vietstock.vn' \
  -H 'Referer: https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  --data-raw 'page=7&pageSize=10&catID=1&date=2026-03-31&__RequestVerificationToken=DNUXE643YJqyQ65FQ9GG_3mjBGgFAeEu-tRaSWJcIw8AIc_yLSqd17XoUqaGuGcywSjQLeIyN7OjKZ5eeqHjO14Q48cuRJG_SOItoAREhbrRNZGLCsJ5je9IfYR3uabxKcAQTyNqBiyLm888oHJENw2' \
  --compressed"""

cm.parse_input(user_curl)
print(f"Parsed Session ID: {cm.get('cookies').get('ASP.NET_SessionId')}")
print(f"Parsed Payload Token: {cm.get('payload_token')}")
print(f"Parsed UI Token (from cookies): {cm.get('cookies').get('__RequestVerificationToken')}")
print(f"User Agent: {cm.get('headers').get('User-Agent')}")
