import pandas as pd
import numpy as np
import os
import sys

# Support Vietnamese characters in Windows terminal
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add current directory to path
sys.path.append(os.getcwd())

from tinvest.analyzer import analyze_stock, format_report

def test_report_rr():
    # Generate dummy data
    n = 100
    dates = pd.date_range(start="2023-01-01", periods=n)
    close = np.linspace(100, 105, n)
    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close + 2,
        "Low": close - 2,
        "Close": close,
        "Volume": [1000000] * n
    })
    
    result = analyze_stock("TCB", df)
    report = format_report(result)
    
    # Check if Risk/Reward percentages are in report
    if "Lợi nhuận:" in report and "Rủi ro:" in report:
        print("SUCCESS: RR Percentages found in report.")
        # Find the RR line
        for line in report.split("\n"):
            if "Tỷ lệ R/R" in line:
                print(f"Report Line: {line}")
    else:
        print("FAILURE: RR Percentages NOT found in report.")
        print(report)

test_report_rr()
