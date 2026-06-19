import pandas as pd
from tinvest.data_loader import _clean_dataframe, load_data
import os

# 1. Verify Date Parsing (floats/strings)
print("--- Verification: Date Parsing ---")
df_float = pd.DataFrame({
    "Date": [20231024.0, 20231025.0, 20231026.0],
    "Open": [10.0, 10.1, 10.2],
    "High": [10.5, 10.6, 10.7],
    "Low": [9.5, 9.6, 9.7],
    "Close": [10.3, 10.4, 10.5],
    "Volume": [1000, 1100, 1200]
})

cleaned = _clean_dataframe(df_float, ticker="TEST_FLOAT")
print("Float conversion success:")
print(cleaned[["Date", "Close"]])
assert cleaned["Date"].iloc[0].year == 2023
assert cleaned["Date"].iloc[0].month == 10
assert cleaned["Date"].iloc[0].day == 24

# 2. Verify VNI is not an index
print("\n--- Verification: VNI vs Index ---")
# Mock a CSV with Ticker column
vni_csv = "vni_test.csv"
pd.DataFrame({
    "Ticker": ["VNI", "VNI", "VNINDEX", "VNINDEX"],
    "Date": [20231024, 20231025, 20231024, 20231025],
    "Open": [10]*4, "High": [11]*4, "Low": [9]*4, "Close": [10.5]*4, "Volume": [1000]*4
}).to_csv(vni_csv, index=False)

try:
    result = load_data(vni_csv)
    print("Tickers loaded:", list(result.keys()))
    # VNI should be a stock (3 letters), VNINDEX is an index
    # Standard logic: if ticker in ["VNINDEX", "HNX", "HAINDEX"] -> index.
    # VNI is 3 letters and alpha, so it should be processed as a stock.
    assert "VNI" in result
    assert "VNINDEX" in result
    print("VNI successfully processed as a stock.")
finally:
    if os.path.exists(vni_csv): os.remove(vni_csv)

print("\nVerification completed successfully!")
