import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('index.html', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines, 1):
    if 'aicpro-tab' in line or 'contact-tab' in line or 'portfolio-tab' in line or 'menuContent' in line or 'market-tab' in line or 'lookup-tab' in line or 'filter-tab' in line:
        print(f'{i}: {line.rstrip()[:180]}')
