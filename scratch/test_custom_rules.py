import unittest
import pandas as pd
import numpy as np
import sys
import os

# Append the project path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from AICcode import CUSTOM_RULES

class TestCustomRules(unittest.TestCase):
    def test_basic_ma_crossovers(self):
        # Create a mock dataframe with Close, MA20, MA50
        dates = pd.date_range(start="2026-01-01", periods=10)
        df = pd.DataFrame({
            "Date": dates,
            "Close": [10, 11, 12, 13, 9, 8, 11, 12, 13, 14], # cross MA20 at index 6 (8 -> 11)
            "MA20": [10.0] * 10,
            "MA50": [9.0] * 10,
        })
        
        # Test Price cuts above MA20
        rule = CUSTOM_RULES["PRICE_CROSS_MA20"]
        
        # Case 1: Ticker is above MA20 (14) and yesterday was above (13) -> No cross
        self.assertFalse(rule["func"](df))
        
        # Case 2: Ticker just crossed (let's truncate to index 7: date 7, close 11, prev close 8)
        df_crossed = df.iloc[:7]
        self.assertTrue(rule["func"](df_crossed))

    def test_macd_signals(self):
        df = pd.DataFrame({
            "Close": [10, 11, 12],
            "MACD": [1.0, 1.2, 1.5],
            "MACD_Signal": [1.1, 1.3, 1.4] # MACD crossed above Signal at index 2 (1.2/1.3 -> 1.5/1.4)
        })
        
        rule_cross = CUSTOM_RULES["MACD_CROSS_SIGNAL"]
        rule_above = CUSTOM_RULES["MACD_ABOVE_SIGNAL"]
        
        self.assertTrue(rule_cross["func"](df))
        self.assertTrue(rule_above["func"](df))

    def test_week_high_breakout(self):
        rule = CUSTOM_RULES["WEEK_HIGH_BREAKOUT"]
        # High of past 5 days (indexes -6 to -2) is 10.
        # Close at index -1 is 11.
        df = pd.DataFrame({
            "Close": [5, 5, 5, 5, 5, 5, 11],
            "High":  [6, 7, 8, 9, 10, 8, 12]
        })
        self.assertTrue(rule["func"](df))

        # Close at index -1 is 9 (not breakout).
        df_no = pd.DataFrame({
            "Close": [5, 5, 5, 5, 5, 5, 9],
            "High":  [6, 7, 8, 9, 10, 8, 12]
        })
        self.assertFalse(rule["func"](df_no))

    def test_accumulation_breakout(self):
        rule = CUSTOM_RULES["ACCUMULATION_BREAKOUT"]
        
        # Scenario 1: Sideways for 20 days with High=10.5, Low=9.5 (range = (10.5-9.5)/9.5 = 10.5% <= 15%)
        # Then breaks out with Close=11.0 today (index -1)
        closes = [10.0] * 20 + [11.0]
        highs = [10.5] * 20 + [11.5]
        lows = [9.5] * 20 + [9.5]
        df = pd.DataFrame({"Close": closes, "High": highs, "Low": lows})
        self.assertTrue(rule["func"](df))

        # Scenario 2: Breakout was 2 days ago (index -3), and it should still trigger.
        # Let's add 2 days of post-breakout data:
        closes_2 = [10.0] * 20 + [11.0, 11.2, 11.5]
        highs_2 = [10.5] * 20 + [11.5, 11.8, 12.0]
        lows_2 = [9.5] * 20 + [9.5, 11.0, 11.2]
        df_2 = pd.DataFrame({"Close": closes_2, "High": highs_2, "Low": lows_2})
        self.assertTrue(rule["func"](df_2))

        # Scenario 3: Consolidation range is too wide (High=12, Low=9, range = 33% > 15%) -> Should be False
        closes_wide = [10.0] * 20 + [13.0]
        highs_wide = [12.0] * 20 + [13.5]
        lows_wide = [9.0] * 20 + [9.0]
        df_wide = pd.DataFrame({"Close": closes_wide, "High": highs_wide, "Low": lows_wide})
        self.assertFalse(rule["func"](df_wide))

    def test_rsi_bullish_divergence(self):
        rule = CUSTOM_RULES["RSI_BULLISH_DIVERGENCE"]

        # Helper to generate base template
        def get_base_df():
            lows = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
            rsis = [45] * 20
            rsis[5] = 30.0  # Bottom 1
            rsis[14] = 38.0  # Bottom 2
            closes = [x + 1 for x in lows]
            return pd.DataFrame({"Low": lows, "RSI": rsis, "Close": closes})

        # 1. Valid divergence case
        # Bottom 1 at idx 5 (Low=100.0, RSI=30.0), Bottom 2 at idx 14 (Low=95.0, RSI=38.0)
        # Dist: 14 - 5 = 9 >= 5. RSI slope: 38 - 30 = 8 > 5. Price decline: (100 - 95)/100 = 5% > 2%
        df_valid = get_base_df()
        self.assertTrue(rule["func"](df_valid))

        # 2. Too close bottoms (distance < 5)
        # Let's make bottom 2 at idx 9 (Low=95.0, RSI=38.0)
        # We also need to adjust surrounding Lows to make idx 9 a pivot low (left=3, right=3)
        # Left of 9: idx 6, 7, 8 must be > 95 (currently 105, 104, 103 - OK)
        # Right of 9: idx 10, 11, 12 must be > 95 (currently 101, 100, 99 - OK)
        # So we can just set low at 9 to 95.0, and adjust RSI
        df_close = get_base_df()
        df_close.loc[9, "Low"] = 95.0
        df_close.loc[9, "RSI"] = 38.0
        # Reset idx 14 to not be a pivot/divergence
        df_close.loc[14, "Low"] = 100.0
        self.assertFalse(rule["func"](df_close))

        # 3. Flat RSI slope (slope <= 5)
        df_flat_rsi = get_base_df()
        df_flat_rsi.loc[14, "RSI"] = 34.0  # Slope = 4.0 <= 5
        self.assertFalse(rule["func"](df_flat_rsi))

        # 4. Small price drop (decline <= 2%)
        # Bottom 1 = 100. Bottom 2 = 99. Decline = 1% <= 2%
        df_small_drop = get_base_df()
        df_small_drop.loc[14, "Low"] = 99.0
        # Adjust surrounding lows so idx 14 is still pivot low (surrounding must be > 99)
        df_small_drop.loc[11, "Low"] = 102.0
        df_small_drop.loc[12, "Low"] = 101.0
        df_small_drop.loc[13, "Low"] = 100.0
        df_small_drop.loc[15, "Low"] = 100.0
        df_small_drop.loc[16, "Low"] = 101.0
        df_small_drop.loc[17, "Low"] = 102.0
        self.assertFalse(rule["func"](df_small_drop))

        # 5. Support broken (Low drops below price2 after bottom 2)
        df_broken = get_base_df()
        df_broken.loc[17, "Low"] = 94.0  # price2 is 95.0, so this breaks support
        self.assertFalse(rule["func"](df_broken))

    def test_macd_bullish_divergence(self):
        rule = CUSTOM_RULES["MACD_BULLISH_DIVERGENCE"]

        def get_base_df():
            lows = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
            macds = [-1.5] * 20
            macds[5] = -1.2  # Bottom 1
            macds[14] = -0.5 # Bottom 2: macd2 > macd1 and both < 0
            closes = [x + 1 for x in lows]
            return pd.DataFrame({"Low": lows, "MACD": macds, "Close": closes})

        # 1. Valid divergence case
        df_valid = get_base_df()
        self.assertTrue(rule["func"](df_valid))

        # 2. Too close bottoms (distance < 5)
        df_close = get_base_df()
        df_close.loc[9, "Low"] = 95.0
        df_close.loc[9, "MACD"] = -0.5
        df_close.loc[14, "Low"] = 100.0
        self.assertFalse(rule["func"](df_close))

        # 3. MACD positive (not < 0)
        df_pos = get_base_df()
        df_pos.loc[14, "MACD"] = 0.1
        self.assertFalse(rule["func"](df_pos))

        # 4. Support broken
        df_broken = get_base_df()
        df_broken.loc[17, "Low"] = 94.0
        self.assertFalse(rule["func"](df_broken))

    def test_macd_hist_bullish_divergence(self):
        rule = CUSTOM_RULES["MACD_HIST_BULLISH_DIVERGENCE"]

        def get_base_df():
            lows = [110, 108, 105, 103, 102, 100, 105, 104, 103, 102, 101, 100, 99, 97, 95, 97, 98, 99, 100, 102]
            hists = [-1.5] * 20
            hists[5] = -1.2  # Bottom 1
            hists[14] = -0.5 # Bottom 2: hist2 > hist1 and both < 0 and abs(hist2) < abs(hist1)
            closes = [x + 1 for x in lows]
            return pd.DataFrame({"Low": lows, "MACD_Hist": hists, "Close": closes})

        # 1. Valid divergence case
        df_valid = get_base_df()
        self.assertTrue(rule["func"](df_valid))

        # 2. Hist positive (not < 0)
        df_pos = get_base_df()
        df_pos.loc[14, "MACD_Hist"] = 0.1
        self.assertFalse(rule["func"](df_pos))

        # 3. abs(hist2) >= abs(hist1)
        df_flat = get_base_df()
        df_flat.loc[14, "MACD_Hist"] = -1.3  # hist2 < hist1, so abs(hist2) > abs(hist1)
        self.assertFalse(rule["func"](df_flat))


if __name__ == "__main__":
    unittest.main()
