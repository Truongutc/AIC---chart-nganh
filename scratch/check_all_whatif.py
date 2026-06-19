import os
import json

history_dir = "Output/history"
files = [f for f in os.listdir(history_dir) if f.endswith(".json")]

total_files = len(files)
has_whatif = 0
whatif_error = 0
whatif_ok = 0
errors = []

for f in files:
    path = os.path.join(history_dir, f)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if "whatif" in data:
                has_whatif += 1
                wi = data["whatif"]
                if not wi:
                     whatif_error += 1
                     errors.append((f, "Empty whatif"))
                elif "error" in wi and wi["error"] is not None:
                     whatif_error += 1
                     errors.append((f, wi["error"]))
                else:
                     whatif_ok += 1
    except Exception as e:
        pass

print(f"Total history files: {total_files}")
print(f"Files with 'whatif' key: {has_whatif}")
print(f"Files with whatif OK: {whatif_ok}")
print(f"Files with whatif Error: {whatif_error}")
print("Sample errors:")
for item in errors[:10]:
    print(f"  {item[0]}: {item[1]}")
