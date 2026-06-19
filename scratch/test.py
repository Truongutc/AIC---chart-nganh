import pandas as pd
import numpy as np
import json

data = json.load(open('Output/history/VND.json', encoding='utf-8'))
prices = pd.Series(data['closes'])
period = 25
md = np.zeros(len(prices))
md[0] = prices.iloc[0]

for i in range(1, len(prices)):
    prev_md = md[i-1]
    if prev_md <= 0: 
        md[i] = prices.iloc[i]
        continue
    ratio = prices.iloc[i] / prev_md
    ratio = min(max(ratio, 0.5), 2.0)
    denom = period * (ratio**4)
    md[i] = prev_md + (prices.iloc[i] - prev_md) / denom

print(md[-15:])
