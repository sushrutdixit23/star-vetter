import pandas as pd

files = [
    "data/processed/cat_tess_ebs_prsa2022.csv",
    "data/processed/table3_new_ebs.parquet",
    "data/processed/table4_known_ebs.parquet",
    "data/processed/table2_unvetted.parquet",
    "data/processed/sample_500.csv",
    "data/processed/f3i_vetting_results.csv",
    "data/processed/f4f_novelty_results.csv",
    "data/processed/diag_pixel_results_v2.csv",
]

for f in files:
    print("=" * 70)
    print(f)
    try:
        if f.endswith(".parquet"):
            df = pd.read_parquet(f)
            print("rows:", len(df))
            print("columns:", list(df.columns))
        else:
            df = pd.read_csv(f, nrows=5)
            print("columns:", list(df.columns))
            print(df.head(2).to_string())
    except Exception as e:
        print("ERROR:", e)