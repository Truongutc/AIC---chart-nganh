"""


AIC code = AI + cơm! Desktop App


Giao diện người dùng cho hệ thống phân tích AIC code = AI + cơm!


"""


import tkinter as tk
import logging
import numpy as np
logger = logging.getLogger(__name__)

class GuiLogHandler(logging.Handler):
    """Custom logging handler to redirect logs to the TinvestApp text_output."""
    def __init__(self, log_func):
        super().__init__()
        self.log_func = log_func
    def emit(self, record):
        msg = self.format(record)
        self.log_func(msg)


from tkinter import filedialog, messagebox


from tinvest.data_loader import _normalize_columns, _clean_dataframe


from tinvest.analyzer import analyze_stock, format_report, evaluate_heatmap


import os


import pandas as pd


import threading


from pathlib import Path


from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed


from tinvest.storage_manager import StorageManager


from tinvest.vietstock_client import VietstockClient


from tinvest.config_manager import ConfigManager


import tkinter.simpledialog as simpledialog


from tkinter import scrolledtext


from datetime import datetime, timedelta


from tinvest.data_loader import enrich_dataframe


from tinvest.ichimoku_engine import analyze_ichimoku


from tinvest.vsa_engine import analyze_vsa


from tinvest.advanced_entry import classify_entry


from tinvest.accumulation_engine import analyze_accumulation, check_breakout_accumulation


from tinvest.ma_engine import analyze_ma_trend


from tinvest.valuation_engine import evaluate_stock_valuation
import sys
import os
import matplotlib
try:
    matplotlib.use('TkAgg') # Force TkAgg for compatibility with Tkinter and PyInstaller
except ImportError:
    matplotlib.use('Agg') # Fallback to Agg for headless mode (e.g. GitHub Actions)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.image as mpimg
import matplotlib.lines as mlines
import matplotlib.ticker as ticker_lib
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)





# --- GLOBAL WORKER FOR MULTIPROCESSING ---


def analyze_ticker_worker(ticker_df_tuple):


    """


    Hàm worker hỗ trợ ThreadPoolExecutor.


    Các import phải nằm ngoài để tránh Deadlock do Import Lock của Python.


    """


    ticker, df_sub = ticker_df_tuple


    try:


        # 1. Enrich data 1 lần duy nhất (MA, ATR, Ichimoku, HA, VSA helpers)


        df_rich = enrich_dataframe(df_sub.copy())


        


        # 2. Call engines — tất cả đều đọc columns đã có sẵn, không tính lại


        ichi = analyze_ichimoku(df_rich)


        vsa = analyze_vsa(df_rich)


        adv = classify_entry(df_rich)


        accum = analyze_accumulation(df_rich)


        ma_trend = analyze_ma_trend(df_rich)


        val = evaluate_stock_valuation(ticker, df_rich, adv)


        




        # Lưu df_rich (đã enrich) thay vì df raw để tái sử dụng cho breadth, scanner


        from tinvest.state_engine import evaluate_state_rules
        state_rules = evaluate_state_rules(df_rich)
        
        # Pre-compute VSA and MCDX so export_web_json can read from cache (no re-compute)
        from tinvest.vsa_engine import analyze_vsa as _vsa_fn
        from tinvest.mcdx_engine import evaluate_mcdx_rules as _mcdx_fn
        vsa_res_cached = _vsa_fn(df_rich)
        mcdx_eval_cached = _mcdx_fn(df_rich)

        # Pre-calculate What-If data to cache it for custom rules and export
        ticker_upper = str(ticker).upper()
        avg_vol_10 = 0.0
        if 'Volume' in df_rich.columns:
            avg_vol_10 = float(df_rich['Volume'].tail(10).mean())
        is_index = ticker_upper in {"VNINDEX", "HNX-INDEX", "UPCOM-INDEX", "VN30", "HNX30"} or ("INDEX" in ticker_upper) or ("VN30" in ticker_upper) or ("HNX" in ticker_upper)
        
        whatif_data = None
        ev10 = 0.0
        ma3_ev10_pct = 0.0
        if is_index or avg_vol_10 >= 100000:
            try:
                from tinvest.whatif_engine import run_whatif_analysis
                cached_fs = None
                try:
                    from tinvest.storage_manager import StorageManager
                    sm = StorageManager()
                    old_analysis = sm.load_latest_analysis(ticker)
                    if old_analysis and 'whatif' in old_analysis and isinstance(old_analysis['whatif'], dict):
                        cached_fs = old_analysis['whatif'].get('forecast_series', [])
                except Exception:
                    pass
                # Tối ưu hóa: Dùng cache
                whatif_data = run_whatif_analysis(ticker, df_rich, compute_forecast_series=True, forecast_days=60, cached_forecast_series=cached_fs)
                if whatif_data and not whatif_data.get('error'):
                    dist = whatif_data.get('distribution', {})
                    if dist:
                        ev10 = dist.get('future_10', {}).get('mean', 0.0) or 0.0
                    fs = whatif_data.get('forecast_series', [])
                    close_val = float(df_rich['Close'].iloc[-1]) if len(df_rich) > 0 else 0.0
                    if fs and close_val > 0:
                        ev10_ma3_vals = [x.get('ev10_ma3', x.get('ev10', 0.0)) for x in fs[-3:] if x]
                        if ev10_ma3_vals:
                            avg_price = sum(ev10_ma3_vals) / len(ev10_ma3_vals)
                            ma3_ev10_pct = (avg_price / close_val - 1) * 100
            except Exception:
                pass

        # Ghi cache vào df.attrs (chuẩn pandas, không gây UserWarning)
        df_rich.attrs['_whatif_ev'] = (ev10, 0.0)
        df_rich.attrs['_whatif_ev_ma3'] = ma3_ev10_pct

        return ticker, {
            "df": df_rich,
            "ichi": ichi,
            "vsa": vsa,
            "vsa_cached": vsa_res_cached,
            "mcdx_eval_cached": mcdx_eval_cached,
            "adv": adv,
            "accum": accum,
            "ma_trend": ma_trend,
            "valuation": val,
            "state_rules": state_rules,
            "whatif": whatif_data
        }


    except Exception:


        return ticker, None





def analyze_batch_worker(batch):
    """Xử lý một nhóm (batch) mã cổ phiếu trong một tiến trình duy nhất."""
    results = []
    for item in batch:
        results.append(analyze_ticker_worker(item))
    return results

def load_cache_worker(args):
    """
    Worker for ThreadPoolExecutor to load data from disk.
    Args: (ticker, storage_instance)
    """
    ticker, storage = args
    try:
        df = storage.load_ticker_data(ticker)
        if df is not None:
            analysis = storage.load_latest_analysis(ticker)
            if analysis:
                analysis['df'] = df
            return ticker, df, analysis
    except Exception:
        pass
    return ticker, None, None
# ==============================================================================
# CENTRALIZED CUSTOM FILTER RULES (RULE_FILTER)
# ==============================================================================
def check_accumulation_breakout(df):
    """
    Sideways for 30 trading days with max-min range <= 15%,
    then breaks out of that range in the last 0-2 sessions (index -1, -2, or -3).
    """
    if 'High' not in df.columns or 'Low' not in df.columns or 'Close' not in df.columns or len(df) < 31:
        return False
    
    # Check if breakout occurred at session t (where t is -1, -2, or -3)
    for t in [-1, -2, -3]:
        idx_start = len(df) + t - 30
        idx_end = len(df) + t
        if idx_start < 0:
            continue
        
        sub_high = df['High'].iloc[idx_start:idx_end].max()
        sub_low = df['Low'].iloc[idx_start:idx_end].min()
        if sub_low <= 0:
            continue
        
        # Max-Min range <= 15%
        if (sub_high - sub_low) / sub_low <= 0.15:
            # Close at session t exceeds the max high of the consolidation range
            if df['Close'].iloc[t] > sub_high:
                return True
    return False


def check_mark_minervini(df):
    """
    Mark Minervini Filter criteria.
    """
    required_cols = ['Close', 'MA50', 'MA100', 'MA200', 'High52', 'Low52', 'AvgVolume10', 'AvgVolume20', 'AvgVolume60', 'SlopeMA200', 'ATR10', 'ATR30']
    if not all(col in df.columns for col in required_cols) or len(df) < 2:
        return False
    try:
        return (
            df['Close'].iloc[-1] > df['MA50'].iloc[-1] > df['MA100'].iloc[-1] > df['MA200'].iloc[-1] and
            df['Close'].iloc[-1] > 0.85 * df['High52'].iloc[-1] and
            df['Close'].iloc[-1] >= 1.3 * df['Low52'].iloc[-1] and
            df['AvgVolume20'].iloc[-1] > df['AvgVolume60'].iloc[-1] and
            df['AvgVolume10'].iloc[-1] < 0.9 * df['AvgVolume20'].iloc[-1] and
            df['SlopeMA200'].iloc[-1] > 0 and
            df['ATR10'].iloc[-1] < df['ATR30'].iloc[-1]
        )
    except Exception:
        return False


