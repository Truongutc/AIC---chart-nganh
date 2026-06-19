import pandas as pd
import numpy as np
import json
from tinvest.octopus_engine import analyze_octopus

def mcginley_dynamic_fixed(series, period):
    md = np.zeros(len(series))
    md[0] = series.iloc[0]
    prices = series.values
    for i in range(1, len(series)):
        prev_md = md[i-1]
        if prev_md <= 0: 
            md[i] = prices[i]
            continue
            
        ratio = prices[i] / prev_md
        # Limit ratio to prevent denom explosion/implosion for parabolic stocks
        ratio = min(max(ratio, 0.5), 2.0)
        
        denom = period * (ratio**4)
        if denom < 0.01:
            md[i] = prev_md + (prices[i] - prev_md) / period
        else:
            md[i] = prev_md + (prices[i] - prev_md) / denom
    return pd.Series(md, index=series.index)

# Patch the module for testing
import tinvest.octopus_engine
tinvest.octopus_engine.mcginley_dynamic = mcginley_dynamic_fixed

data = json.load(open('Output/history/VND.json', encoding='utf-8'))
df = pd.DataFrame({'Date': data['dates'], 'Close': data['closes']})
out = tinvest.octopus_engine.analyze_octopus(df)
print(out[['Date', 'Close', 'OCT_A1', 'OCT_BB_Top', 'OCT_BB_Bot']].tail(15))
