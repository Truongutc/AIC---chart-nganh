"""
Module 2 – Ichimoku Engine
===========================
Computes Ichimoku Kinko Hyo indicators and evaluates trend state, cloud color,
Kijun slope, and Tenkan/Kijun crossover.

Output dict
-----------
{
    "trend"              : "UP" | "DOWN" | "SIDEWAY",
    "price_vs_kumo"      : "above" | "below" | "inside",
    "cloud_color"        : "green" | "red",
    "kijun_slope"        : "up" | "down" | "flat",
    "tenkan_kijun_cross" : "bullish" | "bearish" | "none",
    "score"              : 0 – 3
}
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Indicator helpers ──────────────────────────────────────────────────────────

def _donchian_mid(series_high: pd.Series, series_low: pd.Series, period: int) -> pd.Series:
    """(highest_high + lowest_low) / 2 over rolling window."""
    return (series_high.rolling(window=period).max() + series_low.rolling(window=period).min()) / 2


def compute_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append Ichimoku columns to a copy of df and return it.
    Optimized: only calculates missing columns.
    """
    out = df.copy()

    if "Tenkan" not in out.columns:
        out["Tenkan"] = _donchian_mid(out["High"], out["Low"], 9)
    if "Kijun" not in out.columns:
        out["Kijun"]  = _donchian_mid(out["High"], out["Low"], 26)
    if "Kijun65" not in out.columns:
        out["Kijun65"] = _donchian_mid(out["High"], out["Low"], 65)

    if "SpanA" not in out.columns:
        out["SpanA"]  = ((out["Tenkan"] + out["Kijun"]) / 2).shift(26)
    if "SpanB" not in out.columns:
        out["SpanB"]  = _donchian_mid(out["High"], out["Low"], 52).shift(26)
    if "Chikou" not in out.columns:
        out["Chikou"] = out["Close"].shift(-26)

    if "CloudTop" not in out.columns:
        out["CloudTop"] = out[["SpanA", "SpanB"]].max(axis=1)
    if "CloudBottom" not in out.columns:
        out["CloudBottom"] = out[["SpanA", "SpanB"]].min(axis=1)

    return out


def _kijun_slope(kijun_series: pd.Series, window: int = 5) -> str:
    """Determine Kijun slope over the last `window` bars using linear regression."""
    recent = kijun_series.dropna().iloc[-window:]
    if len(recent) < 2:
        return "flat"
    x = np.arange(len(recent))
    slope, _ = np.polyfit(x, recent.values, 1)
    # Treat anything less than 0.01% per bar as flat
    pct_slope = slope / (recent.mean() + 1e-10)
    if pct_slope > 0.001:
        return "up"
    elif pct_slope < -0.001:
        return "down"
    return "flat"


def _tk_cross(df: pd.DataFrame) -> str:
    """Detect the most recent Tenkan / Kijun crossover in the last 3 bars."""
    sub = df[["Tenkan", "Kijun"]].dropna().iloc[-4:]
    if len(sub) < 2:
        return "none"
    for i in range(len(sub) - 1, 0, -1):
        prev_t, prev_k = sub.iloc[i - 1]["Tenkan"], sub.iloc[i - 1]["Kijun"]
        curr_t, curr_k = sub.iloc[i]["Tenkan"],    sub.iloc[i]["Kijun"]
        if prev_t <= prev_k and curr_t > curr_k:
            return "bullish"
        if prev_t >= prev_k and curr_t < curr_k:
            return "bearish"
    return "none"


def analyze_ichimoku(df: pd.DataFrame) -> dict:
    """
    Run Ichimoku analysis on a clean OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Clean OHLCV DataFrame (output of data_loader.load_data).

    Returns
    -------
    dict  (see module docstring for schema)
    """
    if len(df) < 52:
        pass # Silenced as per user request to allow any row count

    ichi = compute_ichimoku(df)
    last = ichi.iloc[-1]

    close   = last["Close"]
    span_a  = last["SpanA"]
    span_b  = last["SpanB"]

    # ── Price vs Kumo ──────────────────────────────────────────────────────────
    if pd.isna(span_a) or pd.isna(span_b):
        price_vs_kumo = "inside"
        trend         = "SIDEWAY"
    else:
        kumo_top = max(span_a, span_b)
        kumo_bot = min(span_a, span_b)
        if close > kumo_top:
            price_vs_kumo = "above"
            trend         = "UP"
        elif close < kumo_bot:
            price_vs_kumo = "below"
            trend         = "DOWN"
        else:
            price_vs_kumo = "inside"
            trend         = "SIDEWAY"

    # ── Cloud color ────────────────────────────────────────────────────────────
    # Future cloud: compare SpanA and SpanB shifted *forward* 26 bars
    future_a = ((ichi["Tenkan"] + ichi["Kijun"]) / 2).iloc[-1]
    future_b = _donchian_mid(ichi["High"], ichi["Low"], 52).iloc[-1]
    cloud_color = "green" if (not pd.isna(future_a) and not pd.isna(future_b) and future_a >= future_b) else "red"

    # ── Kijun slope ────────────────────────────────────────────────────────────
    kijun_slope = _kijun_slope(ichi["Kijun"])

    # ── TK Cross ───────────────────────────────────────────────────────────────
    tk_cross = _tk_cross(ichi)

    # ── Score (0–3) ───────────────────────────────────────────────────────────
    score = 0
    if price_vs_kumo == "above":
        score += 1
    if cloud_color == "green":
        score += 1
    if kijun_slope == "up":
        score += 1

    result = {
        "trend":              trend,
        "price_vs_kumo":      price_vs_kumo,
        "cloud_color":        cloud_color,
        "kijun_slope":        kijun_slope,
        "tenkan_kijun_cross": tk_cross,
        "score":              score,
        "tenkan":             float(last["Tenkan"]),
        "kijun":              float(last["Kijun"]),
        "kijun65":            float(last["Kijun65"]),
        "span_a":             float(span_a) if not pd.isna(span_a) else 0,
        "span_b":             float(span_b) if not pd.isna(span_b) else 0,
        "cloud_top":          float(max(span_a, span_b)) if not (pd.isna(span_a) or pd.isna(span_b)) else 0,
        "cloud_bottom":       float(min(span_a, span_b)) if not (pd.isna(span_a) or pd.isna(span_b)) else 0,
    }
    logger.debug(f"Ichimoku result: {result}")
    return result
