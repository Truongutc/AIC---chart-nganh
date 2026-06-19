import pandas as pd
import logging

# Mock _clean_dataframe logic or import it
from tinvest.data_loader import _clean_dataframe

logging.basicConfig(level=logging.INFO)

# Simulate CSV with YYYYMMDD integers
df_int = pd.DataFrame({
    "Date": [20231024, 20231025, 20231026],
    "Open": [10.0, 10.1, 10.2],
    "High": [10.5, 10.6, 10.7],
    "Low": [9.5, 9.6, 9.7],
    "Close": [10.3, 10.4, 10.5],
    "Volume": [1000, 1100, 1200]
})

print("Testing with YYYYMMDD integers:")
try:
    # We need to simulate the normalization if we use the internal function
    # Or just call _clean_dataframe if it expects "Date" column
    cleaned = _clean_dataframe(df_int.copy(), ticker="TEST_INT")
    print(cleaned[["Date", "Close"]])
    print("Dates types:", cleaned["Date"].dtype)
except Exception as e:
    print(f"Error with integers: {e}")

# Simulate CSV with YYYYMMDD strings
df_str = pd.DataFrame({
    "Date": ["20231024", "20231025", "20231026"],
    "Open": [10.0, 10.1, 10.2],
    "High": [10.5, 10.6, 10.7],
    "Low": [9.5, 9.6, 9.7],
    "Close": [10.3, 10.4, 10.5],
    "Volume": [1000, 1100, 1200]
})

print("\nTesting with YYYYMMDD strings:")
try:
    cleaned = _clean_dataframe(df_str.copy(), ticker="TEST_STR")
    print(cleaned[["Date", "Close"]])
    print("Dates types:", cleaned["Date"].dtype)
except Exception as e:
    print(f"Error with strings: {e}")
