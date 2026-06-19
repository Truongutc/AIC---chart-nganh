"""Kịch bản dòng lệnh để làm mới token Vietstock theo cách thủ công.
Sử dụng: python scripts/refresh_token.py
"""
import sys
import os

# Thêm đường dẫn gốc vào sys.path để import được tinvest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinvest.config_manager import ConfigManager
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("🚀 Đang bắt đầu làm mới token Vietstock...")
    
    config = ConfigManager()
    if config.refresh_token():
        print("✅ Thành công! Token và Cookie mới đã được lưu vào config.json")
    else:
        print("❌ Thất bại! Vui lòng kiểm tra log lỗi Selenium.")
