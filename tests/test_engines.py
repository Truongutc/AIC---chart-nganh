"""
tests/test_engines.py
=====================
Tests for Modules 2, 3, 4 (Ichimoku, VSA, AIC engines)
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from tinvest.data_loader     import load_data
from tinvest.ichimoku_engine import analyze_ichimoku, compute_ichimoku
from tinvest.vsa_engine      import analyze_vsa
from tinvest.aic_engine      import analyze_aic

SAMPLE_CSV = Path(__file__).parent / "sample_data.csv"


@pytest.fixture(scope="module")
def sample_df():
    return load_data(str(SAMPLE_CSV))


# ═══════════════════════════════════════════════════════════════════
#  Module 2 – Ichimoku
# ═══════════════════════════════════════════════════════════════════

class TestIchimoku:

    def test_returns_dict_with_required_keys(self, sample_df):
        result = analyze_ichimoku(sample_df)
        for key in ("trend", "price_vs_kumo", "cloud_color", "kijun_slope",
                    "tenkan_kijun_cross", "score"):
            assert key in result, f"Missing key: {key}"

    def test_trend_is_valid(self, sample_df):
        result = analyze_ichimoku(sample_df)
        assert result["trend"] in ("UP", "DOWN", "SIDEWAY")

    def test_cloud_color_is_valid(self, sample_df):
        result = analyze_ichimoku(sample_df)
        assert result["cloud_color"] in ("green", "red")

    def test_kijun_slope_is_valid(self, sample_df):
        result = analyze_ichimoku(sample_df)
        assert result["kijun_slope"] in ("up", "down", "flat")

    def test_tenkan_kijun_cross_is_valid(self, sample_df):
        result = analyze_ichimoku(sample_df)
        assert result["tenkan_kijun_cross"] in ("bullish", "bearish", "none")

    def test_score_in_range(self, sample_df):
        result = analyze_ichimoku(sample_df)
        assert 0 <= result["score"] <= 3

    def test_compute_ichimoku_columns(self, sample_df):
        ichi = compute_ichimoku(sample_df)
        for col in ("Tenkan", "Kijun", "SpanA", "SpanB"):
            assert col in ichi.columns


# ═══════════════════════════════════════════════════════════════════
#  Module 3 – VSA
# ═══════════════════════════════════════════════════════════════════

class TestVSA:

    def test_returns_dict_with_required_keys(self, sample_df):
        result = analyze_vsa(sample_df)
        for key in ("signals", "dominant", "score"):
            assert key in result

    def test_dominant_is_valid(self, sample_df):
        result = analyze_vsa(sample_df)
        assert result["dominant"] in ("bullish", "bearish", "neutral")

    def test_score_in_range(self, sample_df):
        result = analyze_vsa(sample_df)
        assert 0 <= result["score"] <= 4

    def test_signals_list(self, sample_df):
        result = analyze_vsa(sample_df)
        assert isinstance(result["signals"], list)
        for sig in result["signals"]:
            assert "type" in sig
            assert "sentiment" in sig
            assert sig["sentiment"] in ("bullish", "bearish")


# ═══════════════════════════════════════════════════════════════════
#  Module 4 – AIC
# ═══════════════════════════════════════════════════════════════════

class TestAIC:

    def test_returns_dict_with_required_keys(self, sample_df):
        result = analyze_aic(sample_df)
        for key in ("setup", "valid", "breakout_level", "score"):
            assert key in result

    def test_setup_is_valid(self, sample_df):
        result = analyze_aic(sample_df)
        assert result["setup"] in ("A", "B", "C", "NONE")

    def test_score_in_range(self, sample_df):
        result = analyze_aic(sample_df)
        assert 0 <= result["score"] <= 4

    def test_setup_a_detected_on_breakout(self):
        """Synthetically create a clear breakout and verify Setup A is found."""
        n = 260
        rng = np.random.default_rng(1)
        closes = np.ones(n) * 50.0
        highs  = closes + 1
        lows   = closes - 1
        opens  = closes.copy()
        vols   = np.ones(n) * 1_000_000

        # Big breakout on last bar
        closes[-1] = 60.0
        highs[-1]  = 61.0
        vols[-1]   = 5_000_000  # 5x volume

        df = pd.DataFrame({
            "Date":   pd.date_range("2023-01-02", periods=n, freq="B"),
            "Open":   opens, "High": highs, "Low": lows,
            "Close":  closes, "Volume": vols,
        })
        result = analyze_aic(df)
        assert result["setup"] == "A", f"Expected Setup A, got {result['setup']}"
        assert result["valid"] is True
