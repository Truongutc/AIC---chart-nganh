import pandas as pd
import numpy as np
import sys
import os

# Import matplotlib and set backend to Agg for non-interactive test
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Generate mock data
n = 150
dates = pd.date_range(start='2023-01-01', periods=n)
df = pd.DataFrame({
    'Date': dates,
    'Open': np.random.rand(n) * 100 + 1000,
    'High': np.random.rand(n) * 100 + 1050,
    'Low': np.random.rand(n) * 100 + 950,
    'Close': np.random.rand(n) * 100 + 1000,
    
    # GreenPink
    'GP_E14': np.random.rand(n) * 100 + 1000,
    'GP_E21': np.random.rand(n) * 100 + 1000,
    'GP_xFast': np.random.rand(n) * 100 + 1000,
    'GP_xSlow': np.random.rand(n) * 100 + 1000,
    'GP_BB_Top': np.random.rand(n) * 100 + 1050,
    'GP_BB_Bot': np.random.rand(n) * 100 + 950,
    'OCT_A1': np.random.rand(n) * 10 - 5,
    'OCT_B1': np.random.rand(n) * 10 - 5,
    'OCT_Color': ['#00FF00' if i % 2 == 0 else '#FF69B4' for i in range(n)],
    'OCT_BB_Top': np.random.rand(n) * 5 + 5,
    'OCT_BB_Bot': np.random.rand(n) * 5 - 10,
    
    # Heikin
    'HK_MHull': np.random.rand(n) * 100 + 1000,
    'HK_SHull': np.random.rand(n) * 100 + 1000,
    'HK_NW': np.random.rand(n) * 100 + 1000,
    'HK_Trend': [1 if i % 2 == 0 else -1 for i in range(n)],
    'HK_Flower_Open': np.random.rand(n) * 100 + 1000,
    'HK_Flower_High': np.random.rand(n) * 100 + 1050,
    'HK_Flower_Low': np.random.rand(n) * 100 + 950,
    'HK_Flower_Close': np.random.rand(n) * 100 + 1000,
    'HK_BarColor': ['brightGreen' if i % 3 == 0 else ('red' if i % 3 == 1 else 'white') for i in range(n)],
    'TC_Trend': np.random.rand(n) * 100 + 1000,
    'TC_TrendColor': ['#00FF00' if i % 2 == 0 else '#FF69B4' for i in range(n)],
    'TC_StopLine': np.random.rand(n) * 100 + 900,
    'TC_StopColor': ['#00FF00' if i % 2 == 0 else '#FF69B4' for i in range(n)],
    'HK_BuySignal': [True if i == 50 else False for i in range(n)],
    'HK_BuyManh': [False for i in range(n)],
    'HK_SellSignal': [True if i == 100 else False for i in range(n)],
    'HK_SellManh': [False for i in range(n)],
    
    'T2_SMA': np.random.rand(n) * 100 + 1000,
    'T2_SMA_Trend': [1 if i % 2 == 0 else -1 for i in range(n)],
    'T2_ST_Upper': np.random.rand(n) * 100 + 1050,
    'T2_ST_Lower': np.random.rand(n) * 100 + 950,
    'T2_ST_Trend': [1 if i % 2 == 0 else -1 for i in range(n)],
})

class DummyApp:
    def log_sync(self, msg, clear=False):
        print(f"[LOG] {msg}")

from AICcode import TinvestApp

# Monkey patch from class
DummyApp.show_greenpink_window = TinvestApp.show_greenpink_window
DummyApp.show_heikin_window = TinvestApp.show_heikin_window

app = DummyApp()

print("Testing show_greenpink_window...")
app.show_greenpink_window("MOCK_GP", df)
plt.close('all')
print("show_greenpink_window passed!")

print("Testing show_heikin_window...")
app.show_heikin_window("MOCK_HK", df)
plt.close('all')
print("show_heikin_window passed!")

print("All chart rendering tests passed successfully!")
