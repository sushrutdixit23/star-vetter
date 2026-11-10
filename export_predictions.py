"""Export eclipse predictions for the site: site/public/data/predictions.json.

Inputs (all written by earlier stages):
  data/processed/f13_ephemerides.csv  one row per candidate (ephemeris, hold-out, grade)
  data/processed/f13_predictions.csv  predicted Year 9 primary eclipses
  data/processed/f14_novelty_extra.csv  optional: extra-catalog cross-match verdicts
  data/processed/f13_validation_prsa.csv  optional: validation against published ephemerides
  data/processed/f14_recall_known_ebs.json  optional: recall of the f14 cross-match
  site/public/data/index.json, detail/TIC*.json  magnitude, position, depth

THE SELECTION RULE (stated here, copied into the output, and applied mechanically):
  A star is LISTED if and only if
    1. f13 produced an ephemeris (status OK),
    2. its hold-out grade is VALIDATED or UNVALIDATED (never REJECTED),
    3. at least one primary eclipse is predicted inside a TESS Year 9 sector
       window the star is on silicon for, and
    4. the smallest 1-sigma uncertainty among its predictions is at most
       MAX_SIGMA_MIN minutes (a prediction good to a day tests nothing).
  Everything else is counted, by reason, under "excluded". Stars that FAILED the
  hold-out are named, so the failures stay visible.

Usage:  python export_predictions.py <root>
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

MAX_SIGMA_MIN = 120.0

SELECTION_RULE = [
    "The ephemeris was fitted (at least two eclipses, status OK).",
    "It is not REJECTED: a REJECTED ephemeris failed to predict a TESS sector, or a block of later sectors, it had not been shown.",
    "At least one primary eclipse falls inside a TESS Year 9 sector the star is on silicon for.",
    f"The best 1-sigma uncertainty among its predictions is at most {MAX_SIGMA_MIN:g} minutes.",
]

CONVENTIONS = {
    "time_scale": "Times are geocentric UTC (barycentric time corrected for light travel to Earth's centre). "
                  "BTJD = BJD_TDB - 2457000 is given alongside.",
    "grades": "VALIDATED: the ephemeris, fitted to the earliest sectors only, predicted the later ones, and the new "
              "predictions reach no more than 3 times as far beyond the data as that test did. UNVALIDATED: either "
              "only one sector could be phase-connected so nothing could be held out, or the test covered a much "
              "shorter distance than the prediction does. Real eclipse timing drifts, and only a long enough test sees it.",
    "sigma": "1-sigma uncertainty of the predicted eclipse time: the ephemeris fit error plus the excess timing "
             "noise found in the star's own history. It does not include the measurement error of the future "
             "observation, which is added when the outcome is graded.",
    "eclipse": "Primary eclipse only, mid-eclipse time.",
    "outcome_rule": "When Year 9 data are public, each eclipse that TESS observed is timed with the same code. "
                    "It counts as RECOVERED if the measured mid-eclipse lies within 3 sigma of the prediction "
                    "(sigma combined with the measurement error), INCONSISTENT if it is observed but outside, "
                    "and INSUFFICIENT DATA if the eclipse was not covered. Nothing is dropped after the fact. "
                    "Where SPOC or TESS-SPOC light curves exist for a sector they are used for grading. When QLP light curves are "
                    "used, a systematic timing term of 3 minutes is added in quadrature to the measurement error, because "
                    "Kostov et al. (2025, ApJS 279, 50, footnote 22) report a timing error of about 3 minutes in QLP light "
                    "curves beyond Sector 74. This rule is fixed before any Year 9 data exist.",
    "approximate_sectors": "Sectors 117-121 have interpolated dates and are marked approximate.",
}


def clean(v):
    """JSON-safe: NaN/inf -> None, numpy scalars -> python."""
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def text(v):
    """String cell -> str, with NaN/None (empty CSV cell) -> ''."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    return str(v)


