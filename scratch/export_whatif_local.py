import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to python path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.ichimoku_engine import analyze_ichimoku
from tinvest.vsa_engine import analyze_vsa
from tinvest.advanced_entry import classify_entry
from tinvest.accumulation_engine import analyze_accumulation
from tinvest.ma_engine import analyze_ma_trend
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.state_engine import evaluate_state_rules
from tinvest.chart_exporter import export_ticker_history_json
from tinvest.whatif_engine import run_whatif_analysis
import json

def main():
    print("[*] Starting local data exporter...")
    storage = StorageManager()
    
    # Selected tickers to generate data for testing
    test_tickers = ["VND", "GMD"]
    
    data_dict = {}
    analysis_cache = {}
    
    for t in test_tickers:
        print(f"[*] Processing {t}...")
        df = storage.load_ticker_data(t)
        if df is None or len(df) < 50:
            print(f"  [WARN] Ticker {t} has no data or too few bars in data_storage. Skipping.")
            continue
            
        try:
            # 1. Enrich data
            df_rich = enrich_dataframe(df)
            
            # 2. Run analyses
            ichi = analyze_ichimoku(df_rich)
            vsa = analyze_vsa(df_rich)
            adv = classify_entry(df_rich)
            accum = analyze_accumulation(df_rich)
            ma_trend = analyze_ma_trend(df_rich)
            val = evaluate_stock_valuation(t, df_rich, adv)
            state_rules = evaluate_state_rules(df_rich)
            
            data_dict[t] = df_rich
            analysis_cache[t] = {
                "df": df_rich,
                "ichi": ichi,
                "vsa": vsa,
                "adv": adv,
                "accum": accum,
                "ma_trend": ma_trend,
                "valuation": val,
                "state_rules": state_rules
            }
            print(f"  [OK] {t} analyzed successfully ({len(df_rich)} bars)")
        except Exception as e:
            print(f"  [ERROR] Error processing {t}: {e}")
            
    if not data_dict:
        print("[ERROR] No data found in local data_storage. Please make sure data_storage contains parquet files.")
        return

    # Export what-if cache JSON FIRST to avoid redundant calculation in export_ticker_history_json
    print("[*] Calculating and caching What-If for test tickers...")
    whatif_cache = {}
    for idx in test_tickers:
        if idx in data_dict:
            print(f"  • Running What-If analysis for {idx}...")
            result = run_whatif_analysis(idx, data_dict[idx], top_n=5, compute_forecast_series=True, forecast_days=90)
            if result and not result.get('error'):
                whatif_cache[idx] = result
                # Inject into analysis_cache so export_ticker_history_json can reuse it
                if idx in analysis_cache:
                    analysis_cache[idx]['whatif'] = result
                else:
                    analysis_cache[idx] = {'whatif': result}

    # Export history JSONs
    output_dir = "Output"
    os.makedirs(output_dir, exist_ok=True)
    print(f"[*] Exporting history JSON files to {output_dir}/history/...")
    export_ticker_history_json(data_dict, analysis_cache, output_dir)
    print("[OK] History files exported.")

    if whatif_cache:
        def default_converter(o):
            if isinstance(o, np.integer): return int(o)
            if isinstance(o, np.floating): return float(o)
            if isinstance(o, np.ndarray): return o.tolist()
            return o
        with open(os.path.join(output_dir, "whatif_results.json"), "w", encoding="utf-8") as f:
            json.dump(whatif_cache, f, ensure_ascii=False, indent=4, default=default_converter)
        print("[OK] whatif_results.json exported.")
    else:
        print("[WARN] No index What-If data could be cached.")

    # Export a minimal analysis_results.json to satisfy index.html
    analysis_results = {
        "last_update": "2026-06-14 09:15:00",
        "vietstock_status": "VALID",
        "stocks_updated_count": len(data_dict),
        "market_indices": {
            "VNINDEX": {
                "regime": "SIDEWAY",
                "action": "WAIT",
                "price": 1280,
                "date": "2026-06-14",
                "alloc": "50%"
            },
            "HNX-INDEX": {
                "regime": "SIDEWAY",
                "action": "WAIT",
                "price": 240,
                "date": "2026-06-14",
                "alloc": "50%"
            }
        },
        "tickers_analysis": [
            {
                "Ticker": t,
                "Price": float(data_dict[t]['Close'].iloc[-1]),
                "Volume": int(data_dict[t]['Volume'].iloc[-1]) if 'Volume' in data_dict[t].columns else 0,
                "Categories": [],
                "Rules": [],
                "VSA_Dominant": "neutral",
                "VSA_Score": 0,
                "MCDX": "N/A",
                "Tech_Health": "N/A"
            } for t in data_dict
        ]
    }
    with open(os.path.join(output_dir, "analysis_results.json"), "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=4)
    print("[OK] minimal analysis_results.json exported.")

    print("\nDone! Localhost should now have enough data to test the What-If analysis.")

if __name__ == "__main__":
    main()
