import json

# Load HPG history JSON
json_path = "Output/history/HPG.json"
try:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print("Keys in JSON:", data.keys())
    dates = data['dates']
    closes = data['closes']
    print("Total dates in JSON:", len(dates))
    print("Total closes in JSON:", len(closes))
    
    # Print the last 15 entries
    for i in range(max(0, len(dates) - 15), len(dates)):
        print(f"Index {i}: Date={dates[i]}, Close={closes[i]}")
except Exception as e:
    print("Error loading JSON:", e)