def split_list(v):
    """Comma-separated CSV cell -> list of strings. NaN/None/'' -> [] (an empty
    cell reads back from pandas as NaN, which is truthy, so test explicitly)."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return []
    return [x.strip() for x in str(v).split(",") if x.strip()]


def rows_of(df):
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def load_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def validation_summary(path):
    """Summary of validate_f13_prsa.py output, or None."""
    df = load_csv(path)
    if df.empty or "d_epoch_min" not in df:
        return None
    z = df["z_period"].to_numpy()
    med = float(pd.Series(z).median())
    mad = 1.4826 * float((pd.Series(z) - med).abs().median())
    return {
        "n_stars": int(len(df)),
        "median_abs_epoch_error_min": clean(float(df["d_epoch_min"].abs().median())),
        "epoch_within_3sigma_fraction": clean(float((df["d_epoch_min"].abs() < 3 * df["sigma_epoch_min"]).mean())),
        "period_z_robust_spread": clean(mad),
        "source": "Prsa et al. 2022 (VizieR J/ApJS/258/16), sectors 1-26, starting ephemeris deliberately degraded",
    }


def holdout_calibration_summary(proc):
    """False-alarm check of the hold-out on known binaries (calibrate_f13_holdout.py), or None.
    Uses the file of the highest seed, i.e. the one run on stars not used for tuning."""
    files = sorted(proc.glob("f13_holdout_calibration_seed*.csv"))
    if not files:
        return None
    df = pd.read_csv(files[-1])
    if df.empty or "status" not in df:
        return None
    failed = df[df["status"] == "FAIL"]
    return {
        "n_stars": int(len(df)),
        "n_failed": int(len(failed)),
        "failed_timing_scatter_min": [clean(round(float(x), 1)) for x in failed["timing_rms_min"]],
        "source": "Prsa et al. 2022 binaries, sectors 1-26, none used to set the test's parameters",
    }


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    root = Path(argv[0]).resolve()
    proc = root / "data" / "processed"
    out_dir = root / "site" / "public" / "data"

    eph = load_csv(proc / "f13_ephemerides.csv")
    pred = load_csv(proc / "f13_predictions.csv")
    if eph.empty:
        print("No f13_ephemerides.csv; run f13_ephemeris.py first.")
        return 1
    ext = load_csv(proc / "f14_novelty_extra.csv")
    ext_by = {int(r["tic"]): r for r in ext.to_dict("records")} if not ext.empty else {}
    index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    tier_of = {int(c["tic"]): c for c in index["candidates"]}

    listed, excluded, rejected = [], {}, []
    for r in eph.to_dict("records"):
        tic = int(r["tic"])

        def skip(reason):
            excluded[reason] = excluded.get(reason, 0) + 1

        if r.get("status") != "OK":
            skip(text(r.get("exclusion_reason")) or text(r.get("status")) or "UNKNOWN")
            continue
        grade = r.get("prediction_grade")
        if grade == "REJECTED":
            rejected.append({"tic": tic, "holdout_min_p_value": clean(r.get("holdout_min_p_value")),
                             "holdout_max_z_equiv": clean(r.get("holdout_max_z_equiv")),
                             "n_eclipses": clean(r.get("n_eclipses")),
                             "baseline_days": clean(r.get("baseline_days")),
                             "grade_note": text(r.get("grade_note"))})
            continue
        p = pred[pred["tic"] == tic].sort_values("t_btjd") if not pred.empty else pred
        if p.empty:
            skip("NO_YEAR9_ECLIPSE")
            continue
        best = float(p["sigma_min"].min())
        if best > MAX_SIGMA_MIN:
            skip("UNCERTAINTY_TOO_LARGE")
            continue
        det_path = out_dir / "detail" / f"TIC{tic}.json"
        det = json.loads(det_path.read_text(encoding="utf-8")) if det_path.exists() else {}
        cat = det.get("catalog") or {}
        e = ext_by.get(tic)
        listed.append({
            "tic": tic,
            "tier": r.get("tier"),
            "grade": grade,
            "tmag": clean(cat.get("tmag")),
            "ra": clean(cat.get("ra")),
            "dec": clean(cat.get("dec")),
            "depth_frac": clean(tier_of.get(tic, {}).get("depth_frac")),
            "ephemeris": {
                "period_days": clean(r["period_days"]),
                "period_sigma_days": clean(r["period_sigma_days"]),
                "t0_btjd": clean(r["t0_btjd"]),
                "n_eclipses": clean(r["n_eclipses"]),
                "sectors_connected": [int(x) for x in split_list(r.get("sectors_connected"))],
                "sectors_unconnected": [int(x) for x in split_list(r.get("sectors_unconnected"))],
                "baseline_days": clean(r["baseline_days"]),
                "timing_jitter_min": clean(r.get("timing_jitter_min")),
                "timing_excess": bool(r.get("timing_excess")),
            },
            "holdout": {
                "status": r.get("holdout_status"),
                "sectors_tested": clean(r.get("holdout_sectors_tested")),
                "min_p_value": clean(r.get("holdout_min_p_value")),
                "tested_reach_days": clean(r.get("holdout_tested_lag_days")),
                "prediction_horizon_days": clean(r.get("prediction_horizon_days")),
                "extrapolation_factor": clean(r.get("extrapolation_factor")),
                "grade_note": text(r.get("grade_note")),
            },
            "novelty_extra": None if e is None else {
                "verdict": e.get("verdict"),
                "matched_catalogs": split_list(e.get("matched_catalogs")),
                "known_other_period": split_list(e.get("known_other_period")),
                "nearby_catalogs": split_list(e.get("nearby_catalogs")),
            },
            "best_sigma_min": clean(best),
            "predictions": [
                {"sector": int(x["sector"]), "cycle": int(x["cycle"]), "t_btjd": clean(x["t_btjd"]),
                 "utc": str(x["utc"]), "sigma_min": clean(x["sigma_min"]),
                 "approximate": bool(x.get("sector_dates_approx")), "horizon_days": clean(x.get("horizon_days"))}
                for x in p.to_dict("records")
            ],
        })
    listed.sort(key=lambda s: s["predictions"][0]["t_btjd"])

    status_counts = eph["status"].value_counts().to_dict()
    holdout_counts = eph["holdout_status"].value_counts().to_dict() if "holdout_status" in eph else {}
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selection_rule": SELECTION_RULE,
        "max_sigma_min": MAX_SIGMA_MIN,
        "conventions": CONVENTIONS,
        "counts": {
            "candidates_considered": int(len(eph)),
            "listed": len(listed),
            "listed_validated": sum(1 for s in listed if s["grade"] == "VALIDATED"),
            "listed_unvalidated": sum(1 for s in listed if s["grade"] == "UNVALIDATED"),
            "rejected_failed_holdout": len(rejected),
            "status": {k: int(v) for k, v in status_counts.items()},
            "holdout": {k: int(v) for k, v in holdout_counts.items()},
        },
        "excluded": dict(sorted(excluded.items(), key=lambda kv: -kv[1])),
        "rejected": rejected,
        "validation": validation_summary(proc / "f13_validation_prsa.csv"),
        "holdout_calibration": holdout_calibration_summary(proc),
        "extra_catalog_recall": (json.loads((proc / "f14_recall_known_ebs.json").read_text(encoding="utf-8"))
                                 if (proc / "f14_recall_known_ebs.json").exists() else None),
        "stars": listed,
    }
    out = out_dir / "predictions.json"
    out.write_text(json.dumps(payload, indent=1, allow_nan=False), encoding="utf-8", newline="\n")
    c = payload["counts"]
    print(f"Wrote {out}")
    print(f"  considered {c['candidates_considered']}, listed {c['listed']} "
          f"({c['listed_validated']} validated, {c['listed_unvalidated']} unvalidated), "
          f"rejected after hold-out {c['rejected_failed_holdout']}")
    for k, v in payload["excluded"].items():
        print(f"  excluded: {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
