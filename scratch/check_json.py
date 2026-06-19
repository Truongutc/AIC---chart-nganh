import json
from pathlib import Path

json_path = Path("Output/history/HPG.json")
if json_path.exists():
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print("Keys in JSON:", list(data.keys()))
    print("Dates length:", len(data['dates']))
    print("Closes head:", data['closes'][:5])
    print("Closes tail:", data['closes'][-5:])
    if 'MA20' in data:
        print("MA20 head:", data['MA20'][:5])
        print("MA20 tail:", data['MA20'][-5:])
    if 'SpanA' in data:
        print("SpanA head:", data['SpanA'][:5])
        print("SpanA tail:", data['SpanA'][-5:])
else:
    print("JSON path does not exist")
