import pandas as pd
from datetime import datetime
from tinvest.storage_manager import StorageManager

sm = StorageManager()

data = [{
    'Ticker': 'VNINDEX',
    'Date': '2026-03-31',
    'Open': 1669.57,
    'High': 1677.83,
    'Low': 1662.54,
    'Close': 1674.49,
    'Volume': 929691249
}]
df = pd.DataFrame(data)

t_min = sm.sync_prices("VNINDEX", df, "API")
print(f"sync_prices returned t_min: {t_min}")
