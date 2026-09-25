import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# How many NEW targets to draw this round, and how many Tmag-brightness
# bins to stratify across. Same stratification method as f1_ingest.py's
# build_stratified_sample - this script exists separately (rather than
# editing f1_ingest.py in place) so it can read the already-parsed
# table2_unvetted.parquet directly instead of re-parsing the 872,720-row
# raw VizieR TSV every time we want a new batch.
#
# Overridable via STAR_VETTER_BATCH_SIZE so the GitHub Actions schedule
# can run a smaller batch (fetch is the slow, network-bound stage, so a
# smaller batch keeps each scheduled run safely under the job time
# limit) without changing the default for a manual local run.
N_NEW_TARGETS = int(os.environ.get("STAR_VETTER_BATCH_SIZE", "500"))
N_BINS = 5


def build_stratified_sample(df: pd.DataFrame, n_total: int, n_bins: int,
                             mag_col: str = "Tmag", seed: int = 42,
                             exclude_ids=None) -> pd.DataFrame:
    """
    Sample n_total rows from df, spread evenly across n_bins brightness
    bins, excluding any TIC already present in exclude_ids (so a repeat
    run of this script - or a later, bigger batch - draws NEW stars
    instead of re-selecting ones already fetched/vetted in a prior round).
    """
    rng = np.random.default_rng(seed)
    df = df.dropna(subset=[mag_col]).copy()

    if exclude_ids:
        before = len(df)
        df = df[~df["TIC"].astype(int).isin(exclude_ids)]
        print(f"Excluded {before - len(df):,} already-sampled TIC(s) from the draw pool "
              f"({len(df):,} remain eligible).")

    df["mag_bin"] = pd.qcut(df[mag_col], q=n_bins, labels=False, duplicates="drop")

    per_bin = n_total // n_bins
    remainder = n_total - per_bin * n_bins

    samples = []
    bins_present = sorted(df["mag_bin"].dropna().unique())
    for i, b in enumerate(bins_present):
        bin_df = df[df["mag_bin"] == b]
        take = per_bin + (1 if i < remainder else 0)
        take = min(take, len(bin_df))
        if take < (per_bin + (1 if i < remainder else 0)):
            print(f"  WARNING: bin {int(b)} only has {len(bin_df)} eligible targets, "
                  f"wanted {per_bin + (1 if i < remainder else 0)} - taking all of it.")
        idx = rng.choice(bin_df.index, size=take, replace=False)
        samples.append(df.loc[idx])

    result = pd.concat(samples).drop(columns=["mag_bin"]).reset_index(drop=True)
    return result


def main():
    if len(sys.argv) != 2:
        print("Usage: py f1b_sample.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    processed_dir = project_root / "data" / "processed"
    history_dir = processed_dir / "sample_history"

    table_path = processed_dir / "table2_unvetted.parquet"
    if not table_path.exists():
        print(f"ERROR: {table_path} not found.")
        print("Run f1_ingest.py first - this script reads its already-parsed output "
              "instead of re-parsing the raw VizieR TSV.")
        sys.exit(1)

    df = pd.read_parquet(table_path)
    print(f"Loaded {len(df):,} candidates from {table_path}")

    if "TIC" not in df.columns:
        print(f"ERROR: expected a 'TIC' column in {table_path}, found: {list(df.columns)}")
        sys.exit(1)

    # One-time migration: earlier rounds wrote their draw straight to
    # sample_{N}.csv, which the next round at the same N would silently
    # overwrite - losing that round's record. That does not lose any
    # actual work (f2c_fetch_lightcurves.py and f3i_vet.py separately
    # skip any TIC they have already touched), but it does mean a later
    # round could re-draw the same stars, quietly shrinking how many
    # genuinely-new stars that round adds. From here on every round's
    # draw is also archived under sample_history/ with a timestamp, and
    # this migrates whatever sample_*.csv already exists at the top
    # level into that history once, so those TICs still count as drawn.
    history_dir.mkdir(parents=True, exist_ok=True)
    if not any(history_dir.glob("*.csv")):
        legacy = sorted(processed_dir.glob("sample_*.csv"))
        for p in legacy:
            dest = history_dir / p.name
            dest.write_text(p.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            print(f"Migrated existing {p.name} into sample_history/ (one-time).")

    # exclude every TIC drawn in any prior round, read from the permanent
    # history archive - not from whatever sample_{N}.csv currently sits
    # at the top level, since that file is just the hand-off copy
    # f2c_fetch_lightcurves.py reads and gets overwritten every round.
    exclude_ids = set()
    prior_samples = sorted(history_dir.glob("*.csv"))
    for p in prior_samples:
        prior = pd.read_csv(p)
        if "TIC" in prior.columns:
            exclude_ids.update(prior["TIC"].astype(int).tolist())
    if prior_samples:
        print(f"Found {len(prior_samples)} prior round(s) in sample_history/: "
              f"{[p.name for p in prior_samples]} ({len(exclude_ids):,} TIC(s) total)")

    sample = build_stratified_sample(df, n_total=N_NEW_TARGETS, n_bins=N_BINS,
                                      exclude_ids=exclude_ids)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = history_dir / f"sample_{N_NEW_TARGETS}_{stamp}.csv"
    sample.to_csv(archive_path, index=False, encoding="utf-8", lineterminator="\n")

    # hand-off file f2c_fetch_lightcurves.py and f6_orchestrator.py read.
    # Fixed name, independent of the batch size, so it stays correct
    # whatever STAR_VETTER_BATCH_SIZE is set to for a given run.
    out_path = processed_dir / "sample_batch.csv"
    sample.to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")

    print(f"\n{'=' * 70}")
    print(f"Drew {len(sample)} new stratified targets (requested {N_NEW_TARGETS})")
    print(f"{'=' * 70}")
    print(sample["Tmag"].describe().to_string())
    print(f"\nSaved round archive: {archive_path}")
    print(f"Saved hand-off file: {out_path}")


if __name__ == "__main__":
    main()
