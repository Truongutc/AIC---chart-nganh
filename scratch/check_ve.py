import json

with open("Output/whatif_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Print keys of the first entry
first_key = list(data.keys())[0]
print("First ticker:", first_key)
print("Keys of ticker data:", list(data[first_key].keys()))
if "distribution" in data[first_key]:
    dist = data[first_key]["distribution"]
    print("distribution keys:", list(dist.keys()))
    if "future_10" in dist:
        print("future_10:", dist["future_10"])
