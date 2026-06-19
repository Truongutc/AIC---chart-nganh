import os
import sys
from pathlib import Path

# Add base path to sys.path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager
from tinvest.chart_exporter import export_ticker_history_json
from AICcode import TinvestApp, analyze_ticker_worker

class SmallExporter:
    def __init__(self):
        self.storage = StorageManager()
        self.data_dict = {}
        self.analysis_cache = {}

    def log_sync(self, msg):
        print(msg)

    def run(self):
        tickers = ["VNINDEX", "VN30", "HPG", "MIG", "HHS", "VIP"]
        print("Loading and analyzing data for:", tickers)
        
        for t in tickers:
            df = self.storage.load_ticker_data(t)
            if df is not None and len(df) >= 100:
                _, analysis = analyze_ticker_worker((t, df))
                if analysis:
                    self.data_dict[t] = analysis["df"]
                    self.analysis_cache[t] = analysis

        # 1. Export history JSON files first (this runs What-If and saves them)
        print("Exporting history JSONs (includes What-If calculations)...")
        export_ticker_history_json(self.data_dict, self.analysis_cache, "Output")

        # 2. Export main web json (this reads What-If data from history JSONs to populate scanner filters)
        print("Exporting main analysis_results.json...")
        self.export_web_json = TinvestApp.export_web_json.__get__(self)
        self.export_web_json()
        print("Subset export finished successfully!")

if __name__ == "__main__":
    exporter = SmallExporter()
    exporter.run()