def check_rsi_bullish_divergence(df):
    """
    RSI Bullish Divergence check:
    - price2 < price1 and rsi2 > rsi1 and idx2 - idx1 >= 5 and rsi1 < 40 and (rsi2 - rsi1) > 5 and (price1 - price2)/price1 > 0.02
    - Confirm the pivot low using right=3.
    - Signal must be recent (idx2 >= len(df) - 10) and support not broken (min Low since idx2 >= price2).
    - Current close must be above the bottom low (Close[-1] > price2).
    """
    if 'Low' not in df.columns or 'RSI' not in df.columns or 'Close' not in df.columns or len(df) < 20:
        return False

    def pivot_low(series, left=3, right=3):
        pivots = []
        vals = series.values
        n = len(vals)
        for i in range(left, n - right):
            is_pivot = True
            for j in range(1, left + 1):
                if vals[i] >= vals[i - j]:
                    is_pivot = False
                    break
            if not is_pivot:
                continue
            for j in range(1, right + 1):
                if vals[i] >= vals[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append(i)
        return pivots

    pivots = pivot_low(df['Low'])
    if len(pivots) < 2:
        return False

    # Scan backwards to find the most recent divergence
    for i in range(len(pivots) - 1, 0, -1):
        idx1 = pivots[i - 1]
        idx2 = pivots[i]

        price1 = float(df['Low'].iloc[idx1])
        price2 = float(df['Low'].iloc[idx2])

        rsi1 = float(df['RSI'].iloc[idx1])
        rsi2 = float(df['RSI'].iloc[idx2])

        if (
            price2 < price1 and
            rsi2 > rsi1 and
            idx2 - idx1 >= 5 and
            rsi1 < 40 and
            (rsi2 - rsi1) > 5 and
            (price1 - price2) / price1 > 0.02
        ):
            # Recency: pivot low index must be within last 10 bars
            if len(df) - 1 - idx2 <= 10:
                current_close = float(df['Close'].iloc[-1])
                if current_close > price2:
                    # Check that the support at price2 has not been broken since idx2
                    if float(df['Low'].iloc[idx2:].min()) >= price2:
                        return True
    return False


def check_macd_bullish_divergence(df):
    """
    MACD Bullish Divergence check:
    - price2 < price1 and macd2 > macd1 and macd1 < 0 and macd2 < 0 and idx2 - idx1 >= 5 and (price1 - price2)/price1 > 0.02
    - Confirm the pivot low using right=3.
    - Signal must be recent (idx2 >= len(df) - 10) and support not broken (min Low since idx2 >= price2).
    - Current close must be above the bottom low (Close[-1] > price2).
    """
    if 'Low' not in df.columns or 'MACD' not in df.columns or 'Close' not in df.columns or len(df) < 20:
        return False

    def pivot_low(series, left=3, right=3):
        pivots = []
        vals = series.values
        n = len(vals)
        for i in range(left, n - right):
            is_pivot = True
            for j in range(1, left + 1):
                if vals[i] >= vals[i - j]:
                    is_pivot = False
                    break
            if not is_pivot:
                continue
            for j in range(1, right + 1):
                if vals[i] >= vals[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append(i)
        return pivots

    pivots = pivot_low(df['Low'])
    if len(pivots) < 2:
        return False

    # Scan backwards to find the most recent divergence
    for i in range(len(pivots) - 1, 0, -1):
        idx1 = pivots[i - 1]
        idx2 = pivots[i]

        price1 = float(df['Low'].iloc[idx1])
        price2 = float(df['Low'].iloc[idx2])

        macd1 = float(df['MACD'].iloc[idx1])
        macd2 = float(df['MACD'].iloc[idx2])

        if (
            price2 < price1 and
            macd2 > macd1 and
            macd1 < 0 and
            macd2 < 0 and
            idx2 - idx1 >= 5 and
            (price1 - price2) / price1 > 0.02
        ):
            # Recency: pivot low index must be within last 10 bars
            if len(df) - 1 - idx2 <= 10:
                current_close = float(df['Close'].iloc[-1])
                if current_close > price2:
                    # Check that the support at price2 has not been broken since idx2
                    if float(df['Low'].iloc[idx2:].min()) >= price2:
                        return True
    return False


def check_macd_hist_bullish_divergence(df):
    """
    MACD Histogram Bullish Divergence check:
    - price2 < price1 and hist2 > hist1 and hist1 < 0 and hist2 < 0 and abs(hist2) < abs(hist1)
    - Confirm the pivot low using right=3.
    - Signal must be recent (idx2 >= len(df) - 10) and support not broken (min Low since idx2 >= price2).
    - Current close must be above the bottom low (Close[-1] > price2).
    """
    hist_col = 'MACD_Hist' if 'MACD_Hist' in df.columns else 'Hist'
    if 'Low' not in df.columns or hist_col not in df.columns or 'Close' not in df.columns or len(df) < 20:
        return False

    def pivot_low(series, left=3, right=3):
        pivots = []
        vals = series.values
        n = len(vals)
        for i in range(left, n - right):
            is_pivot = True
            for j in range(1, left + 1):
                if vals[i] >= vals[i - j]:
                    is_pivot = False
                    break
            if not is_pivot:
                continue
            for j in range(1, right + 1):
                if vals[i] >= vals[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append(i)
        return pivots

    pivots = pivot_low(df['Low'])
    if len(pivots) < 2:
        return False

    # Scan backwards to find the most recent divergence
    for i in range(len(pivots) - 1, 0, -1):
        idx1 = pivots[i - 1]
        idx2 = pivots[i]

        price1 = float(df['Low'].iloc[idx1])
        price2 = float(df['Low'].iloc[idx2])

        hist1 = float(df[hist_col].iloc[idx1])
        hist2 = float(df[hist_col].iloc[idx2])

        if (
            price2 < price1 and
            hist2 > hist1 and
            hist1 < 0 and
            hist2 < 0 and
            abs(hist2) < abs(hist1)
        ):
            # Recency: pivot low index must be within last 10 bars
            if len(df) - 1 - idx2 <= 10:
                current_close = float(df['Close'].iloc[-1])
                if current_close > price2:
                    # Check that the support at price2 has not been broken since idx2
                    if float(df['Low'].iloc[idx2:].min()) >= price2:
                        return True
    return False


def check_octopus_green_cross(df):
    """
    Octopus Green Cross:
    - Octopus crossover (OCT_A1 crosses above 0/OCT_B1) in the last 1-10 sessions.
    - Two lines are green ('#008000' or '#00FF00') and expanding (diverging).
      Since they are green/bright green and expanding, the current values are green/bright green
      and the distance between them is expanding: df['OCT_A1'].iloc[-1] > df['OCT_A1'].iloc[-2]
    """
    if 'OCT_A1' not in df.columns or 'OCT_Color' not in df.columns or len(df) < 12:
        return False
    
    # 1. Currently green/bright green
    current_color = df['OCT_Color'].iloc[-1]
    if current_color not in ['#008000', '#00FF00']:
        return False
        
    # Expanding: OCT_A1[-1] > OCT_A1[-2]
    if df['OCT_A1'].iloc[-1] <= df['OCT_A1'].iloc[-2]:
        return False
        
    # 2. Crossover in the last 1 to 10 sessions (index -1 to -10)
    # Crossover is defined as: A1 > 0 and previous A1 <= 0
    crossed = False
    for i in range(1, 11):
        if len(df) > i:
            # check crossover at session -i (i.e. between -i-1 and -i)
            if df['OCT_A1'].iloc[-i] > 0 and df['OCT_A1'].iloc[-i-1] <= 0:
                crossed = True
                break
                
    return crossed


def check_mcdx_banker_cross_5(df):
    if 'MCDX_Banker' not in df.columns or len(df) < 4:
        return False
    if df['MCDX_Banker'].iloc[-1] <= df['MCDX_Banker'].iloc[-2]:
        return False
    for i in range(1, 4):
        if df['MCDX_Banker'].iloc[-i] > 5 and df['MCDX_Banker'].iloc[-i-1] <= 5:
            return True
    return False

def check_mcdx_banker_cross_10(df):
    if 'MCDX_Banker' not in df.columns or len(df) < 4:
        return False
    if df['MCDX_Banker'].iloc[-1] <= df['MCDX_Banker'].iloc[-2]:
        return False
    for i in range(1, 4):
        if df['MCDX_Banker'].iloc[-i] > 10 and df['MCDX_Banker'].iloc[-i-1] <= 10:
            return True
    return False

def check_mcdx_ma_increasing(df):
    if 'MCDX_Banker_MA' not in df.columns or len(df) < 3:
        return False
    return (df['MCDX_Banker_MA'].iloc[-1] > df['MCDX_Banker_MA'].iloc[-2] and 
            df['MCDX_Banker_MA'].iloc[-2] > df['MCDX_Banker_MA'].iloc[-3])


def get_whatif_ev(df):
    if hasattr(df, 'attrs') and '_whatif_ev' in df.attrs:
        return df.attrs['_whatif_ev']
    ev10 = 0.0
    try:
        ticker = "UNKNOWN"
        if 'Ticker' in df.columns and len(df) > 0:
            ticker = str(df['Ticker'].iloc[-1])
        is_index = ('INDEX' in ticker.upper()) or ('VN30' in ticker.upper()) or ('HNX' in ticker.upper()) or ('UPCOM' in ticker.upper())
        avg_vol_10 = 0.0
        if 'Volume' in df.columns:
            avg_vol_10 = float(df['Volume'].tail(10).mean())
        if is_index or avg_vol_10 >= 100000:
            from tinvest.whatif_engine import run_whatif_analysis
            from tinvest.data_loader import enrich_dataframe
            df_rich = df.copy()
            if 'MA20' not in df_rich.columns or 'RSI' not in df_rich.columns or '_ENRICHED' not in df_rich.columns:
                df_rich = enrich_dataframe(df_rich)
            wi = run_whatif_analysis(ticker, df_rich, compute_forecast_series=True, forecast_days=60)
            if wi and not wi.get('error'):
                dist = wi.get('distribution', {})
                if dist:
                    ev10 = dist.get('future_10', {}).get('mean', 0.0) or 0.0
    except Exception:
        pass
    if hasattr(df, 'attrs'):
        df.attrs['_whatif_ev'] = (ev10, 0.0)
    return (ev10, 0.0)


def get_whatif_ev_ma3(df):
    """
    Tính MA3(EV10): trung bình 3 phiên cuối của ev10_ma3 từ forecast_series.
    Trả về % return so với giá hiện tại.
    """
    # Đọc từ df.attrs (chuẩn pandas)
    if '_whatif_ev_ma3' in getattr(df, 'attrs', {}):
        return df.attrs['_whatif_ev_ma3']
    
    # Fallback: tính lại (chỉ xảy ra khi df chưa qua analyze_ticker_worker)
    ma3_ev10_pct = 0.0
    try:
        ticker = "UNKNOWN"
        if 'Ticker' in df.columns and len(df) > 0:
            ticker = str(df['Ticker'].iloc[-1])
        is_index = ('INDEX' in ticker.upper()) or ('VN30' in ticker.upper()) or ('HNX' in ticker.upper()) or ('UPCOM' in ticker.upper())
        avg_vol_10 = 0.0
        if 'Volume' in df.columns:
            avg_vol_10 = float(df['Volume'].tail(10).mean())
        if is_index or avg_vol_10 >= 100000:
            from tinvest.whatif_engine import run_whatif_analysis
            from tinvest.data_loader import enrich_dataframe
            df_rich = df.copy()
            if 'MA20' not in df_rich.columns or 'RSI' not in df_rich.columns or '_ENRICHED' not in df_rich.columns:
                df_rich = enrich_dataframe(df_rich)
            wi = run_whatif_analysis(ticker, df_rich, compute_forecast_series=True, forecast_days=5)
            if wi and not wi.get('error'):
                fs = wi.get('forecast_series', [])
                if fs:
                    close = float(df_rich['Close'].iloc[-1])
                    ev10_ma3_vals = [x.get('ev10_ma3', x.get('ev10', 0.0)) for x in fs[-3:] if x]
                    if ev10_ma3_vals and close > 0:
                        avg_price = sum(ev10_ma3_vals) / len(ev10_ma3_vals)
                        ma3_ev10_pct = (avg_price / close - 1) * 100
    except Exception:
        pass
    # Ghi cache vào df.attrs để lần sau không phải tính lại
    if hasattr(df, 'attrs'):
        df.attrs['_whatif_ev_ma3'] = ma3_ev10_pct
    return ma3_ev10_pct


CUSTOM_RULES = {
    "RSI_BULLISH_DIVERGENCE": {
        "label": "RSI Phân kỳ tăng giá (Bullish Divergence)",
        "func": check_rsi_bullish_divergence
    },
    "MACD_BULLISH_DIVERGENCE": {
        "label": "MACD Phân kỳ tăng giá (Bullish Divergence)",
        "func": check_macd_bullish_divergence
    },
    "MACD_HIST_BULLISH_DIVERGENCE": {
        "label": "MACD Histogram Phân kỳ tăng giá (Bullish Divergence)",
        "func": check_macd_hist_bullish_divergence
    },
    "RS14_GT_50": {
        "label": "RS 14 Tuần > 50",
        "func": lambda df: df['RS14'].iloc[-1] > 50 if 'RS14' in df.columns and len(df) >= 1 else False
    },
    "RS52_GT_50": {
        "label": "RS 52 Tuần > 50",
        "func": lambda df: df['RS52'].iloc[-1] > 50 if 'RS52' in df.columns and len(df) >= 1 else False
    },
    "PRICE_CROSS_MA20": {
        "label": "Giá cắt lên MA20 (Hôm qua < MA20, nay > MA20)",
        "func": lambda df: (df['Close'].iloc[-1] > df['MA20'].iloc[-1] and df['Close'].iloc[-2] <= df['MA20'].iloc[-2]) if 'MA20' in df.columns and len(df) >= 2 else False
    },
    "PRICE_CROSS_MA50": {
        "label": "Giá cắt lên MA50 (Hôm qua < MA50, nay > MA50)",
        "func": lambda df: (df['Close'].iloc[-1] > df['MA50'].iloc[-1] and df['Close'].iloc[-2] <= df['MA50'].iloc[-2]) if 'MA50' in df.columns and len(df) >= 2 else False
    },
    "RSI_EXIT_OVERSOLD": {
        "label": "RSI14 thoát quá bán (Cắt lên 30)",
        "func": lambda df: (df['RSI'].iloc[-1] > 30 and df['RSI'].iloc[-2] <= 30) if 'RSI' in df.columns and len(df) >= 2 else False
    },
    "RSI_CROSS_70": {
        "label": "RSI14 cắt lên trên 70",
        "func": lambda df: (df['RSI'].iloc[-1] > 70 and df['RSI'].iloc[-2] <= 70) if 'RSI' in df.columns and len(df) >= 2 else False
    },
    "RSI_GT_50": {
        "label": "RSI14 > 50",
        "func": lambda df: df['RSI'].iloc[-1] > 50 if 'RSI' in df.columns and len(df) >= 1 else False
    },
    "PRICE_ABOVE_MA20": {
        "label": "Giá nằm trên MA20",
        "func": lambda df: df['Close'].iloc[-1] > df['MA20'].iloc[-1] if 'MA20' in df.columns and len(df) >= 1 else False
    },
    "PRICE_ABOVE_MA50": {
        "label": "Giá nằm trên MA50",
        "func": lambda df: df['Close'].iloc[-1] > df['MA50'].iloc[-1] if 'MA50' in df.columns and len(df) >= 1 else False
    },
    "MA20_GT_MA50": {
        "label": "MA20 > MA50",
        "func": lambda df: df['MA20'].iloc[-1] > df['MA50'].iloc[-1] if 'MA20' in df.columns and 'MA50' in df.columns and len(df) >= 1 else False
    },
    "MCDX_RED": {
        "label": "MCDX có màu đỏ (Banker > 0)",
        "func": lambda df: df['MCDX_Banker'].iloc[-1] > 0 if 'MCDX_Banker' in df.columns and len(df) >= 1 else False
    },
    "PRICE_ABOVE_KIJUN": {
        "label": "Giá nằm trên Kijun",
        "func": lambda df: df['Close'].iloc[-1] > df['Kijun'].iloc[-1] if 'Kijun' in df.columns and len(df) >= 1 else False
    },
    "PRICE_ABOVE_TENKAN": {
        "label": "Giá nằm trên Tenkan",
        "func": lambda df: df['Close'].iloc[-1] > df['Tenkan'].iloc[-1] if 'Tenkan' in df.columns and len(df) >= 1 else False
    },
    "MACD_CROSS_SIGNAL": {
        "label": "MACD cắt lên đường Tín hiệu (Signal)",
        "func": lambda df: (df['MACD'].iloc[-1] > df['MACD_Signal'].iloc[-1] and df['MACD'].iloc[-2] <= df['MACD_Signal'].iloc[-2]) if 'MACD' in df.columns and 'MACD_Signal' in df.columns and len(df) >= 2 else False
    },
    "MACD_ABOVE_SIGNAL": {
        "label": "MACD nằm trên đường Tín hiệu (Signal)",
        "func": lambda df: df['MACD'].iloc[-1] > df['MACD_Signal'].iloc[-1] if 'MACD' in df.columns and 'MACD_Signal' in df.columns and len(df) >= 1 else False
    },
    "WEEK_HIGH_BREAKOUT": {
        "label": "Giá vượt đỉnh 1 tuần (5 phiên)",
        "func": lambda df: df['Close'].iloc[-1] > df['High'].iloc[-6:-1].max() if 'High' in df.columns and len(df) >= 6 else False
    },
    "BREAKOUT_ACCUMULATION": {
        "label": "Vượt vùng tích lũy 1 tháng (biên độ <= 15%, breakout 0-2 phiên gần đây)",
        "func": check_accumulation_breakout
    },
    "OCTOPUS_GREEN_CROSS": {
        "label": "Octopus Green Cross (Giao cắt & chuyển xanh loe rộng)",
        "func": check_octopus_green_cross
    },
    "PRICE_GT_10": {
        "label": "Thị giá > 10 (Giá > 10,000đ)",
        "func": lambda df: df['Close'].iloc[-1] > 10 if 'Close' in df.columns and len(df) >= 1 else False
    },
    "MA3_EV10_GT_5": {
        "label": "MA3(EV10) > 5% — Kỳ vọng tương đồng trung bình 3 phiên > 5%",
        "func": lambda df: get_whatif_ev_ma3(df) > 5.0
    },
    "MCDX_CROSS_5": {
        "label": "MCDX Đỏ (Banker) tăng và cắt lên 5 (trong 3 phiên)",
        "func": check_mcdx_banker_cross_5
    },
    "MCDX_CROSS_10": {
        "label": "MCDX Đỏ (Banker) tăng và cắt lên 10 (trong 3 phiên)",
        "func": check_mcdx_banker_cross_10
    },
    "MCDX_MA_UP": {
        "label": "MCDX MA (Đường trắng) tăng liên tiếp (T > T-1 > T-2)",
        "func": check_mcdx_ma_increasing
    }
}


class TinvestApp:



    def __init__(self, root):


        self.root = root


        # Determine version name dynamically based on executable name
        version_name = "AIC PRO 2.0"
        try:
            import sys
            if getattr(sys, 'frozen', False):
                exe_name = os.path.basename(sys.executable)
                name_without_ext, _ = os.path.splitext(exe_name)
                if name_without_ext:
                    version_name = name_without_ext
        except Exception:
            pass

        self.root.title(f"AIC code = AI + cơm! - Hệ thống Phân tích Chứng khoán | Contact Zalo - 0988.94.84.67 | {version_name}")


        self.root.geometry("850x650")
        
        # Set Window Icon
        try:
            import sys
            if hasattr(sys, '_MEIPASS'):
                # When running as bundled exe, look in _MEIPASS
                icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
            else:
                # When running as script, look in current dir
                app_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(app_dir, "app_icon.ico")
                
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")


        


        self.data_dict = {}


        self.analysis_cache = {} # Lưu kêt quả tính toán sẵn để tránh delay


        


        # Initialize Storage and API


        self.config_mgr = ConfigManager()


        self.storage = StorageManager()


        self.vs_client = VietstockClient()


        


        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except:
            pass
        self.root.quit()
        self.root.destroy()

        # NOTE: Auto-load on startup disabled as per request.


        # Use the "📂 Load Dữ liệu Cũ" button instead.





    def _build_ui(self):


        # --- Top Frame: Dashboard Controls ---


        frame_top = tk.Frame(self.root, pady=8, padx=10)


        frame_top.pack(fill=tk.X)


        


        tk.Label(frame_top, text="Dữ liệu:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)


        self.lbl_file = tk.Label(frame_top, text="Chưa có (0)", fg="gray", font=("Arial", 10))


        self.lbl_file.pack(side=tk.LEFT, padx=5)


        


        # Right container for actions


        frame_btns = tk.Frame(frame_top)


        frame_btns.pack(side=tk.RIGHT)





        btn_settings = tk.Button(frame_btns, text="⚙️", command=self.open_settings, bg="#607D8B", fg="white", font=("Arial", 9, "bold"), width=3)


        btn_settings.pack(side=tk.RIGHT, padx=2)





        btn_open = tk.Button(frame_btns, text="📥 Nạp CSV", command=self.open_file, bg="#4CAF50", fg="white", font=("Arial", 9, "bold"), padx=8)


        btn_open.pack(side=tk.RIGHT, padx=2)





        btn_load = tk.Button(frame_btns, text="📂 Load Cache", command=self.load_from_cache, bg="#795548", fg="white", font=("Arial", 9, "bold"), padx=8)


        btn_load.pack(side=tk.RIGHT, padx=2)





        btn_vs = tk.Button(frame_btns, text="🌐 Update", command=self.run_vietstock_update, bg="#2196F3", fg="white", font=("Arial", 9, "bold"), padx=8)
        btn_vs.pack(side=tk.RIGHT, padx=2)

        btn_push = tk.Button(frame_btns, text="🌐 Đồng bộ Web", command=self.git_push_to_web, bg="#9C27B0", fg="white", font=("Arial", 9, "bold"), padx=8)
        btn_push.pack(side=tk.RIGHT, padx=2)

        btn_reset = tk.Button(frame_btns, text="🗑️ Reset Dữ liệu", command=self.reset_data_cache, bg="#FF5722", fg="white", font=("Arial", 9, "bold"), padx=8)
        btn_reset.pack(side=tk.RIGHT, padx=2)





        self.lbl_session = tk.Label(frame_top, text="🌐 URL: Checking...", font=("Arial", 9, "bold"), fg="#666")


        self.lbl_session.pack(side=tk.RIGHT, padx=10)


        


        # Initial status check


        self.root.after(1000, self.update_session_ui)





        # --- Middle Frame: Action Buttons ---


        frame_mid = tk.Frame(self.root, pady=15, padx=10)


        frame_mid.pack(fill=tk.X)


        


        # Option 1: Analyzer


        frame_analyze = tk.LabelFrame(frame_mid, text="Phương án 1: Phân Tích Tổng Hợp 1 Mã", font=("Arial", 10, "bold"), pady=10, padx=10)


        frame_analyze.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)


        


        tk.Label(frame_analyze, text="Nhập mã chứng khoán:").pack(side=tk.LEFT, padx=5)


        self.entry_ticker = tk.Entry(frame_analyze, width=10, font=("Arial", 12))


        self.entry_ticker.pack(side=tk.LEFT, padx=5)


        btn_analyze = tk.Button(frame_analyze, text="📈 Tra Cứu", command=self.run_analyzer, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))


        btn_analyze.pack(side=tk.LEFT, padx=5)





        btn_chart = tk.Button(frame_analyze, text="📊 Biểu Đồ", command=self.run_stock_chart, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))


        btn_chart.pack(side=tk.LEFT, padx=5)


        btn_heatmap = tk.Button(frame_analyze, text="🔥 Heatmap", command=self.run_heatmap_chart, bg="#E91E63", fg="white", font=("Arial", 10, "bold"))
        btn_heatmap.pack(side=tk.LEFT, padx=5)


        btn_greenpink = tk.Button(frame_analyze, text="🌸 GP Chart", command=self.run_greenpink_chart, bg="#E91E63", fg="white", font=("Arial", 10, "bold"))
        btn_greenpink.pack(side=tk.LEFT, padx=5)

        btn_heikin = tk.Button(frame_analyze, text="📈 Trending", command=self.run_heikin_chart, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        btn_heikin.pack(side=tk.LEFT, padx=5)





        # --- What-If Frame ---
        frame_whatif = tk.LabelFrame(self.root, text="Phương án 1B: Phân Tích Giả Định (What-If kịch bản)", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_whatif.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(frame_whatif, text="Dự báo phản ứng và kịch bản tương lai dựa theo dữ liệu tương đồng quá khứ:").pack(side=tk.LEFT, padx=5)
        btn_whatif = tk.Button(frame_whatif, text="🔮 Chạy What-If (Giả Định)", command=self.open_whatif_dialog, bg="#7B1FA2", fg="white", font=("Arial", 10, "bold"))
        btn_whatif.pack(side=tk.LEFT, padx=10)

        # --- Advanced Frame: 4 specific buttons ---


        frame_adv = tk.LabelFrame(self.root, text="Phương án 2: Bảng Điều Khiển Lọc (Scanner & Market)", font=("Arial", 10, "bold"), pady=10, padx=10)


        frame_adv.pack(fill=tk.X, padx=10, pady=5)


        


        # Row 1: Market Context (Breadth & Market Analysis)


        frame_market = tk.Frame(frame_adv)


        frame_market.pack(fill=tk.X, pady=2)


        


        btn_breadth = tk.Button(frame_market, text="📊 Chart Breadth (Độ rộng)", command=self.show_market_breadth, bg="#607D8B", fg="white", font=("Arial", 10, "bold"))


        btn_breadth.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)





        btn_market = tk.Button(frame_market, text="🏛️ Phân Tích Tổng Quan VNINDEX", command=self.run_market_analysis, bg="#E91E63", fg="white", font=("Arial", 10, "bold"))


        btn_market.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)





        # Row 2: Signals Part 1
        frame_signals_1 = tk.Frame(frame_adv)
        frame_signals_1.pack(fill=tk.X, pady=2)
        
        btn_add2 = tk.Button(frame_signals_1, text="🟠 Gia Tăng 2", command=lambda: self.run_advanced_scanner("ADD_2"), bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_add2.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_accum = tk.Button(frame_signals_1, text="📦 Tích Lũy", command=lambda: self.run_advanced_scanner("ACCUMULATION"), bg="#9C27B0", fg="white", font=("Arial", 10, "bold"))
        btn_accum.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_ma = tk.Button(frame_signals_1, text="📈 Perfect MA", command=lambda: self.run_advanced_scanner("PERFECT_MA"), bg="#00BCD4", fg="white", font=("Arial", 10, "bold"))
        btn_ma.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Row 3: Signals Part 2
        frame_signals_2 = tk.Frame(frame_adv)
        frame_signals_2.pack(fill=tk.X, pady=2)
        
        btn_heikin = tk.Button(frame_signals_2, text="📈 Heikin", command=lambda: self.run_advanced_scanner("HEIKIN_BUY"), bg="#008B8B", fg="white", font=("Arial", 10, "bold"))
        btn_heikin.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_wait = tk.Button(frame_signals_2, text="☁️ UPCLOUD", command=lambda: self.run_advanced_scanner("UPCLOUD"), bg="#1E90FF", fg="white", font=("Arial", 10, "bold"))
        btn_wait.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_white_adx = tk.Button(frame_signals_2, text="⚪ Trend ADX", command=lambda: self.run_advanced_scanner("WHITE_ADX"), bg="#FFFFFF", fg="black", font=("Arial", 10, "bold"))
        btn_white_adx.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)


        # --- Phương án 3: Đánh giá danh mục ---
        frame_portfolio = tk.LabelFrame(self.root, text="Phương án 3: Đánh giá danh mục đầu tư", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_portfolio.pack(fill=tk.X, padx=10, pady=5)
        
        btn_analys = tk.Button(frame_portfolio, text="🔍 Analys (Đánh Giá Danh Mục)", command=self.open_portfolio_dialog, bg="#673AB7", fg="white", font=("Arial", 10, "bold"))
        btn_analys.pack(side=tk.LEFT, padx=5)
        
        btn_filter = tk.Button(frame_portfolio, text="🔍 Filter (Bộ Lọc Tùy Chọn)", command=self.open_custom_filter_dialog, bg="#009688", fg="white", font=("Arial", 10, "bold"))
        btn_filter.pack(side=tk.LEFT, padx=5)

        # --- Bottom Frame: Output / Results ---

        frame_bottom = tk.LabelFrame(self.root, text="Kết Quả", font=("Arial", 10, "bold"), padx=10, pady=10)


        frame_bottom.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)





        # Scrollable Text area for reports


        self.text_output = tk.Text(frame_bottom, font=("Consolas", 11), wrap=tk.WORD, state=tk.DISABLED)


        scrollbar = tk.Scrollbar(frame_bottom, command=self.text_output.yview)


        self.text_output.configure(yscrollcommand=scrollbar.set)


        


        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


        self.text_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)


        


        self.log_sync("Trạng thái: Sẵn sàng.\nVui lòng bấm 'Nạp Thêm File CSV' để tải tệp. (Không giới hạn số lượng file, hệ thống sẽ gom nhóm tự động và PRE-COMPUTE để lọc với tộc độ 0ms).")





    def _log_internal(self, message: str, clear: bool = False):


        self.text_output.configure(state=tk.NORMAL)


        if clear:


            self.text_output.delete(1.0, tk.END)


        self.text_output.insert(tk.END, message + "\n")


        self.text_output.see(tk.END)


        self.text_output.configure(state=tk.DISABLED)





    def log_sync(self, message: str, clear: bool = False):


        self.root.after(0, self._log_internal, message, clear)





    def open_file(self):


        files = filedialog.askopenfilenames(


            title="Chọn các file dữ liệu CSV",


            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]


        )


        if not files:


            return


            


        self.log_sync(f"\n--- BẮT ĐẦU XỬ LÝ {len(files)} FILE... ---", clear=True)


        threading.Thread(target=self._process_files_bg, args=(files,), daemon=True).start()





    def _process_files_bg(self, files):


        try:


            from concurrent.futures import ThreadPoolExecutor, as_completed


            


            self.log_sync(f"[1/4] Đang nạp thô {len(files)} file CSV...")


            dfs = []


            for f in files:
                try:
                    df_raw = pd.read_csv(f)
                    
                    # Normalize columns IMMEDIATELY so headers like <Ticker> are recognized
                    df_norm = _normalize_columns(df_raw)
                    
                    # Ticker inference from filename if column is missing after normalization
                    if "Ticker" not in df_norm.columns:
                        path_obj = Path(f)
                        potential_ticker = path_obj.stem.upper().split('_')[0].split(' ')[0]
                        is_idx = ("VNINDEX" in potential_ticker) or ("HNX" in potential_ticker) or ("HAINDEX" in potential_ticker)
                        if (len(potential_ticker) == 3 and potential_ticker.isalnum()) or is_idx:
                            df_norm["Ticker"] = potential_ticker
                            self.log_sync(f"   + Nhận diện mã '{potential_ticker}' từ tên file: {path_obj.name}")
                    
                    dfs.append(df_norm)
                except Exception as e:
                    self.log_sync(f"   ! Lỗi đọc/chuẩn hóa file {os.path.basename(f)}: {e}")


            


            if not dfs:


                self.log_sync("❌ Lỗi: Không đọc được dữ liệu hợp lệ từ các file đã chọn.")


                return


                


            self.log_sync("[2/4] Đang chuẩn hóa & Lưu vào Storage (Parquet-SSoT)...")


            df_full = pd.concat(dfs, ignore_index=True)
            
            affected_tickers = set()
            all_valid_tickers = []
            skipped_3char = 0
            skipped_old = 0
            
            if "Ticker" in df_full.columns:
                grouped = df_full.groupby("Ticker")
                for ticker_val, group in grouped:
                    t = str(ticker_val).upper().strip()
                    
                    # 1. Bộ lọc 3 ký tự
                    is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
                    if not (len(t) == 3 and t.isalnum()) and not is_idx:
                        skipped_3char += 1
                        continue

                    sub_df = group.drop(columns=["Ticker"]).copy()
                    try:
                        clean_sub = _clean_dataframe(sub_df, ticker=t)

                        # 2. Bộ lọc 30 ngày (Giữ nguyên theo ý khách hàng)
                        last_date = clean_sub['Date'].max()
                        if (datetime.now() - last_date).days > 30 and not is_idx:
                            skipped_old += 1
                            continue

                        # Mã hợp lệ
                        all_valid_tickers.append(t)

                        # 1. Đồng bộ giá vào Storage
                        self.storage.sync_prices(t, clean_sub, source='CSV')
                        # 2. Luôn thêm vào danh sách tính toán để đảm bảo đủ 100% chỉ báo mới nhất
                        affected_tickers.add(t)
                    except Exception as e_ticker:
                        self.log_sync(f"   ! Lỗi xử lý mã {t}: {e_ticker}")

            if skipped_3char > 0 or skipped_old > 0:
                self.log_sync(f"   [*] Đã lọc bỏ: {skipped_3char} mã rác/không đạt tiêu chí.")

            if not affected_tickers:
                self.log_sync("ℹ️ Không tìm thấy mã cổ phiếu hợp lệ nào để tính toán.")
                return

            # Kích hoạt Registry
            self.storage.save_active_registry(list(affected_tickers))
            
            self.log_sync(f"[3/4] Đang tính toán toàn diện (100% Rules) cho {len(affected_tickers)} mã hợp lệ...")
            self._sync_and_recompute_affected(list(affected_tickers))

            self.log_sync(f"\n✅ HOÀN TẤT! Đã nạp và tính toán xong cho {len(all_valid_tickers)} mã cổ phiếu.")
        except Exception as e:


            self.log_sync(f"\n❌ LỖI XỬ LÝ CSV: {str(e)}")





    def open_whatif_dialog(self):
        """Mở cửa sổ Phân tích kịch bản What-If"""
        top = tk.Toplevel(self.root)
        top.title("Phân tích kịch bản What-If (Scenario Forecast)")
        top.geometry("700x550")

        # Input Frame
        frame_input = tk.Frame(top, pady=10, padx=10)
        frame_input.pack(fill=tk.X)

        tk.Label(frame_input, text="Mã cổ phiếu / Chỉ số (Ví dụ: VNINDEX, FPT, HPG):", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        entry_ticker = tk.Entry(frame_input, width=15, font=("Arial", 11, "bold"))
        entry_ticker.pack(side=tk.LEFT, padx=5)
        
        # Prefill if entry_ticker in main gui is not empty
        main_t = self.entry_ticker.get().strip().upper()
        if main_t:
            entry_ticker.insert(0, main_t)
        else:
            entry_ticker.insert(0, "VNINDEX")

        # Output Frame
        frame_output = tk.LabelFrame(top, text="Kết quả dự báo giả định What-If", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        text_out = scrolledtext.ScrolledText(frame_output, font=("Consolas", 10), wrap=tk.WORD)
        text_out.pack(fill=tk.BOTH, expand=True)

        def run_whatif():
            ticker = entry_ticker.get().strip().upper()
            if not ticker:
                messagebox.showwarning("Cảnh báo", "Vui lòng nhập mã cổ phiếu hoặc chỉ số!")
                return
            
            if not self.data_dict:
                messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")
                return

            df = self.data_dict.get(ticker)
            if df is None or len(df) < 50:
                messagebox.showwarning("Không đủ dữ liệu", f"Mã '{ticker}' không tồn tại hoặc dữ liệu <50 ngày!")
                return

            text_out.delete("1.0", tk.END)
            text_out.insert(tk.END, f"⏳ Đang chạy phân tích What-If cho mã {ticker}...\n")
            top.update()

            threading.Thread(target=self._run_whatif_bg, args=(ticker, df, text_out), daemon=True).start()

        btn_run = tk.Button(frame_input, text="🔮 Chạy Phân Tích", command=run_whatif, bg="#7B1FA2", fg="white", font=("Arial", 10, "bold"))
        btn_run.pack(side=tk.LEFT, padx=10)

    def _run_whatif_bg(self, ticker, df, text_widget):
        try:
            from tinvest.whatif_engine import run_whatif_analysis
            result = run_whatif_analysis(ticker, df, top_n=5, compute_forecast_series=True, forecast_days=90)
            
            if not result or 'error' in result and result['error']:
                err_msg = result.get('error', 'Lỗi không xác định')
                self.root.after(0, lambda: [text_widget.delete("1.0", tk.END), text_widget.insert(tk.END, f"❌ Lỗi: {err_msg}\n")])
                return

            # Format report cleanly
            report = []
            report.append(f"🔮 BÁO CÁO PHÂN TÍCH GIẢ ĐỊNH (WHAT-IF SCENARIO) CHO {ticker}")
            report.append("="*60)
            report.append(f"Giá hiện tại: {result['price']:.2f} (Ngày: {result['date']})")
            report.append("")
            
            report.append("1. XÁC XUẤT PHẢN ỨNG (Historical Distribution):")
            dist = result.get('distribution', {})
            for horizon in ['future_3', 'future_5', 'future_10']:
                h_data = dist.get(horizon, {})
                if h_data:
                    days = horizon.split('_')[1]
                    report.append(f"  • Sau {days} phiên: Tăng {h_data.get('pct_up', 0.0):.1f}% | Giảm {h_data.get('pct_down', 0.0):.1f}% (Số mẫu tương đồng: {h_data.get('n', 0)})")
            report.append("")

            report.append("2. CÁC VÙNG CẢN / HỖ TRỢ & HỘI TỤ (Confluence Zones):")
            zones = result.get('zones', [])
            for z in zones:
                conf_type = "[Hội Tụ]" if z.get('is_confluence', False) else ""
                report.append(f"  • {z['type'].upper()}: {z['price']:.1f} ± {z['tolerance']:.1f} (Độ tin cậy: {z['confidence']}% {conf_type})")
            report.append("")

            report.append("3. CÁC KỊCH BẢN XU HƯỚNG CHÍNH (Scenario Tree):")
            tree = result.get('scenario_tree', {})
            mp = tree.get('main_path', {})
            if mp:
                report.append(f"  🚀 KỊCH BẢN CHÍNH ({mp['probability']}%): {mp['direction']} → {mp['target']}")
                for b in mp.get('branches', []):
                    report.append(f"    └── {b['condition']}: {b['direction']} → {b['target']} (Xác suất nhánh: {b['probability']}%)")
            
            ap = tree.get('alt_path', {})
            if ap:
                report.append(f"  🔄 KỊCH BẢN PHỤ ({ap['probability']}%): {ap['direction']} → {ap['target']}")
                for b in ap.get('branches', []):
                    report.append(f"    └── {b['condition']}: {b['direction']} → {b['target']} (Xác suất nhánh: {b['probability']}%)")
            report.append("")

            report.append("4. CÁC MẪU QUÁ KHỨ TƯƠNG ĐỒNG NHẤT (Top 5 Analogs):")
            matches = result.get('matches', [])[:5]
            for i, m in enumerate(matches):
                report.append(f"  • Top {i+1}: Ngày {m['date']} (Độ tương đồng: {m['similarity']*100:.1f}%) | Phản ứng sau 5 phiên: {m['future_5']}%")
            report.append("")

            report.append("5. DỰ BÁO ATR & BIÊN ĐỘ MỤC TIÊU:")
            proj = result.get('targets', {})
            if proj:
                report.append(f"  • Mục tiêu Tăng (Bull Target 1): {proj.get('bull_target_1', 0.0):.2f}")
                report.append(f"  • Hỗ trợ Cực đại (Cutloss Zone): {proj.get('bear_target_1', 0.0):.2f}")
            report.append("="*60)
            
            final_report = "\n".join(report)
            self.root.after(0, lambda: [text_widget.delete("1.0", tk.END), text_widget.insert(tk.END, final_report)])
        except Exception as e:
            logger.error(f"Error in running What-If background: {e}", exc_info=True)
            self.root.after(0, lambda: [text_widget.delete("1.0", tk.END), text_widget.insert(tk.END, f"❌ Lỗi thực thi: {str(e)}\n")])

    def _refresh_whatif_cache_bg(self):
        """Tính toán và lưu cache kịch bản What-If cho các chỉ số chính VNINDEX, HNX-INDEX, VN30."""
        def run_cache():
            try:
                from tinvest.whatif_engine import run_whatif_analysis
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import json
                self.log_sync("[*] Đang chạy nền tính toán cache What-If cho các chỉ số thị trường (song song)...")

                indices = ["VNINDEX", "HNX-INDEX", "VN30"]

                # D2: Chuẩn bị args cho từng index
                tasks = []
                for idx in indices:
                    t_key = next((k for k in self.data_dict.keys() if idx in k), None)
                    if not t_key:
                        continue
                    df = self.data_dict[t_key]
                    if df is None or len(df) < 50:
                        continue
                    tasks.append((idx, df))

                def _run_one(args):
                    idx_name, df_arg = args
                    return idx_name, run_whatif_analysis(
                        idx_name, df_arg, top_n=5,
                        compute_forecast_series=True, forecast_days=90
                    )

                whatif_cache = {}
                # D2: Chạy song song 3 indices (mỗi index độc lập)
                with ThreadPoolExecutor(max_workers=min(3, len(tasks))) as ex:
                    futures = {ex.submit(_run_one, t): t[0] for t in tasks}
                    for future in as_completed(futures):
                        idx_name = futures[future]
                        try:
                            idx_name, result = future.result()
                            if result and not result.get('error'):
                                whatif_cache[idx_name] = result
                                self.log_sync(f"  ✅ Hoàn thành What-If cho {idx_name}")
                            else:
                                self.log_sync(f"  ⚠️ Bỏ qua {idx_name}: {result.get('error', 'Lỗi không xác định')}")
                        except Exception as e:
                            self.log_sync(f"  ❌ Lỗi What-If cho {idx_name}: {e}")

                if whatif_cache:
                    os.makedirs("Output", exist_ok=True)
                    def default_converter(o):
                        if isinstance(o, np.integer): return int(o)
                        if isinstance(o, np.floating): return float(o)
                        if isinstance(o, np.ndarray): return o.tolist()
                        return o
                    import tempfile
                    temp_fd, temp_path = tempfile.mkstemp(dir="Output", prefix="whatif_results_tmp_")
                    try:
                        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                            json.dump(whatif_cache, f, ensure_ascii=False, indent=4, default=default_converter)
                        target_file = "Output/whatif_results.json"
                        if os.path.exists(target_file):
                            os.replace(temp_path, target_file)
                        else:
                            os.rename(temp_path, target_file)
                    except Exception as e_write:
                        if os.path.exists(temp_path):
                            try: os.remove(temp_path)
                            except: pass
                        raise e_write
                    self.log_sync("✅ Đã cập nhật xong Output/whatif_results.json")
                else:
                    self.log_sync("⚠️ Không có chỉ số thị trường nào được cache.")
            except Exception as e:
                logger.error(f"Error caching what-if index data: {e}", exc_info=True)
                self.log_sync(f"❌ Lỗi cache What-If chỉ số: {e}")
        
        threading.Thread(target=run_cache, daemon=True).start()

    def open_portfolio_dialog(self):
        """Mở cửa sổ Đánh giá danh mục đầu tư"""
        top = tk.Toplevel(self.root)
        top.title("Đánh giá danh mục đầu tư (Portfolio Analysis)")
        top.geometry("800x650")
        
        def format_number(event):
            if event.keysym in ('Left', 'Right', 'Up', 'Down', 'BackSpace', 'Delete', 'End', 'Home'):
                return
            widget = event.widget
            pos = widget.index(tk.INSERT)
            prev_len = len(widget.get())
            text = widget.get().replace(',', '')
            if not text: return
            try:
                parts = text.split('.')
                if parts[0] and parts[0] != '-':
                    parts[0] = "{:,}".format(int(parts[0]))
                formatted = '.'.join(parts)
                widget.delete(0, tk.END)
                widget.insert(0, formatted)
                new_len = len(formatted)
                widget.icursor(max(0, pos + (new_len - prev_len)))
            except ValueError:
                pass

        # Section 1: Thông số tài sản
        frame_params = tk.LabelFrame(top, text="1. Nhóm thông số tài sản", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_params.pack(fill=tk.X, padx=10, pady=5)
        
        # Grid layout for params
        tk.Label(frame_params, text="Tiền mặt đang có (VNĐ):").grid(row=0, column=0, sticky="w", pady=2)
        entry_nav = tk.Entry(frame_params, width=20)
        entry_nav.insert(0, "0") # Default 0
        entry_nav.bind('<KeyRelease>', format_number)
        entry_nav.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(frame_params, text="Tỷ trọng CP khuyến cáo (%):").grid(row=0, column=2, sticky="w", pady=2)
        entry_weight = tk.Entry(frame_params, width=10)
        entry_weight.insert(0, "100")
        entry_weight.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(frame_params, text="Tỷ lệ cutloss (%):").grid(row=1, column=0, sticky="w", pady=2)
        entry_cutloss = tk.Entry(frame_params, width=10)
        entry_cutloss.insert(0, "7")
        entry_cutloss.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(frame_params, text="Số mã mong muốn:").grid(row=1, column=2, sticky="w", pady=2)
        entry_ntickers = tk.Entry(frame_params, width=10)
        entry_ntickers.insert(0, "3")
        entry_ntickers.grid(row=1, column=3, padx=5, pady=2)
        
        # Section 2: Nhóm thông số từng cổ phiếu
        frame_tickers = tk.LabelFrame(top, text="2. Nhóm thông số từng cổ phiếu (Tối đa 10 mã)", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_tickers.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(frame_tickers, text="Mã CP", font=("Arial", 9, "bold")).grid(row=0, column=0, padx=5)
        tk.Label(frame_tickers, text="Số lượng", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=5)
        tk.Label(frame_tickers, text="Giá vốn trung bình", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=5)
        
        entries = []
        for i in range(10):
            e_ticker = tk.Entry(frame_tickers, width=15)
            e_ticker.grid(row=i+1, column=0, padx=5, pady=2)
            e_qty = tk.Entry(frame_tickers, width=15)
            e_qty.bind('<KeyRelease>', format_number)
            e_qty.grid(row=i+1, column=1, padx=5, pady=2)
            e_price = tk.Entry(frame_tickers, width=15)
            e_price.bind('<KeyRelease>', format_number)
            e_price.grid(row=i+1, column=2, padx=5, pady=2)
            entries.append((e_ticker, e_qty, e_price))
            
        def run_analysis():
            try:
                params = {
                    'nav_total': float(entry_nav.get().replace(',', '')),
                    'w_target': float(entry_weight.get()),
                    'r_cl': float(entry_cutloss.get()),
                    'n_tickers': int(entry_ntickers.get())
                }
                tickers_data = []
                for e_t, e_q, e_p in entries:
                    t_val = e_t.get().strip().upper()
                    if t_val:
                        tickers_data.append({
                            'ticker': t_val,
                            'quantity': float(e_q.get().replace(',', '') if e_q.get() else 0),
                            'avg_price': float(e_p.get().replace(',', '') if e_p.get() else 0)
                        })
                
                if not tickers_data:
                    messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập ít nhất 1 mã cổ phiếu.")
                    return
                
                from tinvest.portfolio_engine import analyze_portfolio
                result_text = analyze_portfolio(params, tickers_data, self.storage)
                
                # Show in new Window
                res_top = tk.Toplevel(top)
                res_top.title("Báo Cáo Đánh Giá Danh Mục")
                res_top.geometry("1100x700")
                txt = scrolledtext.ScrolledText(res_top, font=("Consolas", 11), wrap=tk.WORD)
                txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
                txt.insert(tk.END, result_text)
                txt.config(state=tk.DISABLED)
                
            except Exception as e:
                messagebox.showerror("Lỗi", f"Có lỗi xảy ra khi phân tích: {str(e)}")

        # Frame for action button
        frame_action = tk.Frame(top)
        frame_action.pack(fill=tk.X, pady=10)
        btn_run = tk.Button(frame_action, text="🚀 Khởi chạy", command=run_analysis, bg="#FF5722", fg="white", font=("Arial", 12, "bold"))
        btn_run.pack(pady=10)

    def precalculate_custom_filter_data(self):
        """Precalculate RS13 and RS52 for all dataframes in the cache using VNINDEX benchmark."""
        # Find VNINDEX dataframe
        vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), None)
        df_vn = self.data_dict.get(vn_key) if vn_key else None
        
        if df_vn is None or df_vn.empty:
            self.log_sync("Cảnh báo: Không tìm thấy dữ liệu VNINDEX để tính RS13/RS52. Các bộ lọc RS sẽ trả về False.")
            return

        df_vn_indexed = df_vn.set_index('Date')
        
        for ticker, data in self.analysis_cache.items():
            df = data.get("df")
            if df is None or df.empty:
                continue
            
            # Map benchmark Close to ticker df based on Date (with forward/backward fill to be robust)
            bench_close = df['Date'].map(df_vn_indexed['Close']).ffill().bfill()
            rs_raw = df['Close'] / (bench_close + 1e-10)
            
            # RS52: 52 weeks = 260 bars
            rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
            rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
            df['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)
            
            # RS14: 14 weeks = 70 bars
            rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
            rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
            df['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)

    def open_custom_filter_dialog(self):
        if not self.analysis_cache:
            messagebox.showwarning("Cảnh báo", "Hệ thống chưa nạp dữ liệu. Hãy bấm '📂 Load Dữ liệu Cũ' hoặc 'Nạp Thêm File CSV'!")
            return

        # Precalculate RS indicators for all cached stock dfs
        self.precalculate_custom_filter_data()

        dialog = tk.Toplevel(self.root)
        dialog.title("Bộ lọc tùy chỉnh (Custom Filter)")
        dialog.geometry("950x700")
        dialog.resizable(False, False)
        dialog.configure(bg="#222222")
        dialog.transient(self.root)
        dialog.grab_set()

        # Title at the top
        tk.Label(dialog, text="CHỌN CÁC TIÊU CHÍ LỌC (LOGICAL AND)", font=("Arial", 12, "bold"), fg="gold", bg="#222222", pady=15).pack(side=tk.TOP)

        # 11 Primary Signals Def (Filter 1)
        filters_def = [
            ("EARLY", "Mua Sớm (EARLY)"),
            ("ADD_1", "Gia Tăng 1 (ADD_1)"),
            ("ADD_2", "Gia Tăng 2 (ADD_2)"),
            ("STRONG", "Mua Mạnh (STRONG)"),
            ("ACCUMULATION", "Tích Lũy (ACCUMULATION)"),
            ("BREAKOUT_ACCUMULATION", "Phá Vỡ Tích Lũy (BREAKOUT)"),
            ("PERFECT_MA", "Perfect MA (PERFECT_MA)"),
            ("HEIKIN_BUY", "Heikin (HEIKIN_BUY)"),
            ("UPCLOUD", "UPCLOUD"),
            ("WHITE_ADX", "Trend ADX (WHITE_ADX)"),
            ("MARK_MINERVINI", "Mark Minervini (MINERVINI)")
        ]

        vars_categories = {}
        vars_rules = {}

        def run_filter():
            selected_categories = [k for k, v in vars_categories.items() if v.get()]
            selected_rules = [k for k, v in vars_rules.items() if v.get()]
            if not selected_categories and not selected_rules:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất một tiêu chí!")
                return
            dialog.destroy()
            self.run_custom_filter(selected_categories, selected_rules)

        # Launch button at the bottom (guaranteed visibility)
        btn_run = tk.Button(dialog, text="🚀 KHỞI CHẠY", command=run_filter, bg="#009688", fg="white", font=("Arial", 12, "bold"), pady=8)
        btn_run.pack(side=tk.BOTTOM, fill=tk.X, padx=30, pady=15)

        # Two-column layout in the middle
        frame_columns = tk.Frame(dialog, bg="#222222")
        frame_columns.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20)

        # Left Column: Primary categories
        frame_left = tk.LabelFrame(frame_columns, text="1. TÍN HIỆU GIAO DỊCH CHÍNH", font=("Arial", 10, "bold"), fg="gold", bg="#222222", padx=15, pady=10)
        frame_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        for key, label in filters_def:
            var = tk.BooleanVar(value=False)
            vars_categories[key] = var
            chk = tk.Checkbutton(frame_left, text=label, variable=var, font=("Arial", 10), anchor="w",
                                 bg="#222222", fg="white", selectcolor="#333333", activebackground="#222222", activeforeground="white")
            chk.pack(fill=tk.X, pady=4)

        # Right Column: Custom rules with a scrollbar
        frame_right_container = tk.LabelFrame(frame_columns, text="2. TIÊU CHÍ KỸ THUẬT BỔ TRỢ", font=("Arial", 10, "bold"), fg="gold", bg="#222222", padx=5, pady=5)
        frame_right_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

        canvas = tk.Canvas(frame_right_container, bg="#222222", highlightthickness=0)
        scrollbar = tk.Scrollbar(frame_right_container, orient="vertical", command=canvas.yview)
        frame_right = tk.Frame(canvas, bg="#222222")

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas_frame = canvas.create_window((0, 0), window=frame_right, anchor="nw")

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame_right.bind("<Configure>", configure_scroll)

        def configure_width(event):
            canvas.itemconfig(canvas_frame, width=event.width)
        canvas.bind("<Configure>", configure_width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def on_dialog_destroy(event):
            if event.widget == dialog:
                canvas.unbind_all("<MouseWheel>")
        dialog.bind("<Destroy>", on_dialog_destroy)

        # Populate custom rules into scrollable right frame
        for key, r_def in CUSTOM_RULES.items():
            var = tk.BooleanVar(value=False)
            vars_rules[key] = var
            chk = tk.Checkbutton(frame_right, text=r_def["label"], variable=var, font=("Arial", 10), anchor="w",
                                 bg="#222222", fg="white", selectcolor="#333333", activebackground="#222222", activeforeground="white")
            chk.pack(fill=tk.X, pady=3)

    def run_custom_filter(self, selected_categories, selected_rules):
        self.log_sync(f"Đang chạy bộ lọc tùy chỉnh với các tiêu chí: {', '.join(selected_categories + [CUSTOM_RULES[k]['label'] for k in selected_rules])}...", clear=True)
        self.root.update()

        try:
            results = []
            for ticker, data in self.analysis_cache.items():
                df = data.get("df")
                if df is None or (hasattr(df, 'empty') and df.empty):
                    continue

                # Volume check
                current_vol = df['Volume'].iloc[-1] if 'Volume' in df.columns else 0
                if current_vol < 200000:
                    continue

                res = data.get("adv") or data.get("advanced_entry") or data.get("entry_signal") or {}
                accum = data.get("accum") or data.get("accumulation") or {}
                ma_trend = data.get("ma_trend") or data.get("ma") or {}
                val = data.get("valuation") or data.get("val") or {}

                # 1. Filter 1 matching logic (selected categories)
                # If selected_categories is empty, it matches (True).
                # Otherwise, it matches if it satisfies at least one of the selected categories (logical OR).
                matches_filter1 = True
                if selected_categories:
                    matches_filter1 = False
                    for key in selected_categories:
                        if key == "ACCUMULATION":
                            if accum.get("is_accumulation", False):
                                matches_filter1 = True
                                break
                        elif key == "BREAKOUT_ACCUMULATION":
                            if check_breakout_accumulation(df):
                                matches_filter1 = True
                                break
                        elif key == "PERFECT_MA":
                            if ma_trend.get("is_perfect_uptrend", False):
                                matches_filter1 = True
                                break
                        elif key == "HEIKIN_BUY":
                            # Chỉ lọc khi có tín hiệu buy tại T-0 hoặc T-1 (2 phiên gần nhất)
                            buy_2 = False
                            if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
                                sig = df.get('HK_BuySignal', pd.Series(dtype=bool)).fillna(False).tail(2)
                                manh = df.get('HK_BuyManh', pd.Series(dtype=bool)).fillna(False).tail(2)
                                buy_2 = bool(sig.any()) or bool(manh.any())
                            if buy_2:
                                matches_filter1 = True
                                break
                        elif key == "UPCLOUD":
                            if len(df) > 0 and 'High' in df.columns and 'Low' in df.columns:
                                last = df.iloc[-1]
                                current_price = last['Close']
                                span_a = last.get('SpanA', 0)
                                span_b = last.get('SpanB', 0)
                                tenkan = last.get('Tenkan', 0)
                                kijun = last.get('Kijun', 0)
                                ma10 = last.get('MA10', 0)
                                ma20 = last.get('MA20', 0)
                                
                                future_span_a = (tenkan + kijun) / 2
                                h52 = df['High'].iloc[-52:].max() if len(df) >= 52 else df['High'].max()
                                l52 = df['Low'].iloc[-52:].min() if len(df) >= 52 else df['Low'].min()
                                future_span_b = (h52 + l52) / 2
                                
                                c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                                c2 = (future_span_a > future_span_b)
                                c3 = (tenkan > kijun)
                                c4 = (ma10 > ma20)
                                if c1 and c2 and c3 and c4:
                                    matches_filter1 = True
                                    break
                        elif key == "WHITE_ADX":
                            adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
                            if adx_color == "WHITE":
                                matches_filter1 = True
                                break
                        elif key == "MARK_MINERVINI":
                            if check_mark_minervini(df):
                                matches_filter1 = True
                                break
                        else:  # EARLY, ADD_1, ADD_2, STRONG
                            if res.get("entry_type") == key:
                                matches_filter1 = True
                                break

                if not matches_filter1:
                    continue

                # 2. Filter 2 matching logic (selected rules)
                # If selected_rules is empty, it matches (True).
                # Otherwise, it must satisfy all selected rules (logical AND).
                matches_filter2 = True
                if selected_rules:
                    for r_key in selected_rules:
                        rule_func = CUSTOM_RULES[r_key]["func"]
                        if not rule_func(df):
                            matches_filter2 = False
                            break

                if not matches_filter2:
                    continue

                # Risk limit check
                risk_limit = 20.0 if "WHITE_ADX" in selected_categories else 15.0
                if val.get("is_valid", True) is False or val.get("risk_pct", 0) > risk_limit:
                    continue

                current_p = float(df['Close'].iloc[-1]) * 1000
                last_vol = float(df["Volume"].iloc[-1])
                ep = val.get("price", 0)
                tp = val.get("tp1", 0)
                rr_ratio = val.get("rr_ratio", 0)
                val_score = val.get("risk_score", 0)

                reasons = []
                for key in selected_categories:
                    if key == "ACCUMULATION" and accum.get("is_accumulation", False):
                        reasons.append(f"Tích Lũy ({accum.get('base_quality', 'N/A')})")
                    elif key == "BREAKOUT_ACCUMULATION" and check_breakout_accumulation(df):
                        reasons.append("Phá Vỡ Tích Lũy")
                    elif key == "PERFECT_MA" and ma_trend.get("is_perfect_uptrend", False):
                        reasons.append("Perfect MA")
                    elif key == "HEIKIN_BUY":
                        # Chỉ thêm reason khi có tín hiệu buy tại T-0 hoặc T-1
                        buy_2 = False
                        if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
                            sig = df.get('HK_BuySignal', pd.Series(dtype=bool)).fillna(False).tail(2)
                            manh = df.get('HK_BuyManh', pd.Series(dtype=bool)).fillna(False).tail(2)
                            buy_2 = bool(sig.any()) or bool(manh.any())
                        if buy_2:
                            reasons.append("Heikin Buy")
                    elif key == "UPCLOUD":
                        if len(df) > 0 and 'High' in df.columns and 'Low' in df.columns:
                            last = df.iloc[-1]
                            current_price = last['Close']
                            span_a = last.get('SpanA', 0)
                            span_b = last.get('SpanB', 0)
                            tenkan = last.get('Tenkan', 0)
                            kijun = last.get('Kijun', 0)
                            ma10 = last.get('MA10', 0)
                            ma20 = last.get('MA20', 0)
                            
                            future_span_a = (tenkan + kijun) / 2
                            h52 = df['High'].iloc[-52:].max() if len(df) >= 52 else df['High'].max()
                            l52 = df['Low'].iloc[-52:].min() if len(df) >= 52 else df['Low'].min()
                            future_span_b = (h52 + l52) / 2
                            
                            c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                            c2 = (future_span_a > future_span_b)
                            c3 = (tenkan > kijun)
                            c4 = (ma10 > ma20)
                            if c1 and c2 and c3 and c4:
                                reasons.append("UpCloud")
                    elif key == "WHITE_ADX":
                        adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
                        if adx_color == "WHITE":
                            reasons.append("ADX Trắng")
                    elif key == "MARK_MINERVINI":
                        if check_mark_minervini(df):
                            reasons.append("Mark Minervini")
                    elif res.get("entry_type") == key:
                        reasons.append(key)

                for r_key in selected_rules:
                    reasons.append(CUSTOM_RULES[r_key]["label"])

                results.append({
                    "Ticker": ticker,
                    "Price": f"{current_p:,.0f}",
                    "Volume": f"{last_vol:,.0f}",
                    "Entry": f"{ep*1000:,.0f}" if ep > 0 else "N/A",
                    "Target": f"{tp*1000:,.0f}" if tp > 0 else "N/A",
                    "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",
                    "Risk Score": f"{int(val_score)}",
                    "Criteria": " + ".join(reasons)
                })

            if not results:
                self.log_sync("Hoàn tất: Không có mã nào đạt đầy đủ các tiêu chí lọc tùy chỉnh trên.")
            else:
                self.log_sync(f"Hoàn tất: Tìm thấy {len(results)} mã thỏa mãn.\n")
                df_res = pd.DataFrame(results).sort_values("Ticker")
                table_str = df_res.to_string(index=False, justify="left")
                self.log_sync(table_str)
                self.log_sync("\n" + "="*70)
                self.log_sync("Thông tin: Hệ thống đã quét với toàn bộ thanh khoản thị trường.")
        except Exception as e:
            self.log_sync(f"Lỗi: {str(e)}")

    def update_session_ui(self):


        """Update the green/red session status indicator."""


        def run_check():


            status = self.vs_client.check_session_status()


            def apply_ui():


                if status in ["VALID", "LIMITED_BYPASSED"]:


                    self.lbl_session.config(text="🌐 URL: Đang Hoạt Động (Full)", fg="#2E7D32")


                elif status == "LIMITED":


                    self.lbl_session.config(text="🌐 URL: Lỗi (Chỉ lấy được 200 mã)", fg="#D32F2F")


                elif status == "NO_DATA":


                    self.lbl_session.config(text="🌐 URL: Không có dữ liệu hôm nay", fg="#F57C00")


                else:


                    self.lbl_session.config(text="🌐 URL: Lỗi kết nối", fg="#F57C00")


            self.root.after(0, apply_ui)


        threading.Thread(target=run_check, daemon=True).start()





    def open_settings(self):


        """Mở cửa sổ cấu hình nâng cao để dán cURL hoặc Headers từ trình duyệt."""


        top = tk.Toplevel(self.root)


        top.title("Cấu hình Vietstock (Vượt giới hạn 200 mã)")


        top.geometry("750x680")


        top.resizable(False, False)


        


        # Header Help


        frame_help = tk.LabelFrame(top, text="💡 Cách lấy dữ liệu 1 chạm (Khuyên dùng)", font=("Arial", 10, "bold"), padx=10, pady=10, fg="#2E7D32")


        frame_help.pack(fill=tk.X, padx=10, pady=5)


        


        steps = (


            "📌 B1: Truy cập [finance.vietstock.vn] -> Tab [Thống kê giá].\n"


            "📌 B2: Nhấn [F12] -> Chọn tab [Network] (Mạng).\n"


            "📌 B3: Chuột phải vào 'KQGDThongKeGiaPaging' -> Copy -> 'Copy as cURL (bash)'.\n"


            "📌 B4: Quay lại đây, nhấn [📋 Dán từ Clipboard] -> [💾 Lưu & Cập Nhật].\n"


            "--------------------------------------------------------------------------\n"


            "🚀 Mẹo: Bạn chỉ cần Copy toàn bộ mã cURL, phần mềm sẽ tự bóc tách mọi thứ."


        )


        tk.Label(frame_help, text=steps, justify=tk.LEFT, font=("Arial", 9)).pack(side=tk.LEFT)





        # Bookmarklet Section


        frame_bm = tk.Frame(top, padx=10)


        frame_bm.pack(fill=tk.X)


        


        def copy_bookmarklet():


            bm_code = "javascript:(function(){alert('Hướng dẫn: F12 -> Network -> Chuột phải KQGDThongKeGiaPaging -> Copy as cURL (bash)');})()"


            self.root.clipboard_clear()


            self.root.clipboard_append(bm_code)


            messagebox.showinfo("Bookmarklet", "Đã copy mã Bookmarklet vào Clipboard!\n\nHãy tạo 1 Bookmark mới trên trình duyệt và dán mã này vào phần URL.")





        tk.Button(frame_bm, text="🔗 Copy mã hỗ trợ (Bookmarklet)", command=copy_bookmarklet, bg="#607D8B", fg="white", font=("Arial", 8)).pack(side=tk.RIGHT)


        


        txt_area = scrolledtext.ScrolledText(top, width=85, height=18, font=("Consolas", 9))


        txt_area.pack(padx=10, pady=5)


        


        # Pre-fill current status info


        curr_token = self.config_mgr.get("payload_token") or "N/A"


        cookies = self.config_mgr.get("cookies") or {}


        txt_area.insert(tk.END, f"--- DÁN MÃ cURL HOẶC HEADERS VÀO ĐÂY ---\n")


        txt_area.insert(tk.END, f"(Trạng thái hiện tại: Token {curr_token[:15]}..., Cookies: {len(cookies)} keys)\n\n")





        def paste_from_clipboard():


            try:


                clipboard = self.root.clipboard_get()


                txt_area.delete("1.0", tk.END)


                txt_area.insert(tk.END, clipboard)


            except:


                messagebox.showerror("Lỗi", "Không thể đọc dữ liệu từ Clipboard.")





        def save_and_close():


            raw_text = txt_area.get("1.0", tk.END).strip()


            if not raw_text or "DÁN MÃ cURL" in raw_text:


                top.destroy()


                return


            


            success = self.config_mgr.parse_input(raw_text)
            if success:
                self.vs_client.refresh_from_config()
                top.destroy() # Close window


                


                # Check status and show warning ONLY if truly blocked


                def run_bg_check():


                    status = self.vs_client.check_session_status()


                    def apply_ui():


                        if status == "VALID":
                             self.lbl_session.config(text="🌐 URL: Đang Hoạt Động (Full Mã)", fg="#2E7D32")
                             self.log_sync("✅ URL hoàn toàn hợp lệ, sẵn sàng tải 100% dữ liệu.")
                        elif status == "LIMITED_BYPASSED":
                             self.lbl_session.config(text="🌐 URL: Bypass OK (Tải Đủ 100% Mã)", fg="#2E7D32")
                             self.log_sync("✅ URL bị giới hạn nhưng cơ chế Bypass đã sẵn sàng tải đủ 100% dữ liệu.")
                        elif status == "LIMITED":
                             self.lbl_session.config(text="🌐 URL: Bị Giới Hạn (200 Mã)", fg="#FBC02D")
                             self.log_sync("⚠️ Cảnh báo: URL bị giới hạn 200 mã và cơ chế Bypass không hoạt động.")
                        elif status == "NO_DATA":
                             self.lbl_session.config(text="🌐 URL: Không có dữ liệu", fg="#F57C00")
                             self.log_sync("✅ URL kích hoạt thành công (Hôm nay không có dữ liệu giao dịch).")
                        else:
                             self.lbl_session.config(text="🌐 URL: Lỗi / Token Hết Hạn", fg="#C62828")
                             self.log_sync("❌ URL không hoạt động hoặc Token/Cookie đã hết hạn.")


                             self.lbl_session.config(text="🌐 URL: Mất kết nối", fg="#F57C00")


                             messagebox.showerror("Lỗi Mạng", "Không thể kết nối đến máy chủ Vietstock.")


                             


                    self.root.after(0, apply_ui)


                


                self.log_sync("Đang xác thực bảo mật URL...")


                self.lbl_session.config(text="🌐 URL: Đang xác thực...", fg="#2196F3")


                threading.Thread(target=run_bg_check, daemon=True).start()


            else:


                messagebox.showerror("Lỗi", "Không tìm thấy thông tin hợp lệ trong nội dung bạn dán.")





        btn_row = tk.Frame(top)


        btn_row.pack(pady=10)


        


        tk.Button(btn_row, text="📋 Dán từ Clipboard", command=paste_from_clipboard, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=15).pack(side=tk.LEFT, padx=5)


        tk.Button(btn_row, text="💾 Lưu & Cập Nhật", command=save_and_close, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=15).pack(side=tk.LEFT, padx=5)


        tk.Button(btn_row, text="❌ Hủy", command=top.destroy, padx=15).pack(side=tk.LEFT, padx=5)





    def load_from_cache(self):
        """Trigger cache loading in background thread."""
        self.log_sync("\n--- ĐANG TẢI DỮ LIỆU TỪ BỘ NHỚ ĐỆM (CACHE)... ---", clear=True)
        threading.Thread(target=self._load_from_cache_bg, daemon=True).start()

    def reset_data_cache(self):
        """Xóa toàn bộ dữ liệu đã tính toán (Indicators & Analysis) để buộc hệ thống tính lại."""
        confirm = messagebox.askyesno("Xác nhận Reset", 
            "Hành động này sẽ XÓA TOÀN BỘ dữ liệu đã lưu (Giá + Chỉ báo + Phân tích) trên máy tính.\n\n"
            "Hệ thống sẽ trở về trạng thái mới tinh. Bạn sẽ phải nạp lại CSV hoặc Update từ đầu.\n\n"
            "Bạn có chắc chắn muốn thực hiện không?")
        
        if confirm:
            # 1. Clear Disk
            try:
                count = self.storage.clear_computed_data()
                # storage.clear_computed_data now calls clear_registry internally
            except Exception as e:
                self.log_sync(f"❌ Lỗi khi xóa dữ liệu trên đĩa: {e}")
                messagebox.showerror("Lỗi", f"Không thể xóa một số tệp tin. Có thể chúng đang được mở bởi chương trình khác.\nChi tiết: {e}")
                count = 0
            
            # 2. Clear Memory
            self.data_dict = {}
            self.analysis_cache = {}
            self.backtest_results = {}
            
            # 3. Update UI
            self.lbl_file.config(text="Dữ liệu: Đã Reset (0)", fg="red")
            self.log_sync(f"\n✅ Đã xóa {count} file bộ nhớ đệm thành công.")
            self.log_sync("Bây giờ bạn hãy bấm '📂 Load Cache' hoặc '🌐 Update' để hệ thống tính toán lại theo rule mới.")
            messagebox.showinfo("Hoàn tất", f"Đã reset thành công {count} file. Hãy tải lại dữ liệu để áp dụng rule mới.")





    def _load_from_cache_bg(self):


        try:


            tickers = self.storage.get_all_tickers()


            if not tickers:


                self.log_sync("Chưa có dữ liệu trong cache. Vui lòng bấm 'Cập Nhật Vietstock' hoặc 'Nạp Thêm CSV'.")


                return





            self.data_dict = {}


            self.analysis_cache = {}


            


            registry = self.storage.get_active_registry()
            
            # Rule 2: Kiểm tra hủy niêm yết (10 phiên không giao dịch)
            if registry:
                delisted_tickers = self.storage.identify_delisted_tickers(days_threshold=10)
                if delisted_tickers:
                    self.log_sync(f"[*] Rule 2: Phát hiện {len(delisted_tickers)} mã không giao dịch 10 phiên (hủy niêm yết/ngừng hoạt động).")
                    self.storage.remove_from_registry(delisted_tickers)
                    registry = self.storage.get_active_registry() # Refresh
            
            all_storage_tickers = tickers # Original list on disk
            if registry:
                filtered = [t for t in tickers if t in registry]
                self.log_sync(f"[*] Registry tìm thấy {len(registry)} mã. Lọc bỏ {len(tickers)-len(filtered)} mã đã hủy niêm yết/rác.")
                tickers = filtered
            
            total = len(tickers)
            self.log_sync(f"[*] Đang nạp {total} mã cổ phiếu bằng đa luồng (8-16 workers)...")
            
            # --- PARALLEL LOADING ---
            from concurrent.futures import ThreadPoolExecutor, as_completed
            num_workers = min(16, (os.cpu_count() or 4) * 2)
            
            loaded_count = 0
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                tasks = [(t, self.storage) for t in tickers]
                futures = {executor.submit(load_cache_worker, tea): tea[0] for tea in tasks}
                
                for future in as_completed(futures):
                    t, df, analysis = future.result()
                    if df is not None:
                        self.data_dict[t] = df
                        if analysis:
                            self.analysis_cache[t] = analysis
                    
                    loaded_count += 1
                    if loaded_count % 100 == 0 or loaded_count == total:
                        self.log_sync(f" ---> Tiến trình: Đã nạp {loaded_count}/{total} mã cổ phiếu...")

            # --- FINISH ---
            self._update_breadth_from_cache()
            
            loaded_total = len(self.data_dict)
            analyzed_total = len(self.analysis_cache)
            
            # Cập nhật nhãn trạng thái chi tiết hơn
            status_text = f"Dữ liệu: {loaded_total} mã ({analyzed_total} đã phân tích)"
            self.root.after(0, self.lbl_file.config, {"text": status_text, "fg": "#1A237E"})
            self.log_sync(f"✅ Hoàn tất! Đã nạp {loaded_total} mã (trong đó {analyzed_total} mã đã có kết quả phân tích).")
            self.export_web_json()

            
            # Check for missing indicators in the loaded cache
            missing_trending = [t for t, df in self.data_dict.items() if 'HK_NW' not in df.columns or 'T2_SMA' not in df.columns]
            if missing_trending:
                self.log_sync(f"\n⚠️ LƯU Ý: Có {len(missing_trending)} mã thiếu chỉ báo Trending mới (dữ liệu cũ).")
                self.log_sync("Hệ thống sẽ tự động tính bù khi bạn mở biểu đồ hoặc bạn có thể bấm 'Update' để tính lại toàn bộ.")
            
            # Check for physical cleanup
            if registry and len(all_storage_tickers) > len(tickers) + 50:
                self.log_sync(f"\n⚠️ LƯU Ý: Phát hiện {len(all_storage_tickers) - len(tickers)} mã 'rác' trong ổ cứng.")
                self.log_sync("Hệ thống đã tự động lọc bỏ khi nạp các mã rác khỏi bộ nhớ tạm.")

        except Exception as e:
            self.log_sync(f"⚠️ Lỗi khi nạp cache: {e}")





    def run_vietstock_update(self):


        """Trigger incremental update from Vietstock API."""


        self.log_sync("\n--- BẮT ĐẦU CẬP NHẬT DỮ LIỆU TỪ VIETSTOCK API... ---", clear=True)


        threading.Thread(target=self._vietstock_update_bg, daemon=True).start()





    def _vietstock_update_bg(self):


        try:


            # --- STEP 1: INITIAL CHECK ---


            self.log_sync(f"[*] Bắt đầu kiểm tra tính toàn vẹn dữ liệu (SSoT)...", clear=True)


            self.update_session_ui() # Refresh visual indicator





            # --- STEP 2: INTEGRITY CHECK (LAST 3 TRADING DAYS) ---


            # If any day has < 1000 tickers (heuristic for 200-limit error), we treat it as missing.


            last_date = self.storage.get_last_date()


            missing_dates = self.vs_client.get_missing_dates(last_date)


            


            check_dates = []


            current = last_date or datetime.now()


            while len(check_dates) < 3 and current is not None:


                if current.weekday() < 5:


                    check_dates.append(current.strftime("%Y-%m-%d"))


                current -= timedelta(days=1)


            


            if check_dates:


                self.log_sync(f"[*] Đang quét 3 ngày gần nhất để tìm dữ liệu lỗi: {', '.join(check_dates)}...")


                ticker_counts = self.storage.get_ticker_counts_for_dates(check_dates)


                


                # Threshold < 1200 because total stocks HOSE+HNX+UPCOM should be ~1350+
                # If it's < 1200, it means at least one exchange was truncated at 200.
                bad_dates = [d for d, count in ticker_counts.items() if count > 0 and count < 1200]


                if bad_dates:


                    self.log_sync(f"⚠️ Phát hiện {len(bad_dates)} ngày bị thiếu mã (< 1200 mã): {', '.join(bad_dates)}")


                    self.log_sync(f"[*] Đang xóa và chuẩn bị nạp lại dữ liệu đầy đủ cho các ngày lỗi...")


                    self.storage.delete_specific_dates(bad_dates)


                    # Merge with missing_dates and deduplicate


                    missing_dates = sorted(list(set(missing_dates) | set(bad_dates)))





            # --- FORCE UPDATE CURRENT TRADING DAY ---


            now = datetime.now()


            effective_today = now.date()


            if now.weekday() == 5: effective_today -= timedelta(days=1)


            elif now.weekday() == 6: effective_today -= timedelta(days=2)


            eff_today_str = effective_today.strftime("%Y-%m-%d")


            


            if eff_today_str not in missing_dates:


                missing_dates.append(eff_today_str)


                missing_dates = sorted(missing_dates)





            if not missing_dates:


                self.log_sync("✅ Dữ liệu đã đầy đủ và mới nhất (SSoT).")


                self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để hiển thị kết quả phân tích.")


                return





            self.log_sync(f"Tìm thấy {len(missing_dates)} ngày cần đồng bộ: {', '.join(missing_dates)}")


            


            affected_tickers = set()


            


            # --- STEP 3: FULL UPDATE ---


            for i, d in enumerate(missing_dates):


                day_total = []


                self.log_sync(f"\n--- [Ngày {i+1}/{len(missing_dates)}] ĐANG TẢI: {d} ---")


                


                is_any_limited = False
                for cat_id, cat_name in [(1, "HSX"), (2, "HNX"), (3, "UPCOM")]:
                    try:
                        self.log_sync(f"   [+] Đang nạp sàn {cat_name}...")
                        raw, is_limited = self.vs_client.fetch_market_day(cat_id, d)
                        if is_limited:
                            is_any_limited = True
                        
                        if raw:
                            day_total.extend(raw)
                            self.log_sync(f"   ---> ✅ Đã tải: {len(raw)} mã {cat_name}")

                    except Exception as e:
                        self.log_sync(f"   ! Lỗi {cat_name}: {e}")

                if is_any_limited:
                    msg = "❌ PHÁT HIỆN TOKEN/COOKIE BỊ GIỚI HẠN HOẶC HẾT HẠN:\nVietstock đang chặn tài khoản của bạn (chỉ tải được tối đa 50-200 mã).\nHủy bỏ toàn bộ quá trình tải dữ liệu."
                    self.log_sync(msg)
                    
                    def handle_limit_gui():
                        messagebox.showerror("Token Hết Hạn / Bị Chặn", msg + "\n\nVui lòng dán cURL mới vào cửa sổ cấu hình.")
                        self.open_settings()
                        
                    self.root.after(0, handle_limit_gui)
                    break

                if day_total:
                    total_raw = len(day_total)
                    df_day = self.vs_client.format_to_df(day_total)
                    final_count = len(df_day)
                    
                    # Rule 3: Kiểm tra số lượng mã tối thiểu (Ngưỡng 1200 mã thô)
                    if total_raw < 1200:
                        msg = f"❌ LỖI DỮ LIỆU: Ngày {d} chỉ có {total_raw} mã (Yêu cầu tối thiểu 1200).\nDữ liệu ngày này sẽ bị HỦY BỎ."
                        self.log_sync(msg)
                        messagebox.showerror("Dữ liệu thiếu hụt", msg)
                        continue # Bỏ qua ngày này
                    
                    # Rule 1: Kiểm tra tính đúng đắn qua Top 50 vốn hóa (Bluechips)
                    if 'MarketCap' in df_day.columns:
                        top50 = df_day.sort_values('MarketCap', ascending=False).head(50)
                        # Kiểm tra nếu cả 50 mã đều có Open=High=Low=Close (đứng im tuyệt đối)
                        is_stagnant_top50 = (top50['Open'] == top50['High']) & \
                                            (top50['Open'] == top50['Low']) & \
                                            (top50['Open'] == top50['Close'])
                        
                        if is_stagnant_top50.all():
                            msg = f"❌ LỖI HỆ THỐNG: Ngày {d} phát hiện 50 mã Bluechips đều đứng im.\nNghi vấn dữ liệu Vietstock bị lỗi toàn băng. HỦY BỎ ngày này."
                            self.log_sync(msg)
                            messagebox.showerror("Lỗi dữ liệu toàn băng", msg)
                            continue # Bỏ qua ngày này

                    self.log_sync(f"   [DONE] Tổng nạp thô: {total_raw} mã. Kiểm tra toàn vẹn OK.")
                    
                    # Cập nhật Registry (Danh sách mã niêm yết) - Bây giờ tính cho cả mã đứng im
                    if d == missing_dates[-1]:
                        all_tickers = df_day['Ticker'].unique().tolist()
                        # Filter out covered warrants (keep only 3-letter alphanumeric tickers)
                        all_tickers = [t for t in all_tickers if len(t) == 3 and t.isalnum()]
                        self.storage.save_active_registry(all_tickers)
                        self.log_sync(f"   [*] Đã cập nhật Registry: {len(all_tickers)} mã niêm yết.")


                        


                    # Group by Ticker and sync to storage


                    tickers_in_day = df_day["Ticker"].unique()


                    for idx, (ticker, group) in enumerate(df_day.groupby("Ticker")):


                        try:


                            t_min = self.storage.sync_prices(ticker, group, source='API')


                            if t_min is not None: 


                                affected_tickers.add(ticker)


                            


                            # Log progress every 100 tickers to keep it visual


                            if idx > 0 and idx % 200 == 0:


                                self.log_sync(f"      ... Đang lưu dữ liệu: {idx}/{len(tickers_in_day)} mã...")


                        except: pass


                


            # --- STEP 4: INDEPENDENT INDEX UPDATE (PREVENT INDEX LAG BUG) ---
            self.log_sync("\n--- BẮT ĐẦU ĐỒNG BỘ CHỈ SỐ VNINDEX & HNX-INDEX ---")
            indices = [("VNINDEX", 1, -19), ("HNX-INDEX", 2, -18)]
            for ticker, tid, sid in indices:
                try:
                    idx_last_date = self.storage.get_last_date(ticker)
                    self.log_sync(f"[*] Chỉ số {ticker}: Ngày cuối cùng trong storage: {idx_last_date}")
                    idx_missing_dates = self.vs_client.get_missing_dates(idx_last_date)
                    
                    # Force update current trading day for indices too
                    if eff_today_str not in idx_missing_dates:
                        idx_missing_dates.append(eff_today_str)
                        idx_missing_dates = sorted(idx_missing_dates)
                        
                    if idx_missing_dates:
                        self.log_sync(f"[*] Chỉ số {ticker} cần tải {len(idx_missing_dates)} ngày: {', '.join(idx_missing_dates)}")
                        for idx_d in idx_missing_dates:
                            idx_raw = self.vs_client.fetch_index_day(ticker, tid, sid, idx_d)
                            if idx_raw:
                                day_idx = self.vs_client.format_to_df(idx_raw)
                                t_min = self.storage.sync_prices(ticker, day_idx, source='API')
                                if t_min is not None:
                                    affected_tickers.add(ticker)
                                self.log_sync(f"   ---> ✅ Tải xong Index: {ticker} ({idx_d})")
                    else:
                        self.log_sync(f"✅ Chỉ số {ticker} đã cập nhật đầy đủ.")
                except Exception as e:
                    self.log_sync(f"❌ Lỗi cập nhật Index {ticker}: {e}")





            if not affected_tickers:
                self.log_sync("ℹ️ Dữ liệu giá hiện tại đã khớp 100%. Robot đang kiểm tra lại chỉ báo...")
                current_reg = self.storage.get_active_registry() or []
                self._sync_and_recompute_affected(list(current_reg))
                return
            self.log_sync("--- ĐANG TÍNH TOÁN LẠI CHỈ BÁO VÀ SCANNER (0ms) ---")


            


            # Use progress updates in _sync_and_recompute_affected


            self._sync_and_recompute_affected(list(affected_tickers))


            


            self.log_sync(f"\n✨ TẤT CẢ ĐÃ SẴN SÀNG! Đã cập nhật xong {len(affected_tickers)} mã.")


            self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để hiển thị bảng xếp hạng mới nhất.")





        except Exception as e:


            self.log_sync(f"\n❌ LỖI VIETSTOCK UPDATE: {e}")





    def _sync_and_recompute_affected(self, tickers):


        """


        Optimized incremental processing logic.


        Uses existing memory cache if available to avoid heavy Disk I/O and serialization.


        """


        try:


            items_to_recompute = []


            


            # --- STEP 1: LOAD OR PATCH DATA ---


            for t in tickers:


                # D1: Nếu đã có trong memory thì dùng luôn, không reload disk


                if t in self.data_dict and self.data_dict[t] is not None:


                    items_to_recompute.append((t, self.data_dict[t]))


                else:


                    # FRESH LOAD từ disk


                    df_full = self.storage.load_ticker_data(t)


                    if df_full is not None:


                        self.data_dict[t] = df_full


                        items_to_recompute.append((t, df_full))


            


            total = len(items_to_recompute)


            if total == 0: return


            


            self.log_sync(f" ---> Đang tính toán chỉ báo cho {total} mã...")


            


            cmp = 0


            # INCREASE batch_size to reduce process startup and pickling overhead


            batch_size = 10 


            batches = [items_to_recompute[i:i + batch_size] for i in range(0, total, batch_size)]


            


            # Switched to ThreadPoolExecutor: Because passing 1600+ big DataFrames 


            # across Process boundaries (Pickling) is extremely slow and caused the bottleneck.


            # Pandas and Numpy release the GIL for core calculations anyway.


            num_workers = min((os.cpu_count() or 4) * 2, 16) 


            with ThreadPoolExecutor(max_workers=num_workers) as executor:


                futures = [executor.submit(analyze_batch_worker, b) for b in batches]


                for future in as_completed(futures):


                    batch_results = future.result()


                    for ticker, res in batch_results:
                        if res:
                            self.analysis_cache[ticker] = res
                            # [QUAN TRỌNG] Cập nhật lại data_dict với DF đã được làm giàu (Enriched)
                            # Nếu không cập nhật ở đây, bước HẬU KIỂM sẽ báo thiếu cột và tính lại vô ích.
                            if 'df' in res:
                                self.data_dict[ticker] = res['df']

                            # SAVE TO STORAGE
                            self.storage.save_indicators(ticker, res['df'])
                            self.storage.save_analysis(ticker, res)


                    


                    old_cmp = cmp
                    cmp += len(batch_results)


                    if (cmp // 200) > (old_cmp // 200) or cmp == total:


                         self.log_sync(f"      ... Tiến độ: {cmp}/{total} mã...")





            # --- BƯỚC 4: HẬU KIỂM (COMBINED FINAL FILL-CHECK) ---
            missing_after = []
            for t in tickers:
                df_check = self.data_dict.get(t)
                if df_check is not None:
                    has_trending = 'HK_NW' in df_check.columns and 'T2_SMA' in df_check.columns
                    has_ichimoku = 'CloudTop' in df_check.columns and 'Kijun' in df_check.columns
                    if not (has_trending and has_ichimoku):
                        missing_after.append(t)
            
            if missing_after:
                self.log_sync(f"⚠️ HẬU KIỂM: Phát hiện {len(missing_after)} mã thiếu chỉ số (Trending/Ichimoku). Đang bổ sung...")
                for t in missing_after:
                    try:
                        df_final = enrich_dataframe(self.data_dict[t])
                        self.data_dict[t] = df_final
                        self.storage.save_indicators(t, df_final)
                    except: pass
                self.log_sync("✅ Hậu kiểm hoàn tất. Tất cả mã đã đủ 100% thông số.")
            else:
                self.log_sync("✅ Tuyệt vời! 100% mã nạp vào đã đầy đủ chỉ số Trending & Ichimoku.")

            self.root.after(0, self.lbl_file.config, {"text": f"Dữ liệu: {len(self.analysis_cache)} mã", "fg": "blue"})
            self.log_sync("✅ Cập nhật hoàn tất!")
            self.export_web_json()
            # Refresh What-If cache for key indices after data update
            self._refresh_whatif_cache_bg()

        except Exception as e:
            self.log_sync(f"❌ Lỗi xử lý: {e}")

    def _update_breadth_from_cache(self):
        """Recalculate market breadth from data_dict with 30-day persistence."""
        if len(self.data_dict) < 5:
            self.log_sync("⚠️ Cảnh báo: Cần ít nhất 5 mã cổ phiếu để tính độ rộng.")
            return 
            
        # 1. Get reference dates from VNINDEX
        vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
        idx_df = self.data_dict.get(vn_key)
        if idx_df is None or idx_df.empty: 
            self.log_sync("⚠️ Cảnh báo: Không tìm thấy dữ liệu VNINDEX để làm mốc thời gian.")
            return
        
        self.log_sync("📊 Đang tính toán dữ liệu Độ rộng Thị trường (Time-series)...")
        all_dates = pd.to_datetime(idx_df['Date']).sort_values().unique()
        ref_date = all_dates[-1]
            
        breadth_dfs = []
        processed_count = 0
        
        # Load all active registry tickers to compute breadth completely
        current_reg = self.storage.get_active_registry() or []
        full_data_dict = self.data_dict.copy()
        missing_from_cache = [t for t in current_reg if t not in full_data_dict]
        if missing_from_cache:
            self.log_sync(f"📊 Đang tải song song {len(missing_from_cache)} mã từ storage để tính toán độ rộng...")
            def load_one(t):
                df = self.storage.load_ticker_data(t)
                return t, df
            with ThreadPoolExecutor(max_workers=16) as executor:
                results = executor.map(load_one, missing_from_cache)
                for t, df in results:
                    if df is not None:
                        full_data_dict[t] = df

        # Iterate over full_data_dict
        for ticker, df_sub in full_data_dict.items():
            # Align with market_engine.py filtering
            if ticker in ["VNINDEX", "HNXINDEX", "UPCOM", "VN30", "HNX30", "HAINDEX", "UPCOM-INDEX", "HNX-INDEX"]:
                continue
            
            if len(df_sub) < 50:
                continue
                
            try:
                if df_sub is None or df_sub.empty: continue
                
                # Skip if delisted/suspended > 30 days
                last_ticker_date = pd.to_datetime(df_sub['Date'].iloc[-1])
                if (ref_date - last_ticker_date).days > 30:
                    continue
                
                df_sub_clean = df_sub.drop_duplicates(subset=['Date']).copy()
                df_sub_clean['Date'] = pd.to_datetime(df_sub_clean['Date'])
                df_sub_clean = df_sub_clean.sort_values('Date').reset_index(drop=True)
                
                ma10 = df_sub_clean['MA10'] if 'MA10' in df_sub_clean.columns else df_sub_clean['Close'].rolling(10).mean()
                ma20 = df_sub_clean['MA20'] if 'MA20' in df_sub_clean.columns else df_sub_clean['Close'].rolling(20).mean()
                ma50 = df_sub_clean['MA50'] if 'MA50' in df_sub_clean.columns else df_sub_clean['Close'].rolling(50).mean()
                
                tenkan = df_sub_clean['Tenkan'] if 'Tenkan' in df_sub_clean.columns else (df_sub_clean['High'].rolling(9).max() + df_sub_clean['Low'].rolling(9).min()) / 2
                kijun = df_sub_clean['Kijun'] if 'Kijun' in df_sub_clean.columns else (df_sub_clean['High'].rolling(26).max() + df_sub_clean['Low'].rolling(26).min()) / 2
                spana = df_sub_clean['SpanA'] if 'SpanA' in df_sub_clean.columns else ((tenkan + kijun) / 2).shift(26)
                spanb = df_sub_clean['SpanB'] if 'SpanB' in df_sub_clean.columns else ((df_sub_clean['High'].rolling(52).max() + df_sub_clean['Low'].rolling(52).min()) / 2).shift(26)
                
                raw_temp = pd.DataFrame()
                raw_temp['Date'] = df_sub_clean['Date']
                raw_temp['Close'] = df_sub_clean['Close']
                raw_temp['MA10'] = ma10
                raw_temp['MA20'] = ma20
                raw_temp['MA50'] = ma50
                raw_temp['Tenkan'] = tenkan
                raw_temp['Kijun'] = kijun
                raw_temp['SpanA'] = spana
                raw_temp['SpanB'] = spanb
                
                raw_temp = raw_temp.set_index('Date')
                
                temp = pd.DataFrame(index=all_dates)
                temp.index.name = 'Date'
                
                temp = temp.join(raw_temp, how='left')
                temp = temp.ffill()
                
                temp['Valid'] = temp['Close'].notna().astype(int)
                temp['>MA10'] = (temp['Valid'] & (temp['Close'] > temp['MA10']) & temp['MA10'].notna()).astype(int)
                temp['>MA20'] = (temp['Valid'] & (temp['Close'] > temp['MA20']) & temp['MA20'].notna()).astype(int)
                temp['>MA50'] = (temp['Valid'] & (temp['Close'] > temp['MA50']) & temp['MA50'].notna()).astype(int)
                
                kumo_top = temp[['SpanA', 'SpanB']].max(axis=1)
                temp['>CLOUD'] = (temp['Valid'] & (temp['Close'] > kumo_top) & temp['SpanA'].notna() & temp['SpanB'].notna()).astype(int)
                temp['>TENKAN'] = (temp['Valid'] & (temp['Close'] > temp['Tenkan']) & temp['Tenkan'].notna()).astype(int)
                temp['>KIJUN'] = (temp['Valid'] & (temp['Close'] > temp['Kijun']) & temp['Kijun'].notna()).astype(int)
                
                temp = temp.reset_index()
                breadth_dfs.append(temp)
                processed_count += 1

            except Exception as e: 
                if processed_count < 10:
                    logger.error(f"Error processing breadth for {ticker}: {e}")
                pass 
            
        if breadth_dfs:
            all_breadth = pd.concat(breadth_dfs)
            grouped = all_breadth.groupby('Date').sum()
            valid_counts = grouped['Valid'].replace(0, 1)
            
            mb = pd.DataFrame()
            mb['%MA10'] = (grouped['>MA10'] / valid_counts) * 100
            mb['%MA20'] = (grouped['>MA20'] / valid_counts) * 100
            mb['%MA50'] = (grouped['>MA50'] / valid_counts) * 100
            mb['%ICHI_CLOUD'] = (grouped['>CLOUD'] / valid_counts) * 100
            mb['%ICHI_TENKAN'] = (grouped['>TENKAN'] / valid_counts) * 100
            mb['%ICHI_KIJUN'] = (grouped['>KIJUN'] / valid_counts) * 100
            self.market_breadth = mb.sort_index()
            self.log_sync(f"✅ Đã cập nhật Biểu đồ Độ rộng từ {processed_count} mã cổ phiếu.")
        else:
            self.log_sync("⚠️ Cảnh báo: Không có đủ dữ liệu hợp lệ để tính độ rộng.")

    def export_web_json(self):
        """Export current analysis cache to Output/analysis_results.json for web dashboard."""
        try:
            import json
            self.log_sync("[*] Đang xuất dữ liệu ra JSON cho Web dashboard...")
            if not self.analysis_cache:
                self.log_sync("⚠️ Không có dữ liệu phân tích để xuất.")
                return False
            
            # Load precomputed whatif_results to obtain EV10 for tickers
            whatif_data_cache = {}
            import os
            app_dir = os.path.dirname(os.path.abspath(__file__))
            whatif_results_file = os.path.join(app_dir, "Output", "whatif_results.json")
            if os.path.exists(whatif_results_file):
                try:
                    with open(whatif_results_file, 'r', encoding='utf-8') as f_wi:
                        whatif_data_cache = json.load(f_wi)
                except Exception as e_wi:
                    self.log_sync(f"⚠️ Không thể đọc whatif_results.json để lọc EV: {e_wi}")
                
            categories_meta = {
                "ACCUMULATION": "Tích lũy",
                "BREAKOUT_ACCUMULATION": "Phá Vỡ Tích Lũy",
                "PERFECT_MA": "Perfect MA (Xu hướng tăng mạnh)",
                "HEIKIN_BUY": "Heikin Buy (Tín hiệu mua Heikin Ashi)",
                "UPCLOUD": "UpCloud (Xu hướng tăng trên mây)",
                "WHITE_ADX": "ADX Trắng (Đầu chu kỳ xu hướng)",
                "EARLY": "Điểm mua EARLY (Mua sớm)",
                "ADD_1": "Điểm mua gia tăng 1 (ADD_1)",
                "ADD_2": "Điểm mua gia tăng 2 (ADD_2)",
                "STRONG": "Điểm mua MẠNH (STRONG)"
            }
            
            rules_meta = {k: v["label"] for k, v in CUSTOM_RULES.items()}
            
            filtered_results = {cat: [] for cat in categories_meta.keys()}
            for rule_key in rules_meta.keys():
                filtered_results[rule_key] = []
                
            tickers_analysis = []
            
            for ticker, data in list(self.analysis_cache.items()):
                df = data.get("df")
                if df is None or df.empty:
                    continue
                    
                current_vol = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
                
                res = data.get("adv") or {}
                accum = data.get("accum") or {}
                ma_trend = data.get("ma_trend") or {}
                val = data.get("valuation") or {}
                
                

                current_p = float(df['Close'].iloc[-1]) * 1000
                ep = val.get("price", 0)
                tp = val.get("tp1", 0)
                tp2 = val.get("tp2", 0)
                sl = val.get("cutloss_partial", 0)
                rr_ratio = val.get("rr_ratio", 0)
                val_score = val.get("risk_score", 0)
                risk_pct = val.get("risk_pct", 0)
                action = val.get("action", "WAIT")
                
                matched_categories = []
                if accum.get("is_accumulation", False):
                    matched_categories.append("ACCUMULATION")
                if ma_trend.get("is_perfect_uptrend", False):
                    matched_categories.append("PERFECT_MA")
                    
                # HEIKIN_BUY: tín hiệu buy tại T-0 hoặc T-1 (2 phiên gần nhất)
                buy_2 = False
                if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
                    sig = df.get('HK_BuySignal', pd.Series(dtype=bool)).fillna(False).tail(2)
                    manh = df.get('HK_BuyManh', pd.Series(dtype=bool)).fillna(False).tail(2)
                    buy_2 = bool(sig.any()) or bool(manh.any())
                if buy_2:
                    matched_categories.append("HEIKIN_BUY")
                    
                if len(df) > 0 and 'High' in df.columns and 'Low' in df.columns:
                    last = df.iloc[-1]
                    current_price = last['Close']
                    span_a = last.get('SpanA', 0)
                    span_b = last.get('SpanB', 0)
                    tenkan = last.get('Tenkan', 0)
                    kijun = last.get('Kijun', 0)
                    ma10 = last.get('MA10', 0)
                    ma20 = last.get('MA20', 0)
                    
                    future_span_a = (tenkan + kijun) / 2
                    h52 = df['High'].iloc[-52:].max() if len(df) >= 52 else df['High'].max()
                    l52 = df['Low'].iloc[-52:].min() if len(df) >= 52 else df['Low'].min()
                    future_span_b = (h52 + l52) / 2
                    
                    c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                    c2 = (future_span_a > future_span_b)
                    c3 = (tenkan > kijun)
                    c4 = (ma10 > ma20)
                    if c1 and c2 and c3 and c4:
                        matched_categories.append("UPCLOUD")
                        
                adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
                if adx_color == "WHITE":
                    matched_categories.append("WHITE_ADX")
                    
                if check_breakout_accumulation(df):
                    matched_categories.append("BREAKOUT_ACCUMULATION")
                    
                entry_type = res.get("entry_type")
                if entry_type in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                    matched_categories.append(entry_type)
                    
                matched_rules = []
                for rule_key, r_def in CUSTOM_RULES.items():
                    try:
                        if r_def["func"](df):
                            matched_rules.append(rule_key)
                    except:
                        pass

                # VSA Analysis – đọc từ cache đã tính trong worker (không tính lại)
                vsa_res = data.get("vsa_cached") or data.get("vsa") or {}
                if not vsa_res:
                    from tinvest.vsa_engine import analyze_vsa
                    vsa_res = analyze_vsa(df)
                vsa_dominant = vsa_res.get("dominant", "neutral")
                vsa_score = vsa_res.get("score", 0)

                # MCDX Analysis – đọc từ cache đã tính trong worker (không tính lại)
                mcdx_eval = data.get("mcdx_eval_cached") or {}
                if not mcdx_eval:
                    from tinvest.mcdx_engine import evaluate_mcdx_rules
                    mcdx_eval = evaluate_mcdx_rules(df)
                
                banker_val = float(df['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df.columns else 0.0
                hot_val = float(df['MCDX_HotMoney'].iloc[-1]) if 'MCDX_HotMoney' in df.columns else 0.0
                
                banker_aligned = banker_val
                hot_aligned = min(20.0 - banker_aligned, hot_val)
                retailer_aligned = max(0.0, 20.0 - banker_aligned - hot_val)
                
                banker_pct = round((banker_aligned / 20.0) * 100, 1)
                hot_pct = round((hot_aligned / 20.0) * 100, 1)
                retailer_pct = round((retailer_aligned / 20.0) * 100, 1)
                
                # Generate detailed text report
                try:
                    close_26 = df['Close'].iloc[-26] if len(df) > 26 else df['Close'].iloc[0]
                    heatmap_eval_val = evaluate_heatmap(df)
                    
                    report_input = {
                        "ticker": ticker.upper(),
                        "price": float(df['Close'].iloc[-1]),
                        "date": pd.to_datetime(df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(df['Date'].iloc[-1]) else "N/A",
                        "ichi": data.get("ichi"),
                        "vsa": data.get("vsa"),
                        "ma_trend": data.get("ma_trend"),
                        "adv": data.get("adv"),
                        "accum": data.get("accum"),
                        "valuation": val,
                        "state_rules": data.get("state_rules"),
                        "close_26": float(close_26),
                        "ma20": float(df['MA20'].iloc[-1]) if 'MA20' in df.columns else float(df['Close'].rolling(20).mean().iloc[-1]),
                        "ma50": float(df['MA50'].iloc[-1]) if 'MA50' in df.columns else float(df['Close'].rolling(50).mean().iloc[-1]),
                        "heatmap_eval": heatmap_eval_val,
                        "mcdx_eval": mcdx_eval
                    }
                    report_text = format_report(report_input)
                except Exception as e_rep:
                    report_text = f"Không có báo cáo chi tiết cho mã {ticker}."

                # Portfolio Engine compatibility indicators
                mcdx_banker = float(df['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df.columns else 10
                prev_mcdx_banker = float(df['MCDX_Banker'].iloc[-2]) if len(df) > 1 and 'MCDX_Banker' in df.columns else mcdx_banker
                adx = float(df['ADX'].iloc[-1]) if 'ADX' in df.columns else 20
                ha_color = str(df['HA_Color'].iloc[-1]) if 'HA_Color' in df.columns else 'Green'
                ma20 = float(df['MA20'].iloc[-1]) if 'MA20' in df.columns else current_p / 1000
                vol = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
                vol_avg = float(df['AvgVolume20'].iloc[-1]) if 'AvgVolume20' in df.columns else vol
                avg_vol_10 = float(df['Volume'].tail(10).mean()) if 'Volume' in df.columns and len(df) >= 10 else vol
                
                mcdx_weak = (mcdx_banker < prev_mcdx_banker) and (mcdx_banker < 15)
                adx_low = adx < 20
                heikin_red = (ha_color.lower() == 'red')
                price_below_ma20 = (current_p / 1000) < ma20
                tech_weak = mcdx_weak or adx_low or heikin_red or price_below_ma20
                
                sideways_near_res = False
                p_res_vnd = float(val.get('r1', 0)) * 1000
                if len(df) >= 4 and p_res_vnd > 0:
                    recent_highs = df['High'].iloc[-4:].max() * 1000
                    recent_lows = df['Low'].iloc[-4:].min() * 1000
                    recent_vols = df['Volume'].iloc[-4:].mean()
                    if recent_highs >= p_res_vnd * 0.98 and (recent_highs - recent_lows)/recent_lows < 0.05 and recent_vols > vol_avg:
                        sideways_near_res = True
                        
                # Determine State Signal
                state_val = val.get("state", "NONE")
                sig_map = {
                    "STRONG": "Mua mạnh (Trend Leader)", 
                    "ADD_2": "Gia tăng vị thế 2 (Confirm)",
                    "ADD_1": "Gia tăng vị thế 1 (Pullback)", 
                    "EARLY": "Mua sớm (Thăm dò)", 
                    "NONE": "Chưa có tín hiệu dứt khoát"
                }
                holding_sig = sig_map.get(state_val, "Chưa có tín hiệu dứt khoát")
                
                rt_sig_map = {
                    "BREAKOUT_BUY": "MUA BREAKOUT (Tiền tấn công)", 
                    "PULLBACK_BUY": "MUA PULLBACK (Tiền gốc)",
                    "RETEST_BUY": "MUA RETEST (Điểm Giàu)", 
                    "CONTINUATION_BUY": "GIA TĂNG (Trend Confirm)",
                    "TREND_FOLLOW": "ÔM TIẾP (Theo sóng)", 
                    "TAKE_PROFIT": "CHỐT LÃI (Canh nhả hàng)",
                    "EXIT_OR_SHORT": "THOÁT HÀNG (Rủi ro)", 
                    "EXIT_FAST": "CHẠY NGAY (Bẫy giá)", 
                    "SHORT": "Đứng ngoài hoàn toàn"
                }
                realtime_sig = rt_sig_map.get(data.get("state_rules", {}).get("signal", ""), "")
                state_signal = (realtime_sig if realtime_sig else holding_sig).upper()

                s1_vnd = val.get("s1", 0) * 1000
                r1_vnd = val.get("r1", 0) * 1000
                action_upper = action.upper()
                entry_display = int(ep * 1000) if ep > 0 else None

                if "NO " in action_upper or "ĐỨNG NGOÀI" in action_upper:
                    entry_display = "KHÔNG THAM GIA"
                elif "TAKE PROFIT" in action_upper or "CHỐT LỜI" in action_upper:
                    entry_display = int(s1_vnd) if s1_vnd > 0 else entry_display
                elif "WAIT" in action_upper:
                    entry_display = int(s1_vnd) if s1_vnd > 0 else entry_display
                elif "NÊN THAM GIA" in action_upper or "RẤT NÊN" in action_upper:
                    entry_display = int(current_p)
                elif "YES" in action_upper or "MUA" in action_upper or "CÂN NHẮC" in action_upper:
                    if r1_vnd > 0 and s1_vnd > 0:
                        dist_r1 = r1_vnd - current_p
                        dist_s1 = current_p - s1_vnd
                        if dist_r1 > dist_s1:
                            entry_display = int(current_p)
                        else:
                            entry_display = int(s1_vnd)
                    else:
                        entry_display = int(current_p)
                history = {
                    "dates": [d.strftime("%Y-%m-%d") for d in pd.to_datetime(df['Date'].tail(30))],
                    "closes": df['Close'].tail(30).round(2).tolist()
                }

                ticker_record = {
                    "Ticker": ticker,
                    "Price": int(current_p),
                    "Volume": int(current_vol),
                    "AvgVolume10": int(avg_vol_10),
                    "Entry": entry_display,
                    "Target": int(tp * 1000) if tp > 0 else None,
                    "Target2": int(tp2 * 1000) if tp2 > 0 else None,
                    "ReportText": report_text,
                    "StopLoss": int(sl * 1000) if sl > 0 else None,
                    "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",
                    "RiskScore": int(val_score),
                    "RiskPct": float(risk_pct),
                    "Action": action,
                    "Categories": matched_categories,
                    "Rules": matched_rules,
                    
                    # Extended attributes for lookup
                    "CutlossFull": int(val.get("cutloss_full", 0) * 1000) if val.get("cutloss_full", 0) > 0 else None,
                    "TrailingStop": int(val.get("trailing_stop", 0) * 1000) if val.get("trailing_stop", 0) > 0 else None,
                    "OpportunityScore": int(val.get("opp_score", 0)),
                    "OpportunityDesc": str(val.get("opp_desc", "N/A")),
                    "SafetyRating": int(val.get("topup_safety", 0)),
                    "TopupPrice": int(val.get("topup_price", 0) * 1000) if val.get("topup_price", 0) > 0 else None,
                    "TopupDesc": str(val.get("topup_desc", "N/A")),
                    "AccumulationQuality": str(accum.get("base_quality", "NONE")),
                    "AccumulationNotes": accum.get("notes", []),
                    "AccumulationRangePct": float(accum.get("range_pct", 0.0)),
                    "ReadyToBreak": bool(accum.get("ready_to_break", False)),
                    
                    # Portfolio Engine helpers
                    "Support1": int(val.get("s1", 0) * 1000) if val.get("s1", 0) > 0 else None,
                    "Support2": int(val.get("s2", 0) * 1000) if val.get("s2", 0) > 0 else None,
                    "Resistance1": int(val.get("r1", 0) * 1000) if val.get("r1", 0) > 0 else None,
                    "Resistance2": int(val.get("r2", 0) * 1000) if val.get("r2", 0) > 0 else None,
                    "TrendStatus": str(ma_trend.get("trend_status", "Sideway")),
                    "TechWeak": bool(tech_weak),
                    "SidewaysNearRes": bool(sideways_near_res),
                    "StateSignal": state_signal,
                    "AntiTrap": bool(data.get("state_rules", {}).get("metrics", {}).get("anti_trap_block", False)),
                    "AvoidEntry": bool(data.get("state_rules", {}).get("avoid_entry", False)),
                    
                    # MCDX Cash Flow
                    "MCDX": {
                        "banker_pct": banker_pct,
                        "hot_pct": hot_pct,
                        "retailer_pct": retailer_pct,
                        "status": str(mcdx_eval.get("status", "N/A")),
                        "action": str(mcdx_eval.get("action", "N/A")),
                        "details": str(mcdx_eval.get("details", "N/A"))
                    },
                    
                    # Technical Diagnostics Table
                    "Diagnostics": {
                        "rsi": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("status", "N/A")), 
                                "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("action", "N/A"))},
                        "macd": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("status", "N/A")), 
                                 "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("action", "N/A"))},
                        "adx": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("status", "N/A")), 
                                "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("action", "N/A"))},
                        "ichimoku": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("status", "N/A")), 
                                     "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("action", "N/A"))},
                        "ma": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("status", "N/A")), 
                               "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("action", "N/A"))},
                        "vsa": {"status": f"VSA Dominant: {vsa_dominant.upper()}", 
                                "action": f"VSA Score: {vsa_score}/4"}
                    },
                    
                    # History for Chart.js
                    "History": history
                }
                # Only append if ticker is in active registry (not delisted/warrants)
                current_reg = self.storage.get_active_registry() or set()
                if ticker in current_reg:
                    tickers_analysis.append(ticker_record)
                    for cat in matched_categories:
                        filtered_results[cat].append(ticker)
                    for rule_key in matched_rules:
                        filtered_results[rule_key].append(ticker)
            
            # Format market breadth
            mb_data = {}
            breadth_ma20 = 50.0
            breadth_ma50 = 50.0
            if hasattr(self, 'market_breadth') and self.market_breadth is not None and not self.market_breadth.empty:
                mb = self.market_breadth
                breadth_ma20 = float(mb['%MA20'].iloc[-1])
                breadth_ma50 = float(mb['%MA50'].iloc[-1])
                mb_dates = [d.strftime("%Y-%m-%d") for d in mb.index]
                
                # Align VNINDEX Closes
                vn_closes = []
                vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
                df_vn = self.data_dict.get(vn_key)
                if df_vn is not None and not df_vn.empty:
                    df_vn_aligned = df_vn.copy()
                    df_vn_aligned['Date'] = pd.to_datetime(df_vn_aligned['Date'])
                    df_vn_aligned = df_vn_aligned.set_index('Date')
                    
                    for d in mb.index:
                        if d in df_vn_aligned.index:
                            vn_closes.append(float(df_vn_aligned.loc[d, 'Close']))
                        else:
                            vn_closes.append(vn_closes[-1] if vn_closes else 0.0)
                else:
                    vn_closes = [0.0] * len(mb)

                mb_data = {
                    "dates": mb_dates,
                    "MA10": mb['%MA10'].round(2).tolist(),
                    "MA20": mb['%MA20'].round(2).tolist(),
                    "MA50": mb['%MA50'].round(2).tolist(),
                    "ICHI_CLOUD": mb['%ICHI_CLOUD'].round(2).tolist(),
                    "ICHI_TENKAN": mb['%ICHI_TENKAN'].round(2).tolist(),
                    "ICHI_KIJUN": mb['%ICHI_KIJUN'].round(2).tolist(),
                    "VNINDEX_Closes": vn_closes
                }

            # Market Indices Analysis
            market_indices = {}
            for index_ticker in ["VNINDEX", "HNX-INDEX"]:
                idx_df = self.data_dict.get(index_ticker)
                if idx_df is not None and not idx_df.empty:
                    try:
                        from tinvest.market_engine import analyze_market_index, analyze_momentum_divergence
                        from tinvest.ichimoku_engine import analyze_ichimoku
                        from tinvest.vsa_engine import analyze_vsa
                        from tinvest.ma_engine import analyze_ma_trend
                        from tinvest.data_loader import enrich_dataframe
                        from tinvest.advanced_entry import classify_entry
                        from tinvest.valuation_engine import evaluate_stock_valuation
                        from tinvest.state_engine import evaluate_state_rules
                        from tinvest.analyzer import evaluate_heatmap
                        from tinvest.mcdx_engine import evaluate_mcdx_rules
                        
                        df_rich = enrich_dataframe(idx_df.copy())
                        mom = analyze_momentum_divergence(idx_df)
                        signals = classify_entry(df_rich)
                        val = evaluate_stock_valuation("INDEX", df_rich, signals)
                        sr = {"s1": float(val.get("s1", 0)), "s2": float(val.get("s2", 0)),
                              "r1": float(val.get("r1", 0)), "r2": float(val.get("r2", 0))}
                        
                        state_rules = evaluate_state_rules(df_rich)
                        heatmap_eval = evaluate_heatmap(df_rich)
                        mcdx_eval = evaluate_mcdx_rules(df_rich)
                        
                        res_regime = analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
                        
                        st_pri_raw = state_rules.get('primary', '')
                        ftd_on = res_regime.get('ftd_active', False)
                        dist_n = res_regime.get('distribution_count', 0)
                        
                        alloc = "10-30%"
                        alloc_note = "Chưa xác định rõ"
                        
                        if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                            if ftd_on and dist_n <= 2:
                                alloc = "80-100%"
                                alloc_note = "Xu hướng mạnh, FTD xác nhận, phân phối ít -> ALL IN được"
                            elif ftd_on and dist_n > 2:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng phân phối đang tăng -> vẫn giữ tỷ trọng cao nhưng sẵn sàng hạ"
                            else:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng chưa có FTD xác nhận -> chưa nên full"
                        elif st_pri_raw == 'WEAK_UPTREND':
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Tăng yếu dần nhưng FTD còn sống -> canh giữ, giảm dần nếu chớm gãy"
                            else:
                                alloc = "30-50%"
                                alloc_note = "Tăng yếu dần, không có FTD -> cẩn thận chuyển giao"
                        elif st_pri_raw in ['RANGE', 'SQUEEZE', 'SIDEWAY', 'NEUTRAL']:
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Đang tích lũy/chuyển giao trong nhịp hồi có FTD -> ưu tiên nắm giữ cổ phiếu Leader"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Chưa rõ xu hướng, đang tích lũy/trung tính -> giữ tiền mặt chờ xác nhận"
                        elif st_pri_raw == 'WEAK_DOWNTREND':
                            if ftd_on:
                                alloc = "40-60%"
                                alloc_note = "Nhịp điều chỉnh/nghỉ chân trong đà hồi phục có FTD -> CƠ HỘI GOM HÀNG"
                            elif dist_n >= 3:
                                alloc = "0-15%"
                                alloc_note = "Giảm nhẹ + phân phối nhiều -> RỦI RO CAO, BÁN HẠ TỶ TRỌNG gấp"
                            else:
                                alloc = "15-30%"
                                alloc_note = "Điều chỉnh bình thường -> giữ ít, chờ xem có giữ nền không"
                        elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START']:
                            alloc = "0-10%"
                            alloc_note = "Gãy xu hướng xác nhận -> BÁN SẠCH, RA NGOÀI"
                        elif st_pri_raw == 'RECOVERY':
                            if ftd_on:
                                alloc = "50-75%"
                                alloc_note = "Hồi phục ổn định có FTD -> ưu tiên nắm giữ & quan sát điểm gia tăng"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Hồi phục kỹ thuật, chưa có FTD -> chỉ nên test tỷ trọng nhỏ"
                        else:
                            reg_str = res_regime.get('regime', 'UNKNOWN')
                            if reg_str == "STABLE_RECOVERY":
                                alloc, alloc_note = "50-75%", "Hồi phục ổn định trên MA20"
                            elif reg_str == "RECOVERY":
                                alloc, alloc_note = "30-50%", "Đang nỗ lực hồi phục"
                            else:
                                alloc = "10-30%"
                                alloc_note = "Chưa xác định rõ -> giữ ít phòng thủ"
                                
                        st_avoid = state_rules.get('avoid_entry', False)
                        if st_avoid:
                            if st_pri_raw in ['UPTREND', 'UPTREND_START', 'WEAK_UPTREND', 'RECOVERY'] and ftd_on:
                                if alloc == "80-100%": alloc = "60-80%"
                                elif alloc == "60-80%": alloc = "40-60%"
                                elif alloc == "50-70%": alloc = "30-50%"
                                elif alloc == "50-75%": alloc = "40-60%"
                                alloc_note = "⚠️ CẢNH BÁO: Thị trường quá nhiệt / MCDX phân phối -> Ưu tiên nắm giữ, hạn chế mua đuổi"
                            elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START', 'MARKET_WEAKENING']:
                                alloc = "0-10%"
                                alloc_note = "Bộ Lọc Rủi Ro đang BẬT -> CẤM MUA MỚI"
                            else:
                                alloc = "10-20%"
                                alloc_note = "Thị trường lưỡng lự, bộ lọc rủi ro đang bật -> Tỷ trọng thấp"

                        cleaned_sr = {k: float(v) for k, v in sr.items()}
                        
                        market_indices[index_ticker] = {
                            "price": float(idx_df['Close'].iloc[-1]),
                            "date": pd.to_datetime(idx_df['Date'].iloc[-1]).strftime("%Y-%m-%d") if not pd.isna(idx_df['Date'].iloc[-1]) else "N/A",
                            "regime": str(res_regime.get("regime", "UNKNOWN")),
                            "action": str(res_regime.get("action", "WAIT")),
                            "ftd_active": bool(res_regime.get("ftd_active", False)),
                            "ftd_date": str(res_regime.get("ftd_date", "N/A")),
                            "ftd_quality": str(res_regime.get("ftd_quality", "N/A")),
                            "ra_day": int(res_regime.get("ra_day", 0)),
                            "distribution_count": int(res_regime.get("distribution_count", 0)),
                            "support_resistance": cleaned_sr,
                            "alloc": str(alloc),
                            "alloc_note": str(alloc_note),
                            "diagnostics": {
                                "ma": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("status", "N/A")), 
                                       "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ma", {}).get("action", "N/A"))},
                                "ichimoku": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("status", "N/A")), 
                                             "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("ichimoku", {}).get("action", "N/A"))},
                                "rsi": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("status", "N/A")), 
                                        "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("rsi", {}).get("action", "N/A"))},
                                "macd": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("status", "N/A")), 
                                         "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("macd", {}).get("action", "N/A"))},
                                "adx": {"status": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("status", "N/A")), 
                                        "action": str(val.get("tech_health", {}).get("diagnostics", {}).get("adx", {}).get("action", "N/A"))}
                            },
                            "heatmap_eval": str(heatmap_eval),
                            "mcdx_eval": {
                                "status": str(mcdx_eval.get("status", "N/A")),
                                "action": str(mcdx_eval.get("action", "N/A")),
                                "details": str(mcdx_eval.get("details", "N/A")),
                                "banker_pct": float(df_rich['MCDX_Banker'].iloc[-1]) if 'MCDX_Banker' in df_rich.columns else 0.0,
                                "hot_pct": float(df_rich['MCDX_Hot'].iloc[-1]) if 'MCDX_Hot' in df_rich.columns else 0.0,
                                "retailer_pct": float(df_rich['MCDX_Retailer'].iloc[-1]) if 'MCDX_Retailer' in df_rich.columns else 0.0
                            },
                            "state_rules": {
                                "primary": str(state_rules.get('primary', 'N/A')),
                                "secondary": str(state_rules.get('secondary', 'N/A')),
                                "signal": str(state_rules.get('signal', 'N/A')),
                                "regime": str(state_rules.get('regime', 'N/A')),
                                "confidence": int(state_rules.get('confidence', 0)),
                                "avoid_entry": bool(state_rules.get('avoid_entry', False)),
                                "adx": float(state_rules.get('metrics', {}).get('adx', 0.0)),
                                "macd_hist": float(state_rules.get('metrics', {}).get('hist', 0.0)),
                                "trend_bias": float(state_rules.get('metrics', {}).get('trend_bias', 0.0)),
                                "vol_spike": bool(state_rules.get('metrics', {}).get('vol_spike', False)),
                                "vol_dry": bool(state_rules.get('metrics', {}).get('vol_dry', False)),
                                "strong_trend": bool(state_rules.get('metrics', {}).get('strong_trend', False)),
                                "breakout_up": bool(state_rules.get('metrics', {}).get('breakout_up', False)),
                                "dist_ma20": float(state_rules.get('metrics', {}).get('dist_ma20', 0.0)),
                                "rsi": float(state_rules.get('metrics', {}).get('rsi', 50.0))
                            },
                            "alloc_note": str(alloc_note)
                        }
                    except Exception as e_idx:
                        self.log_sync(f"⚠️ Lỗi phân tích Index {index_ticker}: {e_idx}")

            # Write to Output/analysis_results.json
            app_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(app_dir, "Output")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, "analysis_results.json")
            
            from datetime import timezone
            ict_time = datetime.now(timezone.utc) + timedelta(hours=7)
            last_update_str = ict_time.strftime("%Y-%m-%d %H:%M:%S")

            # ── MERGE-BEFORE-WRITE: giữ lại dữ liệu các mã không được tính lại lần này ──
            # Tránh việc Update (chỉ tính ~N mã bị ảnh hưởng) ghi đè và xóa mất
            # toàn bộ phân tích của các mã còn lại trong file JSON cũ.
            existing_tickers_map = {}
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f_old:
                        old_data = json.load(f_old)
                    for rec in old_data.get("tickers_analysis", []):
                        if isinstance(rec, dict) and "Ticker" in rec:
                            existing_tickers_map[rec["Ticker"]] = rec
                    # Preserve old market_breadth and market_indices if not regenerated
                    if not mb_data and old_data.get("market_breadth"):
                        mb_data = old_data["market_breadth"]
                    if not market_indices and old_data.get("market_indices"):
                        market_indices = old_data["market_indices"]
                    self.log_sync(f"💾 Merge: đọc {len(existing_tickers_map)} mã từ JSON cũ để hợp nhất.")
                except Exception as e_merge:
                    self.log_sync(f"⚠️ Không thể đọc JSON cũ để merge: {e_merge}")

            # Overwrite existing with freshly computed (new data wins)
            new_tickers_set = {r["Ticker"] for r in tickers_analysis}
            for ticker_key, old_rec in existing_tickers_map.items():
                if ticker_key not in new_tickers_set:
                    tickers_analysis.append(old_rec)
                    # Rebuild filtered_results for preserved tickers
                    for cat in old_rec.get("Categories", []):
                        if cat in filtered_results:
                            filtered_results[cat].append(ticker_key)
                    for rule_key in old_rec.get("Rules", []):
                        if rule_key in filtered_results:
                            filtered_results[rule_key].append(ticker_key)

            self.log_sync(f"💾 Tổng sau merge: {len(tickers_analysis)} mã (mới/cập nhật: {len(new_tickers_set)}, giữ từ cũ: {len(tickers_analysis)-len(new_tickers_set)}).")

            final_output = {
                "last_update": last_update_str,
                "market_breadth": mb_data,
                "market_indices": market_indices,
                "categories_meta": categories_meta,
                "rules_meta": rules_meta,
                "tickers_analysis": tickers_analysis,
                "filtered_results": filtered_results
            }

            import tempfile
            temp_fd, temp_path = tempfile.mkstemp(dir=output_dir, prefix="analysis_results_tmp_")
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(final_output, f, ensure_ascii=False, indent=2)
                if os.path.exists(output_file):
                    os.replace(temp_path, output_file)
                else:
                    os.rename(temp_path, output_file)
            except Exception as e_write:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                raise e_write
                
            self.log_sync(f"✅ Đã xuất {len(tickers_analysis)} mã ra {output_file}.")
            
            # Export individual history JSONs for Web Dashboard (chart rendering)
            self.log_sync("📊 Đang xuất dữ liệu lịch sử JSON cho Web Dashboard...")
            try:
                from tinvest.chart_exporter import export_ticker_history_json
                export_ticker_history_json(self.data_dict, self.analysis_cache, output_dir)
            except Exception as e_hist:
                self.log_sync(f"⚠️ Cảnh báo: Lỗi khi xuất history JSON: {e_hist}")
            
            return True
        except Exception as e:
            self.log_sync(f"❌ Lỗi xuất dữ liệu Web JSON: {e}")
            return False

    def git_push_to_web(self):
        """Automatically stage, commit, and push Output/analysis_results.json to GitHub."""
        def run_push():
            try:
                self.log_sync("\n--- ĐANG ĐỒNG BỘ LÊN GITHUB PAGES... ---")
                
                # Make sure file exists first
                self.export_web_json()
                
                import subprocess
                app_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Git status check
                res = subprocess.run(["git", "status"], cwd=app_dir, capture_output=True, text=True)
                if res.returncode != 0:
                    self.log_sync("❌ Thư mục không phải Git repository hoặc Git chưa được cài đặt.")
                    return
                
                # Git add Output/analysis_results.json and Output/history/
                self.log_sync("   [+] Đang thêm file dữ liệu vào Git...")
                subprocess.run(["git", "add", "Output/analysis_results.json"], cwd=app_dir, check=True)
                subprocess.run(["git", "add", "Output/history/"], cwd=app_dir, check=True)
                
                # Git commit
                self.log_sync("   [+] Đang tạo commit...")
                commit_msg = f"Update web dashboard data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                diff_res = subprocess.run(["git", "diff", "--quiet", "--cached"], cwd=app_dir)
                if diff_res.returncode == 0:
                    self.log_sync("ℹ️ Không có thay đổi nào mới để commit. Tiến hành push...")
                else:
                    subprocess.run(["git", "commit", "-m", commit_msg], cwd=app_dir, check=True)
                
                # Git push
                self.log_sync("   [+] Đang push lên GitHub (vui lòng chờ)...")
                push_res = subprocess.run(["git", "push"], cwd=app_dir, capture_output=True, text=True)
                
                if push_res.returncode == 0:
                    self.log_sync("🎉 ĐỒNG BỘ THÀNH CÔNG! Dashboard web sẽ được cập nhật sau vài giây.")
                    messagebox.showinfo("Đồng Bộ Web", "Đã đồng bộ dữ liệu lên web thành công!\nBạn có thể truy cập dashboard trên điện thoại.")
                else:
                    self.log_sync(f"❌ Git Push thất bại:\n{push_res.stderr}")
                    messagebox.showerror("Lỗi Đồng Bộ", f"Git Push thất bại:\n{push_res.stderr}\n\nVui lòng kiểm tra quyền truy cập/SSH key hoặc mạng internet.")
                    
            except Exception as e:
                self.log_sync(f"❌ Lỗi đồng bộ GitHub: {e}")
                messagebox.showerror("Lỗi Hệ Thống", f"Lỗi đồng bộ GitHub: {e}")
                
        threading.Thread(target=run_push, daemon=True).start()




    def run_analyzer(self):
        if not self.data_dict:   
            messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")
            return
            
        ticker = self.entry_ticker.get().strip().upper()
        if not ticker: return
            
        df = self.data_dict.get(ticker)
        if df is None:
            messagebox.showwarning("Không tìm thấy", f"Mã '{ticker}' không tồn tại hoặc dữ liệu <25 ngày!")
            return
            
        self.log_sync(f"Đang phân tích các tín hiệu của hãng {ticker} (cập nhật mới nhất)...", clear=True)
        self.root.update()
        
        try:
            from tinvest.analyzer import analyze_stock, format_report
            result = analyze_stock(ticker, df)
            report = format_report(result)
            self.log_sync(f"BÁO CÁO CHI TIẾT MÃ: {ticker}\n" + report, clear=True)
        except Exception as e:
            self.log_sync(f"Lỗi phân tích: {str(e)}")

    def run_heatmap_chart(self):
        ticker = self.entry_ticker.get().strip().upper()
        if not ticker: return
        df = self.data_dict.get(ticker)
        if df is None or len(df) < 20:
            messagebox.showwarning("Không đủ dữ liệu", f"Mã '{ticker}' cần ít nhất 20 phiên để tính Heatmap.")
            return
        
        self.log_sync(f"Đang khởi tạo Bản đồ nhiệt cho mã {ticker} (1 năm gần nhất)...", clear=True)
        self.show_heatmap_window(ticker, df)

    def show_heatmap_window(self, ticker, df_full):
        try:
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
            from tinvest.data_loader import enrich_dataframe

            # --- PREPARE DATA (Last 250 bars ~ 1 year) ---
            count = 250
            # Comprehensive check for all technical heatmap columns
            required_cols = [
                'HM_PFE', 'HM_STC', 'HM_MoneyFlow',
                'HM_Flower_Open', 'HM_Flower_High', 'HM_Flower_Low', 'HM_Flower_Close',
                'HM_Band_Hi', 'HM_Band_KH', 'HM_Band_KM', 'HM_Band_KL', 'HM_Band_Lo'
            ]
            if not all(col in df_full.columns for col in required_cols):
                self.log_sync(f"Thiếu cột kỹ thuật cho {ticker}. Đang tính toán lại...", clear=True)
                df_full = enrich_dataframe(df_full)
                self.data_dict[ticker] = df_full

            self.log_sync(f"Dữ liệu {ticker} đã sẵn sàng. Đang vẽ biểu đồ...", clear=False)
            df = df_full.tail(count).copy().reset_index(drop=True)
            x_idx = np.arange(len(df))
            dates = df['Date']

            # --- SETUP FIGURE ---
            plt.style.use('dark_background')
            fig = plt.figure(figsize=(16, 10))
            gs = gridspec.GridSpec(2, 1, height_ratios=[2, 1], hspace=0.1)
            
            ax_hm = fig.add_subplot(gs[0])
            ax_vni = fig.add_subplot(gs[1], sharex=ax_hm)
            
            fig.patch.set_facecolor('black')
            ax_hm.set_facecolor('#080808')
            ax_vni.set_facecolor('#080808')

            # --- 1. PLOT HEATMAP (Top Panel - ax_hm) ---
            # Bands Long
            if 'HM_Band_Long_Hr' in df.columns and 'HM_Band_Long_Ls' in df.columns:
                ax_hm.fill_between(x_idx, df['HM_Band_Long_Ls'], df['HM_Band_Long_Hr'], 
                               color='#1A1A1A', alpha=0.3)

            # Bands Short (Heatmap Clouds)
            if 'HM_Band_Hi' in df.columns:
                ax_hm.fill_between(x_idx, df['HM_Band_KH'], df['HM_Band_Hi'], color='#003737', alpha=0.6)
                ax_hm.fill_between(x_idx, df['HM_Band_KM'], df['HM_Band_KH'], color='#3C0F00', alpha=0.5)
                ax_hm.fill_between(x_idx, df['HM_Band_KL'], df['HM_Band_KM'], color='#000053', alpha=0.5)
                ax_hm.fill_between(x_idx, df['HM_Band_Lo'], df['HM_Band_KL'], color='#2B2B59', alpha=0.6)

            # Flower Candlesticks
            f_o, f_h, f_l, f_c = df['HM_Flower_Open'], df['HM_Flower_High'], df['HM_Flower_Low'], df['HM_Flower_Close']
            up_f = (f_c >= f_o) & (df['HM_MoneyFlow'] == 1)
            dn_f = (f_c < f_o) & (df['HM_MoneyFlow'] == -1)
            neutral_f = ~(up_f | dn_f)
            
            ax_hm.vlines(x_idx[up_f], f_l[up_f], f_h[up_f], color='#E0E0E0', linewidth=1)
            ax_hm.vlines(x_idx[dn_f], f_l[dn_f], f_h[dn_f], color='#E60000', linewidth=1)
            ax_hm.vlines(x_idx[neutral_f], f_l[neutral_f], f_h[neutral_f], color='#FFD700', linewidth=1)
            
            ax_hm.bar(x_idx[up_f], f_c[up_f] - f_o[up_f], bottom=f_o[up_f], color='white', width=0.6, alpha=0.9)
            ax_hm.bar(x_idx[dn_f], f_o[dn_f] - f_c[dn_f], bottom=f_c[dn_f], color='#E60000', width=0.6, alpha=0.9)
            ax_hm.bar(x_idx[neutral_f], np.abs(f_c[neutral_f] - f_o[neutral_f]), bottom=np.minimum(f_o[neutral_f], f_c[neutral_f]), 
                   color='#FFFF00', width=0.6, alpha=0.9)

            ax_hm.set_title(f"BẢN ĐỒ NHIỆT THỊ TRƯỜNG - AIC: {ticker}", fontsize=16, fontweight='bold', color='aqua')
            ax_hm.set_ylabel("Price", color='white')
            ax_hm.grid(True, color='#222222', linestyle=':', alpha=0.3)
            plt.setp(ax_hm.get_xticklabels(), visible=False)

            # --- 2. PLOT NORMAL CANDLES (Bottom Panel - ax_vni) ---
            # Using the same 'df' as the top panel for consistency
            v_o, v_h, v_l, v_c = df['Open'], df['High'], df['Low'], df['Close']
            up_v = v_c >= v_o
            dn_v = v_c < v_o
            
            # Normal Candlesticks (Green/Red)
            ax_vni.vlines(x_idx, v_l, v_h, color='white', linewidth=0.5, alpha=0.5)
            ax_vni.bar(x_idx[up_v], v_c[up_v] - v_o[up_v], bottom=v_o[up_v], color='#00E600', width=0.6) # Green
            ax_vni.bar(x_idx[dn_v], v_o[dn_v] - v_c[dn_v], bottom=v_c[dn_v], color='#FF0000', width=0.6) # Red
            
            ax_vni.set_title(f"BIỂU ĐỒ GIÁ (NẾN THƯỜNG) - {ticker}", fontsize=12, color='white', pad=10)
            ax_vni.set_ylabel("Price", color='white')
            ax_vni.grid(True, color='#222222', linestyle=':', alpha=0.3)

            # --- 3. FORMATTING ---
            # Date X-axis labels on bottom plot
            date_labels = dates.dt.strftime('%d/%m/%y').tolist()
            import matplotlib.ticker as ticker_lib
            ax_vni.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
            ax_vni.xaxis.set_major_locator(ticker_lib.MaxNLocator(10))
            
            for axis_obj in [ax_hm, ax_vni]:
                axis_obj.tick_params(colors='white')
                for spine in axis_obj.spines.values():
                    spine.set_color('#333333')

            plt.tight_layout()
            plt.show(block=False)
        except Exception as e:
            logger.error(f"Error showing heatmap: {e}")
            import traceback
            traceback.print_exc()


    def run_greenpink_chart(self):
        ticker = self.entry_ticker.get().strip().upper()
        if not ticker: return
        df = self.data_dict.get(ticker)
        if df is None or len(df) < 30:
            messagebox.showwarning("Không đủ dữ liệu", f"Mã '{ticker}' cần ít nhất 30 phiên để phân tích GreenPink.")
            return
        
        self.log_sync(f"Đang mở Biểu đồ GreenPink cho mã {ticker} (150 phiên gần nhất)...", clear=True)
        self.show_greenpink_window(ticker, df)

    def show_greenpink_window(self, ticker, df_full):
        try:
            import matplotlib.pyplot as plt
            from tinvest.data_loader import enrich_dataframe

            plt.style.use('dark_background')

            # --- ROBUST DATA CHECK ---
            if 'GP_xFast' not in df_full.columns or 'OCT_A1' not in df_full.columns:
                self.log_sync("Dữ liệu GreenPink/Octopus bị thiếu. Đang tính toán bổ sung...", clear=True)
                df_full = enrich_dataframe(df_full)
                self.data_dict[ticker] = df_full

            # --- CALCULATE RS14 & RS52 ---
            if 'RS14' not in df_full.columns or 'RS52' not in df_full.columns:
                df_vn = None
                if hasattr(self, 'data_dict'):
                    vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), None)
                    df_vn = self.data_dict.get(vn_key) if vn_key else None
                if df_vn is not None and not df_vn.empty:
                    df_vn_indexed = df_vn.set_index('Date')
                    bench_close = df_full['Date'].map(df_vn_indexed['Close']).ffill().bfill()
                    rs_raw = df_full['Close'] / (bench_close + 1e-10)
                    
                    # RS52: 52 weeks = 260 bars
                    rs52_min = rs_raw.rolling(window=260, min_periods=1).min()
                    rs52_max = rs_raw.rolling(window=260, min_periods=1).max()
                    df_full['RS52'] = 100 * (rs_raw - rs52_min) / (rs52_max - rs52_min + 0.0001)
                    
                    # RS14: 14 weeks = 70 bars
                    rs14_min = rs_raw.rolling(window=70, min_periods=1).min()
                    rs14_max = rs_raw.rolling(window=70, min_periods=1).max()
                    df_full['RS14'] = 100 * (rs_raw - rs14_min) / (rs14_max - rs14_min + 0.0001)
                else:
                    df_full['RS14'] = 50.0
                    df_full['RS52'] = 50.0

            # 1. Prepare Data (Last 150 bars)
            count = 150
            df = df_full.tail(count).copy().reset_index(drop=True)
            x_idx = np.arange(len(df))
            
            # 2. Setup Figure with 3 subplots
            fig, (ax, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1]})
            fig.patch.set_facecolor('black') 
            ax.set_facecolor('black')
            ax2.set_facecolor('black')
            ax3.set_facecolor('black')
            
            # --- TOP SUBPLOT: GREENPINK ---
            # 3. Plot Cloud (E14 vs E21)
            e14 = df['GP_E14']
            e21 = df['GP_E21']
            c = df['Close']
            green_mask = (c > e14) & (c > e21)
            pink_mask = ~green_mask
            ax.fill_between(x_idx, e14, e21, where=green_mask, color='#00FF00', alpha=0.3, interpolate=True, linewidth=0)
            ax.fill_between(x_idx, e14, e21, where=pink_mask, color='#FF69B4', alpha=0.3, interpolate=True, linewidth=0)

            # 4. Plot xFast and xSlow
            ax.plot(x_idx, df['GP_xFast'], color='lime', linewidth=2.5, label='xFast (Green)')
            ax.plot(x_idx, df['GP_xSlow'], color='red', linewidth=2.5, label='xSlow (Red)')

            # 5. Plot Bollinger Bands on xSlow
            ax.plot(x_idx, df['GP_BB_Top'], color='blue', linewidth=1.2, alpha=0.8, label='BB Top (xSlow)')
            ax.plot(x_idx, df['GP_BB_Bot'], color='blue', linewidth=1.2, alpha=0.8, label='BB Bot (xSlow)')
            ax.fill_between(x_idx, df['GP_BB_Bot'], df['GP_BB_Top'], color='blue', alpha=0.1)

            # 6. Plot Candlesticks
            close_val = df['Close']
            open_val = df['Open']
            high_val = df['High']
            low_val = df['Low']
            up_mask = close_val >= open_val
            down_mask = ~up_mask
            if up_mask.any():
                ax.vlines(x_idx[up_mask], low_val[up_mask], high_val[up_mask], color='#00FF00', linewidth=1.0)
                ax.bar(x_idx[up_mask], close_val[up_mask] - open_val[up_mask], bottom=open_val[up_mask], color='#00FF00', width=0.6)
            if down_mask.any():
                ax.vlines(x_idx[down_mask], low_val[down_mask], high_val[down_mask], color='#FF0000', linewidth=1.0)
                ax.bar(x_idx[down_mask], open_val[down_mask] - close_val[down_mask], bottom=close_val[down_mask], color='#FF0000', width=0.6)

            # --- BOTTOM SUBPLOT: OCTOPUS (MACD MCGINLEY) ---
            ax2.plot(x_idx, df['OCT_A1'], color='white', linewidth=0.8, alpha=0.3) # Reference line
            
            # Plot A1 and B1 (Mirror) with dynamic color dots/line
            from matplotlib.collections import LineCollection
            oct_colors = df['OCT_Color'].iloc[1:].tolist()
            
            a1_np = df['OCT_A1'].to_numpy()
            points_a1 = np.array([x_idx, a1_np]).T.reshape(-1, 1, 2)
            segments_a1 = np.concatenate([points_a1[:-1], points_a1[1:]], axis=1)
            lc_a1 = LineCollection(segments_a1, colors=oct_colors, linewidths=2.5)
            ax2.add_collection(lc_a1)
            
            b1_np = df['OCT_B1'].to_numpy()
            points_b1 = np.array([x_idx, b1_np]).T.reshape(-1, 1, 2)
            segments_b1 = np.concatenate([points_b1[:-1], points_b1[1:]], axis=1)
            lc_b1 = LineCollection(segments_b1, colors=oct_colors, linewidths=2.5)
            ax2.add_collection(lc_b1)

            
            # Plot Bollinger Bands Cloud on A1
            ax2.plot(x_idx, df['OCT_BB_Top'], color='#00008B', linewidth=1.0, linestyle='--', alpha=0.6)
            ax2.plot(x_idx, df['OCT_BB_Bot'], color='#00008B', linewidth=1.0, linestyle='--', alpha=0.6)
            ax2.fill_between(x_idx, df['OCT_BB_Bot'], df['OCT_BB_Top'], color='#ADD8E6', alpha=0.2, label='Octopus Band')
            ax2.axhline(0, color='white', linewidth=0.5, alpha=0.5)

            # --- THIRD SUBPLOT: RS CHART ---
            ax3.plot(x_idx, df['RS14'], color='white', linewidth=2.0, label='RS14')
            ax3.plot(x_idx, df['RS52'], color='yellow', linewidth=2.0, label='RS52')
            ax3.axhline(50, color='red', linewidth=0.8, linestyle='--', alpha=0.5)

            # 7. Formatting
            ax.set_title(f"GP & OCTOPUS CHART (HHV-LLV + McGinley): {ticker}", color='gold', fontsize=15, fontweight='bold', pad=12)
            ax.set_ylabel("Price", color='white', fontweight='bold')
            ax2.set_ylabel("Octopus MACD", color='white', fontweight='bold')
            ax3.set_ylabel("RS Rating", color='white', fontweight='bold')
            
            for axis in [ax, ax2, ax3]:
                axis.grid(True, color='#222222', linestyle=':', alpha=0.5)
                axis.tick_params(colors='white')
                for spine in axis.spines.values():
                    spine.set_color('#444444')
            
            date_labels = df['Date'].dt.strftime('%d/%m/%y').tolist()
            import matplotlib.ticker as ticker_lib
            ax3.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
            
            ax.legend(loc='lower left', facecolor='black', edgecolor='#00FF00', labelcolor='white', fontsize=8)
            ax2.legend(loc='lower left', facecolor='black', edgecolor='#FF69B4', labelcolor='white', fontsize=8)
            ax3.legend(loc='lower left', facecolor='black', edgecolor='yellow', labelcolor='white', fontsize=8)
            
            plt.tight_layout()
            plt.show(block=False)

        except Exception as e:
            logger.error(f"Error showing GreenPink window: {e}")
            import traceback
            traceback.print_exc()

    def run_heikin_chart(self):
        ticker = self.entry_ticker.get().strip().upper()
        if not ticker: return
        df = self.data_dict.get(ticker)
        if df is None or len(df) < 30:
            messagebox.showwarning("Không đủ dữ liệu", f"Mã '{ticker}' cần ít nhất 30 phiên để phân tích Heikin.")
            return
        
        self.log_sync(f"Đang mở Biểu đồ Heikin Ashi Signal cho mã {ticker} (150 phiên gần nhất)...", clear=True)
        self.show_heikin_window(ticker, df)

    def show_heikin_window(self, ticker, df_full):
        try:
            import matplotlib.pyplot as plt
            from tinvest.data_loader import enrich_dataframe

            plt.style.use('dark_background')

            # --- ROBUST DATA CHECK ---
            if 'HK_NW' not in df_full.columns or 'T2_SMA' not in df_full.columns:
                self.log_sync("Dữ liệu Heikin/2Trend bị thiếu. Đang tính toán bổ sung...", clear=True)
                df_full = enrich_dataframe(df_full)
                self.data_dict[ticker] = df_full
                # SAVE to disk so we don't have to recompute next time
                try:
                    self.storage.save_indicators(ticker, df_full)
                    # Also update analysis cache if exists
                    if ticker in self.analysis_cache:
                        self.analysis_cache[ticker]['df'] = df_full
                except: pass

            # 1. Prepare Data (Last 150 bars)
            count = 150
            df = df_full.tail(count).copy().reset_index(drop=True)
            x_idx = np.arange(len(df))
            
            # 2. Setup Figure with 2 subplots
            fig, (ax, ax2) = plt.subplots(2, 1, figsize=(15, 11), sharex=True, gridspec_kw={'height_ratios': [1, 1]})
            fig.patch.set_facecolor('black') 
            ax.set_facecolor('black')
            ax2.set_facecolor('black')
            
            # --- TOP SUBPLOT: HEIKIN & TREND COLOR ---
            # 3. Plot Hull MA Cloud
            mh = df['HK_MHull']
            sh = df['HK_SHull']
            ax.fill_between(x_idx, mh, sh, where=(mh > sh), color='lime', alpha=0.1)
            ax.fill_between(x_idx, mh, sh, where=(mh <= sh), color='red', alpha=0.1)

            # 3.1. Trend Color Line (EMA 13)
            from matplotlib.collections import LineCollection
            tc_trend = df['TC_Trend']
            tc_t_color = df['TC_TrendColor'].fillna('#434651')
            tc_trend_np = tc_trend.to_numpy()
            points_tc = np.array([x_idx, tc_trend_np]).T.reshape(-1, 1, 2)
            segments_tc = np.concatenate([points_tc[:-1], points_tc[1:]], axis=1)
            tc_colors = tc_t_color.iloc[1:].tolist()
            lc_tc = LineCollection(segments_tc, colors=tc_colors, linewidths=2.5, alpha=0.9)
            ax.add_collection(lc_tc)
            
            # 3.2. Stop Line (ATR Stop)
            tc_stop = df['TC_StopLine']
            tc_s_color = df['TC_StopColor'].fillna('#434651')
            ax.scatter(x_idx, tc_stop, c=tc_s_color, s=10, marker='_')

            # 4. Plot NW Trailing Stop
            nw = df['HK_NW']
            trend = df['HK_Trend']
            nw_np = nw.to_numpy()
            points_nw = np.array([x_idx, nw_np]).T.reshape(-1, 1, 2)
            segments_nw = np.concatenate([points_nw[:-1], points_nw[1:]], axis=1)
            nw_colors = ['#00FF00' if trend.iloc[i] == 1 else '#FF0000' for i in range(1, len(df))]
            lc_nw = LineCollection(segments_nw, colors=nw_colors, linewidths=2)
            ax.add_collection(lc_nw)

            # 5. Plot Smoothed Heikin Ashi Candles
            ho, hh, hl, hc = df['HK_Flower_Open'], df['HK_Flower_High'], df['HK_Flower_Low'], df['HK_Flower_Close']
            bar_colors = df['HK_BarColor']
            color_map = {'brightGreen': '#00FF00', 'red': '#FF0000', 'white': '#FFFFFF'}
            for color_name, color_hex in color_map.items():
                mask = bar_colors == color_name
                if mask.any():
                    ax.vlines(x_idx[mask], hl[mask], hh[mask], color=color_hex, linewidth=1)
                    ax.bar(x_idx[mask], abs(hc[mask] - ho[mask]) + 0.001, bottom=np.minimum(ho[mask], hc[mask]), color=color_hex, width=0.6, alpha=0.8)

            # 6. Plot Signal Shapes
            buys = df[df['HK_BuySignal'] | df['HK_BuyManh']]
            sells = df[df['HK_SellSignal'] | df['HK_SellManh']]
            if not buys.empty:
                ax.plot(buys.index, buys['HK_Flower_Low'] * 0.985, '^', markersize=10, color='lime', markeredgecolor='white')
            if not sells.empty:
                ax.plot(sells.index, sells['HK_Flower_High'] * 1.015, 'v', markersize=10, color='red', markeredgecolor='white')

            # --- BOTTOM SUBPLOT: NORMAL CANDLES & 2TREND ---
            # 7. Plot Normal Candlesticks
            o, h, l, c_val = df['Open'], df['High'], df['Low'], df['Close']
            up_mask = c_val >= o
            down_mask = ~up_mask
            if up_mask.any():
                ax2.vlines(x_idx[up_mask], l[up_mask], h[up_mask], color='#00FF00', linewidth=1)
                ax2.bar(x_idx[up_mask], abs(c_val[up_mask] - o[up_mask]) + 0.001, bottom=np.minimum(o[up_mask], c_val[up_mask]), color='#00FF00', width=0.6)
            if down_mask.any():
                ax2.vlines(x_idx[down_mask], l[down_mask], h[down_mask], color='#FF0000', linewidth=1)
                ax2.bar(x_idx[down_mask], abs(c_val[down_mask] - o[down_mask]) + 0.001, bottom=np.minimum(o[down_mask], c_val[down_mask]), color='#FF0000', width=0.6)

            # 8. Plot 2Trend SMA
            t2_sma = df['T2_SMA']
            t2_trend = df['T2_SMA_Trend']
            t2_sma_np = t2_sma.to_numpy()
            points_t2 = np.array([x_idx, t2_sma_np]).T.reshape(-1, 1, 2)
            segments_t2 = np.concatenate([points_t2[:-1], points_t2[1:]], axis=1)
            t2_colors = ['#00ffaa' if t2_trend.iloc[i] == 1 else '#ff0000' for i in range(1, len(df))]
            lc_t2 = LineCollection(segments_t2, colors=t2_colors, linewidths=3)
            ax2.add_collection(lc_t2)

            # 9. Plot 2Trend Supertrend Bands
            st_upper = df['T2_ST_Upper']
            st_lower = df['T2_ST_Lower']
            st_trend = df['T2_ST_Trend']
            mid = (o + c_val) / 2
            ax2.fill_between(x_idx, mid, st_lower, where=(st_trend == 1), color='#00ffaa', alpha=0.2)
            ax2.fill_between(x_idx, mid, st_upper, where=(st_trend == -1), color='#ff0000', alpha=0.2)
            
            # 10. Signals for 2Trend
            # ta.crossover(trend_state, 0)
            t2_sma_shift = df['T2_SMA_Trend'].shift(1).fillna(0)
            t2_st_shift = df['T2_ST_Trend'].shift(1).fillna(0)
            
            buys2 = df[(df['T2_SMA_Trend'] == 1) & (t2_sma_shift <= 0)]
            sells2 = df[(df['T2_SMA_Trend'] == -1) & (t2_sma_shift >= 0)]
            
            if not buys2.empty:
                for idx in buys2.index:
                    ax2.text(idx, df['Low'].iloc[idx]*0.97, "𝑳", color='#00ffaa', fontsize=12, fontweight='bold', ha='center')
            if not sells2.empty:
                for idx in sells2.index:
                    ax2.text(idx, df['High'].iloc[idx]*1.03, "𝑺", color='#ff0000', fontsize=12, fontweight='bold', ha='center')

            # 11. Formatting
            last_date = df['Date'].iloc[-1].strftime('%d/%m/%Y') if 'Date' in df.columns else "N/A"
            ax.set_title(f"Chart trend color - {ticker} - {last_date}", color='gold', fontsize=16, fontweight='bold', pad=15)
            ax2.set_title(f"Normal Candles & 2Trend Logic", color='gold', fontsize=14, fontweight='bold')
            
            for a in [ax, ax2]:
                a.set_ylabel("Price", color='white', fontweight='bold')
                a.grid(True, color='#222222', linestyle=':', alpha=0.5)
                a.tick_params(colors='white')
                for spine in a.spines.values():
                    spine.set_color('#444444')
            
            date_labels = df['Date'].dt.strftime('%d/%m/%y').tolist()
            import matplotlib.ticker as ticker_lib
            ax2.xaxis.set_major_formatter(ticker_lib.FuncFormatter(lambda x, pos: date_labels[int(round(x))] if 0 <= int(round(x)) < len(date_labels) else ""))
            
            plt.tight_layout()
            plt.show(block=False)

        except Exception as e:
            logger.error(f"Error showing Heikin window: {e}")
            import traceback
            traceback.print_exc()


    def run_advanced_scanner(self, entry_target: str):


        if not self.analysis_cache:


            messagebox.showwarning("Cảnh báo", "Hệ thống chưa nạp dữ liệu. Hãy bấm '📂 Load Dữ liệu Cũ' hoặc 'Nạp Thêm File CSV'!")


            return


            


        self.log_sync(f"Đang hiển thị các mã ứng với [{entry_target}] (thời gian tính 0ms)...", clear=True)


        self.root.update()


        


        try:


            results = []


            for ticker, data in self.analysis_cache.items():


                # Flexible key mapping for signal and accumulation
                res = data.get("adv") or data.get("advanced_entry") or data.get("entry_signal") or {}
                accum = data.get("accum") or data.get("accumulation") or {}
                ma_trend = data.get("ma_trend") or data.get("ma") or {}

                # Ensure backward compatibility for valuation key
                val = data.get("valuation") or data.get("val") or {}


                


                df = data.get("df")
                if df is None or (hasattr(df, 'empty') and df.empty):
                    continue

                # --- NEW: Minimum Volume Filter (200,000) ---
                current_vol = df['Volume'].iloc[-1] if 'Volume' in df.columns else 0
                if current_vol < 200000:
                    continue

                avg_vol_20 = df["Volume"].tail(20).mean() if len(df) >= 20 else df["Volume"].mean()





                match = False


                if entry_target == "ACCUMULATION":


                    if accum["is_accumulation"]:


                        match = True


                        size = "N/A"


                        conf = accum["base_quality"]


                        flags = "Ready to break" if accum["ready_to_break"] else ", ".join(accum["notes"])


                elif entry_target == "BREAKOUT_ACCUMULATION":


                    if check_breakout_accumulation(df):


                        match = True


                        size = "N/A"


                        conf = accum.get("base_quality", "MEDIUM")


                        flags = "Phá vỡ tích lũy"


                elif entry_target == "PERFECT_MA":


                    ma_trend = data.get("ma_trend") or data.get("ma") or {}


                    if ma_trend.get("is_perfect_uptrend"):


                        match = True


                        size = "N/A"


                        conf = "HIGH"


                        flags = "MA10 > MA20 > MA50 > 100 > 200 (Giá > MA20 & Hỗ trợ MA50)"


                elif entry_target == "HEIKIN_BUY":
                    # Logic: Tín hiệu Mua Heikin (HK_BuySignal hoặc HK_BuyManh) xuất hiện trong T-0 hoặc T-1
                    # Khớp với yêu cầu mới: Chỉ lấy mã báo mua hôm nay hoặc hôm qua
                    
                    buy_2 = df['HK_BuySignal'].fillna(False).tail(2).any() or df['HK_BuyManh'].fillna(False).tail(2).any()
                    
                    if buy_2:
                        match = True
                        # Xác định phiên có tín hiệu gần nhất trong 2 phiên
                        last_2 = df.tail(2)
                        sig_type = "MUA MẠNH" if last_2['HK_BuyManh'].any() else "MUA SỚM"
                        
                        current_price = df['Close'].iloc[-1]
                        nw_val = df['HK_NW'].iloc[-1]
                        
                        size = "N/A"
                        conf = "HEIKIN"
                        flags = f"{sig_type} | Giá: {current_price} | Stoploss: {nw_val:.2f}"


                elif entry_target == "UPCLOUD":
                    # Criteria:
                    # 1. Price > Cloud top (SpanA, SpanB)
                    # 2. Future Cloud is Green (SpanA_ahead > SpanB_ahead)
                    # 3. Tenkan > Kijun
                    # 4. MA10 > MA20
                    
                    last = df.iloc[-1]
                    current_price = last['Close']
                    span_a = last.get('SpanA', 0)
                    span_b = last.get('SpanB', 0)
                    tenkan = last.get('Tenkan', 0)
                    kijun = last.get('Kijun', 0)
                    ma10 = last.get('MA10', 0)
                    ma20 = last.get('MA20', 0)
                    
                    # Future Cloud calculation (plotted 26 days ahead based on today's data)
                    future_span_a = (tenkan + kijun) / 2
                    h52 = df['High'].iloc[-52:].max()
                    l52 = df['Low'].iloc[-52:].min()
                    future_span_b = (h52 + l52) / 2
                    
                    c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                    c2 = (future_span_a > future_span_b)
                    c3 = (tenkan > kijun)
                    c4 = (ma10 > ma20)
                    
                    if c1 and c2 and c3 and c4:
                        match = True
                        size = "N/A"
                        conf = "ICHIMOKU"
                        flags = "UPCLOUD (Price > Cloud | Mây TL Xanh | T>K | MA10>MA20)"
                elif entry_target == "WHITE_ADX":
                    adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
                    if adx_color == "WHITE":
                        match = True
                        size = "N/A"
                        conf = "STRONG"
                        flags = "ADX Trắng (Rising & DI+ > DI-)"
                        val["risk_pct"] = val.get("risk_pct", 0) * 0.7  # Relax risk for scanner display



                else:


                    if res["entry_type"] == entry_target:


                        match = True


                        size = res["position_size"]


                        conf = res["confidence"]


                        flags = ", ".join(res["risk_flags"]) if res["risk_flags"] else "None"


                        


                if match:


                    # Skip if risk is too high or explicitly invalid data
                    risk_limit = 20.0 if entry_target == "WHITE_ADX" else 15.0
                    # For compatibility, if 'is_valid' is missing (None), we treat it as True
                    if val.get("is_valid", True) is False or val.get("risk_pct", 0) > risk_limit:
                        continue 

                    # Filter final output table to only display the 6 specified categories:
                    # Gia Tang 2 (ADD_2), Tich Luy (ACCUMULATION), Perfect MA (PERFECT_MA), Heikin (HEIKIN_BUY), UPCLOUD (UPCLOUD), Trend ADX (WHITE_ADX)
                    has_add2 = (res.get("entry_type") == "ADD_2")
                    has_accum = accum.get("is_accumulation", False)
                    has_perfect_ma = ma_trend.get("is_perfect_uptrend", False)
                    
                    has_heikin = False
                    if 'HK_BuySignal' in df.columns or 'HK_BuyManh' in df.columns:
                        has_heikin = df.get('HK_BuySignal', pd.Series(dtype=bool)).fillna(False).tail(2).any() or df.get('HK_BuyManh', pd.Series(dtype=bool)).fillna(False).tail(2).any()
                    
                    has_upcloud = False
                    if len(df) > 0 and 'High' in df.columns and 'Low' in df.columns:
                        last = df.iloc[-1]
                        current_price = last['Close']
                        span_a = last.get('SpanA', 0)
                        span_b = last.get('SpanB', 0)
                        tenkan = last.get('Tenkan', 0)
                        kijun = last.get('Kijun', 0)
                        ma10 = last.get('MA10', 0)
                        ma20 = last.get('MA20', 0)
                        
                        future_span_a = (tenkan + kijun) / 2
                        h52 = df['High'].iloc[-52:].max() if len(df) >= 52 else df['High'].max()
                        l52 = df['Low'].iloc[-52:].min() if len(df) >= 52 else df['Low'].min()
                        future_span_b = (h52 + l52) / 2
                        
                        c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                        c2 = (future_span_a > future_span_b)
                        c3 = (tenkan > kijun)
                        c4 = (ma10 > ma20)
                        has_upcloud = (c1 and c2 and c3 and c4)
                        
                    has_trend_adx = False
                    if 'ADX_Color' in df.columns:
                        adx_color = str(df['ADX_Color'].iloc[-1]).upper()
                        has_trend_adx = (adx_color == "WHITE")
                        
                    has_breakout_accum = check_breakout_accumulation(df)
                        
                    if not (has_add2 or has_accum or has_perfect_ma or has_heikin or has_upcloud or has_trend_adx or has_breakout_accum):
                        continue 


                    time_lbl = "T0" if entry_target in ["ACCUMULATION", "PERFECT_MA", "BREAKOUT_ACCUMULATION"] else ("T-1" if any("T-1" in flag for flag in res.get("risk_flags", [])) else "T0")


                    if entry_target == "ACCUMULATION":
                        reason = f"Tích Lũy ({accum.get('base_quality', '')})"
                    elif entry_target == "BREAKOUT_ACCUMULATION":
                        reason = "Phá Vỡ Tích Lũy"
                    elif entry_target == "PERFECT_MA":
                        reason = "Full MA Up"
                    elif entry_target == "WHITE_ADX":
                        reason = "ADX TRẮNG"
                    else:
                        reason = res.get("details", {}).get("source", "System")


                    


                    ep = val.get("price", 0)


                    tp = val.get("tp1", 0)


                    rr_ratio = val.get("rr_ratio", 0)


                    val_score = val.get("risk_score", 0)


                    current_p = float(df['Close'].iloc[-1]) * 1000
                    last_vol = float(df["Volume"].iloc[-1])


                    


                    results.append({


                        "Ticker": ticker,


                        "Price": f"{current_p:,.0f}",


                        "Volume": f"{last_vol:,.0f}",


                        "Entry": f"{ep*1000:,.0f}" if ep > 0 else "N/A",


                        "Target": f"{tp*1000:,.0f}" if tp > 0 else "N/A",


                        "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",


                        "Risk Score": f"{int(val_score)}",


                        "Time": time_lbl,


                        "Reason": reason


                    })


                    


            if not results:


                self.log_sync(f"Hoàn tất: Không có mã nào đạt tiêu chí [{entry_target}].")


            else:


                self.log_sync(f"Hoàn tất: Tìm thấy {len(results)} mã thỏa mãn.\n")


                df_res = pd.DataFrame(results).sort_values("Ticker")


                table_str = df_res.to_string(index=False, justify="left")


                self.log_sync(table_str)


                self.log_sync("\n" + "="*70)


                self.log_sync("Thông tin: Hệ thống đã quét với toàn bộ thanh khoản thị trường.")


        except Exception as e:


            self.log_sync(f"Lỗi: {str(e)}")





    def run_stock_chart(self):


        """Displays a professional technical analysis chart for the selected stock."""


        ticker = self.entry_ticker.get().upper().strip()


        if not ticker:


            messagebox.showwarning("Cảnh báo", "Vui lòng nhập mã chứng khoán!")


            return


            


        df = self.data_dict.get(ticker)


        if df is None or df.empty:


            messagebox.showwarning("Lỗi", f"Không tìm thấy dữ liệu cho mã [{ticker}]. Hãy nạp dữ liệu trước!")


            return


            


        self.log_sync(f"\n--- ĐANG KHỞI TẠO BIỂU ĐỒ: {ticker} ---")


        


        def chart_task():


            try:


                from tinvest.data_loader import enrich_dataframe
                
                plt.style.use('default')


                


                # Enrich data to ensure all indicators (MA, Ichimoku, VSA) are present


                df_rich = enrich_dataframe(df.copy())


                


                # Take last 100 days for clearer visibility


                df_plot = df_rich.tail(100).copy()


                df_plot['Date'] = pd.to_datetime(df_plot['Date'])


                df_plot = df_plot.sort_values('Date')


                # --- NEW: Extend for Ichimoku Future (26 periods) ---


                last_date = df_plot['Date'].iloc[-1]


                future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=26)


                df_future = pd.DataFrame({'Date': future_dates})


                df_ext = pd.concat([df_plot, df_future], ignore_index=True)


                


                # --- Fix Ichimoku Cloud Plotting (Future Alignment) ---


                df_rich['raw_a'] = (df_rich['Tenkan'] + df_rich['Kijun']) / 2


                df_rich['raw_b'] = (df_rich['High'].rolling(52).max() + df_rich['Low'].rolling(52).min()) / 2


                


                hist_cloud = df_rich[['Date', 'SpanA', 'SpanB']].tail(100).copy()


                


                future_spans = []


                for i in range(1, 27):


                    source_idx = -26 + i


                    val_a = df_rich['raw_a'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan


                    val_b = df_rich['raw_b'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan


                    future_spans.append({'Date': df_future['Date'].iloc[i-1], 'SpanA': val_a, 'SpanB': val_b})


                


                df_future_cloud = pd.DataFrame(future_spans)


                df_total_cloud = pd.concat([hist_cloud, df_future_cloud], ignore_index=True)





                # Subsets for Candlesticks


                up = df_plot[df_plot['Close'] >= df_plot['Open']]


                down = df_plot[df_plot['Close'] < df_plot['Open']]





                # Fetch analysis (RE-CALCULATE to ensure chart is in sync with latest logic)
                from tinvest.analyzer import analyze_stock
                analysis_fresh = analyze_stock(ticker, df_rich)
                val = analysis_fresh.get('valuation', {})
                adv = analysis_fresh.get('adv', {})
                analysis = analysis_fresh # Use fresh for the rest of drawing too


                


                # Create fig (4 subplots for Price, Volume, RSI, ADX)


                fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [5, 1.2, 1.2, 1.5]}, sharex=True)


                plt.subplots_adjust(hspace=0.08, bottom=0.1)


                


                # --- MAP X AXIS TO ORDINAL SCALAR TO PREVENT GAPS ---
                x_idx_plot = np.arange(len(df_plot))
                x_idx_ext = np.arange(len(df_ext))
                
                date_labels = df_ext['Date'].dt.strftime('%d/%m').tolist()
                def format_date(x, pos):
                    try:
                        idx = int(round(x))
                        if 0 <= idx < len(date_labels):
                            return date_labels[idx]
                    except:
                        pass
                    return ""
                
                # Plot Candlesticks...
                up_mask = df_plot['Close'] >= df_plot['Open']
                down_mask = df_plot['Close'] < df_plot['Open']
                ax1.bar(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Close'] - df_plot.loc[up_mask, 'Open'], bottom=df_plot.loc[up_mask, 'Open'], color='green', width=0.6, alpha=0.8)
                ax1.bar(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Open'] - df_plot.loc[down_mask, 'Close'], bottom=df_plot.loc[down_mask, 'Close'], color='red', width=0.6, alpha=0.8)
                ax1.vlines(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Low'], df_plot.loc[up_mask, 'High'], color='green', linewidth=1)
                ax1.vlines(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Low'], df_plot.loc[down_mask, 'High'], color='red', linewidth=1)

                # Plot MAs...
                ma_styles = [('MA10', 'black', 'MA10', 2), ('MA20', 'green', 'MA20', 2), ('MA50', 'brown', 'MA50', 1)]
                for ma_col, color, label, lw in ma_styles:
                    if ma_col in df_plot.columns:
                        ax1.plot(x_idx_plot, df_plot[ma_col], label=label, color=color, linewidth=lw, alpha=0.8)

                # Plot Ichimoku Cloud
                ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                                 where=(df_total_cloud['SpanA'] >= df_total_cloud['SpanB']), color='lime', alpha=0.3, label='Kumo Green')
                ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                                 where=(df_total_cloud['SpanA'] < df_total_cloud['SpanB']), color='red', alpha=0.3, label='Kumo Red')
                    
                if 'Tenkan' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Tenkan'], color='blue', label='Tenkan', linewidth=1.0, alpha=0.9)
                if 'Kijun' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Kijun'], color='red', label='Kijun', linewidth=1.0, alpha=0.9)
                if 'Kijun65' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Kijun65'], color='orange', linestyle='--', label='Dao 65', linewidth=2.0, alpha=0.8)

                # Scaling: Limit Y axis to price area
                p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
                ax1.set_ylim(p_min * 0.95, p_max * 1.05)
                
                # Plot S1, S2, R1, R2 lines...
                last_idx = x_idx_plot[-1]
                future_idx = last_idx + 22
                
                # Formatting helper and Title
                is_index = ticker.upper().endswith("INDEX") or "VN30" in ticker.upper()
                fmt = "{:,.0f}" if is_index else "{:,.2f}"
                
                logo_name = "Vector logo.png"
                logo_path = resource_path(logo_name)
                
                logo_found = False
                try:
                    if os.path.exists(logo_path):
                        img = mpimg.imread(logo_path)
                        imagebox = OffsetImage(img, zoom=0.05) # Adjust zoom as needed
                        ab = AnnotationBbox(imagebox, (0.05, 0.94), frameon=False, xycoords='figure fraction')
                        fig.add_artist(ab)
                        fig.text(0.07, 0.94, "=AI+CƠM!", ha="left", va="center", fontsize=12, fontweight='bold', color='black')
                        logo_found = True
                except Exception as e:
                    logger.error(f"Error loading logo: {e}")
                
                if not logo_found:
                    fig.text(0.05, 0.98, "AIC CODE = AI + CƠM!", ha="left", va="top", fontsize=20, fontweight='bold', color='black')
                
                # --- Title Formatting ---
                report_date = df_plot['Date'].iloc[-1].strftime('%d/%m/%Y')
                full_title = f"Technical Analysis Report: {ticker} - {report_date}"
                
                ax1.set_title(full_title, fontsize=16, fontweight='bold', color='darkblue', pad=30, loc='center')

                # Current Price Marker
                current_price = df_plot['Close'].iloc[-1]
                ax1.hlines(current_price, xmin=last_idx, xmax=future_idx, color='black', linestyle='-', linewidth=2.0, alpha=0.8)
                ax1.text(future_idx, current_price, f" {fmt.format(current_price)}", color='black', fontsize=10, fontweight='bold', va='center', ha='left', bbox=dict(facecolor='yellow', alpha=0.8, edgecolor='none', pad=1))
                
                if val:
                    sr_config = [('s1', 'green', 'S1'), ('s2', 'darkgreen', 'S2'), 
                                 ('r1', 'red', 'R1'), ('r2', 'darkred', 'R2')]
                    for sr_key, color, lbl in sr_config:
                        level = val.get(sr_key, 0)
                        if level > 0:
                            ax1.hlines(level, xmin=last_idx, xmax=future_idx, color=color, linestyle='--', alpha=0.8, linewidth=1.5)
                            ax1.text(future_idx, level, f" {lbl}: {fmt.format(level)}", color=color, 
                                     fontsize=9, fontweight='bold', va='center', ha='left')

                # --- Summary Assessment Overlay ---
                sr = analysis.get('state_rules', {})
                sr_pri = sr.get('primary', 'N/A')
                sr_sec = sr.get('secondary', 'N/A')
                opp_score = val.get('opp_score', 0)
                risk_score = val.get('risk_score', 0)
                report_date = df_plot['Date'].iloc[-1].strftime('%d/%m/%Y')
                action_str = val.get('action', '')
                if "YES" in action_str:
                    rec_text = f"NÊN MUA (giá {fmt.format(current_price)}), Target 1: {fmt.format(val.get('tp1', 0))}, Target 2: {fmt.format(val.get('tp2', 0))}, Cutloss: {fmt.format(val.get('cutloss_full', 0))}"
                elif "NO" in action_str or risk_score > 75 or "DOWNTREND" in sr_pri:
                    rec_text = f"NÊN BÁN (giá {fmt.format(current_price)})"
                else:
                    rec_text = "TRUNG LẬP (hiện tại trung lập chưa nên hành động)"
                
                summary_text = (
                    f"TÓM LƯỢC NHẬN ĐỊNH ({report_date})\n"
                    f"● Trạng thái: {sr_pri}\n"
                    f"● Vận động: {sr_sec}\n"
                    f"● Opp Score: {opp_score}/100 | Risk: {risk_score}/100\n"
                    f"● Xu hướng: {'TĂNG' if opp_score > 50 else 'THEO DÕI' if opp_score > 30 else 'YẾU'}\n"
                    f"● Khuyến nghị: {rec_text}"
                )
                
                # Move summary box down to avoid Legend overlap
                ax1.text(0.01, 0.75, summary_text, transform=ax1.transAxes, fontsize=10,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='darkblue'))


                


                # Signals... (up to 3 arrows)
                from tinvest.advanced_entry import _eval_day
                buy_signals = []
                for real_idx in df_plot.index.tolist():
                    rel_idx = -(len(df_rich) - df_rich.index.get_loc(real_idx))
                    sig = _eval_day(df_rich, rel_idx)
                    if sig and sig.get('type') in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                        buy_signals.append({'date': df_rich['Date'].loc[real_idx], 'type': sig['type'], 
                                           'source': sig.get('details', {}).get('source', 'N/A'), 'price': df_rich['Low'].loc[real_idx]})

                buy_signals = sorted(buy_signals, key=lambda x: x['date'], reverse=True)[:3]
                annotation_text = "3 ĐIỂM MUA GẦN NHẤT:\n\n"
                for i, b in enumerate(buy_signals):
                    matches = np.where(df_plot['Date'] == b['date'])[0]
                    if len(matches) > 0:
                        pos = matches[0]
                        ax1.plot(pos, b['price'] * 0.98, '^', markersize=12, color='lime', markeredgecolor='green')
                        annotation_text += f" • #{i+1}: {b['date'].strftime('%d/%m')} - {b['type']} ({b['source']})\n\n"

                if buy_signals:
                    fig.text(0.1, 0.02, annotation_text, fontsize=10, color='darkgreen', 
                             linespacing=1.8, bbox=dict(facecolor='white', alpha=0.9, edgecolor='lime', pad=5))

                # MCDX...
                if 'MCDX_Banker' in df_plot.columns:
                    # Banker (Red) - Bottom to Banker value
                    ax2.bar(x_idx_plot, df_plot['MCDX_Banker'], color='red', width=0.8, alpha=0.8, label='Banker')
                    # Hot Money (Yellow) - Stacked on top of Banker
                    ax2.bar(x_idx_plot, df_plot['MCDX_HotMoney'], bottom=df_plot['MCDX_Banker'], color='yellow', width=0.8, alpha=0.8, label='Hot Money')
                    # Retailer (Green) - Stacked on top of Banker + HotMoney
                    ax2.bar(x_idx_plot, df_plot['MCDX_Retailer'], bottom=df_plot['MCDX_Banker'] + df_plot['MCDX_HotMoney'], color='green', width=0.8, alpha=0.8, label='Retailer')
                    
                    if 'MCDX_Banker_MA' in df_plot.columns:
                        ax2.plot(x_idx_plot, df_plot['MCDX_Banker_MA'], color='black', linewidth=1.5, label='Banker MA')
                    
                    ax2.set_ylabel('MCDX', fontweight='bold', fontsize=9)
                    ax2.set_ylim(0, 20)
                    ax2.legend(loc='upper left', fontsize=8, ncol=4)
                else:
                    ax2.set_visible(False)

                # --- ADX Subplot ---
                if 'ADX' in df_plot.columns:
                    # Draw multi-colored ADX line
                    adx_vals = df_plot['ADX'].values
                    if 'ADX_Color' in df_plot.columns:
                        adx_colors = df_plot['ADX_Color'].values
                        for i in range(1, len(x_idx_plot)):
                            c = str(adx_colors[i]).lower()
                            if c == 'white': c = 'purple'
                            ax3.plot(x_idx_plot[i-1:i+1], adx_vals[i-1:i+1], color=c, linewidth=2.0)
                    else:
                        ax3.plot(x_idx_plot, df_plot['ADX'], color='black', linewidth=1.5)
                        
                    ax3.plot(x_idx_plot, df_plot['DI_Plus'], color='green', linewidth=1.0, label='+DI')
                    ax3.plot(x_idx_plot, df_plot['DI_Minus'], color='red', linewidth=1.0, label='-DI')
                    ax3.axhline(25, color='gray', linestyle='--', alpha=0.8, label='Trend Threshold')
                    ax3.set_ylabel('ADX', fontweight='bold', fontsize=9)
                    ax3.set_ylim(bottom=0)
                    
                    adx_legend = mlines.Line2D([], [], color='purple', linewidth=2.0, label='ADX (14)')
                    handles, labels = ax3.get_legend_handles_labels()
                    handles.insert(0, adx_legend)
                    labels.insert(0, 'ADX (14)')
                    ax3.legend(handles, labels, loc='upper left', fontsize=8, ncol=4)
                    
                    ax3.grid(True, linestyle='--', alpha=0.3)
                else:
                    ax3.set_visible(False)

                # --- MACD Subplot ---
                if 'MACD' in df_plot.columns and 'MACD_Signal' in df_plot.columns:
                    ax4.plot(x_idx_plot, df_plot['MACD'], color='blue', linewidth=1.5, label='MACD')
                    ax4.plot(x_idx_plot, df_plot['MACD_Signal'], color='orange', linewidth=1.5, label='Signal')
                    if 'MACD_Hist' in df_plot.columns:
                        colors = np.where(df_plot['MACD_Hist'] >= 0, 'green', 'red')
                        ax4.bar(x_idx_plot, df_plot['MACD_Hist'], color=colors, alpha=0.6, width=0.6)
                    ax4.axhline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
                    ax4.set_ylabel('MACD', fontweight='bold', fontsize=9)
                    ax4.legend(loc='upper left', fontsize=8, ncol=3)
                    ax4.grid(True, linestyle='--', alpha=0.3)
                else:
                    ax4.set_visible(False)

                # Final Layout
                ax1.grid(True, linestyle='--', alpha=0.3)
                ax1.tick_params(labelright=True) # Ensure right-side price labels
                ax1.legend(loc='upper left', fontsize=9, ncol=4)
                
                # Use FuncFormatter to map ordinal x back to Dates
                ax4.xaxis.set_major_formatter(ticker_lib.FuncFormatter(format_date))
                
                # Make sure the x limits are bounded by the total ordinal length
                ax1.set_xlim(0, len(x_idx_ext) + 2)
                ax2.grid(True, linestyle='--', alpha=0.3)
                plt.show(block=False)


                


            except Exception as e:


                import traceback


                self.log_sync(f"❌ LỖI VẼ BIỂU ĐỒ [{ticker}]: {e}")


                print(traceback.format_exc())


                


        self.root.after(0, chart_task)





    def run_market_analysis(self):


        if not self.data_dict:


            from tkinter import messagebox


            messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")


            return


            


        self.log_sync("Đang xử lý Dữ liệu Thị trường (FTD, Phân phối, Breadth)...", clear=True)


        


        def analyze_task():


            try:


                from tinvest.market_engine import analyze_market_index, analyze_market_breadth, analyze_momentum_divergence, calculate_index_sr


                from tinvest.ichimoku_engine import analyze_ichimoku


                from tinvest.vsa_engine import analyze_vsa


                from tinvest.ma_engine import analyze_ma_trend


                


                self.log_sync("   ... Đang tính toán độ rộng (Breadth)...")
                breadth_res = analyze_market_breadth(self.data_dict, "VNINDEX")
                self.log_sync(f"   ... Độ rộng: {breadth_res['breadth_label']} ({breadth_res['strong_stocks_pct']}% > MA50)")
                
                breadth_ma20 = breadth_res.get("strong_stocks_ma20_pct", 50.0)
                breadth_ma50 = breadth_res.get("strong_stocks_pct", 50.0)


                


                regime_labels = {


                    "UPTREND": "📈 UPTREND (Tăng giá xác nhận)",


                    "UPTREND_UNDER_PRESSURE": "⚠️ UPTREND RỦI RO (Suy yếu/Phân phối)",


                    "STABLE_RECOVERY": "🔵 HỒI PHỤC ỔN ĐỊNH (Trên MA20/Kijun)",


                    "RECOVERY": "🟡 HỒI PHỤC (FTD và trên MA10)",


                    "WEAK_RECOVERY": "⚪ HỒI PHỤC YẾU (Có RA Day 3+)",


                    "SIDEWAY": "↔️ SIDEWAY (Đi ngang quanh MA50)",


                    "MARKET_WEAKENING": "📉 SUY YẾU (Giá dưới MA50)",


                    "DOWNTREND": "🔴 DOWNTREND (Thị trường giảm giá)",


                    "UNKNOWN": "❓ CHƯA XÁC ĐỊNH"


                }





                def analyze_full_index(idx_df: pd.DataFrame):


                    if idx_df is None or idx_df.empty: return None


                    from tinvest.data_loader import enrich_dataframe


                    from tinvest.advanced_entry import classify_entry


                    from tinvest.valuation_engine import evaluate_stock_valuation


                    


                    df_rich = enrich_dataframe(idx_df.copy())


                    mom = analyze_momentum_divergence(idx_df)


                    signals = classify_entry(df_rich)


                    


                    has_signal = signals.get('entry_type', 'NONE') != 'NONE'
                    val = evaluate_stock_valuation("INDEX", df_rich, signals)
                    sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),
                          "r1": val.get("r1", 0), "r2": val.get("r2", 0)}

                    # State Engine cho Index
                    from tinvest.state_engine import evaluate_state_rules
                    from tinvest.analyzer import evaluate_heatmap
                    from tinvest.mcdx_engine import evaluate_mcdx_rules
                    state_rules = evaluate_state_rules(df_rich)
                    
                    heatmap_eval = evaluate_heatmap(df_rich)
                    mcdx_eval = evaluate_mcdx_rules(df_rich)

                    res_regime = analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
                    res_regime['price'] = float(idx_df['Close'].iloc[-1])

                    return {
                        "regime": res_regime,
                        "momentum": mom,
                        "ichi": analyze_ichimoku(df_rich),
                        "vsa": analyze_vsa(df_rich),
                        "ma": analyze_ma_trend(df_rich),
                        "sr": sr,
                        "sr_source": "SIGNAL" if has_signal else "PIVOT",
                        "signals": signals,
                        "valuation": val,
                        "state_rules": state_rules,
                        "heatmap_eval": heatmap_eval,
                        "elliott_eval": "N/A",
                        "mcdx_eval": mcdx_eval,
                        "date": pd.to_datetime(idx_df['Date'].iloc[-1]).strftime("%Y-%m-%d") if ('Date' in idx_df.columns and idx_df['Date'].iloc[-1] is not None and not pd.isna(idx_df['Date'].iloc[-1])) else "N/A"
                    }





                def format_index(name, res_dict, prefix=""):


                    if not res_dict or res_dict['regime']['regime'] == "UNKNOWN":


                        return f"\n--- TỔNG QUAN {name}: Không tìm thấy dữ liệu."


                    


                    res = res_dict['regime']


                    mom = res_dict['momentum']


                    ichi = res_dict['ichi']


                    vsa = res_dict['vsa']


                    ma = res_dict['ma']


                    sr = res_dict.get('sr', {'s1':0, 's2':0, 'r1':0, 'r2':0})


                    sr_source = res_dict.get('sr_source', 'PIVOT')


                    sr_label = "Dựa trên tín hiệu mua" if sr_source == "SIGNAL" else "Dựa trên đỉnh/đáy lịch sử"


                    regime_label = regime_labels.get(res['regime'], res['regime'])


                    


                    txt = f"\n{prefix}THỊ TRƯỜNG {name} ({res['date']})"
                    txt += f"\n * CHỈ SỐ: {res['price']:,.0f}"


                    txt += f"\n * TRẠNG THÁI: {regime_label}"


                    txt += f"\n * HÀNH ĐỘNG: {res['action']}"


                    txt += f"\n * KHÁNG CỰ (R): {sr['r1']:,.0f} | {sr['r2']:,.0f}" if sr['r1'] > 0 else "\n * KHÁNG CỰ (R): N/A"
                    txt += f"\n * HỖ TRỢ (S): {sr['s1']:,.0f} | {sr['s2']:,.0f}" if sr['s1'] > 0 else "\n * HỖ TRỢ (S): N/A"


                    txt += f"\n   (S/R: {sr_label})"


                    


                    if res['ftd_active']: 
                        ftd_str = res.get('ftd_date', 'N/A')
                        txt += f"\n   - XÁC NHẬN FTD: Đang Kích Hoạt (Từ phiên {ftd_str} - {res.get('ftd_quality', 'N/A')})"


                    txt += f"\n   - Nỗ lực hồi phục (RA) : Ngày thứ {res['ra_day']}" if res['ra_day'] > 0 else ""
                    txt += f"\n   - Ngày Phân Phối      : {res['distribution_count']} ngày\n"
                    
                    diag = res_dict.get('valuation', {}).get('tech_health', {}).get('diagnostics', {})
                    if diag:
                        ma_d = diag.get('ma', {})
                        ichi_d = diag.get('ichimoku', {})
                        rsi_d = diag.get('rsi', {})
                        macd_d = diag.get('macd', {})
                        adx_d = diag.get('adx', {})
                        
                        txt += "\n [2.1 CHẨN ĐOÁN CHỈ BÁO THỊ TRƯỜNG]"
                        txt += f"\n   ● [MA] {ma_d.get('status', '')}"
                        txt += f"\n   ● [MA Hành động] {ma_d.get('action', '')}"
                        txt += f"\n   ● [Ichimoku] {ichi_d.get('status', '')}"
                        txt += f"\n   ● [RSI Setup] {rsi_d.get('status', '')}"
                        txt += f"\n   [MACD Setup] {macd_d.get('status', '')}"
                        txt += f"\n   ● [ADX Setup] {adx_d.get('status', '')}"
                        
                        txt += f"\n\n [2.2 ĐÁNH GIÁ NẾN NHIỆT & ELLIOTT]"
                        txt += f"\n   ● Heatmap: {res_dict.get('heatmap_eval', 'N/A')}"
                        txt += f"\n   ● Elliott: {res_dict.get('elliott_eval', 'N/A')}\n"
                        
                        mcdx = res_dict.get('mcdx_eval', {})
                        if mcdx:
                            txt += f"\n [CHỈ BÁO DÒNG TIỀN TẠO LẬP - MCDX]"
                            txt += f"\n   ● Trạng thái : {mcdx.get('status', 'N/A')}"
                            txt += f"\n   ● Hành động  : {mcdx.get('action', 'N/A')}"
                            txt += f"\n   ● Chi tiết   : {mcdx.get('details', 'N/A')}\n"
                    else:
                        txt += f"\n * VSA: {vsa['dominant']} | Ichi: {ichi['trend']} | MA: {ma['trend_label']}"
                        txt += f"\n * RSI: {mom['rsi_val']} | MACD: {mom['macd_val']}\n"
                    
                    sigs = res_dict.get('signals', {})
                    if sigs and sigs.get('entry_type') != "NONE":
                        txt += f"\n 🔥 TÍN HIỆU: {sigs['entry_type']} ({sigs['confidence']})"
                    
                    # === STATE ENGINE: DAC DIEM TRANG THAI THI TRUONG ===
                    st = res_dict.get('state_rules', {})
                    alloc = "10-30%" # Default
                    alloc_note = "Chưa xác định rõ"
                    if st:
                        pri_map = {"UPTREND": "Sóng Tăng mạnh", "DOWNTREND": "Sóng Giảm mạnh", "UPTREND_START": "Vừa bứt phá vào sóng Tăng", "DOWNTREND_START": "Vừa gãy nền vào sóng Giảm", "WEAK_UPTREND": "Tăng nhưng yếu dần", "WEAK_DOWNTREND": "Giảm nhẹ (đà rơi chậm lại)", "RECOVERY": "Giai đoạn HỒI PHỤC", "RANGE": "Đi biên ngang", "SQUEEZE": "Nén chặt biên hẹp", "NEUTRAL": "Trạng thái Trung tính", "SIDEWAY": "Đi ngang"}
                        sec_map = {"PULLBACK": "Nhịp kéo ngược (chỉnh lành mạnh)", "FAILED_PULLBACK": "Kéo ngược thất bại (thủng nền)", "EXHAUSTION": "Đuối sức (nguy cơ đảo chiều)", "REVERSAL_BUILD": "Xây nền đảo chiều đáy", "ROLL_OVER": "Xác nhận gãy", "ACCUMULATION": "Gom hàng bám nền", "DISTRIBUTION": "Phân phối", "TRAP": "Bẫy giá (lùa gà)", "UNDER_PRESSURE": "Áp lực bán (Tiệm cận hỗ trợ)", "NORMAL": "Bình thường"}
                        sig_map = {"BREAKOUT_BUY": "MUA BREAKOUT", "PULLBACK_BUY": "MUA PULLBACK", "TREND_FOLLOW": "ÔM TIẾP", "REVERSAL_BUY": "MUA BẮT ĐÁY", "TAKE_PROFIT": "CHỐT LÃI", "EXIT_OR_SHORT": "THOÁT HÀNG", "EXIT_FAST": "CHẠY NGAY", "SHORT": "Đứng ngoài", "NO_TRADE": "Hạn chế mua mới", "NONE": "Chưa có tín hiệu"}
                        
                        st_pri = pri_map.get(st.get('primary', ''), st.get('primary', 'N/A'))
                        st_sec = sec_map.get(st.get('secondary', ''), st.get('secondary', 'N/A'))
                        st_sig = sig_map.get(st.get('signal', ''), st.get('signal', 'N/A'))
                        st_pri_raw = st.get('primary', '')
                        if st.get('signal') == "NO_TRADE":
                            if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                                st_sig = "Ưu tiên nắm giữ (Đợi chỉnh để mua)"
                            else:
                                st_sig = "Cần thận trọng (Chưa có điểm mua)"
                        
                        st_conf = int(st.get('confidence', 0))
                        st_avoid = st.get('avoid_entry', False)
                        
                        if st_conf >= 3: st_win = "Tốt (>= 70%)"
                        elif st_conf == 2: st_win = "Khá (~ 60%)"
                        elif st_conf >= 0: st_win = "Trung bình (~ 50%)"
                        else: st_win = "Thấp (< 50%)"
                        
                        # Ty trong khuyen nghi: ket hop State Engine + FTD + Phan phoi
                        st_pri_raw = st.get('primary', '')
                        ftd_on = res['ftd_active']
                        dist_n = res.get('distribution_count', 0)
                        
                        if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                            if ftd_on and dist_n <= 2:
                                alloc = "80-100%"
                                alloc_note = "Xu hướng mạnh, FTD xác nhận, phân phối ít -> ALL IN được"
                            elif ftd_on and dist_n > 2:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng phân phối đang tăng -> vẫn giữ tỷ trọng cao nhưng sẵn sàng hạ"
                            else:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng chưa có FTD xác nhận -> chưa nên full"
                        elif st_pri_raw == 'WEAK_UPTREND':
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Tăng yếu dần nhưng FTD còn sống -> canh giữ, giảm dần nếu chớm gãy"
                            else:
                                alloc = "30-50%"
                                alloc_note = "Tăng yếu dần, không có FTD -> cẩn thận chuyển giao"
                        elif st_pri_raw in ['RANGE', 'SQUEEZE', 'SIDEWAY', 'NEUTRAL']:
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Đang tích lũy/chuyển giao trong nhịp hồi có FTD -> ưu tiên nắm giữ cổ phiếu Leader"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Chưa rõ xu hướng, đang tích lũy/trung tính -> giữ tiền mặt chờ xác nhận"
                        elif st_pri_raw == 'WEAK_DOWNTREND':
                            if ftd_on:
                                alloc = "40-60%"
                                alloc_note = "Nhịp điều chỉnh/nghỉ chân trong đà hồi phục có FTD -> CƠ HỘI GOM HÀNG"
                            elif dist_n >= 3:
                                alloc = "0-15%"
                                alloc_note = "Giảm nhẹ + phân phối nhiều -> RỦI RO CAO, BÁN HẠ TỶ TRỌNG gấp"
                            else:
                                alloc = "15-30%"
                                alloc_note = "Điều chỉnh bình thường -> giữ ít, chờ xem có giữ nền không"
                        elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START']:
                            # Kiểm tra: FTD còn sống + regime đang RECOVERY → đây là nền MA giảm dài hạn,
                            # không phải gãy trend mới. Chỉ bán sạch khi FTD đã bị hủy.
                            _reg_now = res.get('regime', 'UNKNOWN')
                            if ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']:
                                alloc = "30-50%"
                                alloc_note = "Nền MA dài hạn còn giảm nhưng FTD đang kích hoạt + regime RECOVERY -> Thăm dò, KHÔNG bán sạch"
                            else:
                                alloc = "0-10%"
                                alloc_note = "Gãy xu hướng xác nhận (không có FTD bảo vệ) -> BÁN SẠCH, RA NGOÀI"
                        elif st_pri_raw == 'RECOVERY':
                            if ftd_on:
                                alloc = "50-75%"
                                alloc_note = "Hồi phục ổn định có FTD -> ưu tiên nắm giữ & quan sát điểm gia tăng"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Hồi phục kỹ thuật, chưa có FTD -> chỉ nên test tỷ trọng nhỏ"
                        else:
                            # Unify with regime if possible
                            reg = res['regime']
                            if reg == "STABLE_RECOVERY":
                                alloc, alloc_note = "50-75%", "Hồi phục ổn định trên MA20"
                            elif reg == "RECOVERY":
                                alloc, alloc_note = "30-50%", "Đang nỗ lực hồi phục"
                            else:
                                alloc = "10-30%"
                                alloc_note = "Chưa xác định rõ -> giữ ít phòng thủ"
                        
                        # Override boi avoid - CHI AP DUNG KHI THI TRUONG YEU HOAC DOWNTREND
                        if st_avoid:
                            if st_pri_raw in ['UPTREND', 'UPTREND_START', 'WEAK_UPTREND', 'RECOVERY'] and ftd_on:
                                # Neu dang vao trend manh, chi ha ty trong xuong muc than trong, khong ve 0-10%
                                if alloc == "80-100%": alloc = "60-80%"
                                elif alloc == "60-80%": alloc = "40-60%"
                                elif alloc == "50-70%": alloc = "30-50%"
                                elif alloc == "50-75%": alloc = "40-60%"
                                alloc_note = "⚠️ CẢNH BÁO: Thị trường quá nhiệt / MCDX phân phối -> Ưu tiên nắm giữ, hạn chế mua đuổi"
                            elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START', 'MARKET_WEAKENING']:
                                # Chi ban sach neu khong co FTD bao ve; neu FTD con song trong RECOVERY thi giu nguyen alloc
                                _reg_now = res.get('regime', 'UNKNOWN')
                                if not (ftd_on and _reg_now in ['RECOVERY', 'WEAK_RECOVERY', 'STABLE_RECOVERY']):
                                    alloc = "0-10%"
                                    alloc_note = "Bộ Lọc Rủi Ro đang BẬT + không có FTD -> CẤM MUA MỚI"
                            elif st_pri_raw in ['RECOVERY', 'WEAK_DOWNTREND'] and ftd_on:
                                # Dang hoi phuc co FTD: khong ep xuong 10-20%, ha nhe thoi
                                if alloc not in ['0-10%', '10-20%']:
                                    alloc_note = "⚠️ Bộ lọc rủi ro bật nhưng FTD còn sống -> Giữ thận trọng, hạn chế mua thêm"
                            else:
                                # Cac truong hop khac (Sideway/Neutral)
                                alloc = "10-20%"
                                alloc_note = "Thị trường lưỡng lự, bộ lọc rủi ro đang bật -> Tỷ trọng thấp"
                        
                        m = st.get('metrics', {})
                        
                        txt += "\n\n [2.3 ĐẶC ĐIỂM TRẠNG THÁI THỊ TRƯỜNG (ROBOT)]"
                        txt += f"\n   ● Xu Hướng Cốt Lõi    : {st_pri}"
                        txt += f"\n   ● Hành Vi Vận Động     : {st_sec}"
                        txt += f"\n   ● Tín Hiệu Khuyến Nghị: {st_sig}"
                        txt += f"\n   ● Xác Suất Thắng      : {st_win} (Hệ số: {st_conf})"
                        txt += f"\n   ● Tỷ Trọng Khuyên     : {alloc} cổ phiếu ({alloc_note})"
                        if m:
                            txt += f"\n   ● ADX: {m.get('adx',0):.1f} | MACD Hist: {m.get('hist',0):.2f} | Vol Spike: {m.get('vol_spike', False)} | Trend Bias: {m.get('trend_bias', 0)}"
                    
                    txt += "\n\n 🎯 TỔNG KẾT CHIẾN LƯỢC TỪ AI:"
                    
                    mcdx = res_dict.get('mcdx_eval', {})
                    if mcdx:
                        txt += f"\n  💰 DÒNG TIỀN TẠO LẬP (MCDX - Tham khảo): {mcdx.get('status', 'N/A')} -> {mcdx.get('action', 'N/A')}"
                        
                    reg = res['regime']
                    s1_val = f"{sr['s1']:,.0f}" if sr['s1'] > 0 else 'N/A'
                    s2_val = f"{sr['s2']:,.0f}" if sr['s2'] > 0 else 'N/A'
                    r1_val = f"{sr['r1']:,.0f}" if sr['r1'] > 0 else 'N/A'
                    r2_val = f"{sr['r2']:,.0f}" if sr['r2'] > 0 else 'N/A'
                    dist_count = res.get('distribution_count', 0)
                    ra_day = res.get('ra_day', 0)
                    ftd_quality = res.get('ftd_quality', 'N/A')
                    
                    # Tinh SL cho Index dua tren S1
                    sl_idx = f"{sr['s1'] * 0.99:,.0f}" if sr['s1'] > 0 else 'N/A'
                    
                    if res['ftd_active']:
                        if reg in ["UPTREND", "STABLE_RECOVERY"]:
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD XÁC NHẬN + ĐỒNG THUẬN TĂNG. MÔI TRƯỜNG THUẬN LỢI."
                            txt += f"\n     - Phân Bổ Tỷ Trọng      : Duy trì {alloc} cổ phiếu. Ưu tiên mã đang dẫn dắt (Leader)."
                            txt += f"\n     - 🛒 Vùng Mua Gia Tăng   : Nhặt thêm hàng khi Index test lại hỗ trợ {s1_val}. Mạnh dạn gom nếu về {s2_val}."
                            txt += f"\n     - 🎯 Vùng Chốt Một Phần  : Tỉa lộc khi Index chạm cản {r1_val} - {r2_val}. Không bán sạch khi trend còn sống."
                            txt += f"\n     - ✂ Báo Động Đỏ Khi Nào? : Nếu Index đóng cửa thủng hỗ trợ {s1_val} kèm Volume lớn -> Hạ về 50% tiền mặt ngay."
                        
                        elif reg == "UPTREND_UNDER_PRESSURE":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - CÓ FTD NHƯNG ÁP LỰC BÁN ĐANG TĂNG ({dist_count} phiên phân phối)."
                            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : BÁN BỚT HÀNG YẾU NGAY HÔM NAY. Không chờ hồi lên cản mới bán!"
                            txt += f"\n     - Cơ Cấu Danh Mục        : Loại bỏ ngay các mã gãy MA20 / mã thua lỗ nhiều. Chỉ giữ {alloc} cổ phiếu Leader khỏe."
                            txt += f"\n     - 🛡️ Phòng Thủ Khi Thủng S1: Nếu Index thủng hỗ trợ {s1_val} nhưng FTD chưa hỏng -> Hạ tỷ trọng về 50% cổ phiếu."
                            txt += f"\n     - ⚠️ Gãy Trend Xác Nhận   : Nếu FTD bị hủy (thủng đáy cũ) hoặc gãy xu hướng -> Nâng TIỀN MẶT lên 70%+, chỉ giữ 10-30% hoặc thoát sạch."
                            txt += f"\n     - 🛒 Mua Mới Được Không?  : CẤM FOMO. Chỉ test lượng nhỏ nếu Index đạp chuẩn về sâu {s2_val} rồi nảy lên giữ được."
                            txt += f"\n     - 📌 FTD Còn Sống Không?  : FTD ({ftd_quality}) sẽ BỊ HỦY nếu Index đóng cửa dưới mốc FTD cũ. Lúc đó -> chuyển sang DOWNTREND."
                        
                        elif reg == "RECOVERY":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD VỪA KÍCH HOẠT, MỚI VƯỢT MA10. CÒN SỚM ĐỂ BẮT ĐÁY MẠNH."
                            txt += f"\n     - Phân Bổ Tỷ Trọng      : Giữ {alloc} cổ phiếu. Test hàng nhỏ ở mã Leader."
                            txt += f"\n     - 🛒 Mua Ở Đâu?          : Chỉ nhặt khi Index duy trì trên {s1_val}. Nếu xé rào vượt {r1_val} kèm vol -> tăng lên 50%."
                            txt += f"\n     - ✂ Stoploss Cho Cả Port : Rút về 10% cổ phiếu nếu Index quay đầu thủng {sl_idx}."
                        
                        else:  # WEAK_RECOVERY hoac cac trang thai FTD khac
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD CÓ NHƯNG XUNG LỰC CHƯA RÕ. MÔI TRƯỜNG TRUNG TÍNH."
                            txt += f"\n     - Mua Dò Đường           : Giải ngân {alloc} test vị thế nhỏ khi Index nén quanh {s1_val}."
                            txt += f"\n     - Chờ Xác Nhận           : Chỉ tăng tỷ trọng lên 50%+ khi Index vượt {r1_val} kèm thanh khoản rõ ràng."
                            txt += f"\n     - ✂ Rút Lui Nếu          : Index đóng cửa dưới {sl_idx} -> xoá vị thế test, giữ tiền mặt chờ."
                    else:
                        if ra_day > 0:
                            txt += f"\n  👉 THỊ TRƯỜNG [ĐANG NỖ LỰC HỒI PHỤC - RA Ngày {ra_day}] - CHỜ XÁC NHẬN FTD."
                            txt += f"\n     - Tình Trạng             : Thị trường đang cố ngưng rơi nhưng CHƯA CÓ FTD. Mọi nhịp hồi đều có thể là bẫy."
                            txt += f"\n     - Tỷ Trọng Khuyên        : Giữ {alloc} cổ phiếu (toàn mã cực khỏe)."
                            txt += f"\n     - 🛒 Canh Mua Test        : Mua mồi 10% ở mã Leader nền đẹp khi Index đang test hỗ trợ {s1_val}."
                            txt += f"\n     - ⚡ Khi Nào Tăng Tỷ Trọng: Chờ FTD xuất hiện (Volume bùng nổ > TB20 + Close tăng > 1.5%). Khi đó mới nâng lên 40%."
                            txt += f"\n     - ✂ Đổ Máu Khi Nào?      : Nếu Index thủng đáy cũ {s2_val} -> BÁN SẠCH, RA NGOÀI HOÀN TOÀN."
                        elif reg == "MARKET_WEAKENING":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐÀ TĂNG CHẤM DỨT, BẮT ĐẦU SUY YẾU."
                            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : Cắt bỏ mã yếu NGAY LẬP TỨC. Không đợi hồi, không gồng."
                            txt += f"\n     - Tỷ Trọng Phòng Thủ     : Tối đa {alloc} cổ phiếu. Chỉ giữ mã còn trên MA50."
                            txt += f"\n     - 🔪 Người Kẹp Hàng Nặng : Canh bất kỳ nhịp kéo ảo nào chạm gần {r1_val} -> BÁN XẢ giảm tải. Đừng hy vọng."
                            txt += f"\n     - 🛒 Mua Lại Khi Nào?    : Chỉ khi Index đạp rã thật sâu về tận {s2_val} + xuất hiện FTD mới."
                        elif reg == "SIDEWAY":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐI NGANG BIÊN HẸP, KHÔNG CÓ XU HƯỚNG RÕ."
                            txt += f"\n     - Chiến Lược             : SWING TRADE biên. Mua sát {s1_val}, bán sát {r1_val}."
                            txt += f"\n     - Tỷ Trọng               : {alloc} cổ phiếu, ưu tiên mã có câu chuyện riêng."
                            txt += f"\n     - ✂ Rào Chắn             : Thủng {s2_val} -> chuyển sang phòng thủ 100% tiền mặt."
                        else:  # DOWNTREND / UNKNOWN
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - DOWNTREND / RỦI RO LỚN. ƯU TIÊN ÔM TIỀN MẶT."
                            txt += f"\n     - ⛔ LỆNH CẤM             : TUYỆT ĐỐI KHÔNG BẮT ĐÁY. Mọi nhịp hồi đều là bẫy Bull Trap."
                            txt += f"\n     - ✂ Cắt Lỗ Kỷ Luật       : Bán tháo toàn bộ mã yếu, mã thua lỗ. Không ngoại lệ."
                            txt += f"\n     - 🔪 Canh Xả Hàng Kẹp    : Nếu có nhịp Bull Trap nảy lên sát {r1_val} -> thoát sạch. Đây là CƠ HỘI VÀNG để chạy."
                            txt += f"\n     - 🛒 Vùng Cứu Trợ        : Chỉ quay lại thị trường khi Index đạp cạn kiệt về tận {s2_val} + FTD mới xác nhận."
                        
                    # Dong tong ket tu State Engine
                    if st:
                        txt += f"\n\n  📊 ĐÁNH GIÁ TỔNG HỢP TỪ ROBOT:"
                        txt += f"\n     Xu hướng: {st_pri} | Hành vi: {st_sec} | Tín hiệu: {st_sig}"
                        txt += f"\n     Xác suất tiếp diễn xu hướng hiện tại: {st_win}"
                        txt += f"\n     ➡️ TỶ TRỌNG KHUYẾN NGHỊ: NẮM GIỮ {alloc} CỔ PHIẾU."
                        if st_avoid:
                            if st_pri_raw in ['UPTREND', 'UPTREND_START'] and ftd_on:
                                txt += f"\n     ⚠️ CẢNH BÁO: Trạng thái quá nhiệt / Phân kỳ âm -> Ưu tiên bảo vệ thành quả, CHỐT LỜI DẦN."
                            else:
                                txt += f"\n     ⛔ BỘ LỌC RỦI RO: ĐANG BẬT - TUYỆT ĐỐI KHÔNG MUA MỚI."
                    
                    return txt





                vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")


                hn_key = next((k for k in self.data_dict.keys() if "HNX" in k or "HAINDEX" in k), "HNXINDEX")


                


                self.log_sync("   ... Đang phân tích kỹ thuật VNINDEX...")
                vn_full = analyze_full_index(self.data_dict.get(vn_key))
                
                self.log_sync("   ... Đang phân tích kỹ thuật HNX/UPCOM...")
                hn_full = analyze_full_index(self.data_dict.get(hn_key))


                


                report = []
                report.append("\n" + "="*60)
                vn_date_str = vn_full['date'] if vn_full else "N/A"
                report.append(f"💎 ĐÁNH GIÁ TỔNG QUAN THỊ TRƯỜNG - {vn_date_str} - AIC code! 💎")
                report.append(f"A. ĐỘ RỘNG THỊ TRƯỜNG (BREADTH): {breadth_res['breadth_label']}")
                report.append(f" - Tổng mã quét: {breadth_res['total_scanned']}")
                report.append(f" - Tỷ lệ mã > MA20: {breadth_res.get('strong_stocks_ma20_pct', 'N/A')}%")
                report.append(f" - Tỷ lệ mã > MA50: {breadth_res['strong_stocks_pct']}%")
                
                report.append("\n" + "="*60)
                if vn_full:
                    report.append(format_index(vn_key, vn_full, prefix="B. "))
                else:
                    report.append(f"\n--- TỔNG QUAN VNINDEX: Không tìm thấy dữ liệu.")
                if hn_full:
                    report.append("\n" + "="*60)
                    report.append(format_index(hn_key, hn_full, prefix="C. "))

                report.append("\n" + "="*60)


                    


                report.append("\n" + "="*60)


                


                self.log_sync("\n".join(report))


                


            except Exception as e:


                import traceback


                self.log_sync(f"\n❌ LỖI PHÂN TÍCH THỊ TRƯỜNG: {str(e)}\n{traceback.format_exc()}")


        


        import threading


        threading.Thread(target=analyze_task, daemon=True).start()





    def show_market_breadth(self):
        mb_data = getattr(self, 'market_breadth', None)
        if mb_data is None or mb_data.empty:
            # Try a last-minute update if we have enough analysis cache but mb is missing
            if len(self.analysis_cache) >= 5:
                self.log_sync("Đang khởi tạo lại dữ liệu biểu đồ độ rộng...")
                self._update_breadth_from_cache()
                mb_data = getattr(self, 'market_breadth', None)
            
            if mb_data is None or mb_data.empty:
                from tkinter import messagebox
                messagebox.showwarning("Cảnh báo", "Dữ liệu độ rộng thị trường chưa sẵn sàng. Vui lòng nhấn '📂 Load Cache' hoặc '🌐 Update' trước!")
                return
            
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            import matplotlib.ticker as mticker
            
            # --- Prepare Data ---
            days = 504
            df_plot = mb_data.tail(days).copy()
            if df_plot.empty: 
                messagebox.showwarning("Cảnh báo", "Dữ liệu độ rộng trống. Không thể vẽ.")
                return

            dates = pd.to_datetime(df_plot.index)
            df_plot['%MA20_smooth'] = df_plot['%MA20'].rolling(window=5, min_periods=1).mean()
            df_plot['%MA50_smooth'] = df_plot['%MA50'].rolling(window=5, min_periods=1).mean()
            
            # --- Create Figure ---
            fig, ax1 = plt.subplots(figsize=(14, 8))
            plt.style.use('default') # Use default white style
            fig.patch.set_facecolor('white')
            ax1.set_facecolor('white')
            
            # Ensure text visibility on white
            for item in ([ax1.title, ax1.xaxis.label, ax1.yaxis.label] +
                         ax1.get_xticklabels() + ax1.get_yticklabels()):
                item.set_color('black')

            # --- Primary Axis: Breadth (%) ---
            line1, = ax1.plot(dates, df_plot['%MA20_smooth'], color='#1A237E', linewidth=2.5, label='% Cổ phiếu > MA20')
            line2, = ax1.plot(dates, df_plot['%MA50_smooth'], color='#E65100', linewidth=2.5, label='% Cổ phiếu > MA50')
            
            ax1.set_title('BIỂU ĐỒ ĐỘ RỘNG THỊ TRƯỜNG & VNINDEX', fontsize=16, fontweight='bold', color='black', pad=25)
            ax1.set_xlabel('Thời Gian', color='black', fontweight='bold')
            ax1.set_ylabel('Tỉ Lệ Độ Rộng (%)', fontsize=11, fontweight='bold', color='black')
            ax1.set_ylim(0, 105)
            ax1.grid(True, linestyle=':', color='gray', alpha=0.3)
            
            # --- Secondary Axis: VNINDEX Price ---
            vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
            df_vn = self.data_dict.get(vn_key)
            if df_vn is not None and not df_vn.empty:
                # Merge logic to align VNIndex with Breadth dates
                df_vn_indexed = df_vn.copy()
                df_vn_indexed['Date'] = pd.to_datetime(df_vn_indexed['Date'])
                df_vn_indexed = df_vn_indexed.set_index('Date')
                
                # Get common dates
                common_dates = dates.intersection(df_vn_indexed.index)
                if not common_dates.empty:
                    df_vn_plot = df_vn_indexed.loc[common_dates]
                    ax2 = ax1.twinx()
                    
                    up = df_vn_plot[df_vn_plot['Close'] >= df_vn_plot['Open']]
                    down = df_vn_plot[df_vn_plot['Close'] < df_vn_plot['Open']]
                    
                    # Candlestick Bodies
                    ax2.bar(mdates.date2num(up.index), up['Close'] - up['Open'], bottom=up['Open'], color='#00CC00', edgecolor='black', linewidth=0.5, width=0.6, alpha=0.8, zorder=3)
                    ax2.bar(mdates.date2num(down.index), down['Open'] - down['Close'], bottom=down['Close'], color='#FF0000', edgecolor='black', linewidth=0.5, width=0.6, alpha=0.8, zorder=3)
                    
                    # Candlestick Wicks
                    ax2.vlines(mdates.date2num(up.index), up['Low'], up['High'], color='black', linewidth=1.0, zorder=2)
                    ax2.vlines(mdates.date2num(down.index), down['Low'], down['High'], color='black', linewidth=1.0, zorder=2)
                    
                    # Dummy line for legend
                    import matplotlib.lines as mlines
                    line3 = mlines.Line2D([], [], color='black', marker='s', linestyle='None', markersize=8, label='VNINDEX (Nến)')
                    
                    ax2.set_ylabel('Điểm số VNINDEX', color='black', fontsize=11, fontweight='bold')
                    ax2.tick_params(axis='y', labelcolor='black')
                    
                    # Combine legends
                    lines = [line1, line2, line3]
                    labels = [l.get_label() for l in lines]
                    ax1.legend(lines, labels, loc='upper left', frameon=True, shadow=True, facecolor='white', edgecolor='black', labelcolor='black')
            else:
                ax1.legend(loc='upper left', frameon=True, shadow=True, facecolor='white', edgecolor='black', labelcolor='black')

            # Annotate current values with clear background and separate positions to avoid overlap
            bbox_props = dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7)
            # MA20 (Navy) aligned to bottom (shows above the point)
            ax1.text(self.market_breadth.index[-1], self.market_breadth['%MA20'].iloc[-1], f" {self.market_breadth['%MA20'].iloc[-1]:.1f}%", 
                    color='#1A237E', fontweight='bold', va='bottom', ha='left', bbox=bbox_props)
            # MA50 (Orange) aligned to top (shows below the point)
            ax1.text(self.market_breadth.index[-1], self.market_breadth['%MA50'].iloc[-1], f" {self.market_breadth['%MA50'].iloc[-1]:.1f}%", 
                    color='#E65100', fontweight='bold', va='top', ha='left', bbox=bbox_props)


            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%Y'))
            fig.autofmt_xdate()
            
            plt.tight_layout()
            plt.show(block=False)

        except Exception as e:
            import traceback
            trace_str = traceback.format_exc()
            logger.error(f"Error in show_market_breadth: {e}\n{trace_str}")
            from tkinter import messagebox
            messagebox.showerror("Lỗi biểu đồ", f"Lỗi khi vẽ biểu đồ: {str(e)}")






if __name__ == "__main__":


    root = tk.Tk()


    app = TinvestApp(root)


    root.mainloop()


