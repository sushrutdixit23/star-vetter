import sys
import json
from pathlib import Path

import pandas as pd
from astroquery.mast import Catalogs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diag_pixel as dp


def main():
    if len(sys.argv) != 2:
        print("Usage: py regen_pixel_plots.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    lc_dir = root / "data" / "lightcurves"
    plot_dir = root / "data" / "pixel_check"

    # the exact 23 TICs the site shows: confirmed on-target candidates,
    # taken from the site's own index so this never drifts from what is
    # actually published
    index_path = root / "site" / "public" / "data" / "index.json"
    tics = [c["tic"] for c in json.loads(index_path.read_text(encoding="utf-8"))["candidates"]]
    print(f"Regenerating pixel-check plots for {len(tics)} confirmed candidates (dark theme).")

    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    info = Catalogs.query_criteria(catalog="Tic", ID=tics)
    info = info[["ID", "ra", "dec", "Tmag"]].to_pandas()
    info["ID"] = info["ID"].astype(int)
    info = info.set_index("ID")

    for i, tic in enumerate(tics):
        print(f"[{i + 1}/{len(tics)}] TIC {tic} ... ", end="", flush=True)
        try:
            res = dp.analyse_one(tic, "candidate", vet.loc[tic], lc_dir / f"TIC{tic}.csv",
                                 info.loc[tic], plot_dir)
            print(res.get("verdict", "done"))
        except Exception as exc:
            print(f"FAILED: {repr(exc)[:150]}")

    print("\nDone. This only overwrote the PNGs in data/pixel_check - it did not touch")
    print("diag_pixel_results_v2.csv, so none of the site's numbers changed.")
    print("Next: re-run export_site_data.py (and export_extras.py if you use it) then")
    print("refresh localhost:3000, or vercel --prod to push the new images live.")


if __name__ == "__main__":
    main()
