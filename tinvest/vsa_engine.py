"""
Module 3 – VSA Engine (Volume Spread Analysis)
===============================================
Identifies VSA signal patterns in the last N bars of OHLCV data.

Signal types
------------
Bullish:
  - stopping_volume   : Very high volume, small body, long lower wick
  - no_supply         : Low volume, narrow spread, close near high
  - push_up           : Wide up bar, above-average volume

Bearish:
  - upthrust          : Wide spread up bar, very high volume, close near low
  - no_demand         : Narrow up bar, below-average volume

Output dict
-----------
{
    "signals"  : [{"type": str, "bar": int, "sentiment": "bullish"|"bearish"}, ...],
    "dominant" : "bullish" | "bearish" | "neutral",
    "score"    : 0 – 4
}
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Tuneable thresholds ────────────────────────────────────────────────────────
VOL_WINDOW       = 20   # baseline rolling window for avg volume
SPREAD_WINDOW    = 20   # baseline rolling window for avg spread (H-L)
SCAN_BARS        = 5    # how many recent bars to scan for signals
VOL_HIGH_MULT    = 1.5  # volume multiplier for "high volume"
VOL_VERY_HIGH    = 2.0  # volume multiplier for "very high volume"
VOL_LOW_MULT     = 0.7  # volume multiplier for "low volume"
WICK_RATIO       = 0.4  # lower wick / total range threshold for long wick
BODY_RATIO       = 0.35 # body / total range threshold for "small body"
CLOSE_HIGH_RATIO = 0.7  # close position in range for "near high"
CLOSE_LOW_RATIO  = 0.3  # close position in range for "near low"


def _body(row: pd.Series) -> float:
    return abs(row["Close"] - row["Open"])


def _spread(row: pd.Series) -> float:
    return row["High"] - row["Low"] + 1e-10


def _lower_wick(row: pd.Series) -> float:
    return min(row["Open"], row["Close"]) - row["Low"]


def _upper_wick(row: pd.Series) -> float:
    return row["High"] - max(row["Open"], row["Close"])


def _close_pos(row: pd.Series) -> float:
    """Where close sits within H-L range (0 = at Low, 1 = at High)."""
    rng = _spread(row)
    return (row["Close"] - row["Low"]) / rng


def _is_up_bar(row: pd.Series) -> bool:
    return row["Close"] > row["Open"]


def _detect_signals(df: pd.DataFrame, avg_vol: pd.Series, avg_spread: pd.Series) -> list[dict]:
    signals = []
    scan_start = max(0, len(df) - SCAN_BARS)
    sub = df.iloc[scan_start:].reset_index(drop=True)
    av  = avg_vol.iloc[scan_start:].reset_index(drop=True)
    asp = avg_spread.iloc[scan_start:].reset_index(drop=True)

    for i in range(len(sub)):
        row   = sub.iloc[i]
        avol  = av.iloc[i]
        asprd = asp.iloc[i]
        vol   = row["Volume"]
        sprd  = _spread(row)
        body  = _body(row)
        lwck  = _lower_wick(row)
        cpos  = _close_pos(row)

        # ── Stopping Volume (bullish) ──────────────────────────────────────────
        if (vol > avol * VOL_VERY_HIGH
                and body / sprd < BODY_RATIO
                and lwck / sprd > WICK_RATIO):
            signals.append({"type": "stopping_volume", "bar": scan_start + i, "sentiment": "bullish"})
            continue  # most significant – skip further checks on same bar

        # ── Upthrust (bearish) ────────────────────────────────────────────────
        if (_is_up_bar(row)
                and vol > avol * VOL_VERY_HIGH
                and sprd > asprd * 1.2
                and cpos < CLOSE_LOW_RATIO):
            signals.append({"type": "upthrust", "bar": scan_start + i, "sentiment": "bearish"})
            continue

        # ── Push Up (bullish) ─────────────────────────────────────────────────
        if (_is_up_bar(row)
                and vol > avol * VOL_HIGH_MULT
                and sprd > asprd * 1.1
                and cpos > CLOSE_HIGH_RATIO):
            signals.append({"type": "push_up", "bar": scan_start + i, "sentiment": "bullish"})

        # ── No Supply (bullish) ───────────────────────────────────────────────
        elif (not _is_up_bar(row)
              and vol < avol * VOL_LOW_MULT
              and sprd < asprd * 0.9
              and cpos > CLOSE_HIGH_RATIO):
            signals.append({"type": "no_supply", "bar": scan_start + i, "sentiment": "bullish"})

        # ── No Demand (bearish) ───────────────────────────────────────────────
        elif (_is_up_bar(row)
              and vol < avol * VOL_LOW_MULT
              and sprd < asprd * 0.9):
            signals.append({"type": "no_demand", "bar": scan_start + i, "sentiment": "bearish"})

    return signals


def analyze_vsa(df: pd.DataFrame) -> dict:
    """
    Run Volume Spread Analysis on a clean OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame  – clean OHLCV data (output of data_loader)

    Returns
    -------
    dict  (see module docstring for schema)
    """
    if len(df) < VOL_WINDOW:
        pass # Silenced as per user request to allow any row count

    avg_vol    = df["Volume"].rolling(VOL_WINDOW).mean()
    avg_spread = (df["High"] - df["Low"]).rolling(SPREAD_WINDOW).mean()

    signals = _detect_signals(df, avg_vol, avg_spread)

    # ── Dominant sentiment & score ─────────────────────────────────────────────
    bullish_signals = [s for s in signals if s["sentiment"] == "bullish"]
    bearish_signals = [s for s in signals if s["sentiment"] == "bearish"]

    # Weights: stopping_volume=2, push_up=1, no_supply=1
    bull_weight = sum(
        2 if s["type"] == "stopping_volume" else 1
        for s in bullish_signals
    )
    bear_weight = len(bearish_signals)

    if bull_weight > bear_weight:
        dominant = "bullish"
    elif bear_weight > bull_weight:
        dominant = "bearish"
    else:
        dominant = "neutral"

    # Score: clamp to 0–4
    raw_score = bull_weight - bear_weight
    score = int(min(4, max(0, raw_score)))

    result = {
        "signals":  signals,
        "dominant": dominant,
        "score":    score,
    }
    logger.debug(f"VSA result: dominant={dominant}, score={score}, signals={signals}")
    return result
