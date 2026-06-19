import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add hammer and zoom plugin
content = content.replace('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>', 
    '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n    <script src="https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.min.js"></script>\n    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>')

# 2. Add test_probability
content = content.replace(
    'Giá kỳ vọng mục tiêu ban đầu: <strong style="color:white;">${formatPrice(mp.target_price * 1000, ticker.includes(\'INDEX\'))}</strong>',
    '<div style="margin-bottom: 4px;">Xác suất test vùng giá: <strong style="color:var(--accent-purple);">${mp.test_probability || mp.probability}%</strong></div>\n                                Giá kỳ vọng mục tiêu ban đầu: <strong style="color:white;">${formatPrice(mp.target_price * 1000, ticker.includes(\'INDEX\'))}</strong>'
)
content = content.replace(
    'Giá kỳ vọng mục tiêu ban đầu: <strong style="color:white;">${formatPrice(ap.target_price * 1000, ticker.includes(\'INDEX\'))}</strong>',
    '<div style="margin-bottom: 4px;">Xác suất test vùng giá: <strong style="color:var(--accent-purple);">${ap.test_probability || ap.probability}%</strong></div>\n                                Giá kỳ vọng mục tiêu ban đầu: <strong style="color:white;">${formatPrice(ap.target_price * 1000, ticker.includes(\'INDEX\'))}</strong>'
)

# 3. Fix subtabs visibility and hide nav
content = content.replace('class="whatif-subtabs-nav"', 'class="whatif-subtabs-nav" style="display: none;"')
content = content.replace('class="whatif-subtabs-select-container"', 'class="whatif-subtabs-select-container" style="display: none;"')
content = content.replace('style="display: none;"', 'style="margin-bottom: 20px;"')
content = content.replace('style="display: block;"', 'style="margin-bottom: 20px;"')

# Ensure we undo any global replace for things that shouldn\'t be modified
content = content.replace('id="whatifSuggestions" class="search-suggestions" style="margin-bottom: 20px;"', 'id="whatifSuggestions" class="search-suggestions" style="display: none;"')
content = content.replace('id="whatifDashboard" class="stock-dashboard" style="margin-bottom: 20px;"', 'id="whatifDashboard" class="stock-dashboard" style="display: none;"')
content = content.replace('id="techReportModal" class="modal" style="margin-bottom: 20px;"', 'id="techReportModal" class="modal" style="display: none;"')
content = content.replace('id="whatifFsCloseBtn" onclick="toggleWhatifChartFullscreen()" style="margin-bottom: 20px;', 'id="whatifFsCloseBtn" onclick="toggleWhatifChartFullscreen()" style="display: none;')
content = content.replace('style="margin-bottom: 20px;" position:', 'style="display: none;" position:')
content = content.replace('style="margin-bottom: 20px; position:', 'style="display: none; position:')

# Empty out switchWhatifSubtab
content = re.sub(
    r'function switchWhatifSubtab\(subtabId\) \{.*?\n        \}',
    'function switchWhatifSubtab(subtabId) { /* disabled tabs */ }',
    content, flags=re.DOTALL
)

# Replace the "Switch back to tree tab" in catch
content = re.sub(
    r'// Switch back to tree tab or previous active\s+const activeBtn.*?\n                \}',
    '',
    content, flags=re.DOTALL
)

# 4. Update zoom plugin for whatifForecastChart
zoom_cfg = """                                zoom: {
                                    zoom: {
                                        wheel: { enabled: true },
                                        pinch: { enabled: true },
                                        mode: 'xy'
                                    },
                                    pan: {
                                        enabled: true,
                                        mode: 'xy'
                                    }
                                },
                                legend: {"""
content = content.replace('legend: {', zoom_cfg, 1)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
