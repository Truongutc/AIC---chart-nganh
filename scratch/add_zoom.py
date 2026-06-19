import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add hammer and zoom plugin
content = content.replace('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>', 
    '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n    <script src="https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.min.js"></script>\n    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>')

# 2. Update zoom plugin for whatifForecastChart
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
