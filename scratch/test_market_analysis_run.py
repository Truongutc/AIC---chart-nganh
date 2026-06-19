import pandas as pd
from tinvest.data_loader import load_data, enrich_dataframe
from tinvest.market_engine import analyze_market_index, analyze_market_breadth, analyze_momentum_divergence
from tinvest.ichimoku_engine import analyze_ichimoku
from tinvest.vsa_engine import analyze_vsa
from tinvest.ma_engine import analyze_ma_trend
from tinvest.valuation_engine import evaluate_stock_valuation
from tinvest.advanced_entry import classify_entry
from tinvest.state_engine import evaluate_state_rules
from tinvest.analyzer import evaluate_heatmap
from tinvest.mcdx_engine import evaluate_mcdx_rules
import traceback
import sys

# Set output encoding to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def run_test():
    with open("scratch/diagnostic_log.txt", "w", encoding="utf-8") as f_out:
        def log(msg):
            print(msg)
            f_out.write(str(msg) + "\n")
            
        log("Loading data...")
        # Load all parquet files in data_storage/prices
        data_dict = {}
        import os
        prices_dir = "data_storage/prices"
        for f in os.listdir(prices_dir):
            if f.endswith(".parquet"):
                ticker = f.replace(".parquet", "")
                path = os.path.join(prices_dir, f)
                try:
                    df = pd.read_parquet(path)
                    data_dict[ticker] = df
                except Exception as e:
                    log(f"Error loading {f}: {e}")
        
        log(f"Loaded {len(data_dict)} files.")
        
        vn_key = next((k for k in data_dict.keys() if "VNINDEX" in k), "VNINDEX")
        hn_key = next((k for k in data_dict.keys() if "HNX" in k or "HAINDEX" in k), "HNXINDEX")
        
        log(f"VNINDEX key: {vn_key}, HNX/HAINDEX key: {hn_key}")
        
        vn_df = data_dict.get(vn_key)
        if vn_df is not None:
            log("VNINDEX data head:")
            log(vn_df.head(2).to_string())
            log("VNINDEX columns and types:")
            log(str(vn_df.dtypes))
            log(f"VNINDEX date type: {type(vn_df['Date'].iloc[-1])}")
        
        try:
            log("\nCalculating breadth...")
            breadth_res = analyze_market_breadth(data_dict, "VNINDEX")
            log(f"Breadth result: {breadth_res}")
            breadth_ma20 = breadth_res.get("strong_stocks_ma20_pct", 50.0)
            breadth_ma50 = breadth_res.get("strong_stocks_pct", 50.0)
            
            log("\nAnalyzing VNINDEX...")
            idx_df = vn_df
            df_rich = enrich_dataframe(idx_df.copy())
            mom = analyze_momentum_divergence(idx_df)
            signals = classify_entry(df_rich)
            has_signal = signals.get('entry_type', 'NONE') != 'NONE'
            val = evaluate_stock_valuation("INDEX", df_rich, signals)
            sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),
                  "r1": val.get("r1", 0), "r2": val.get("r2", 0)}
            
            state_rules = evaluate_state_rules(df_rich)
            heatmap_eval = evaluate_heatmap(df_rich)
            mcdx_eval = evaluate_mcdx_rules(df_rich)
            
            res_regime = analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
            res_regime['price'] = float(idx_df['Close'].iloc[-1])
            
            log("Regime analysis completed successfully!")
            log(f"Regime: {res_regime}")
        except Exception as e:
            log("\n--- ERROR DURING ANALYSIS ---")
            log(traceback.format_exc())

if __name__ == "__main__":
    run_test()
