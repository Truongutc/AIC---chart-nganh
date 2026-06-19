import pandas as pd
import os

df = pd.DataFrame({'Date': ['2023-01-01', '2023-01-02'], 'Close': [100, 105]})
test_path = "test_parquet.parquet"

try:
    df.to_parquet(test_path, index=False)
    print("SUCCESS: to_parquet worked.")
    df_read = pd.read_parquet(test_path)
    print("SUCCESS: read_parquet worked.")
    print(df_read)
    os.remove(test_path)
except Exception as e:
    print(f"FAILURE: {e}")
