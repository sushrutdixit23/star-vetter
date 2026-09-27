import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import f2c_fetch_lightcurves as f2c

PROBLEM_TICS = [220423668, 365998904, 233452636, 437171483, 411457490,
                295373509, 374158907, 348884775, 70762350, 446502638]


def main():
    project_root = Path(sys.argv[1]).resolve()
    lc_dir = project_root / "data" / "lightcurves"
    plot_dir = lc_dir / "plots"
    lc_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = project_root / "data" / "processed" / "f2c_manifest.csv"
    training_set_path = project_root / "data" / "processed" / "f7_training_set.csv"

    # Their Tmag was removed from the manifest along with the stale OK rows.
    # Recover it from the training set built earlier this run, before that
    # cleanup happened - it still has these TICs' real Tmag via the manifest
    # join f7a_build_training_set.py did at the time.
    tmag_by_tic = {}
    if training_set_path.exists():
        ts = pd.read_csv(training_set_path)
        ts["TIC"] = ts["TIC"].astype(int)
        for tic in PROBLEM_TICS:
            match = ts[ts["TIC"] == tic]
            if len(match) > 0 and "Tmag" in match.columns and pd.notna(match.iloc[0]["Tmag"]):
                tmag_by_tic[tic] = float(match.iloc[0]["Tmag"])

    missing_tmag = [t for t in PROBLEM_TICS if t not in tmag_by_tic]
    if missing_tmag:
        print(f"WARNING: could not recover real Tmag for {missing_tmag} from "
              f"f7_training_set.csv - using 99.0 as a harmless placeholder "
              f"(only affects display and the ML feature columns for these "
              f"rows, never the fetch itself).")

    already_in_manifest = set()
    if manifest_path.exists():
        prior = pd.read_csv(manifest_path)
        already_in_manifest = set(prior["TIC"].astype(int))

    write_header = not manifest_path.exists()
    for tic in PROBLEM_TICS:
        if tic in already_in_manifest:
            print(f"TIC {tic} is already back in the manifest - skipping (already handled).")
            continue
        tmag = tmag_by_tic.get(tic, 99.0)
        print(f"TIC {tic} (Tmag={tmag:.2f}) ... ", end="", flush=True)
        res = f2c.process_one_target(tic, tmag, lc_dir, plot_dir)
        f2c.append_manifest_row(manifest_path, res, write_header)
        write_header = False
        if res["status"] == "OK":
            print(f"OK  author={res['author_used']}  sectors={res['n_sectors']}  points={res['n_points']}  (tried: {res['authors_tried']})")
        else:
            print(f"{res['status']}  tried={res['authors_tried']}  {res['error']}")

    print("\nDone. Re-run f5_dossier.py (or the full orchestrator) to rebuild "
          "dossiers for these 10 now that their light curves exist again.")


if __name__ == "__main__":
    main()