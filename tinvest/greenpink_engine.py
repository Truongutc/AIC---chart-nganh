import pandas as pd
import numpy as np

def analyze_greenpink(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implements HHV-LLV-Scalper (Rule GreenPink)
    AFL conversion:
    E14 = MA(C, 14)
    E21 = MA(C, 21)
    xFast = LLV(Ref((H+L)/2, -1), 5)
    xSlow = LLV(Ref((H+L)/2, -1), 14)
    BBands on xSlow (15, 2)
    """
    df = df.copy()
    
    # 1. Moving Averages
    df['GP_E14'] = df['Close'].rolling(window=14).mean()
    df['GP_E21'] = df['Close'].rolling(window=21).mean()
    
    # 2. Median Price and Refs
    median_price = (df['High'] + df['Low']) / 2
    # xFast = LLV(Ref(median, -1), 5)
    df['GP_xFast'] = median_price.shift(1).rolling(window=5).min()
    # xSlow = LLV(Ref(median, -1), 14)
    df['GP_xSlow'] = median_price.shift(1).rolling(window=14).min()
    
    # 3. Bollinger Bands on xSlow
    periods = 15
    width = 2
    df['GP_BB_Mid'] = df['GP_xSlow'].rolling(window=periods).mean()
    df['GP_BB_Std'] = df['GP_xSlow'].rolling(window=periods).std()
    df['GP_BB_Top'] = df['GP_BB_Mid'] + (width * df['GP_BB_Std'])
    df['GP_BB_Bot'] = df['GP_BB_Mid'] - (width * df['GP_BB_Std'])
    
    # 4. Color logic for Cloud
    # brightGreen if C > e14 AND C > e21, else pink/red
    df['GP_Cloud_Color'] = np.where((df['Close'] > df['GP_E14']) & (df['Close'] > df['GP_E21']), 'brightGreen', 'pink')
    
    return df
