import subprocess
import sys
import io
import os
from pathlib import Path

import pandas as pd

CSV_MERGE_FILES = [
    "data/processed/diag_blend_neighbours.csv",
    "data/processed/diag_blend_results.csv",
    "data/processed/diag_pixel_results_v2.csv",
    "data/processed/f2c_manifest.csv",
    "data/processed/f3i_vetting_results.csv",
    "data/processed/f4b_asassn_cache.csv",
    "data/processed/f4f_novelty_results.csv",
]

TAKE_OURS_FILES = [
    "data/processed/sample_batch.csv",
    "site/public/data/dashboard.json",
    "site/public/data/index.json",
    "site/public/data/site_meta.json",
    "data/dossiers/star_vetter_dossiers.pdf",
    "site/public/dossiers/star_vetter_dossiers.pdf",
]


def get_blob(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout


def find_key_column(columns):
    for c in columns:
        if str(c).strip().lower() in ("tic", "ticid", "tic_id"):
            return c
    return None


def merge_csv(path):
    ours_bytes = get_blob("HEAD", path)
    theirs_bytes = get_blob("MERGE_HEAD", path)
    if ours_bytes is None or theirs_bytes is None:
        print(f"  SKIP {path}: missing one side (ours={ours_bytes is not None} theirs={theirs_bytes is not None})")
        return

    try:
        ours_df = pd.read_csv(io.BytesIO(ours_bytes))
        theirs_df = pd.read_csv(io.BytesIO(theirs_bytes))
    except Exception as e:
        print(f"  ERROR reading {path}: {e}")
        return

    key = find_key_column(ours_df.columns)

    if key is not None and key in theirs_df.columns:
        ours_keys = set(ours_df[key])
        only_theirs = theirs_df[~theirs_df[key].isin(ours_keys)]
        merged = pd.concat([ours_df, only_theirs], ignore_index=True)
        print(f"  {path}: key='{key}' ours={len(ours_df)} theirs={len(theirs_df)} "
              f"new_from_theirs={len(only_theirs)} -> merged={len(merged)}")
    else:
        combined = pd.concat([ours_df, theirs_df], ignore_index=True)
        merged = combined.drop_duplicates(keep="first").reset_index(drop=True)
        print(f"  {path}: no tic-like key column, exact-row dedup. "
              f"ours={len(ours_df)} theirs={len(theirs_df)} -> merged={len(merged)}")

    merged.to_csv(path, index=False, encoding="utf-8")


def take_ours(path):
    ours_bytes = get_blob("HEAD", path)
    if ours_bytes is None:
        print(f"  SKIP {path}: no HEAD version found")
        return
    Path(path).write_bytes(ours_bytes)
    print(f"  {path}: kept our version (will regenerate from merged data)")


def main(project_root):
    os.chdir(project_root)

    print("Merging per-candidate CSVs (union by TIC, preferring our row on overlap):")
    for path in CSV_MERGE_FILES:
        merge_csv(path)

    print()
    print("Resolving generated/rollup files by keeping our version for now:")
    for path in TAKE_OURS_FILES:
        take_ours(path)

    print()
    print("Staging resolved files...")
    subprocess.run(["git", "add"] + CSV_MERGE_FILES + TAKE_OURS_FILES)
    print("Done. Run: git status   then   git commit --no-edit")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")