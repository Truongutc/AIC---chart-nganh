import pandas as pd
import numpy as np

# Load HPG data
path = "data_storage/prices/HPG.parquet"
df = pd.read_parquet(path)
print("Total rows:", len(df))
print("Columns:", df.columns)

# Check duplicates in Date (converting to pandas datetime first to see)
df['ParsedDate'] = pd.to_datetime(df['Date'])
df['OnlyDate'] = df['ParsedDate'].dt.date

duplicates_by_exact = df[df.duplicated(subset=['Date'], keep=False)]
duplicates_by_only_date = df[df.duplicated(subset=['OnlyDate'], keep=False)]

print("\n--- Duplicates by EXACT Date field ---")
print(len(duplicates_by_exact))
if len(duplicates_by_exact) > 0:
    print(duplicates_by_exact.head(10))

print("\n--- Duplicates by normalized OnlyDate ---")
print(len(duplicates_by_only_date))
if len(duplicates_by_only_date) > 0:
    print(duplicates_by_only_date.sort_values('OnlyDate').head(20))

# Print the last 15 rows of the data
print("\n--- Last 15 rows ---")
print(df.tail(15)[['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'source']])
