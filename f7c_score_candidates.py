"""
f7c_score_candidates.py

Scores every novel candidate with the trained pixel-outcome model, and
records the score. This stage NEVER filters or skips anything - it only
writes an ml_score column alongside whatever pipeline stage runs next, so
the model's predictions can be compared against real pixel-check outcomes
over several runs before anyone decides whether to trust it enough to skip
downloads.

Usage:
  py f7c_score_candidates.py <project_root>

Reads:
  <project_root>/data/models/f7_pixel_screen.joblib   (written by f7b; if
                                                        missing, this script
                                                        exits cleanly and
                                                        changes nothing)
  <project_root>/data/processed/f3i_vetting_results.csv
  <project_root>/data/processed/f4f_novelty_results.csv
  <project_root>/data/processed/f2c_manifest.csv        (optional)
  <project_root>/data/processed/diag_pixel_results_v2.csv (optional - if a
                                                        candidate has already
                                                        been pixel-checked,
                                                        its real outcome is
                                                        recorded alongside
                                                        the score, so
                                                        accuracy can be
                                                        tracked over time)

Writes:
  <project_root>/data/processed/f7_scores.csv
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import joblib
except ImportError:
    print("NOTE: joblib/scikit-learn not installed - skipping scoring stage. "
          "Install with: py -m pip install scikit-learn")
    sys.exit(2)  # environment not ready - an orchestrator should not retry this

NUMERIC_FEATURES = [
    "bls_period", "bls_duration", "bls_depth", "bls_snr",
    "n_eclipses_observed", "depth_ratio", "robust_sigma", "robust_depth",
    "odd_even_z", "depth_odd", "depth_even",
    "secondary_detected", "secondary_phase", "secondary_sigma",
    "Tmag", "n_sectors", "n_points",
]
CATEGORICAL_FEATURES = ["author_used"]


def main():
    if len(sys.argv) < 2:
        print("Usage: py f7c_score_candidates.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"
    model_path = project_root / "data" / "models" / "f7_pixel_screen.joblib"

    if not model_path.exists():
        print(f"NOTE: {model_path} not found - no trained model yet, nothing to score. "
              f"Run f7a_build_training_set.py and f7b_train_classifier.py first. "
              f"This is not an error - continuing without scoring.")
        sys.exit(2)  # nothing to do yet - an orchestrator should not retry this

    saved = joblib.load(model_path)
    pipe = saved["pipeline"]
    numeric_cols = saved["numeric_cols"]
    categorical_cols = saved["categorical_cols"]
    model_name = saved["model_name"]

    vet_path = proc / "f3i_vetting_results.csv"
    nov_path = proc / "f4f_novelty_results.csv"
    if not vet_path.exists() or not nov_path.exists():
        print(f"NOTE: required input files not found ({vet_path.name}, {nov_path.name}). "
              f"Nothing to score yet - continuing.")
        sys.exit(2)  # nothing to do yet - an orchestrator should not retry this

    vet = pd.read_csv(vet_path)
    nov = pd.read_csv(nov_path)

    novel = nov[nov["verdict"] == "NOVEL"][["TIC"]].copy()
    if novel.empty:
        print("No NOVEL candidates found in f4f_novelty_results.csv - nothing to score.")
        sys.exit(2)  # nothing to do yet - an orchestrator should not retry this

    # Only pull the f3i-specific features from vet, never the manifest-owned
    # columns (Tmag, n_sectors, n_points, author_used) even if vet happens to
    # carry a same-named column too - otherwise merging both frames renames
    # the colliding column to <name>_x/<name>_y and silently drops the plain
    # name the model expects. This is the actual root cause of the n_points
    # NaN warning above: your real f3i_vetting_results.csv also carries an
    # n_points column, and merging the whole vet frame collided with the
    # manifest's n_points column instead of keeping the manifest's real value.
    manifest_owned = {"Tmag", "n_sectors", "n_points", "author_used"}
    vet_cols = [c for c in numeric_cols if c in vet.columns and c not in manifest_owned]
    df = novel.merge(vet[["TIC"] + vet_cols], on="TIC", how="left")

    manifest_path = proc / "f2c_manifest.csv"
    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path)
        man_cols = [c for c in ("Tmag", "n_sectors", "n_points", "author_used")
                    if c in manifest.columns]
        df = df.merge(manifest[["TIC"] + man_cols], on="TIC", how="left")

    for bool_col in ("secondary_detected",):
        if bool_col in df.columns:
            df[bool_col] = df[bool_col].map(
                {True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}
            ).fillna(0).astype(int)

    missing_features = [c for c in numeric_cols + categorical_cols if c not in df.columns]
    if missing_features:
        print(f"NOTE: the trained model expects columns {missing_features} that are not "
              f"present in this run's merged data - filling with NaN. The imputer inside "
              f"the model handles this, but predictions relying on these features will be "
              f"less reliable until this data is available again.")
    for col in missing_features:
        df[col] = np.nan

    X = df[numeric_cols + categorical_cols]
    proba = pipe.predict_proba(X)[:, 1]

    out = pd.DataFrame({
        "TIC": df["TIC"],
        "ml_score": proba.round(4),
        "ml_model_name": model_name,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    })

    pixel_path = proc / "diag_pixel_results_v2.csv"
    if pixel_path.exists():
        pixel = pd.read_csv(pixel_path)
        pixel_candidates = pixel[pixel["role"] == "candidate"][["TIC", "verdict"]].rename(
            columns={"verdict": "actual_pixel_verdict"}
        )
        out = out.merge(pixel_candidates, on="TIC", how="left")
    else:
        out["actual_pixel_verdict"] = pd.NA

    out_path = proc / "f7_scores.csv"
    out.to_csv(out_path, index=False, encoding="utf-8")

    n = len(out)
    n_checked = int(out["actual_pixel_verdict"].notna().sum())
    print(f"Scored {n} novel candidates with model '{model_name}'.")
    print(f"  Of those, {n_checked} already have a real pixel-check outcome to compare against.")
    if n_checked > 0:
        checked = out[out["actual_pixel_verdict"].notna()].copy()
        checked["actual_on_target"] = (checked["actual_pixel_verdict"] == "ON_TARGET").astype(int)
        high_score = checked[checked["ml_score"] >= 0.5]
        if len(high_score) > 0:
            hit_rate = high_score["actual_on_target"].mean()
            print(f"  Of {len(high_score)} candidates the model scored >= 0.5, "
                  f"{hit_rate*100:.1f}% actually turned out ON_TARGET.")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()