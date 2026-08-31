import glob
import pandas as pd

files = glob.glob('trading-system/data/*.csv')
for f in files:
    try:
        df = pd.read_csv(f)
        date_col = None
        for col in ['datetime', 'Datetime', 'date', 'Date']:
            if col in df.columns:
                date_col = col
                break
        if date_col:
            initial_len = len(df)
            df = df.dropna(subset=[date_col])
            df = df.drop_duplicates(subset=[date_col])
            df = df.sort_values(date_col)
            df.to_csv(f, index=False)
            print(f"Cleaned {f}: {initial_len} -> {len(df)} rows (sorted & deduplicated)")
    except Exception as e:
        print(f"Error cleaning {f}: {e}")
