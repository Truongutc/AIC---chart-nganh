import os

file_path = r'd:\Github\Phan-mem-phan-tich\AICcode.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Detect the start of the buggy block
    if 'if not affected_tickers:' in line and i > 750:
        new_lines.append('            if not affected_tickers:\n')
        new_lines.append('                self.log_sync("ℹ️ Tất cả mã hợp lệ đã có sẵn trong bộ nhớ và ổ cứng.")\n')
        new_lines.append('                return\n')
        new_lines.append('\n')
        new_lines.append(f'            self.log_sync(f"[3/4] Đã chuẩn bị {{len(affected_tickers)}} mã. Đang tính toán chỉ báo...")\n')
        new_lines.append('            self._sync_and_recompute_affected(list(affected_tickers))\n')
        new_lines.append('            self.log_sync(f"\\n✅ HOÀN TẤT NẠP DỮ LIỆU!")\n')
        skip = True
        continue
    
    # Skip until we find the end of the buggy block or the end of the try block
    if skip:
        if 'except Exception as e:' in line or 'return' in line:
            skip = False
            new_lines.append(line)
        continue
    
    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("SUCCESS: Patch applied.")
