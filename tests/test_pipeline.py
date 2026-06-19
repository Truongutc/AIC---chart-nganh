import unittest
import pandas as pd
from tinvest.scoring_engine import calculate_score

class TestScoringEngine(unittest.TestCase):
    def test_scoring_engine(self):
        # Create a mock dataframe suitable for testing
        df = pd.DataFrame({
            "Open": [10.0] * 50,
            "High": [11.0] * 50,
            "Low": [9.0] * 50,
            "Close": [10.5] * 50,
            "Volume": [1000] * 50,
        })
        
        # Mock Ichimoku result matching Strong Trend (+3)
        ichi = {"score": 3}
        
        result = calculate_score(df, ichi)
        
        # Default mock dataframe should give a predictable baseline score
        self.assertIn("total_score", result)
        self.assertIn("classification", result)

if __name__ == '__main__':
    unittest.main()
