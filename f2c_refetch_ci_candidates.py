import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import f2c_fetch_lightcurves as f2c

PROBLEM_TICS = [446758441, 373896170, 273212554, 78955414]


def find_tmag_col(columns):
    if "Tmag" in columns:
        return "Tmag"
    for c in columns:
        if str(c).strip().lower() == "tmag":
            return c
    return None


def main():
    project_root = Path(sys.argv[1]).resolve()
    lc_dir = project_root / "data" / "lightcurves"
    plot_dir = lc_dir / "plots"
    lc_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = project_root / "data" / "processed" / "f2c_manifest.csv"

    manifest = pd.read_csv(manifest_path)
    manifest["TIC"] = manifest["TIC"].astype(int)
    tmag_col = find_tmag_col(manifest.columns)

    tmag_by_tic = {}
    for tic in PROBLEM_TICS:
        rows = manifest[manifest["TIC"] == tic]
        if len(rows) > 0 and tmag_col is not None and pd.notna(rows.iloc[0][tmag_col]):
            tmag_by_tic[tic] = float(rows.iloc[0][tmag_col])

    missing_tmag = [t for t in PROBLEM_TICS if t not in tmag_by_tic]
    if missing_tmag:
        print(f"WARNING: could not recover real Tmag for {missing_tmag} from "
              f"the manifest - using 99.0 as a harmless placeholder (only "
              f"affects display and ML feature columns, never the fetch).")

    confirmed_missing = []
    for tic in PROBLEM_TICS:
        lc_file = lc_dir / f"TIC{tic}.csv"
        if lc_file.exists():
            print(f"TIC {tic}: light curve file already exists locally ({lc_file}) - leaving manifest row alone, skipping re-fetch.")
        else:
            confirmed_missing.append(tic)

    if not confirmed_missing:
        print("Nothing to re-fetch - all light curve files already present.")
        return

    before = len(manifest)
    manifest = manifest[~manifest["TIC"].isin(confirmed_missing)]
    after = len(manifest)
    manifest.to_csv(manifest_path, index=False, encoding="utf-8")
    print(f"Dropped {before - after} stale manifest row(s) for {confirmed_missing} before re-fetching.")

    for tic in confirmed_missing:
        tmag = tmag_by_tic.get(tic, 99.0)
        print(f"TIC {tic} (Tmag={tmag:.2f}) ... ", end="", flush=True)
        res = f2c.process_one_target(tic, tmag, lc_dir, plot_dir)
        f2c.append_manifest_row(manifest_path, res, write_header=False)
        if res["status"] == "OK":
            print(f"OK  author={res['author_used']}  sectors={res['n_sectors']}  points={res['n_points']}  (tried: {res['authors_tried']})")
        else:
            print(f"{res['status']}  tried={res['authors_tried']}  {res['error']}")

    print("\nDone. Now re-run: regen_pixel_plots.py, export_site_data.py, "
          "export_dashboard.py, export_extras.py, then check_artifacts.py.")


if __name__ == "__main__":
    main()