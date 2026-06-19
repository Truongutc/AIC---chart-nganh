import sys
import os
import pandas as pd
import unittest

# Append the project path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from AICcode import TinvestApp

class DummyRoot:
    def update(self):
        pass

class MockApp:
    def __init__(self):
        self.analysis_cache = {}
        self.logged_messages = []
        self.root = DummyRoot()
        
    def log_sync(self, message, clear=False):
        if clear:
            self.logged_messages = []
        self.logged_messages.append(message)

    def run_custom_filter(self, selected_categories, selected_rules):
        # We reuse the actual method from TinvestApp but bind it to our mock context
        TinvestApp.run_custom_filter(self, selected_categories, selected_rules)

    def run_advanced_scanner(self, entry_target):
        # We reuse the actual method from TinvestApp but bind it to our mock context
        TinvestApp.run_advanced_scanner(self, entry_target)

class TestCustomDisplayFilter(unittest.TestCase):
    def test_display_filtering_category_only(self):
        app = MockApp()
        
        # 1. Mock a stock that has Gia Tăng 2 (ADD_2) - SHOULD BE DISPLAYED
        df_add2 = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
        })
        app.analysis_cache["TCK_ADD2"] = {
            "df": df_add2,
            "adv": {"entry_type": "ADD_2"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }
        
        # 2. Mock a stock that has Mua Sớm (EARLY) - SHOULD NOT BE DISPLAYED since it's not in the 6 selected categories
        df_early = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
        })
        app.analysis_cache["TCK_EARLY"] = {
            "df": df_early,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # 3. Mock a stock that has Tích Lũy (ACCUMULATION) - SHOULD BE DISPLAYED
        df_accum = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
        })
        app.analysis_cache["TCK_ACCUM"] = {
            "df": df_accum,
            "adv": {"entry_type": "NONE"},
            "accum": {"is_accumulation": True, "base_quality": "HIGH"},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # Run custom filter with categories filter only (ADD_2 and ACCUMULATION)
        app.run_custom_filter(["ADD_2", "ACCUMULATION"], [])
        
        output_text = "\n".join(app.logged_messages)
        print("Category-Only Filter Test Output:\n", output_text)
        
        # TCK_ADD2 and TCK_ACCUM should be in the results
        self.assertIn("TCK_ADD2", output_text)
        self.assertIn("TCK_ACCUM", output_text)
        
        # TCK_EARLY should be filtered out
        self.assertNotIn("TCK_EARLY", output_text)

    def test_display_filtering_rule_only(self):
        app = MockApp()
        
        # 1. Mock a stock that matches RS13 > 50 (Filter 2 rule) but does NOT have one of the 6 signals - SHOULD BE DISPLAYED
        df_rs13_pass = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
            "RS13": [60.0] * 10,
        })
        app.analysis_cache["TCK_RS_PASS"] = {
            "df": df_rs13_pass,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }
        
        # 2. Mock a stock that fails RS13 > 50 - SHOULD NOT BE DISPLAYED
        df_rs13_fail = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
            "RS13": [40.0] * 10,
        })
        app.analysis_cache["TCK_RS_FAIL"] = {
            "df": df_rs13_fail,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # Run custom filter with rule filter only (RS13_GT_50)
        app.run_custom_filter([], ["RS13_GT_50"])
        
        output_text = "\n".join(app.logged_messages)
        print("Rule-Only Filter Test Output:\n", output_text)
        
        # TCK_RS_PASS should be in the results
        self.assertIn("TCK_RS_PASS", output_text)
        
        # TCK_RS_FAIL should be filtered out
        self.assertNotIn("TCK_RS_FAIL", output_text)

    def test_rsi_divergence_custom_filter(self):
        app = MockApp()
        
        # 1. Mock a stock that has a valid RSI Bullish Divergence
        lows_pass = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
        rsis_pass = [45] * 20
        rsis_pass[5] = 30.0
        rsis_pass[14] = 38.0
        closes_pass = [x + 1 for x in lows_pass]
        df_pass = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=20),
            "Low": lows_pass,
            "RSI": rsis_pass,
            "Close": closes_pass,
            "Volume": [250000] * 20,
        })
        app.analysis_cache["TCK_DIV_PASS"] = {
            "df": df_pass,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # 2. Mock a stock that does NOT have RSI Bullish Divergence (flat RSI)
        df_fail = df_pass.copy()
        df_fail.loc[14, "RSI"] = 34.0  # slope <= 5
        app.analysis_cache["TCK_DIV_FAIL"] = {
            "df": df_fail,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # Run custom filter with the RSI_BULLISH_DIVERGENCE rule
        app.run_custom_filter([], ["RSI_BULLISH_DIVERGENCE"])
        
        output_text = "\n".join(app.logged_messages)
        print("RSI Divergence Filter Test Output:\n", output_text)
        
        # TCK_DIV_PASS should be in the results
        self.assertIn("TCK_DIV_PASS", output_text)
        # TCK_DIV_FAIL should be filtered out
        self.assertNotIn("TCK_DIV_FAIL", output_text)

    def test_macd_divergence_custom_filter(self):
        app = MockApp()
        
        # 1. Mock a stock that has a valid MACD Bullish Divergence
        lows_pass = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
        macds_pass = [-1.5] * 20
        macds_pass[5] = -1.2
        macds_pass[14] = -0.5
        closes_pass = [x + 1 for x in lows_pass]
        df_pass = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=20),
            "Low": lows_pass,
            "MACD": macds_pass,
            "Close": closes_pass,
            "Volume": [250000] * 20,
        })
        app.analysis_cache["TCK_MACD_PASS"] = {
            "df": df_pass,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # 2. Mock a stock that does NOT have MACD Bullish Divergence (MACD positive)
        df_fail = df_pass.copy()
        df_fail.loc[14, "MACD"] = 0.1
        app.analysis_cache["TCK_MACD_FAIL"] = {
            "df": df_fail,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # Run custom filter with the MACD_BULLISH_DIVERGENCE rule
        app.run_custom_filter([], ["MACD_BULLISH_DIVERGENCE"])
        
        output_text = "\n".join(app.logged_messages)
        print("MACD Divergence Filter Test Output:\n", output_text)
        
        # TCK_MACD_PASS should be in the results
        self.assertIn("TCK_MACD_PASS", output_text)
        # TCK_MACD_FAIL should be filtered out
        self.assertNotIn("TCK_MACD_FAIL", output_text)

    def test_macd_hist_divergence_custom_filter(self):
        app = MockApp()
        
        # 1. Mock a stock that has a valid MACD Histogram Bullish Divergence
        lows_pass = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
        hists_pass = [-1.5] * 20
        hists_pass[5] = -1.2
        hists_pass[14] = -0.5
        closes_pass = [x + 1 for x in lows_pass]
        df_pass = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=20),
            "Low": lows_pass,
            "MACD_Hist": hists_pass,
            "Close": closes_pass,
            "Volume": [250000] * 20,
        })
        app.analysis_cache["TCK_HIST_PASS"] = {
            "df": df_pass,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # 2. Mock a stock that does NOT have MACD Histogram Bullish Divergence (positive)
        df_fail = df_pass.copy()
        df_fail.loc[14, "MACD_Hist"] = 0.1
        app.analysis_cache["TCK_HIST_FAIL"] = {
            "df": df_fail,
            "adv": {"entry_type": "EARLY"},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }

        # Run custom filter with the MACD_HIST_BULLISH_DIVERGENCE rule
        app.run_custom_filter([], ["MACD_HIST_BULLISH_DIVERGENCE"])
        
        output_text = "\n".join(app.logged_messages)
        print("MACD Histogram Divergence Filter Test Output:\n", output_text)
        
        # TCK_HIST_PASS should be in the results
        self.assertIn("TCK_HIST_PASS", output_text)
        # TCK_HIST_FAIL should be filtered out
        self.assertNotIn("TCK_HIST_FAIL", output_text)


    def test_advanced_scanner_display_filtering(self):
        app = MockApp()
        
        # 1. Mock a stock that has Mua Sớm (EARLY) and is in Tích Lũy (ACCUMULATION) - SHOULD BE DISPLAYED
        df_early_accum = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
        })
        app.analysis_cache["TCK_EARLY_ACCUM"] = {
            "df": df_early_accum,
            "adv": {"entry_type": "EARLY", "position_size": "20%", "confidence": "HIGH", "risk_flags": []},
            "accum": {"is_accumulation": True, "base_quality": "HIGH"},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }
        
        # 2. Mock a stock that has Mua Sớm (EARLY) but no other of the 6 signals - SHOULD NOT BE DISPLAYED
        df_early_only = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=10),
            "Close": [10.0] * 10,
            "Volume": [250000] * 10,
        })
        app.analysis_cache["TCK_EARLY_ONLY"] = {
            "df": df_early_only,
            "adv": {"entry_type": "EARLY", "position_size": "20%", "confidence": "HIGH", "risk_flags": []},
            "accum": {"is_accumulation": False},
            "ma_trend": {"is_perfect_uptrend": False},
            "valuation": {"is_valid": True, "risk_pct": 5.0, "price": 10.0, "tp1": 12.0, "rr_ratio": 2.0, "risk_score": 10}
        }
        
        app.run_advanced_scanner("EARLY")
        
        output_text = "\n".join(app.logged_messages)
        print("Advanced Scanner Test Output:\n", output_text)
        
        # TCK_EARLY_ACCUM should be in the results because it is in accumulation
        self.assertIn("TCK_EARLY_ACCUM", output_text)
        # TCK_EARLY_ONLY should not be in the results because it doesn't satisfy any of the 6 signals
        self.assertNotIn("TCK_EARLY_ONLY", output_text)

if __name__ == "__main__":
    unittest.main()
