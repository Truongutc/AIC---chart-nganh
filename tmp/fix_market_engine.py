import os

filepath = 'e:/projects/2. Codeinvest/Codeinvest/tinvest/market_engine.py'
if not os.path.exists(filepath):
    print(f"Error: {filepath} not found")
    exit(1)

with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

new_lines = []
target_string = 'rsi_div_bear = (price_top_1 > price_top_2)'
fixed = False
for line in lines:
    if target_string in line and not fixed:
        # Avoid double fixing if script is somehow rerun
        if 'price_top_1 = ' not in lines[lines.index(line)-1]:
            new_lines.append("    # Define peak variables for divergence calculation\n")
            new_lines.append("    price_top_1 = df['Close'].iloc[-15:].max()\n")
            new_lines.append("    price_top_2 = df['Close'].iloc[-30:-15].max()\n")
            new_lines.append("    rsi_last_15 = rsi.iloc[-15:].max()\n")
            new_lines.append("    rsi_prev_15 = rsi.iloc[-30:-15].max()\n")
            new_lines.append("    macd_last_15 = macd.iloc[-15:].max()\n")
            new_lines.append("    macd_prev_15 = macd.iloc[-30:-15].max()\n\n")
            fixed = True
    new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

if fixed:
    print("SUCCESS: Inserted 7 peak variable definitions.")
else:
    print("FAILED: Target line not found or already fixed.")
