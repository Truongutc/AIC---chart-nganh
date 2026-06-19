"""
Module 1 – Data Loader
======================
Reads OHLCV CSV files, normalizes columns, and returns clean DataFrames.
Supports single-ticker and multi-ticker CSV files.
"""

import logging
import numpy as np
import pandas as pd
from pathlib import Path


logger = logging.getLogger(__name__)


# ── Centralized Enrichment ─────────────────────────────────────────────────────

def _donchian_mid(series_high: pd.Series, series_low: pd.Series, period: int) -> pd.Series:
    """(highest_high + lowest_low) / 2 over rolling window."""
    return (series_high.rolling(window=period).max() + series_low.rolling(window=period).min()) / 2


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches an OHLCV DataFrame with ALL technical indicators.
    Ensures SSoT by re-calculating all indicators to prevent data drift.
    """
    if '_ENRICHED' in df.columns and not df['_ENRICHED'].isna().any():
        return df

    if len(df) < 2:
        return df

    # Incremental calculation logic
    if '_ENRICHED' in df.columns and df['_ENRICHED'].isna().any():
        first_nan_idx = df['_ENRICHED'].isna().idxmax()
        if first_nan_idx > 260:
            warmup_idx = max(0, first_nan_idx - 260)
            df_slice = df.iloc[warmup_idx:].copy()
            # Drop old indicators to compute fresh
            df_slice = df_slice[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            if 'source' in df.columns: df_slice['source'] = df.iloc[warmup_idx:]['source']
            if 'updated_at' in df.columns: df_slice['updated_at'] = df.iloc[warmup_idx:]['updated_at']
            
            df_slice_enriched = enrich_dataframe(df_slice)
            
            # Extract new rows
            new_enriched = df_slice_enriched.iloc[first_nan_idx - warmup_idx:].copy()
            new_enriched.index = new_enriched.index + warmup_idx
            
            out = df.copy().reset_index(drop=True)
            for col in new_enriched.columns:
                if col not in out.columns:
                    out[col] = np.nan
                out.loc[new_enriched.index, col] = new_enriched[col]
            return out

    out = df.copy().reset_index(drop=True) 

    # ── 1. Moving Averages ─────────────────────────────────────────────────
    for period, name in [(10, 'MA10'), (20, 'MA20'), (50, 'MA50'), (100, 'MA100'), (200, 'MA200')]:
        out[name] = out['Close'].rolling(period).mean()

    # Slope of MA200: MA200 > Ref(MA200,-1) and (MA200 - Ref(MA200,-20))/Ref(MA200,-20) > 0
    cond1 = out['MA200'] > out['MA200'].shift(1)
    cond2 = (out['MA200'] - out['MA200'].shift(20)) / (out['MA200'].shift(20) + 1e-10) > 0
    out['SlopeMA200'] = (cond1 & cond2).astype(int)

    # ── 2. ATR indicators ───────────────────────────────────────────────────
    high_low = out['High'] - out['Low']
    high_prev_close = (out['High'] - out['Close'].shift(1)).abs()
    low_prev_close = (out['Low'] - out['Close'].shift(1)).abs()
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    out['ATR14'] = tr.rolling(14).mean()
    out['ATR10'] = tr.rolling(10).mean()
    out['ATR30'] = tr.rolling(30).mean()

    # ── 3. Volume ──────────────────────────────────────────────────────────
    out['AvgVolume10'] = out['Volume'].rolling(10).mean()
    out['AvgVolume20'] = out['Volume'].rolling(20).mean()
    out['AvgVolume60'] = out['Volume'].rolling(60).mean()

    # ── 3b. 52-Week High and Low ───────────────────────────────────────────
    out['High52'] = out['High'].rolling(260, min_periods=1).max()
    out['Low52'] = out['Low'].rolling(260, min_periods=1).min()

    # ── 4. Ichimoku Cloud ──────────────────────────────────────────────────
    for period, name in [(9, 'Tenkan'), (26, 'Kijun'), (65, 'Kijun65'), (52, 'SpanB_raw')]:
        target_name = name if name != 'SpanB_raw' else 'SpanB'
        res = (out['High'].rolling(period).max() + out['Low'].rolling(period).min()) / 2
        if name == 'SpanB_raw':
            res = res.shift(26)
        out[target_name] = res

    out['SpanA'] = ((out['Tenkan'] + out['Kijun']) / 2).shift(26)
    out['Chikou'] = out['Close'].shift(-26)
    out['CloudTop'] = out[['SpanA', 'SpanB']].max(axis=1)
    out['CloudBottom'] = out[['SpanA', 'SpanB']].min(axis=1)

    # ── 5. Heikin Ashi ─────────────────────────────────────────────────────
    # HA is a chain - must compute from start to ensure integrity
    ha_close = (out['Open'] + out['High'] + out['Low'] + out['Close']) / 4
    ha_close_shifted = ha_close.shift(1).fillna((out['Open'].iloc[0] + out['Close'].iloc[0]) / 2)
    ha_open = ha_close_shifted.ewm(alpha=0.5, adjust=False).mean()
        
    out['HA_Open'] = ha_open
    out['HA_Close'] = ha_close
    out['HA_Color'] = np.where(ha_close > ha_open, 'Green', 'Red')

    # ── 6. RSI (Relative Strength Index) ──────────────────────────────────
    delta = out['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # Use Wilder's smoothing/EWM
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10)
    out['RSI'] = 100 - (100 / (1 + rs))

    # ── 7. MACD (Moving Average Convergence Divergence) ───────────────────
    ema12 = out['Close'].ewm(span=12, adjust=False).mean()
    ema26 = out['Close'].ewm(span=26, adjust=False).mean()
    out['MACD'] = ema12 - ema26
    out['MACD_Signal'] = out['MACD'].ewm(span=9, adjust=False).mean()
    out['MACD_Hist'] = out['MACD'] - out['MACD_Signal']
    
    # ── 8. ADX (Average Directional Index) - PineScript Implementation ─────
    period = 14
    up = out['High'].diff()
    down = -out['Low'].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    
    tr1 = out['High'] - out['Low']
    tr2 = (out['High'] - out['Close'].shift(1)).abs()
    tr3 = (out['Low'] - out['Close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # PineScript RMA = ewm(alpha=1/period)
    alpha = 1.0 / period
    tr_rma = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=alpha, adjust=False).mean() / tr_rma)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=alpha, adjust=False).mean() / tr_rma)
    
    sum_di = plus_di + minus_di
    sum_di_safe = np.where(sum_di == 0, 1, sum_di)
    dx = 100 * (plus_di - minus_di).abs() / sum_di_safe
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    
    out['ADX'] = adx
    out['DI_Plus'] = plus_di
    out['DI_Minus'] = minus_di
    
    # Calculate ADX Color State
    adx_up = adx > adx.shift(1)
    di_up = plus_di >= minus_di
    hl_range = adx <= 20
    
    conditions = [
        hl_range,
        (~hl_range) & adx_up & di_up,
        (~hl_range) & (~adx_up) & di_up,
        (~hl_range) & di_up == False
    ]
    choices = ['ORANGE', 'WHITE', 'GREEN', 'RED']
    out['ADX_Color'] = np.select(conditions, choices, default='ORANGE')

    # ── 9. Pivot (Swing) Points (Fractal n=2 Strict) ────────────────────
    # Identify true Swing Highs / Lows matching exactly specific condition
    highs = out['High']
    lows = out['Low']
    
    is_swing_high = (highs > highs.shift(1)) & (highs > highs.shift(2)) & (highs > highs.shift(-1)) & (highs > highs.shift(-2))
    out['SwingHigh'] = np.where(is_swing_high, highs, 0)
    
    is_swing_low = (lows < lows.shift(1)) & (lows < lows.shift(2)) & (lows < lows.shift(-1)) & (lows < lows.shift(-2))
    out['SwingLow'] = np.where(is_swing_low, lows, 0)

    # ── 10. AIC Professional Indicators ──────────────────────────────────────
    # ATR Slope over 5 days to measure price compression (Nén nền)
    out['ATR14_Slope'] = out['ATR14'].diff(5)
    
    # Distance from MA20 (Độ rướn)
    out['Dist_MA20'] = (out['Close'] - out['MA20']) / out['MA20']
    
    # Count green candles in last 3 days (Quá nhiệt)
    is_green = (out['Close'] > out['Open']).astype(int)
    out['Green_Count_3'] = is_green.rolling(3).sum()

    # ── 11. VSA Helpers ─────────────────────────────────────────────────────
    out['Spread'] = out['High'] - out['Low']
    out['Avg_Spread_20'] = out['Spread'].rolling(20).mean()
    
    out['Stopping_Vol'] = (out['Volume'] > 1.5 * out['AvgVolume20']) & \
                          (out['Spread'] > out['Avg_Spread_20']) & \
                          (out['Close'] > out['Low'] + 0.3 * out['Spread'])
    
    out['No_Supply'] = (out['Volume'] < 0.7 * out['AvgVolume20']) & \
                       (out['Spread'] < out['Avg_Spread_20']) & \
                       (out['Close'] < out['Open'])
    
    out['Test_Supply'] = (out['Volume'] < out['AvgVolume20']) & \
                         (out['Spread'] < out['Avg_Spread_20'] * 0.8) & \
                         (out['Close'] > out['Low'] + 0.4 * out['Spread'])

    # ── 12. Heatmap Engine (AFL Logic Confluence) ──────────────────────────
    try:
        from .heatmap_engine import calculate_heatmap_matrix
        hm_df = calculate_heatmap_matrix(out)
        # Prefix with HM_ to avoid conflicts and identify clearly in cache
        for col in hm_df.columns:
            out[f"HM_{col}"] = hm_df[col].values
    except Exception as e:
        logger.error(f"Error enriching with Heatmap signals: {e}")


    # ── 14. Heikin Ashi Engine (Trailing Stop & Smoothed HA) ───────────────
    try:
        from .heikin_engine import analyze_heikin
        out = analyze_heikin(out)
    except Exception as e:
        logger.error(f"Error enriching with Heikin signals: {e}")

    # ── 15. MCDX Engine (Retailer, Hot Money, Banker) ─────────────────────────
    try:
        from .mcdx_engine import calculate_mcdx
        mcdx_df = calculate_mcdx(out)
        for col in mcdx_df.columns:
            out[col] = mcdx_df[col].values
    except Exception as e:
        logger.error(f"Error enriching with MCDX signals: {e}")

    # ── 16. GreenPink Engine (HHV-LLV Scalper) ─────────────────────────────
    try:
        from .greenpink_engine import analyze_greenpink
        out = analyze_greenpink(out)
    except Exception as e:
        logger.error(f"Error enriching with GreenPink signals: {e}")

    # ── 17. Octopus Engine (McGinley MACD) ─────────────────────────────────
    try:
        from .octopus_engine import analyze_octopus
        out = analyze_octopus(out)
    except Exception as e:
        logger.error(f"Error enriching with Octopus signals: {e}")

    out['_ENRICHED'] = 1
    return out

# ── Column name aliases accepted in input CSV ──────────────────────────────────
_COLUMN_ALIASES = {
    # CSV column from Amibroker/MetaStock: <DTYYYYMMDD>, <DATE>, etc.
    "date":   ["date", "time", "datetime", "ngay", "ngày", "trading_date",
               "dtyyyymmdd", "dtyyyymm", "date_time", "dtdate"],
    "open":   ["open", "mo_cua", "mở_cửa", "open_price"],
    "high":   ["high", "cao_nhat", "cao_nhất", "high_price"],
    "low":    ["low", "thap_nhat", "thấp_nhất", "low_price"],
    "close":  ["close", "dong_cua", "đóng_cửa", "close_price", "last"],
    "volume": ["volume", "vol", "klgd", "khoi_luong", "klgd_cp"],
    # Amibroker exports the ticker as <Ticker>, normalized to 'ticker'
    "ticker": ["ticker", "symbol", "ma_ck", "mã_ck", "stock", "code", "name"],
}

MIN_ROWS = 200


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw CSV column names to canonical names (Date, Open, High, Low, Close, Volume, Ticker)."""
    lower_cols = {c: c.lower().strip().replace(" ", "_").replace("<", "").replace(">", "") for c in df.columns}
    df = df.rename(columns=lower_cols)

    rename_map = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for col in df.columns:
            if col in aliases:
                rename_map[col] = canonical.capitalize() if canonical != "ticker" else "Ticker"
                break

    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}. Found: {list(df.columns)}")

    return df


