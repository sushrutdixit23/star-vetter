import sys
from pathlib import Path
import pandas as pd

PROBLEM_TICS = [220423668, 365998904, 233452636, 437171483, 411457490,
                295373509, 374158907, 348884775, 70762350, 446502638]

def main():
    project_root = Path(sys.argv[1]).resolve()
    manifest_path = project_root / "data" / "processed" / "f2c_manifest.csv"
    lc_dir = project_root / "data" / "lightcurves"

    manifest = pd.read_csv(manifest_path)
    manifest["TIC"] = manifest["TIC"].astype(int)

    print(f"{'TIC':>12}  {'manifest_status':<16}  light_curve_file_exists")
    rows_to_drop = []
    for tic in PROBLEM_TICS:
        rows = manifest[manifest["TIC"] == tic]
        lc_path = lc_dir / f"TIC{tic}.csv"
        exists = lc_path.exists()
        if len(rows) == 0:
            print(f"{tic:>12}  {'NOT IN MANIFEST':<16}  {exists}")
            continue
        status = str(rows.iloc[0]["status"])
        print(f"{tic:>12}  {status:<16}  {exists}")
        if status == "OK" and not exists:
            rows_to_drop.append(tic)

    if rows_to_drop:
        print(f"\n{len(rows_to_drop)} TIC(s) marked OK in the manifest but with no light curve "
              f"file on disk - these are the ones f5_dossier.py keeps skipping. Removing them "
              f"from the manifest so the next F2c run re-fetches them for real:")
        for tic in rows_to_drop:
            print(f"  {tic}")
        before = len(manifest)
        cleaned = manifest[~manifest["TIC"].isin(rows_to_drop)]
        cleaned.to_csv(manifest_path, index=False, encoding="utf-8")
        print(f"\nWrote cleaned manifest: {manifest_path} ({before} -> {len(cleaned)} rows)")
    else:
        print("\nNo OK-but-missing mismatches found among these 10 - the cause is something else.")

if __name__ == "__main__":
    main()