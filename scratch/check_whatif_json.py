import json
import os

history_dir = "Output/history"
files = ["VNINDEX.json", "FPT.json", "HPG.json"]

for f in files:
    path = os.path.join(history_dir, f)
    if os.path.exists(path):
        print(f"File {f} exists. Reading...")
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            print(f"Keys in {f}: {list(data.keys())}")
            if "whatif" in data:
                wi = data["whatif"]
                print(f"whatif status: {'error' if 'error' in wi else 'OK'}")
                if 'error' in wi:
                    print(f"Error detail: {wi['error']}")
                else:
                    print(f"whatif keys: {list(wi.keys())}")
                    print(f"sims count: {len(wi.get('simulations', [])) if 'simulations' in wi else 'N/A'}")
                    print(f"scenarios: {list(wi.get('scenario_tree', {}).keys()) if 'scenario_tree' in wi else 'N/A'}")
            else:
                print("whatif key NOT found!")
    else:
        print(f"File {f} does NOT exist!")
