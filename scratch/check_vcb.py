import sys
from pathlib import Path
import json

# Fix unicode print issue on Windows
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
from tinvest.whatif_engine import run_whatif_analysis

def main():
    try:
        storage = StorageManager()
        df = storage.load_ticker_data("VCB")
        if df is not None:
            df_rich = enrich_dataframe(df)
            res = run_whatif_analysis("VCB", df_rich)
            
            if res.get("error"):
                print("Error:", res.get("error"))
                return
            
            match_quality = res.get("match_quality", {})
            
            print("=== Ket qua phien tuong dong cho VCB ===")
            print(f"Chat luong: Hang {match_quality.get('dominant_tier')} - {match_quality.get('confidence_label')}")
            if "warning" in match_quality and match_quality["warning"]:
                print(f"Canh bao: {match_quality['warning']}")
                
            matches = res.get("matches", [])
            if not matches:
                print("Khong tim thay phien tuong dong nao!")
            else:
                print(f"Tim thay {len(matches)} phien tuong dong nhat:")
                for i, m in enumerate(matches[:5]):
                    print(f" {i+1}. Ngay: {m.get('date')} - Do tuong dong: {m.get('similarity', 0)*100:.2f}% (Hang {m.get('tier')})")
        else:
            print("Khong tim thay du lieu cho VCB.")
    except Exception as e:
        print("Loi:", e)

if __name__ == "__main__":
    main()
