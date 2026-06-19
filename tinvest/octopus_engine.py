import pandas as pd
import numpy as np


def mcginley_dynamic(series, period, dates=None, gap_days=30):
    """
    McGinley Dynamic calculation.
    Formula: MD[i] = MD[i-1] + (Price[i] - MD[i-1]) / (N * (Price[i] / MD[i-1])^4)

    Parameters
    ----------
    series : pd.Series
        Close price series (must be sorted ascending).
    period : int
        McGinley period (e.g. 12 or 25).
    dates : pd.Series, optional
        Corresponding date series. When provided, if the gap between consecutive
        dates exceeds ``gap_days`` calendar days the accumulator is reset to the
        current price, preventing calculation drift caused by large data gaps
        (e.g. VND's missing history from 2018-2021).
    gap_days : int
        Number of calendar days that constitute a data gap (default 30).
    """
    md = np.zeros(len(series))
    md[0] = series.iloc[0]
    prices = series.values

    # Pre-compute date differences in days if dates are provided
    date_gaps = None
    if dates is not None:
        try:
            ts = pd.to_datetime(dates).values.astype("datetime64[D]")
            diffs = np.diff(ts).astype(int)  # gaps in calendar days
            date_gaps = diffs  # length = len(series)-1
        except Exception:
            date_gaps = None

    for i in range(1, len(series)):
        # Reset accumulator when there is a large data gap
        if date_gaps is not None and date_gaps[i - 1] > gap_days:
            md[i] = prices[i]
            continue

        prev_md = md[i - 1]
        if prev_md <= 0:
            md[i] = prices[i]
            continue

        ratio = prices[i] / prev_md
        # Clamp ratio to prevent extreme denominator values
        ratio = min(max(ratio, 0.5), 2.0)

        denom = period * (ratio ** 4)
        if denom < 0.01:
            # Fallback to simple EMA step to avoid division by near-zero
            md[i] = prev_md + (prices[i] - prev_md) / period
        else:
            md[i] = prev_md + (prices[i] - prev_md) / denom

    return pd.Series(md, index=series.index)


def analyze_octopus(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implements Rule Octopus (MACD Band with McGinley Dynamic)
    AFL conversion:
    A1 = MCGin(C, 12) - MCGin(C, 25)
    B1 = MCGin(C, 25) - MCGin(C, 12)
    BBands on A1 (20, 1)
    """
    df = df.copy()

    # Use Date column for gap detection if available
    dates = df['Date'] if 'Date' in df.columns else None

    # 1. McGinley Dynamic averages (with gap-aware reset)
    mc12 = mcginley_dynamic(df['Close'], 12, dates=dates)
    mc25 = mcginley_dynamic(df['Close'], 25, dates=dates)

    # 2. MACD values
    df['OCT_A1'] = mc12 - mc25
    df['OCT_B1'] = mc25 - mc12

    # 3. Bollinger Bands on A1
    periods = 20
    width = 1
    df['OCT_BB_Mid'] = df['OCT_A1'].rolling(window=periods).mean()
    df['OCT_BB_Std'] = df['OCT_A1'].rolling(window=periods).std()
    df['OCT_BB_Top'] = df['OCT_BB_Mid'] + (width * df['OCT_BB_Std'])
    df['OCT_BB_Bot'] = df['OCT_BB_Mid'] - (width * df['OCT_BB_Std'])

    # 4. Color Logic
    # Color=IIf(a1<0 AND a1>Ref(a1,-1), colorGreen,
    #           IIf(a1>0 AND a1>Ref(a1,-1), colorBrightGreen,
    #               IIf(a1>0 AND a1<Ref(a1,-1), colorCustom12, colorRed)));
    a1 = df['OCT_A1']
    a1_prev = a1.shift(1)

    conditions = [
        (a1 < 0) & (a1 > a1_prev),
        (a1 > 0) & (a1 > a1_prev),
        (a1 > 0) & (a1 < a1_prev),
        (a1 < 0) & (a1 <= a1_prev)
    ]
    # Green, BrightGreen, Pink, Red
    choices = ['#008000', '#00FF00', '#FF69B4', '#FF0000']
    df['OCT_Color'] = np.select(conditions, choices, default='#808080')

    return df
