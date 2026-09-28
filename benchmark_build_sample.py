"""
benchmark_build_sample.py

Draws a stratified pilot sample of known eclipsing binaries from Kostov et
al. 2025's own "new EBs" table (data/processed/table3_new_ebs.parquet,
7936 rows, already on disk from the original catalog ingest) and sets up
an ISOLATED benchmark project_root folder so the real pipeline stage
scripts (f2c_fetch_lightcurves.py, f3i_vet.py, f4f_novelty.py,
diag_pixel.py) can be run against it without touching the live
production data/processed files at all - those scripts hardcode their
input/output filenames relative to whatever project_root they are given,
so pointing them at benchmark_run/ instead of the real project root keeps
this completely separate.

This is the ground-truth half of the benchmark-and-injection harness from
the tech roadmap: known real EBs run blind through the unmodified pipeline
tell us the per-gate recall (how often each vetting gate would have wrongly
rejected a real eclipsing binary), independent of the novelty/"is this
already known" question, which is not what this measurement is about.

Usage:
  py benchmark_build_sample.py <project_root> [--n 60] [--seed 42]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    argv = sys.argv[1:]
    n = 60
    seed = 42
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--n" and i + 1 < len(argv):
            n = int(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1])
            i += 2
            continue
        positional.append(argv[i])
        i += 1

    if len(positional) != 1:
        print("Usage: py benchmark_build_sample.py <project_root> [--n 60] [--seed 42]")
        sys.exit(1)
    root = Path(positional[0]).resolve()

    src_path = root / "data" / "processed" / "table3_new_ebs.parquet"
    df = pd.read_parquet(src_path)
    print(f"Loaded {len(df)} rows from {src_path}")

    required = ["TIC", "RAJ2000", "DEJ2000", "Tmag", "Per", "T0-pri", "Depth-pri", "Dur-pri"]
    before = len(df)
    df = df.dropna(subset=required).copy()
    print(f"Dropped {before - len(df)} rows missing one of {required}; {len(df)} remain")

    print("\nDepth-pri diagnostic (units unknown - inspect before trusting as fraction or ppm):")
    print(df["Depth-pri"].describe())

    # Stratify by Tmag quartile so the pilot sample spans the real brightness
    # range rather than skewing toward whichever stars happen to sort first.
    df["tmag_quartile"] = pd.qcut(df["Tmag"], 4, labels=False, duplicates="drop")

    rng = np.random.default_rng(seed)
    per_bin = max(1, n // df["tmag_quartile"].nunique())
    picked = []
    for q, group in df.groupby("tmag_quartile"):
        take = min(per_bin, len(group))
        picked.append(group.sample(n=take, random_state=seed))
    sample = pd.concat(picked).sample(frac=1, random_state=seed).reset_index(drop=True)
    # top up to exactly n if bins were uneven
    if len(sample) < n:
        remaining = df.drop(sample.index, errors="ignore")
        extra = remaining.sample(n=min(n - len(sample), len(remaining)), random_state=seed)
        sample = pd.concat([sample, extra]).reset_index(drop=True)
    sample = sample.head(n)

    print(f"\nPicked {len(sample)} stars, Tmag range {sample['Tmag'].min():.2f} to "
          f"{sample['Tmag'].max():.2f}, period range {sample['Per'].min():.4f} to "
          f"{sample['Per'].max():.2f} days")

    bench_root = root / "benchmark_run"
    processed_dir = bench_root / "data" / "processed"
    lc_dir = bench_root / "data" / "lightcurves"
    processed_dir.mkdir(parents=True, exist_ok=True)
    lc_dir.mkdir(parents=True, exist_ok=True)

    # Exactly the schema f2c_fetch_lightcurves.py expects as its input sample.
    sample_batch = sample[["TIC", "RAJ2000", "DEJ2000", "Tmag"]].copy()
    sample_batch["TIC"] = sample_batch["TIC"].astype(int)
    sample_batch_path = processed_dir / "sample_batch.csv"
    sample_batch.to_csv(sample_batch_path, index=False)
    print(f"Wrote {sample_batch_path} ({len(sample_batch)} rows)")

    ground_truth = sample[[
        "TIC", "RAJ2000", "DEJ2000", "Tmag", "Per", "T0-pri", "Depth-pri", "Dur-pri"
    ]].rename(columns={
        "Per": "true_period_days",
        "T0-pri": "true_t0_btjd",
        "Depth-pri": "true_depth_pri_kostov_units",
        "Dur-pri": "true_duration_days",
    })
    ground_truth["TIC"] = ground_truth["TIC"].astype(int)
    ground_truth_path = processed_dir / "benchmark_ground_truth.csv"
    ground_truth.to_csv(ground_truth_path, index=False)
    print(f"Wrote {ground_truth_path} ({len(ground_truth)} rows)")

    print(f"\nBenchmark project_root is ready at: {bench_root}")
    print("Next steps (run each pointed at THIS folder, not the real project root):")
    print(f"  py f2c_fetch_lightcurves.py \"{bench_root}\"")
    print(f"  py f3i_vet.py \"{bench_root}\"")
    print(f"  py f4f_novelty.py \"{bench_root}\"")
    print(f"  py diag_pixel.py \"{bench_root}\"")


if __name__ == "__main__":
    main()