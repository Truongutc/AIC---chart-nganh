# --- HƯỚNG DẪN ---
# 1. Mở Chrome -> F12 -> Network.
# 2. Chuột phải 'KQGDThongKeGiaPaging' -> Copy -> 'Copy as cURL (bash)'.
# 3. Dán toàn bộ vào biến `raw_input` dưới đây.
# 4. Chạy script này.

raw_input = r"""
PASTE_CURL_OR_HEADERS_HERE
"""

from tinvest.config_manager import ConfigManager
import logging

logging.basicConfig(level=logging.INFO)
cm = ConfigManager()

if "PASTE_CURL_OR_HEADERS_HERE" in raw_input:
    print("❌ LỖI: Bạn chưa dán mã cURL vào biến raw_input!")
else:
    success = cm.parse_input(raw_input)
    if success:
        print("✅ THÀNH CÔNG: Đã cập nhật Session thành công.")
        print(f"   - Cookies: {len(cm.get('cookies', {}))} keys")
        print(f"   - Token: {str(cm.get('payload_token'))[:20]}...")
    else:
        print("❌ THẤT BẠI: Không tìm thấy dữ liệu hợp lệ. Hãy kiểm tra lại mã cURL.")