def _clean_dataframe(df: pd.DataFrame, ticker: str = "", min_rows: int = 1) -> pd.DataFrame:
    """Parse dates, sort, deduplicate, handle missing data, validate row count."""
    # Parse Date
    try:
        # Convert to string and clean up potential float strings (e.g. "20231026.0")
        # This handles the case where CSV stores YYYYMMDD as int64 (e.g. 20260528)
        date_series = df["Date"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        parsed = pd.Series(pd.NaT, index=df.index)
        
        # Parse 8-digit YYYYMMDD values
        mask_8d = date_series.str.match(r"^\d{8}$") == True
        if mask_8d.any():
            parsed[mask_8d] = pd.to_datetime(date_series[mask_8d], format="%Y%m%d", errors="coerce")
            
        # Parse other valid date formats
        mask_other = ~mask_8d & (date_series.notna()) & (date_series != "") & (date_series.str.lower() != "nan")
        if mask_other.any():
            parsed[mask_other] = pd.to_datetime(date_series[mask_other], format='mixed', dayfirst=False, errors="coerce")

        df["Date"] = parsed

        if df["Date"].isna().any():
            n_bad = df["Date"].isna().sum()
            logger.warning(f"[{ticker}] {n_bad} unparseable date row(s) dropped.")
            df = df.dropna(subset=["Date"])

        if df.empty:
            raise ValueError(f"[{ticker}] All date values were invalid.")

    except Exception as exc:
        raise ValueError(f"[{ticker}] Cannot parse Date column: {exc}") from exc

    # Sort ascending
    df = df.sort_values("Date").reset_index(drop=True)

    # ── Deduplicate by Date (keep last row per date = most recent CSV update) ──
    dup_count = df.duplicated(subset=["Date"]).sum()
    if dup_count > 0:
        logger.warning(f"[{ticker}] Removing {dup_count} duplicate date row(s).")
        df = df.drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

    # Drop rows where ALL price columns are NaN
    price_cols = ["Open", "High", "Low", "Close", "Volume"]
    df = df.dropna(subset=price_cols, how="all")

    # Forward-fill remaining NaN (e.g. sparse volume)
    df[price_cols] = df[price_cols].ffill()

    # Ensure numeric types
    for col in price_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows that still have NaN after ffill (e.g. leading rows)
    df = df.dropna(subset=price_cols).reset_index(drop=True)

    # Minimum row check
    if len(df) < min_rows:
        raise ValueError(
            f"[{ticker}] Insufficient data: {len(df)} rows found, minimum required is {min_rows}."
        )

    logger.info(f"[{ticker}] Loaded {len(df)} rows from {df['Date'].iloc[0].date()} to {df['Date'].iloc[-1].date()}")
    return df


def load_data(file_path: "str | list[str]") -> "pd.DataFrame | dict[str, pd.DataFrame]":
    """
    Load OHLCV CSV file(s) and return a clean DataFrame or dict of DataFrames.

    Parameters
    ----------
    file_path : str | list[str]
        Path or list of paths to the CSV file(s) containing OHLCV data.

    Returns
    -------
    pd.DataFrame
        If the CSV contains a single ticker (no 'Ticker' column or only one unique ticker).
    dict[str, pd.DataFrame]
        If the CSV contains multiple tickers keyed by ticker symbol.
    """
    try:
        if isinstance(file_path, list):
            logger.info(f"Loading data from {len(file_path)} files")
            dfs = []
            for path in file_path:
                p = Path(path)
                if p.exists() and p.suffix.lower() == ".csv":
                    dfs.append(pd.read_csv(p))
            if not dfs:
                raise ValueError("No valid CSV files found in the provided list.")
            raw = pd.concat(dfs, ignore_index=True)
        else:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            if path.suffix.lower() != ".csv":
                raise ValueError(f"Expected a CSV file, got: {path.suffix}")
            logger.info(f"Loading data from: {file_path}")
            raw = pd.read_csv(file_path)
            
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to read CSV(s): {exc}") from exc

    if raw.empty:
        raise ValueError("Loaded CSV data is empty.")

    df = _normalize_columns(raw)

    # ── Multi-ticker handling ──────────────────────────────────────────────────
    if "Ticker" in df.columns:
        tickers = df["Ticker"].dropna().unique()
        if len(tickers) == 1:
            ticker = str(tickers[0]).upper()
            single = df[df["Ticker"] == tickers[0]].copy().drop(columns=["Ticker"])
            return _clean_dataframe(single, ticker=ticker, min_rows=MIN_ROWS)

        result = {}
        errors = []
        for ticker_val in tickers:
            ticker = str(ticker_val).upper()
            
            is_index = ("VNINDEX" in ticker) or ("HNX" in ticker) or ("HAINDEX" in ticker)
            if not (len(ticker) == 3 and ticker.isalnum()) and not is_index:
                continue
                
            sub = df[df["Ticker"] == ticker_val].copy().drop(columns=["Ticker"])
            try:
                result[ticker] = _clean_dataframe(sub, ticker=ticker, min_rows=MIN_ROWS)
            except ValueError as e:
                errors.append(str(e))
                logger.debug(f"Skipping ticker {ticker}: {e}")

        if not result:
            raise ValueError(f"No valid tickers loaded. Errors:\n" + "\n".join(errors))

        if errors:
            logger.warning(f"{len(errors)} ticker(s) skipped due to validation errors.")

        logger.info(f"Loaded {len(result)} tickers: {sorted(result.keys())}")
        return result

    # ── Single-ticker (no Ticker column) ──────────────────────────────────────
    return _clean_dataframe(df, ticker="SINGLE", min_rows=MIN_ROWS)
