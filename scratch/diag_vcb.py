import sys
from pathlib import Path
import json
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.whatif_engine import build_state_vector_fast, _build_col_arrays, _classify_tier, TIER3_THRESHOLD, TIER4_FLOOR, DEFAULT_WEIGHT_CONFIG

def cosine_sim(v1, v2):
    dot = np.dot(v1, v2)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    return dot / norm if norm > 0 else 0.0

def main():
    try:
        storage = StorageManager()
        df = storage.load_ticker_data("VCB")
        if df is None:
            print("Khong tim thay data VCB.")
            return
            
        print(f"1. So luong data raw VCB: {len(df)} dong")
        if len(df) > 0:
            print(f"Ngay gan nhat raw: {df.iloc[-1]['Date']}")
            
        df_rich = enrich_dataframe(df)
        print(f"2. So luong data sau enrich: {len(df_rich)} dong")
        
        if len(df_rich) < 50:
            print("Can it nhat 50 dong de phan tich, data qua it.")
            return
            
        col_arrays = _build_col_arrays(df_rich)
        n = len(df_rich)
        
        # Get state vectors
        print("3. Kiem tra vector trang thai (state vector) cua phien gan nhat...")
        current_idx = n - 1
        current_sv = build_state_vector_fast(col_arrays, current_idx, n)
        
        # Check if there are NaNs in current_sv
        nans = [k for k, v in current_sv.items() if (v is None or (isinstance(v, float) and np.isnan(v)))]
        print(f"Cac dac trung bi NaN: {nans}")
        
        # Build vector array
        keys = list(DEFAULT_WEIGHT_CONFIG.keys())
        w_arr = np.array([DEFAULT_WEIGHT_CONFIG[k] for k in keys])
        v_current = np.array([current_sv.get(k, 0.0) for k in keys])
        v_current = np.nan_to_num(v_current)
        v_current_w = v_current * w_arr
        
        # Find matches
        print("4. Quet tim cac phien tuong dong...")
        max_sim = 0
        max_idx = -1
        max_date = ""
        
        sims = []
        for i in range(50, current_idx - 5): # skip too close to current
            sv_i = build_state_vector_fast(col_arrays, i, n)
            v_i = np.array([sv_i.get(k, 0.0) for k in keys])
            v_i = np.nan_to_num(v_i)
            v_i_w = v_i * w_arr
            sim = cosine_sim(v_current_w, v_i_w)
            sims.append((i, df_rich.iloc[i]['Date'], sim))
            
            if sim > max_sim:
                max_sim = sim
                max_idx = i
                max_date = df_rich.iloc[i]['Date']
                
        print(f" -> Do tuong dong cao nhat trong lich su la: {max_sim*100:.2f}% vao ngay {max_date}")
        print(f" -> Nguong de duoc cong nhan la tuong dong (Tier 3): {TIER3_THRESHOLD*100}%")
        print(f" -> Nguong toi thieu Floor (Tier 4 Floor): {TIER4_FLOOR*100}%")
        
        sims.sort(key=lambda x: x[2], reverse=True)
        print("Top 5 phien co do tuong dong cao nhat (nhung chua dat chuan):")
        for idx, date, sim in sims[:5]:
            print(f" - Ngay {date}: {sim*100:.2f}%")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
