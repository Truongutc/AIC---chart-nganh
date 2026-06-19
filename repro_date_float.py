import pandas as pd
import logging
from tinvest.data_loader import _clean_dataframe

logging.basicConfig(level=logging.INFO)

df_float = pd.DataFrame({
    "Date": [20231024.0, 20231025.0, 20231026.0],
    "Open": [10.0, 10.1, 10.2],
    "High": [10.5, 10.6, 10.7],
    "Low": [9.5, 9.6, 9.7],
    "Close": [10.3, 10.4, 10.5],
    "Volume": [1000, 1100, 1200]
})

print("Testing with YYYYMMDD floats:")
try:
    cleaned = _clean_dataframe(df_float.copy(), ticker="TEST_FLOAT")
    print(cleaned[["Date", "Close"]])
    print("Dates types:", cleaned["Date"].dtype)
except Exception as e:
    print(f"Error with floats: {e}")

# Try another case: pd.to_datetime on float directly
print("\nDirect pd.to_datetime(20231024.0):")
try:
    print(pd.to_datetime(20231024.0))
except Exception as e:
    print(f"Error: {e}")

# Try pd.to_datetime(str(20231024.0))
print("\nDirect pd.to_datetime(str(20231024.0)):")
try:
    print(pd.to_datetime(str(20231024.0)))
except Exception as e:
    print(f"Error: {e}")
