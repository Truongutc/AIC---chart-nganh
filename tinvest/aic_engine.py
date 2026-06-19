"""
Module 4 – AIC Engine (Entry Setup Detection)
=============================================
Identifies AIC entry setups (A, B, C) based on breakout / pullback / early logic.

Setup definitions
-----------------
A – Breakout  : Close > highest High of last 20–50 bars AND volume spike
B – Pullback  : Price retreated to breakout zone, no breakdown, declining volume
C – Early     : Stopping-volume candle + hammer pattern (pre-breakout accumulation)

Output dict
-----------
{
    "setup"          : "A" | "B" | "C" | "NONE",
    "valid"          : bool,
    "breakout_level" : float | None,
    "detail"         : str,
    "score"          : 0 – 4
}
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
BO_LOOKBACK_MIN  = 20   # min lookback for breakout high
BO_LOOKBACK_MAX  = 50   # max lookback for breakout high
BO_VOL_MULT      = 1.5  # volume multiplier for breakout confirmation
PB_ZONE_PCT      = 0.03 # pullback tolerance around breakout level (3%)
PB_VOL_DECLINE   = 0.8  # pullback volume must be < 80% of avg volume
EARLY_VOL_MULT   = 2.0  # high volume required for stopping candle
EARLY_WICK_RATIO = 0.4  # lower wick ratio for hammer
EARLY_BODY_RATIO = 0.35 # small body ratio for stopping candle


def _rolling_max_high(df: pd.DataFrame, lookback: int) -> float:
    """Max High over last `lookback` bars (excluding the current bar)."""
    hist = df["High"].iloc[-(lookback + 1):-1]
    return float(hist.max()) if not hist.empty else float("nan")


def _avg_volume(df: pd.DataFrame, window: int = 20) -> float:
    hist = df["Volume"].iloc[-(window + 1):-1]
    return float(hist.mean()) if not hist.empty else float("nan")


def _is_hammer(row: pd.Series) -> bool:
    """True if the candle has a long lower wick and small body (hammer pattern)."""
    total = row["High"] - row["Low"] + 1e-10
    body  = abs(row["Close"] - row["Open"])
    lower_wick = min(row["Open"], row["Close"]) - row["Low"]
    return (body / total < EARLY_BODY_RATIO) and (lower_wick / total > EARLY_WICK_RATIO)


def _find_breakout_level(df: pd.DataFrame) -> tuple[float | None, int | None]:
    """
    Scan last BO_LOOKBACK_MAX bars for a breakout event.
    Returns (breakout_level, bar_index_of_breakout) or (None, None).
    """
    # We look within the recent window for a bar where Close exceeded the prior max
    scan_start = max(0, len(df) - BO_LOOKBACK_MAX - 1)
    sub = df.iloc[scan_start:]
    for i in range(BO_LOOKBACK_MIN, len(sub)):
        prior_high = sub["High"].iloc[max(0, i - BO_LOOKBACK_MAX):i].max()
        bar = sub.iloc[i]
        if bar["Close"] > prior_high:
            avg_vol = sub["Volume"].iloc[max(0, i - 20):i].mean()
            if bar["Volume"] > avg_vol * BO_VOL_MULT:
                return float(prior_high), scan_start + i
    return None, None


def _check_setup_a(df: pd.DataFrame) -> dict:
    """Setup A – fresh breakout on the most recent bar or very recent bars."""
    last   = df.iloc[-1]
    avg_v  = _avg_volume(df)

    # Try multiple lookbacks from 20 to 50
    for lookback in range(BO_LOOKBACK_MIN, BO_LOOKBACK_MAX + 1, 5):
        max_high = _rolling_max_high(df, lookback)
        if pd.isna(max_high):
            continue
        if last["Close"] > max_high and last["Volume"] > avg_v * BO_VOL_MULT:
            return {
                "setup": "A",
                "valid": True,
                "breakout_level": max_high,
                "detail": (
                    f"Breakout: Close {last['Close']:.2f} > {lookback}-bar high {max_high:.2f}, "
                    f"Volume {last['Volume']:.0f} ({last['Volume']/avg_v:.1f}x avg)"
                ),
                "score": 4,
            }
    return {}


def _check_setup_b(df: pd.DataFrame, breakout_level: float) -> dict:
    """Setup B – pullback to breakout level with declining volume."""
    last  = df.iloc[-1]
    avg_v = _avg_volume(df)

    above_floor = last["Close"] >= breakout_level * (1 - PB_ZONE_PCT)
    within_zone = last["Close"] <= breakout_level * (1 + PB_ZONE_PCT * 2)
    low_vol     = last["Volume"] < avg_v * PB_VOL_DECLINE
    no_break    = last["Low"] >= breakout_level * (1 - PB_ZONE_PCT)

    if above_floor and within_zone and low_vol and no_break:
        return {
            "setup": "B",
            "valid": True,
            "breakout_level": breakout_level,
            "detail": (
                f"Pullback: Close {last['Close']:.2f} near breakout {breakout_level:.2f}, "
                f"Volume {last['Volume']:.0f} ({last['Volume']/avg_v:.1f}x avg, declining)"
            ),
            "score": 3,
        }
    return {}


def _check_setup_c(df: pd.DataFrame) -> dict:
    """Setup C – early accumulation: stopping-volume hammer candle."""
    avg_v = _avg_volume(df)
    # Check last 3 bars for a stopping-volume hammer
    for i in range(-1, -4, -1):
        row = df.iloc[i]
        total = row["High"] - row["Low"] + 1e-10
        body  = abs(row["Close"] - row["Open"])
        lower = min(row["Open"], row["Close"]) - row["Low"]
        high_vol = row["Volume"] > avg_v * EARLY_VOL_MULT
        hammer   = (body / total < EARLY_BODY_RATIO) and (lower / total > EARLY_WICK_RATIO)
        if high_vol and hammer:
            return {
                "setup": "C",
                "valid": True,
                "breakout_level": None,
                "detail": (
                    f"Early setup: Stopping-volume hammer at bar {i} "
                    f"(Volume {row['Volume']:.0f}, {row['Volume']/avg_v:.1f}x avg)"
                ),
                "score": 2,
            }
    return {}


def analyze_aic(df: pd.DataFrame) -> dict:
    """
    Detect AIC entry setups on a clean OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame  – clean OHLCV data (output of data_loader)

    Returns
    -------
    dict  (see module docstring for schema)
    """
    default = {
        "setup": "NONE",
        "valid": False,
        "breakout_level": None,
        "detail": "No AIC setup detected.",
        "score": 0,
    }

    if len(df) < BO_LOOKBACK_MIN + 5:
        logger.warning("Not enough bars for AIC analysis.")
        return default

    # Priority: A → B → C
    result = _check_setup_a(df)
    if result:
        logger.debug(f"AIC: {result}")
        return result

    # For B, we need a historical breakout level
    bo_level, _ = _find_breakout_level(df)
    if bo_level is not None:
        result = _check_setup_b(df, bo_level)
        if result:
            logger.debug(f"AIC: {result}")
            return result

    result = _check_setup_c(df)
    if result:
        logger.debug(f"AIC: {result}")
        return result

    logger.debug("AIC: No setup found.")
    return default
