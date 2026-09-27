"""
f7a_build_training_set.py

Builds a tabular training set for the pixel-stage outcome model.

Why this stage exists:
  The pixel check (diag_pixel.py) is the pipeline's most expensive stage -
  it downloads a TESS pixel cutout for every candidate that survives
  statistical vetting and novelty cross-match, then runs difference imaging.
  About 90 percent of candidates fail it. This script assembles the features
  that were already known BEFORE the pixel check ran (statistical vetting
  output, novelty verdict, manifest metadata) alongside the actual pixel
  outcome, so a model can later be trained to predict that outcome ahead of
  time and skip the expensive download for likely failures.

  This is not a new pipeline stage that changes results. It only reads
  CSVs that f3i_vet.py, f4f_novelty.py, diag_pixel.py and
  f2c_fetch_lightcurves.py already write, and joins them into one row per
  candidate with a label. Every value in the output is a real number from
  a real pipeline run - nothing here is estimated or synthetic.

Usage:
  py f7a_build_training_set.py <project_root>

Reads (all under <project_root>/data/processed/):
  f3i_vetting_results.csv   - statistical vetting features (required)
  f4f_novelty_results.csv   - novelty verdict (required)
  diag_pixel_results_v2.csv - pixel-check outcome, used as the label (required)
  f2c_manifest.csv          - light-curve fetch metadata (optional, enriches features)

Writes:
  <project_root>/data/processed/f7_training_set.csv
"""

import sys
from pathlib import Path

import pandas as pd

FEATURE_COLUMNS_F3I = [
    "bls_period", "bls_duration", "bls_depth", "bls_snr",
    "n_eclipses_observed", "depth_ratio", "robust_sigma", "robust_depth",
    "odd_even_z", "depth_odd", "depth_even",
    "secondary_detected", "secondary_phase", "secondary_sigma",
]

FEATURE_COLUMNS_MANIFEST = ["Tmag", "n_sectors", "n_points", "author_used"]

LABEL_SOURCE_COLUMN = "verdict"
POSITIVE_VERDICT = "ON_TARGET"


def read_required_csv(path, label):
    if not path.exists():
        print(f"ERROR: required file not found: {path}")
        print(f"  ({label} - this file is written by an earlier pipeline stage. "
              f"Run the full orchestrator at least once before building a training set.)")
        return None
    return pd.read_csv(path)


def main():
    if len(sys.argv) < 2:
        print("Usage: py f7a_build_training_set.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"

    vet = read_required_csv(proc / "f3i_vetting_results.csv", "f3i statistical vetting output")
    nov = read_required_csv(proc / "f4f_novelty_results.csv", "f4f novelty cross-match output")
    pix = read_required_csv(proc / "diag_pixel_results_v2.csv", "diag_pixel pixel-check output")

    if vet is None or nov is None or pix is None:
        print("\nCannot build a training set without all three files. Stopping.")
        sys.exit(2)  # data not ready yet, not a bug - an orchestrator should not retry this

    manifest_path = proc / "f2c_manifest.csv"
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else None
    if manifest is None:
        print(f"NOTE: {manifest_path} not found - skipping manifest features (Tmag, n_sectors, "
              f"n_points, author_used). The training set will still build without them.")

    # Only real candidates get a label from the pixel stage, not the two
    # fixed control stars (WASP-32, TIC 158329671) used for QA on every run.
    pix_candidates = pix[pix["role"] == "candidate"].copy()
    if pix_candidates.empty:
        print("ERROR: no rows with role == 'candidate' in diag_pixel_results_v2.csv. "
              "Nothing to train on.")
        sys.exit(2)  # data not ready yet, not a bug - an orchestrator should not retry this

    df = pix_candidates[["TIC", LABEL_SOURCE_COLUMN]].rename(
        columns={LABEL_SOURCE_COLUMN: "pixel_verdict"}
    )

    vet_cols_present = [c for c in FEATURE_COLUMNS_F3I if c in vet.columns]
    missing_vet_cols = [c for c in FEATURE_COLUMNS_F3I if c not in vet.columns]
    if missing_vet_cols:
        print(f"NOTE: f3i_vetting_results.csv is missing expected columns "
              f"{missing_vet_cols} - continuing without them.")
    df = df.merge(vet[["TIC"] + vet_cols_present], on="TIC", how="left")

    if "verdict" in nov.columns:
        df = df.merge(
            nov[["TIC", "verdict"]].rename(columns={"verdict": "novelty_verdict"}),
            on="TIC", how="left",
        )

    if manifest is not None:
        man_cols_present = [c for c in FEATURE_COLUMNS_MANIFEST if c in manifest.columns]
        df = df.merge(manifest[["TIC"] + man_cols_present], on="TIC", how="left")

    for bool_col in ("secondary_detected",):
        if bool_col in df.columns:
            df[bool_col] = df[bool_col].map(
                {True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}
            ).fillna(0).astype(int)

    df["on_target"] = (df["pixel_verdict"] == POSITIVE_VERDICT).astype(int)

    out_path = proc / "f7_training_set.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")

    n = len(df)
    n_pos = int(df["on_target"].sum())
    print(f"Training set written: {out_path}")
    print(f"  rows: {n}")
    print(f"  label balance: {n_pos} ON_TARGET (positive) / {n - n_pos} not ON_TARGET (negative)")
    print(f"  pixel_verdict breakdown:")
    for verdict, count in df["pixel_verdict"].value_counts().items():
        print(f"    {verdict}: {count}")
    if n_pos < 15:
        print(f"\n  NOTE: only {n_pos} positive examples. Cross-validated metrics from this small "
              f"a sample will be noisy - treat them as directional until more runs accumulate.")


if __name__ == "__main__":
    main()