"""
TINVEST – Trading Analysis System
==================================
Modules:
  1. data_loader     – Load & normalize OHLCV CSV data
  2. ichimoku_engine – Ichimoku cloud trend analysis
  3. vsa_engine      – Volume Spread Analysis
  4. aic_engine      – AIC entry setup detection
  5. scoring_engine  – Aggregate scoring & classification
  6. decision_engine – Opportunity & risk signals
  7. scanner         – Multi-ticker stock scanner
  8. analyzer        – Single-stock full analysis
"""

from .data_loader import load_data, enrich_dataframe
from .analyzer import analyze_stock, format_report
from .advanced_entry import classify_entry
from .accumulation_engine import analyze_accumulation
from .ma_engine import analyze_ma_trend

__all__ = ["load_data", "enrich_dataframe", "analyze_stock", "format_report"]
