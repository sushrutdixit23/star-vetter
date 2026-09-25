import sys
import csv
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import lightkurve as lk

AUTHOR_PRIORITY = ["SPOC", "TESS-SPOC", "GSFC-ELEANOR-LITE", "QLP", "TGLC", "DIAMANTE", "TASOC", "TARS"]

MANIFEST_COLUMNS = ["TIC", "Tmag", "status", "author_used", "n_sectors",
                     "n_points", "authors_tried", "error"]


def ordered_available_authors(search_result):
    available = list(dict.fromkeys(search_result.author))
    ordered = [a for a in AUTHOR_PRIORITY if a in available]
    ordered += [a for a in available if a not in ordered]
    return ordered


def safe_flatten(lc):
    n = len(lc.time)
    if n < 20:
        return lc.remove_nans().normalize()
    window = min(401, n // 2)
    if window % 2 == 0:
        window -= 1
    window = max(window, 3)
    return lc.remove_nans().flatten(window_length=window)


def try_search_with_retry(tic, retries=2, delay=5):
    last_err = None
    for attempt in range(retries + 1):
        try:
            return lk.search_lightcurve(f"TIC {tic}"), None
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(delay)
    return None, last_err


def process_one_target(tic: int, tmag: float, lc_dir: Path, plot_dir: Path) -> dict:
    result = {
        "TIC": tic, "Tmag": tmag, "status": None,
        "author_used": None, "n_sectors": 0, "n_points": 0,
        "authors_tried": "", "error": "",
    }

    sr, search_err = try_search_with_retry(tic)
    if sr is None:
        result["status"] = "SEARCH_ERROR"
        result["error"] = str(search_err)[:200]
        return result

    if len(sr) == 0:
        result["status"] = "NO_DATA"
        return result

    authors_to_try = ordered_available_authors(sr)
    tried = []
    last_error = ""
    last_status = "NO_DATA"

    for author in authors_to_try:
        tried.append(author)
        sr_author = sr[sr.author == author]

        try:
            lcc = sr_author.download_all()
        except Exception as e:
            last_status, last_error = "DOWNLOAD_ERROR", str(e)[:200]
            continue

        if lcc is None or len(lcc) == 0:
            last_status = "DOWNLOAD_EMPTY"
            continue

        try:
            lc = lcc.stitch()
            if len(lc.time) == 0:
                last_status = "PROCESSING_ERROR"
                last_error = "stitched light curve has zero points"
                continue
            flat = safe_flatten(lc)
            if len(flat.time) == 0:
                last_status = "PROCESSING_ERROR"
                last_error = "flattened light curve has zero points"
                continue
        except Exception as e:
            last_status, last_error = "PROCESSING_ERROR", str(e)[:200]
            continue

        result["author_used"] = author
        result["n_sectors"] = len(sr_author)
        result["n_points"] = len(flat.time)
        result["authors_tried"] = ",".join(tried)

        lc_path = lc_dir / f"TIC{tic}.csv"
        out_df = pd.DataFrame({
            "time": np.asarray(flat.time.value),
            "flux": np.asarray(flat.flux.value),
            "flux_err": np.asarray(flat.flux_err.value) if flat.flux_err is not None else np.nan,
        })
        out_df.to_csv(lc_path, index=False)

        try:
            fig, ax = plt.subplots(figsize=(10, 3))
            flat.scatter(ax=ax, s=2)
            ax.set_title(f"TIC {tic}  (Tmag={tmag:.2f}, author={author}, sectors={result['n_sectors']})")
            fig.tight_layout()
            fig.savefig(plot_dir / f"TIC{tic}.png", dpi=100)
            plt.close(fig)
        except Exception:
            pass

        result["status"] = "OK"
        return result

    result["status"] = last_status
    result["error"] = last_error
    result["authors_tried"] = ",".join(tried)
    return result


def append_manifest_row(manifest_path: Path, row: dict, write_header: bool):
    with open(manifest_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in MANIFEST_COLUMNS})
        f.flush()


