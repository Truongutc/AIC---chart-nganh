import os

file_path = r'd:\Github\Phan-mem-phan-tich\AICcode.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Detect the corrupted block in the Indices fetch function
    # It starts with 'if not affected_tickers:' but is at a much later line number (around 1547)
    if i > 1500 and 'if not affected_tickers:' in line:
        new_lines.append('            if not affected_tickers:\n')
        new_lines.append('                return\n')
        skip = True
        continue
    
    if skip:
        # Skip until we find the real end of the corruption
        # We want to skip my accidentally inserted "Đã chuẩn bị... mã" and the buggy "return"
        if '"--- ĐANG TÍNH TOÁN LẠI CHỈ BÁO VÀ SCANNER (0ms) ---"' in line:
            skip = False
            # Append the rest of the original logic starting from the line before this one (if we can find it)
            # Actually, let's just resume from here
            new_lines.append(line)
        continue
    
    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("SUCCESS: Indices block cleaned up.")
