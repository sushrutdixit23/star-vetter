"""
export_model_metrics.py

Publishes the trained pixel-outcome model's honest, cross-validated
performance to the site, alongside the rule baseline it is being compared
against. Nothing here is re-computed or re-estimated - it republishes what
f7b_train_classifier.py already measured with cross-validation, rounded for
display, plus a live count of predictions made but not yet checked against
a real pixel-check outcome.

Usage:
  py export_model_metrics.py <project_root>

Reads:
  <project_root>/data/processed/f7_model_metrics.json (written by f7b; if
                                                        missing, this script
                                                        exits cleanly - no
                                                        model has been
                                                        trained yet)
  <project_root>/data/processed/f7_scores.csv          (written by f7c,
                                                        optional)

Writes:
  <project_root>/site/public/data/model_metrics.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def clean(x, decimals=4):
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, bool):
        return x
    if isinstance(x, (int,)):
        return x
    if isinstance(x, float):
        return round(x, decimals)
    return x


def clean_dict(d, decimals=4):
    return {k: clean(v, decimals) for k, v in d.items()}


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_model_metrics.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"
    metrics_path = proc / "f7_model_metrics.json"

    if not metrics_path.exists():
        print(f"NOTE: {metrics_path} not found - no trained model yet, nothing to publish. "
              f"Run f7a_build_training_set.py and f7b_train_classifier.py first. "
              f"This is not an error - continuing without a model metrics export.")
        sys.exit(2)  # nothing to do yet - an orchestrator should not retry this

    with open(metrics_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    models_out = {}
    for name, m in raw.get("models", {}).items():
        models_out[name] = clean_dict(m)

    feature_importance = [
        {"feature": row["feature"], "importance_mean": clean(row["importance_mean"])}
        for row in raw.get("feature_importance", [])
    ]

    screening_value = [
        {
            "target_recall": clean(row["target_recall"], 2),
            "threshold": clean(row["threshold"], 3),
            "recall": clean(row["recall"], 3),
            "fraction_screened_out": clean(row["fraction_screened_out"], 3),
        }
        for row in raw.get("screening_value", [])
    ]

    scores_path = proc / "f7_scores.csv"
    pending_evaluation = None
    total_scored = None
    if scores_path.exists():
        scores = pd.read_csv(scores_path)
        total_scored = int(len(scores))
        if "actual_pixel_verdict" in scores.columns:
            pending_evaluation = int(scores["actual_pixel_verdict"].isna().sum())

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trained_at": raw.get("trained_at"),
        "n_training_samples": raw.get("n_samples"),
        "n_training_positive": raw.get("n_positive"),
        "n_training_negative": raw.get("n_negative"),
        "n_cv_folds": raw.get("n_folds"),
        "baseline": clean_dict(raw.get("baseline", {})),
        "models": models_out,
        "chosen_model": raw.get("chosen_model"),
        "beats_baseline": raw.get("beats_baseline"),
        "screening_value": screening_value,
        "feature_importance": feature_importance,
        "total_scored_this_run": total_scored,
        "pending_pixel_check": pending_evaluation,
        "note": "Precision and recall come from cross-validation (out-of-fold predictions), "
                "not from scoring the model's own training data. beats_baseline means the "
                "model's ROC AUC is meaningfully above 0.5 (random guessing) - it does not "
                "mean the model is currently used to skip any pixel check. See "
                "screening_value for the recall/skip-rate trade-off at different thresholds.",
    }

    site_data_dir = project_root / "site" / "public" / "data"
    site_data_dir.mkdir(parents=True, exist_ok=True)
    out_path = site_data_dir / "model_metrics.json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, ensure_ascii=True)

    print(f"Wrote {out_path}")
    print(f"  chosen model: {out['chosen_model']}  beats_baseline: {out['beats_baseline']}")
    if total_scored is not None:
        print(f"  {total_scored} candidates scored this run, "
              f"{pending_evaluation} awaiting a real pixel-check outcome")


if __name__ == "__main__":
    main()