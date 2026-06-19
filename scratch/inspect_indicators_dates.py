import pandas as pd

# Read local HPG parquet
df = pd.read_parquet("data_storage/prices/HPG.parquet")
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date').reset_index(drop=True)

# Select dates around the dividend (May 11 to May 28)
mask = (df['Date'] >= '2026-05-08') & (df['Date'] <= '2026-05-28')
sub_df = df[mask]

print(sub_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'source', 'updated_at']])
