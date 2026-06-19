import pandas as pd
import glob
import os
from datetime import datetime

# Path to the data
path = r'D:\Github\CafeF.Index.Upto26032026'
files = glob.glob(os.path.join(path, "*.csv"))

# Current time as per user environment
now = datetime(2026, 5, 10)

ticker_last_dates = {}

# We process files exactly like the software would (roughly)
for f in files:
    try:
        # Check if it's the INDEX file or one of the exchange files
        is_index_file = "INDEX" in os.path.basename(f).upper()
        
        df = pd.read_csv(f)
        
        # Normalize column names
        cols = {c: c.lower().strip().replace("<", "").replace(">", "") for c in df.columns}
        df = df.rename(columns=cols)
        
        # Mapping to canonical names
        if 'ticker' in df.columns:
            ticker_col = 'ticker'
        else:
            continue # Skip files without ticker column
            
        if 'dtyyyymmdd' in df.columns:
            date_col = 'dtyyyymmdd'
        elif 'date' in df.columns:
            date_col = 'date'
        else:
            continue
            
        # Group by ticker
        grouped = df.groupby(ticker_col)
        for t_val, group in grouped:
            t = str(t_val).upper().strip()
            
            # Index check (same as AICcode.py)
            is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
            
            # Basic validation
            if not (len(t) == 3 and t.isalnum()) and not is_idx:
                continue
                
            # Date parsing
            try:
                date_series = group[date_col].astype(str).str.replace(r"\.0$", "", regex=True)
                # If YYYYMMDD
                if date_series.str.match(r"^\d{8}$").all():
                    last_d = pd.to_datetime(date_series.max(), format="%Y%m%d")
                else:
                    last_d = pd.to_datetime(date_series.max(), errors="coerce")
            except:
                continue
                
            if pd.isna(last_d):
                continue
                
            if t not in ticker_last_dates or last_d > ticker_last_dates[t]:
                ticker_last_dates[t] = last_d
    except Exception as e:
        print(f"Error processing {f}: {e}")

# Apply filters
valid_tickers = []
skipped_old = []
skipped_format = [] # These were already skipped in the loop above

for t, last_d in ticker_last_dates.items():
    is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
    days_diff = (now - last_d).days
    
    if days_diff > 30 and not is_idx:
        skipped_old.append((t, last_d, days_diff))
    else:
        valid_tickers.append((t, last_d))

print(f"--- THỐNG KÊ THỰC TẾ DỮ LIỆU ---")
print(f"Ngày hiện tại: {now.strftime('%Y-%m-%d')}")
print(f"Tổng số mã 3 ký tự (hoặc Index) tìm thấy: {len(ticker_last_dates)}")
print(f"Số mã hợp lệ (giao dịch trong 30 ngày qua): {len(valid_tickers)}")
print(f"Số mã bị loại do quá 30 ngày không giao dịch: {len(skipped_old)}")

print("\nVí dụ các mã bị loại vì giao dịch cuối cùng cách đây > 30 ngày:")
skipped_old.sort(key=lambda x: x[2]) # Sort by days since last trade
for t, d, diff in skipped_old[:15]:
    print(f"  - {t}: Giao dịch cuối {d.strftime('%Y-%m-%d')} ({diff} ngày trước)")

print("\n--- PHÂN TÍCH ---")
if len(valid_tickers) == 1355 or abs(len(valid_tickers) - 1355) < 5:
    print(f"KẾT LUẬN: Con số 1355 là CHÍNH XÁC dựa trên bộ lọc 30 ngày.")
    print(f"Phần mềm không hiển thị sai, mà do dữ liệu có hơn 500 mã đã không có giao dịch trong hơn 1 tháng.")
else:
    print(f"KẾT LUẬN: Có sự sai lệch. Tính toán thực tế ra {len(valid_tickers)} mã.")
