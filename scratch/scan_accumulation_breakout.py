import os
import glob
import pandas as pd
import sys

# Add base path to sys.path
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

from AICcode import check_accumulation_breakout

def main():
    prices_dir = "data_storage/prices"
    parquet_files = glob.glob(os.path.join(prices_dir, "*.parquet"))
    
    matching_tickers = []
    print(f"Scanning {len(parquet_files)} tickers for accumulation breakout...")
    
    for p_file in parquet_files:
        ticker = os.path.splitext(os.path.basename(p_file))[0].upper()
        if any(idx in ticker for idx in ["INDEX", "HNX30", "VN30"]):
            continue
        try:
            df = pd.read_parquet(p_file)
            if df.empty:
                continue
            
            # Run the breakout check
            if check_accumulation_breakout(df):
                # Calculate some stats for display
                current_price = float(df['Close'].iloc[-1])
                avg_vol_10 = float(df['Volume'].tail(10).mean()) if 'Volume' in df.columns else 0
                matching_tickers.append({
                    "ticker": ticker,
                    "close": current_price,
                    "avg_vol_10": round(avg_vol_10, 0)
                })
        except Exception as e:
            continue
            
    print(f"\nScan complete. Found {len(matching_tickers)} tickers:")
    for item in sorted(matching_tickers, key=lambda x: x['avg_vol_10'], reverse=True):
        print(f"  Ticker: {item['ticker']} | Close: {item['close']} | Avg Vol 10D: {item['avg_vol_10']:,.0f}")

if __name__ == "__main__":
    main()
