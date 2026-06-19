with open('../index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'setMarkers' in line or 'triangleUp' in line or 'HK_' in line or 'BuySignal' in line:
        print(f"{i+1}: {line.strip()}")
