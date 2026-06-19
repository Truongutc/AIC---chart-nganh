import pandas as pd
import numpy as np
from tinvest.market_engine import analyze_momentum_divergence

# Create dummy data with 50+ rows
dates = pd.date_range(start="2024-01-01", periods=60)
df = pd.DataFrame({
    "Date": dates,
    "Close": np.linspace(100, 150, 60),
    "Open": np.linspace(100, 150, 60),
    "High": np.linspace(105, 155, 60),
    "Low": np.linspace(95, 145, 60),
    "Volume": np.random.randint(1000, 5000, 60)
})

try:
    print("Running analyze_momentum_divergence...")
    res = analyze_momentum_divergence(df)
    print("Success! Result keys:", res.keys())
    print("RSI Divergence:", res.get("rsi_divergence"))
    print("MACD Divergence:", res.get("macd_divergence"))
except Exception as e:
    print("FAILED with Exception:", e)
    import traceback
    traceback.print_exc()
