import sys
from pathlib import Path

import pandas as pd
from astroquery.mast import Catalogs

CONTROLS = [427332229, 158329671]

def main():
    if len(sys.argv) != 2:
        print("Usage: py append_controls.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    sample_path = root / "data" / "processed" / "sample_batch.csv"
    df = pd.read_csv(sample_path)
    existing = set(df["TIC"].astype(int))

    rows = []
    for tic in CONTROLS:
        if tic in existing:
            print(f"TIC {tic} already in sample_batch.csv, skipping")
            continue
        print(f"Querying MAST TIC catalog for control TIC {tic}...")
        result = Catalogs.query_criteria(catalog="Tic", ID=str(tic)).to_pandas()
        if len(result) == 0:
            print(f"  ERROR: TIC {tic} not found in TIC catalog - skipping")
            continue
        row = result.iloc[0]
        rows.append({
            "TIC": tic,
            "RAJ2000": float(row["ra"]),
            "DEJ2000": float(row["dec"]),
            "Tmag": float(row["Tmag"]),
        })
        print(f"  TIC {tic}: RA={row['ra']:.5f} Dec={row['dec']:.5f} Tmag={row['Tmag']:.2f}")

    if not rows:
        print("Nothing to add.")
        return

    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(sample_path, index=False)
    print(f"Wrote {len(rows)} new row(s) to {sample_path} ({len(df)} total)")

if __name__ == "__main__":
    main()