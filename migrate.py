import sqlite3
import pandas as pd
from tinvest.storage_manager import StorageManager
from tinvest.data_loader import enrich_dataframe
import os

def migrate():
    db_path = 'tinvest_cache.db'
    if not os.path.exists(db_path):
        print("Old database not found. Skipping migration.")
        return

    storage = StorageManager()
    conn = sqlite3.connect(db_path)
    
    # 1. Get all tickers
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ticker FROM prices")
    tickers = [row[0] for row in cursor.fetchall() if row[0] is not None and str(row[0]).strip() != ""]
    
    print(f"Found {len(tickers)} tickers to migrate.")
    
    for t in tickers:
        print(f"Migrating {t}...")
        df = pd.read_sql(f"SELECT * FROM prices WHERE ticker='{t}'", conn)
        
        # Normalize
        df = df.rename(columns={
            'date': 'Date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Sync to new storage (Mark as API initially)
        storage.sync_prices(t, df, source='API')
        
        # Load and Enrich (to ensure indicators are consistent with new logic)
        full_df = storage.load_ticker_data(t)
        if full_df is not None:
            rich_df = enrich_dataframe(full_df)
            storage.save_indicators(t, rich_df)
            print(f"  - {t}: Migrated and Re-enriched.")
            
    conn.close()
    print("\n✅ Migration complete! You can now delete tinvest_cache.db safely.")

if __name__ == "__main__":
    migrate()
