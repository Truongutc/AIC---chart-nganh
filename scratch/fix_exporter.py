import re

with open('tinvest/chart_exporter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change compute_forecast_series=is_index to compute_forecast_series=True
content = content.replace('compute_forecast_series=is_index', 'compute_forecast_series=True')

with open('tinvest/chart_exporter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated chart_exporter.py")
