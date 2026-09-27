"""
f7b_train_classifier.py

Trains a model to predict the pixel-check outcome (ON_TARGET vs not) from
features that are already known BEFORE the pixel check runs, and reports
whether it earns a place in the pipeline against the current baseline of
"send everything novel to the pixel check."

This is the actual AI/ML component of Star Vetter: two real, trained
classifiers (logistic regression and a gradient-boosted tree model),
evaluated with cross-validation on real pipeline output, compared head to
head against a rule baseline, with the losing or winning result reported
either way.

Usage:
  py f7b_train_classifier.py <project_root>

Reads:
  <project_root>/data/processed/f7_training_set.csv  (written by f7a)

Writes:
  <project_root>/data/models/f7_pixel_screen.joblib   (the trained pipeline)
  <project_root>/data/processed/f7_model_metrics.json (cross-validated metrics)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
except ImportError:
    print("ERROR: scikit-learn is not installed in this Python environment.")
    print("Install it with:")
    print("  py -m pip install scikit-learn")
    print("(joblib is a scikit-learn dependency and will install alongside it)")
    sys.exit(2)  # environment not ready - an orchestrator should not retry this

try:
    import joblib
except ImportError:
    print("ERROR: joblib is not installed. Install scikit-learn first:")
    print("  py -m pip install scikit-learn")
    sys.exit(2)  # environment not ready - an orchestrator should not retry this

NUMERIC_FEATURES = [
    "bls_period", "bls_duration", "bls_depth", "bls_snr",
    "n_eclipses_observed", "depth_ratio", "robust_sigma", "robust_depth",
    "odd_even_z", "depth_odd", "depth_even",
    "secondary_detected", "secondary_phase", "secondary_sigma",
    "Tmag", "n_sectors", "n_points",
]
CATEGORICAL_FEATURES = ["author_used"]
TARGET = "on_target"

# The recall level we actually operate at. Model selection picks whichever
# model screens out the most work while still hitting this recall, not
# whichever has the best ROC AUC - a model can rank well overall yet still
# be unusable at a specific high-recall operating point. (2026-09-27:
# hist_gradient_boosting had the better AUC but a recall_mean of just
# 0.149, so it could not hit 0.80 recall at any threshold above 0, while
# logistic_regression's recall_mean of 0.598 made it the only one with any
# real screening value - but the old AUC-only selection never checked.)
PRIMARY_TARGET_RECALL = 0.80


def build_pipeline(numeric_cols, categorical_cols, model):
    transformers = []
    if numeric_cols:
        transformers.append((
            "numeric",
            Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]),
            numeric_cols,
        ))
    if categorical_cols:
        transformers.append((
            "categorical",
            Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]),
            categorical_cols,
        ))
    pre = ColumnTransformer(transformers)
    return Pipeline([("pre", pre), ("model", model)])


def cv_metrics(pipeline, X, y, n_splits):
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scoring = ["precision", "recall", "roc_auc", "average_precision"]
    scores = cross_validate(pipeline, X, y, cv=skf, scoring=scoring, error_score="raise")
    out = {}
    for metric in scoring:
        key = f"test_{metric}"
        out[f"{metric}_mean"] = float(np.mean(scores[key]))
        out[f"{metric}_std"] = float(np.std(scores[key]))
    return out


def screening_value(pipeline, X, y, n_splits):
    """How much of the expensive pixel-check download could be skipped, and
    at what cost in recall, if we screened with this model instead of
    sending every candidate through. Uses cross-validated (out-of-fold)
    predicted probabilities so this is an honest, not in-sample, estimate."""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    proba = cross_val_predict(pipeline, X, y, cv=skf, method="predict_proba")[:, 1]
    results = []
    for target_recall in (0.95, 0.90, 0.80):
        best = None
        for threshold in np.linspace(0.0, 0.95, 96):
            pred = (proba >= threshold).astype(int)
            tp = int(((pred == 1) & (y == 1)).sum())
            fn = int(((pred == 0) & (y == 1)).sum())
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            if recall >= target_recall:
                skipped = int((pred == 0).sum())
                best = {"threshold": round(float(threshold), 3),
                        "recall": round(recall, 3),
                        "fraction_screened_out": round(skipped / len(y), 3)}
        if best:
            results.append({"target_recall": target_recall, **best})
    return results


def skip_fraction_at(screening_rows, target_recall):
    for row in screening_rows:
        if row["target_recall"] == target_recall:
            return row["fraction_screened_out"]
    return 0.0


def main():
    if len(sys.argv) < 2:
        print("Usage: py f7b_train_classifier.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"
    train_path = proc / "f7_training_set.csv"

    if not train_path.exists():
        print(f"ERROR: {train_path} not found. Run f7a_build_training_set.py first.")
        sys.exit(2)  # data not ready yet - an orchestrator should not retry this

    df = pd.read_csv(train_path)
    if TARGET not in df.columns:
        print(f"ERROR: expected column '{TARGET}' not found in {train_path}.")
        sys.exit(2)  # data not ready yet - an orchestrator should not retry this

    y = df[TARGET].astype(int)
    n = len(df)
    n_pos = int(y.sum())
    n_neg = n - n_pos

    if n_pos < 6 or n_neg < 6:
        print(f"ERROR: too few examples to cross-validate honestly "
              f"({n_pos} positive, {n_neg} negative). Need at least 6 of each. "
              f"Run more pipeline batches through the pixel check, then retry.")
        sys.exit(2)  # data not ready yet - an orchestrator should not retry this

    numeric_cols = [c for c in NUMERIC_FEATURES if c in df.columns]
    categorical_cols = [c for c in CATEGORICAL_FEATURES if c in df.columns]
    missing = [c for c in NUMERIC_FEATURES if c not in df.columns]
    if missing:
        print(f"NOTE: training set is missing columns {missing} - training without them.")

    X = df[numeric_cols + categorical_cols]
    n_splits = min(5, n_pos, n_neg)

    baseline_precision = n_pos / n
    print(f"Rule baseline (send every candidate to the pixel check): "
          f"recall 1.000, precision {baseline_precision:.3f}")

    model_defs = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced", max_iter=2000, random_state=42
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            random_state=42, max_depth=4, learning_rate=0.08
        ),
    }

    model_metrics = {}
    pipelines = {}
    model_screening = {}
    print(f"\nCross-validated ({n_splits}-fold) metrics:")
    for name, model in model_defs.items():
        pipe = build_pipeline(numeric_cols, categorical_cols, model)
        pipelines[name] = pipe
        metrics = cv_metrics(pipe, X, y, n_splits)
        model_metrics[name] = metrics
        print(f"  {name}:")
        print(f"    precision {metrics['precision_mean']:.3f} (+/- {metrics['precision_std']:.3f})"
              f"  recall {metrics['recall_mean']:.3f} (+/- {metrics['recall_std']:.3f})"
              f"  roc_auc {metrics['roc_auc_mean']:.3f}")
        model_screening[name] = screening_value(pipe, X, y, n_splits)
        skip_80 = skip_fraction_at(model_screening[name], PRIMARY_TARGET_RECALL)
        print(f"    screening value at recall >= {PRIMARY_TARGET_RECALL:.2f}: "
              f"{skip_80*100:.1f}% of downloads skippable")

    # Pick whichever model screens out the most work at our real operating
    # recall, tie-broken by roc_auc_mean (see PRIMARY_TARGET_RECALL comment
    # above for why AUC alone picked a worse model on 2026-09-27).
    chosen_name = max(
        model_metrics,
        key=lambda k: (
            skip_fraction_at(model_screening[k], PRIMARY_TARGET_RECALL),
            model_metrics[k]["roc_auc_mean"],
        ),
    )
    chosen_auc = model_metrics[chosen_name]["roc_auc_mean"]
    baseline_auc_equivalent = 0.5  # a coin flip / "send everyone" has no discriminative power
    beats_baseline = chosen_auc > baseline_auc_equivalent + 0.05

    print(f"\nBest model by screening value at recall >= {PRIMARY_TARGET_RECALL:.2f}: "
          f"{chosen_name} (roc_auc {chosen_auc:.3f})")
    if not beats_baseline:
        print("  This does not clearly beat random guessing yet. Recommendation: "
              "do NOT use this to skip pixel checks. Keep collecting labeled runs.")
    else:
        print("  This shows real discriminative signal over the current no-filter baseline.")

    chosen_pipe = pipelines[chosen_name]
    screening = model_screening[chosen_name]
    print("\nScreening value (out-of-fold, honest estimate):")
    for row in screening:
        print(f"  at recall >= {row['target_recall']:.2f}: could skip "
              f"{row['fraction_screened_out']*100:.1f}% of pixel-check downloads "
              f"(threshold {row['threshold']:.2f}, achieved recall {row['recall']:.3f})")

    # Fit the chosen model on all available data for saving/scoring future candidates.
    chosen_pipe.fit(X, y)
    models_dir = project_root / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "f7_pixel_screen.joblib"
    joblib.dump(
        {"pipeline": chosen_pipe, "numeric_cols": numeric_cols,
         "categorical_cols": categorical_cols, "model_name": chosen_name},
        model_path,
    )
    print(f"\nSaved trained pipeline: {model_path}")

    try:
        importance = permutation_importance(
            chosen_pipe, X, y, n_repeats=20, random_state=42, scoring="roc_auc"
        )
        feature_names = numeric_cols + categorical_cols
        ranked = sorted(
            zip(feature_names, importance.importances_mean),
            key=lambda t: t[1], reverse=True,
        )
        feature_importance = [
            {"feature": f, "importance_mean": round(float(v), 4)} for f, v in ranked
        ]
    except Exception as exc:
        print(f"NOTE: could not compute permutation importance ({exc}). Continuing without it.")
        feature_importance = []

    if feature_importance:
        print("\nTop features (in-sample permutation importance, ROC AUC drop):")
        for row in feature_importance[:6]:
            print(f"  {row['feature']}: {row['importance_mean']:.4f}")

    metrics_out = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": n,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_folds": n_splits,
        "baseline": {
            "description": "current pipeline behavior: every candidate that passes "
                            "statistical vetting and novelty cross-match goes to the "
                            "pixel check",
            "recall": 1.0,
            "precision": round(baseline_precision, 4),
        },
        "models": model_metrics,
        "chosen_model": chosen_name,
        "chosen_model_selection": f"best fraction_screened_out at recall >= "
                                   f"{PRIMARY_TARGET_RECALL:.2f}, tie-broken by roc_auc_mean",
        "beats_baseline": bool(beats_baseline),
        "screening_value": screening,
        "models_screening_value": model_screening,
        "feature_importance": feature_importance,
        "note": "n_positive is small; treat these numbers as directional until more "
                "runs accumulate. Cross-validated (out-of-fold) throughout - not in-sample.",
    }

    metrics_path = proc / "f7_model_metrics.json"
    with open(metrics_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(metrics_out, f, indent=2, ensure_ascii=True)
    print(f"\nSaved metrics: {metrics_path}")


if __name__ == "__main__":
    main()