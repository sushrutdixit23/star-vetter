"""Offline tests for export_predictions.py on a small synthetic data root."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_predictions as ep  # noqa: E402


def eph_row(tic, status="OK", grade="VALIDATED", **kw):
    base = {"tic": tic, "tier": "CLEAN", "eligible": True, "exclusion_reason": "", "status": status,
            "n_eclipses": 20, "period_days": 3.0, "period_sigma_days": 1e-6, "t0_btjd": 2000.0,
            "baseline_days": 900.0, "timing_jitter_min": 0.5, "timing_excess": False,
            "holdout_status": {"VALIDATED": "PASS", "REJECTED": "FAIL"}.get(grade, "NOT_TESTABLE"),
            "holdout_sectors_tested": 3, "holdout_min_p_value": 0.4, "holdout_max_z_equiv": 0.8,
            "prediction_grade": grade, "sectors_connected": "10,11,40", "sectors_unconnected": "",
            "grade_note": f"note for {grade}", "holdout_tested_lag_days": 400.0,
            "prediction_horizon_days": 600.0, "extrapolation_factor": 1.5}
    base.update(kw)
    return base


def pred_row(tic, t, sigma, sector=112):
    return {"tic": tic, "sector": sector, "sector_dates_approx": False, "cycle": 800,
            "t_btjd": t, "sigma_min": sigma, "utc": "2026-12-30 01:02:03", "grade": "VALIDATED",
            "horizon_days": 600.0}


@pytest.fixture
def root(tmp_path):
    data = tmp_path / "site" / "public" / "data"
    (data / "detail").mkdir(parents=True)
    tics = [1, 2, 3, 4, 5, 6, 7]
    (data / "index.json").write_text(json.dumps({"candidates": [
        {"tic": t, "tier": "CLEAN", "depth_frac": 0.05} for t in tics]}), encoding="utf-8")
    for t in tics:
        (data / "detail" / f"TIC{t}.json").write_text(json.dumps(
            {"catalog": {"ra": 10.0 + t, "dec": -5.0, "tmag": 12.0 + t / 10}}), encoding="utf-8")
    proc = tmp_path / "data" / "processed"
    proc.mkdir(parents=True)
    pd.DataFrame([
        eph_row(1, grade="VALIDATED"),
        eph_row(2, grade="UNVALIDATED", timing_jitter_min=np.nan),      # NaN must not leak into JSON
        eph_row(3, grade="REJECTED"),
        eph_row(4, grade="VALIDATED"),                                  # too uncertain
        eph_row(5, grade="VALIDATED"),                                  # no Year 9 eclipse
        {"tic": 6, "tier": "CLEAN", "eligible": False, "exclusion_reason": "PERIOD_ALIAS",
         "status": "NOT_ELIGIBLE"},
        {"tic": 7, "tier": "CLEAN", "eligible": True, "exclusion_reason": "", "status": "TOO_FEW_ECLIPSES"},
    ]).to_csv(proc / "f13_ephemerides.csv", index=False)
    pd.DataFrame([pred_row(1, 2400.0, 30.0), pred_row(1, 2403.0, 31.0),
                  pred_row(2, 2380.0, 90.0), pred_row(3, 2390.0, 20.0),
                  pred_row(4, 2395.0, 300.0)]).to_csv(proc / "f13_predictions.csv", index=False)
    pd.DataFrame([{"tic": 1, "verdict": "ALREADY_KNOWN", "matched_catalogs": "atlas",
                   "known_other_period": np.nan, "nearby_catalogs": np.nan}]
                 ).to_csv(proc / "f14_novelty_extra.csv", index=False)
    return tmp_path


def run(root):
    assert ep.main([str(root)]) == 0
    return json.loads((root / "site" / "public" / "data" / "predictions.json").read_text(encoding="utf-8"))


def test_selection_rule_is_applied_exactly(root):
    out = run(root)
    assert [s["tic"] for s in out["stars"]] == [2, 1]               # sorted by first eclipse, not by TIC
    assert out["counts"]["listed_validated"] == 1 and out["counts"]["listed_unvalidated"] == 1
    assert [r["tic"] for r in out["rejected"]] == [3]               # failures stay visible
    assert out["excluded"] == {"UNCERTAINTY_TOO_LARGE": 1, "NO_YEAR9_ECLIPSE": 1,
                               "PERIOD_ALIAS": 1, "TOO_FEW_ECLIPSES": 1}
    assert 3 not in [s["tic"] for s in out["stars"]]                # REJECTED is never listed


def test_every_listed_star_satisfies_the_published_rule(root):
    out = run(root)
    for s in out["stars"]:
        assert s["grade"] in ("VALIDATED", "UNVALIDATED")
        assert s["predictions"] and s["best_sigma_min"] <= out["max_sigma_min"]
        assert s["best_sigma_min"] == min(p["sigma_min"] for p in s["predictions"])


def test_output_is_strict_json_with_no_nan(root):
    out = run(root)                       # export uses allow_nan=False, so NaN would have raised
    star2 = next(s for s in out["stars"] if s["tic"] == 2)
    assert star2["ephemeris"]["timing_jitter_min"] is None


def test_rule_and_conventions_travel_with_the_data(root):
    out = run(root)
    assert len(out["selection_rule"]) == 4 and "3 sigma" in out["conventions"]["outcome_rule"]
    assert "geocentric UTC" in out["conventions"]["time_scale"]


def test_extra_catalog_verdict_is_attached_and_missing_ones_are_null(root):
    out = run(root)
    s1 = next(s for s in out["stars"] if s["tic"] == 1)
    s2 = next(s for s in out["stars"] if s["tic"] == 2)
    assert s1["novelty_extra"]["verdict"] == "ALREADY_KNOWN"
    assert s1["novelty_extra"]["matched_catalogs"] == ["atlas"] and s1["novelty_extra"]["nearby_catalogs"] == []
    assert s2["novelty_extra"] is None


def test_validation_summary_absent_is_null_and_present_is_summarised(root):
    assert run(root)["validation"] is None
    pd.DataFrame({"d_epoch_min": [1.0, -2.0, 4.0], "sigma_epoch_min": [1.0, 1.0, 1.0],
                  "z_period": [0.1, -0.3, 0.2]}).to_csv(
        root / "data" / "processed" / "f13_validation_prsa.csv", index=False)
    v = run(root)["validation"]
    assert v["n_stars"] == 3 and v["median_abs_epoch_error_min"] == 2.0
    assert v["epoch_within_3sigma_fraction"] == pytest.approx(2 / 3)


def test_no_f13_output_is_a_clean_failure(tmp_path):
    (tmp_path / "data" / "processed").mkdir(parents=True)
    assert ep.main([str(tmp_path)]) == 1


def test_grade_evidence_travels_with_each_star(root):
    out = run(root)
    s1 = next(s for s in out["stars"] if s["tic"] == 1)
    h = s1["holdout"]
    assert h["tested_reach_days"] == 400.0 and h["prediction_horizon_days"] == 600.0
    assert h["extrapolation_factor"] == 1.5 and h["grade_note"] == "note for VALIDATED"
    assert s1["predictions"][0]["horizon_days"] == 600.0
    assert out["rejected"][0]["grade_note"] == "note for REJECTED"
    assert "grades" in out["conventions"]


def test_holdout_calibration_summary_is_null_without_a_file_and_counts_failures_with_one(root):
    assert run(root)["holdout_calibration"] is None
    pd.DataFrame({"tic": [1, 2, 3, 4], "status": ["PASS", "PASS", "FAIL", "PASS"],
                  "timing_rms_min": [0.1, 0.2, 14.6, 0.3]}).to_csv(
        root / "data" / "processed" / "f13_holdout_calibration_seed23.csv", index=False)
    c = run(root)["holdout_calibration"]
    assert c["n_stars"] == 4 and c["n_failed"] == 1 and c["failed_timing_scatter_min"] == [14.6]
