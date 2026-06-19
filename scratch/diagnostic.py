import logging
import sys
from tinvest.vietstock_client import VietstockClient

# Configure logging to console
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("diagnostic")

def run_diagnostic():
    client = VietstockClient()
    print("\n--- DIAGNOSTIC START ---")
    
    # 1. Test basic connectivity
    print("[1] Testing basic GET to Vietstock...")
    try:
        r = client.session.get("https://finance.vietstock.vn", timeout=15)
        print(f"    Result: SUCCESS (Status: {r.status_code})")
    except Exception as e:
        print(f"    Result: FAILED - {type(e).__name__}: {e}")

    # 2. Test status probe
    print("[2] Running check_session_status...")
    status = client.check_session_status()
    print(f"    Final Status: {status}")
    
    # 3. Test API POST
    print("[3] Testing API POST (Small probe)...")
    try:
        raw = client._fetch_page(1, "2024-05-09", page=1, page_size=1)
        if raw:
            print("    Result: SUCCESS")
        else:
            print("    Result: RETURNED NONE")
    except Exception as e:
        print(f"    Result: FAILED - {type(e).__name__}: {e}")

if __name__ == "__main__":
    run_diagnostic()