def main():
    if len(sys.argv) != 2:
        print("Usage: py f2c_fetch_lightcurves.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    sample_path = project_root / "data" / "processed" / "sample_batch.csv"
    lc_dir = project_root / "data" / "lightcurves"
    plot_dir = lc_dir / "plots"
    lc_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    if not sample_path.exists():
        print(f"ERROR: sample file not found at {sample_path}")
        print("Run f1b_sample.py first.")
        sys.exit(1)

    sample = pd.read_csv(sample_path)
    print(f"Loaded {len(sample)} targets from {sample_path}")

    manifest_path = project_root / "data" / "processed" / "f2c_manifest.csv"
    already_done = {}
    if manifest_path.exists():
        prior = pd.read_csv(manifest_path)
        for _, r in prior.iterrows():
            already_done[int(r["TIC"])] = r.to_dict()
        n_ok = sum(1 for r in already_done.values() if r["status"] == "OK")
        print(f"Found existing manifest with {len(already_done)} target(s) already attempted "
              f"({n_ok} OK) - resuming, these will be skipped.")

    write_header = not manifest_path.exists()

    n_remaining = len(sample) - len(already_done.keys() & set(sample["TIC"].astype(int)))
    print(f"{n_remaining} target(s) remaining to fetch this run.\n")

    start_time = time.time()
    n_done_this_run = 0

    for i, row in sample.iterrows():
        tic = int(row["TIC"])
        tmag = float(row["Tmag"])

        if tic in already_done:
            continue

        print(f"[{i + 1}/{len(sample)}] TIC {tic} (Tmag={tmag:.2f}) ... ", end="", flush=True)
        res = process_one_target(tic, tmag, lc_dir, plot_dir)

        append_manifest_row(manifest_path, res, write_header)
        write_header = False
        n_done_this_run += 1

        if res["status"] == "OK":
            print(f"OK  author={res['author_used']}  sectors={res['n_sectors']}  points={res['n_points']}  (tried: {res['authors_tried']})")
        else:
            print(f"{res['status']}  tried={res['authors_tried']}  {res['error']}")

        if n_done_this_run % 10 == 0:
            elapsed = time.time() - start_time
            rate = elapsed / n_done_this_run
            eta_remaining = rate * (n_remaining - n_done_this_run)
            print(f"    ... {n_done_this_run}/{n_remaining} done this run, "
                  f"{elapsed/60:.1f} min elapsed, ~{eta_remaining/60:.0f} min remaining "
                  f"at this rate (safe to stop anytime - resume by re-running this script)")

    elapsed = time.time() - start_time

    manifest = pd.read_csv(manifest_path)
    print(f"\n{'=' * 70}")
    print("F2c FETCH SUMMARY (incremental, resumable)")
    print(f"{'=' * 70}")
    print(f"Targets fetched this run: {n_done_this_run}")
    print(f"Time this run:            {elapsed / 60:.1f} min")
    print(f"Total in manifest so far: {len(manifest)} / {len(sample)}")
    print(f"\nStatus breakdown (all time):")
    print(manifest["status"].value_counts().to_string())

    ok = manifest[manifest["status"] == "OK"]
    print(f"\nSuccessful fetches: {len(ok)}/{len(manifest)} ({100 * len(ok) / len(manifest):.1f}%)")

    failed = manifest[manifest["status"] != "OK"]
    if len(failed) > 0:
        print(f"\nFailed targets ({len(failed)}):")
        print(failed[["TIC", "Tmag", "status", "authors_tried", "error"]].to_string(index=False))

    if len(manifest) < len(sample):
        print(f"\n{len(sample) - len(manifest)} target(s) not yet attempted - "
              f"re-run this script to continue.")
    else:
        print(f"\nAll {len(sample)} targets attempted. Fetch stage complete.")

    print(f"\nManifest saved: {manifest_path}")


if __name__ == "__main__":
    main()