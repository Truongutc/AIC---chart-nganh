"""
tests/generate_sample.py
Generates a synthetic OHLCV CSV with two tickers for testing.
Run once to create tests/sample_data.csv and tests/multi_ticker.csv
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(42)

def _make_ohlcv(n: int = 300, start_price: float = 50.0, trend: float = 0.001) -> pd.DataFrame:
    closes = [start_price]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + rng.normal(trend, 0.02)))
    closes = np.array(closes)
    highs  = closes * (1 + rng.uniform(0.005, 0.02, n))
    lows   = closes * (1 - rng.uniform(0.005, 0.02, n))
    opens  = closes * (1 + rng.normal(0, 0.01, n))
    vols   = rng.integers(1_000_000, 10_000_000, n).astype(float)

    # Inject a breakout at bar 270 with volume spike
    closes[270:] *= 1.05
    highs[270:]  *= 1.05
    lows[270:]   *= 1.05
    opens[270:]  *= 1.05
    vols[270]    *= 3.0

    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "Date":   dates,
        "Open":   np.round(opens, 2),
        "High":   np.round(highs, 2),
        "Low":    np.round(lows, 2),
        "Close":  np.round(closes, 2),
        "Volume": vols.astype(int),
    })

out_dir = Path(__file__).parent

# Single-ticker CSV
df_single = _make_ohlcv()
df_single.to_csv(out_dir / "sample_data.csv", index=False)
print(f"Written {len(df_single)} rows -> tests/sample_data.csv")

# Multi-ticker CSV
df_vnm = _make_ohlcv(start_price=80.0, trend=0.0015)
df_vnm.insert(0, "Ticker", "VNM")
df_hpg = _make_ohlcv(start_price=25.0, trend=0.002)
df_hpg.insert(0, "Ticker", "HPG")

df_multi = pd.concat([df_vnm, df_hpg], ignore_index=True)
df_multi.to_csv(out_dir / "multi_ticker.csv", index=False)
print(f"Written {len(df_multi)} rows (2 tickers) -> tests/multi_ticker.csv")
