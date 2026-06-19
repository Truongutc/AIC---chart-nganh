"""
tests/test_data_loader.py
=========================
Tests for Module 1 – Data Loader
"""
import pytest
import pandas as pd
from pathlib import Path

from tinvest.data_loader import load_data

SAMPLE_CSV    = Path(__file__).parent / "sample_data.csv"
MULTI_CSV     = Path(__file__).parent / "multi_ticker.csv"


class TestLoadData:

    def test_single_ticker_returns_dataframe(self):
        df = load_data(str(SAMPLE_CSV))
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 200

    def test_required_columns_present(self):
        df = load_data(str(SAMPLE_CSV))
        for col in ("Date", "Open", "High", "Low", "Close", "Volume"):
            assert col in df.columns, f"Missing column: {col}"

    def test_date_is_datetime(self):
        df = load_data(str(SAMPLE_CSV))
        assert pd.api.types.is_datetime64_any_dtype(df["Date"])

    def test_sorted_ascending(self):
        df = load_data(str(SAMPLE_CSV))
        assert df["Date"].is_monotonic_increasing

    def test_no_nan_in_ohlcv(self):
        df = load_data(str(SAMPLE_CSV))
        for col in ("Open", "High", "Low", "Close", "Volume"):
            assert df[col].isna().sum() == 0, f"NaN found in {col}"

    def test_multi_ticker_returns_dict(self):
        result = load_data(str(MULTI_CSV))
        assert isinstance(result, dict)
        assert "VNM" in result
        assert "HPG" in result

    def test_multi_ticker_each_is_dataframe(self):
        result = load_data(str(MULTI_CSV))
        for ticker, df in result.items():
            assert isinstance(df, pd.DataFrame), f"{ticker} should be a DataFrame"
            assert len(df) >= 200

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_data("non_existent_file.csv")

    def test_too_few_rows_raises(self, tmp_path):
        small = pd.DataFrame({
            "Date":   pd.date_range("2024-01-01", periods=50),
            "Open":   [10.0] * 50,
            "High":   [11.0] * 50,
            "Low":    [9.0]  * 50,
            "Close":  [10.5] * 50,
            "Volume": [1000] * 50,
        })
        p = tmp_path / "small.csv"
        small.to_csv(p, index=False)
        with pytest.raises(ValueError, match="Insufficient data"):
            load_data(str(p))
