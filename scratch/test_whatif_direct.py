import sys
from pathlib import Path
import traceback

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.whatif_engine import run_whatif_analysis

try:
    storage = StorageManager()
    df = storage.load_ticker_data("VNINDEX")
    if df is not None:
        df_rich = enrich_dataframe(df)
        print(f"Dataframe loaded: {len(df_rich)} rows.")
        print("Running run_whatif_analysis...")
        res = run_whatif_analysis("VNINDEX", df_rich)
        print("Result type:", type(res))
        if isinstance(res, dict):
            print("Keys:", list(res.keys()))
            if "error" in res:
                print("Error key value:", res["error"])
        else:
            print("Result:", res)
    else:
        print("No VNINDEX data loaded.")
except Exception as e:
    print("Exception occurred:")
    traceback.print_exc()
