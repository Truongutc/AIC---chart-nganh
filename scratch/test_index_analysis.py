import sys
import os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from tinvest.data_loader import enrich_dataframe
from tinvest.market_engine import analyze_market_index, analyze_market_breadth, analyze_momentum_divergence
from tinvest.ichimoku_engine import analyze_ichimoku
from tinvest.vsa_engine import analyze_vsa
from tinvest.ma_engine import analyze_ma_trend
from tinvest.advanced_entry import classify_entry
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.state_engine import evaluate_state_rules
from tinvest.analyzer import evaluate_heatmap
from tinvest.mcdx_engine import evaluate_mcdx_rules

def test_analysis():
    print("Generating mock index data...")
    dates = pd.date_range(end="2026-05-21", periods=200)
    
    # Standard OHLCV columns plus some typical technical inputs
    mock_df = pd.DataFrame({
        "Date": dates,
        "Open": np.linspace(1100, 1200, 200) + np.random.randn(200) * 10,
        "High": np.linspace(1110, 1210, 200) + np.random.randn(200) * 10,
        "Low": np.linspace(1090, 1190, 200) + np.random.randn(200) * 10,
        "Close": np.linspace(1105, 1205, 200) + np.random.randn(200) * 10,
        "Volume": np.random.randint(100000, 1000000, 200),
    })
    
    # Ensure High is max, Low is min
    mock_df["High"] = mock_df[["Open", "Close", "High"]].max(axis=1)
    mock_df["Low"] = mock_df[["Open", "Close", "Low"]].min(axis=1)
    
    # Add Heatmap required columns
    mock_df["HM_Flower_Open"] = mock_df["Open"]
    mock_df["HM_Flower_Close"] = mock_df["Close"]
    mock_df["HM_MoneyFlow"] = np.random.choice([1, -1, 0], size=200)
    
    # Add MCDX required columns
    mock_df["MCDX_Banker"] = np.random.uniform(0, 100, 200)
    mock_df["MCDX_HotMoney"] = np.random.uniform(0, 100, 200)
    mock_df["MCDX_Retailer"] = np.random.uniform(0, 100, 200)
    
    # Add Heikin Ashi columns (normally populated by Heikin engine)
    mock_df["HK_MHull"] = mock_df["Close"].rolling(9).mean()
    mock_df["HK_SHull"] = mock_df["Close"].rolling(26).mean()
    mock_df["TC_Trend"] = mock_df["Close"].rolling(13).mean()
    mock_df["TC_TrendColor"] = ["#ff0000"] * 200
    mock_df["TC_StopLine"] = mock_df["Low"] - 10
    mock_df["TC_StopColor"] = ["#ff0000"] * 200
    mock_df["HK_NW"] = mock_df["Close"].rolling(5).mean()
    mock_df["HK_Trend"] = [1] * 200
    mock_df["HK_Flower_Open"] = mock_df["Open"]
    mock_df["HK_Flower_High"] = mock_df["High"]
    mock_df["HK_Flower_Low"] = mock_df["Low"]
    mock_df["HK_Flower_Close"] = mock_df["Close"]
    mock_df["HK_BarColor"] = ["brightGreen"] * 200

    print("Enriching data...")
    df_rich = enrich_dataframe(mock_df)
    
    print("Testing analyze_full_index equivalent steps...")
    breadth_ma20 = 50.0
    breadth_ma50 = 50.0
    
    mom = analyze_momentum_divergence(mock_df)
    signals = classify_entry(df_rich)
    has_signal = signals.get('entry_type', 'NONE') != 'NONE'
    
    val = evaluate_stock_valuation("INDEX", df_rich, signals)
    sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),
          "r1": val.get("r1", 0), "r2": val.get("r2", 0)}
          
    state_rules = evaluate_state_rules(df_rich)
    heatmap_eval = evaluate_heatmap(df_rich)
    mcdx_eval = evaluate_mcdx_rules(df_rich)
    
    res_regime = analyze_market_index(mock_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
    res_regime['price'] = float(mock_df['Close'].iloc[-1])
    
    result = {
        "regime": res_regime,
        "momentum": mom,
        "ichi": analyze_ichimoku(df_rich),
        "vsa": analyze_vsa(df_rich),
        "ma": analyze_ma_trend(df_rich),
        "sr": sr,
        "sr_source": "SIGNAL" if has_signal else "PIVOT",
        "signals": signals,
        "valuation": val,
        "state_rules": state_rules,
        "heatmap_eval": heatmap_eval,
        "elliott_eval": "N/A",
        "mcdx_eval": mcdx_eval,
        "date": mock_df['Date'].iloc[-1].strftime("%Y-%m-%d") if 'Date' in mock_df.columns else "N/A"
    }
    
    print("SUCCESS: Index analysis logic completed without errors!")
    print(f"Heatmap Eval: {result['heatmap_eval']}")
    print(f"Elliott Eval: {result['elliott_eval']}")

if __name__ == "__main__":
    test_analysis()
