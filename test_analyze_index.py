from tinvest.storage_manager import StorageManager
from AICcode import analyze_ticker_worker
import pandas as pd

sm = StorageManager()
df = sm.load_ticker_data("VNINDEX")
print("DF loaded for VNINDEX. Rows:", len(df))
print(df.tail(3))

ticker, res = analyze_ticker_worker(("VNINDEX", df))
if res:
    print("\nAnalysis successful. Last row of enriched DF:")
    print(res["df"].tail(1)[["Date", "Close", "MA10", "MA20"]])
    
    print("\nValuation report:")
    print(res["val"])
else:
    print("Analysis failed.")
