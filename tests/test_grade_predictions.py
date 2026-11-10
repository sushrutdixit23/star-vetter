import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import grade_predictions as gp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PRED = {"conventions": {"outcome_rule": "frozen rule text"},
        "stars": [{"tic": 1, "grade": "VALIDATED", "predictions": [{"sector": 115, "cycle": 10, "t_btjd": 4000.0, "sigma_min": 4.0},
                                                                    {"sector": 115, "cycle": 11, "t_btjd": 4030.0, "sigma_min": 4.0}]},
                  {"tic": 2, "grade": "UNVALIDATED", "predictions": [{"sector": 118, "cycle": 5, "t_btjd": 4100.0, "sigma_min": 50.0}]}]}


def meas(rows):
    return pd.DataFrame(rows, columns=["tic", "cycle", "covered", "t_btjd", "sigma_min", "source"])


def test_verdict_boundaries_and_qlp_term():
    # sigma_total = hypot(4, 3) = 5 min; 3 sigma = 15 min
    off = 14.9 / 1440.0
    assert gp.verdict(4000.0, 4.0, True, 4000.0 + off, 3.0, "SPOC")[0] == "RECOVERED"
    assert gp.verdict(4000.0, 4.0, True, 4000.0 + 15.1 / 1440.0, 3.0, "SPOC")[0] == "INCONSISTENT"
    # QLP adds 3 min in quadrature: hypot(4, 3, 3) = 5.83 min, so 3 sigma = 17.5 min: a 16 min offset is recovered
    assert gp.verdict(4000.0, 4.0, True, 4000.0 + 16.0 / 1440.0, 3.0, "QLP")[0] == "RECOVERED"
    assert gp.verdict(4000.0, 4.0, True, 4000.0 + 16.0 / 1440.0, 3.0, "SPOC")[0] == "INCONSISTENT"
    assert gp.verdict(4000.0, 4.0, False)[0] == "INSUFFICIENT_DATA"
    assert gp.verdict(4000.0, 4.0, True, float("nan"), 3.0, "SPOC")[0] == "INSUFFICIENT_DATA"


def test_every_prediction_is_reported_and_misses_are_not_dropped():
    m = meas([[1, 10, True, 4000.0 + 1 / 1440, 2.0, "SPOC"], [1, 11, True, 4030.0 + 90 / 1440, 2.0, "SPOC"]])
    rep = gp.grade(PRED, m)
    assert rep["counts"] == {"predicted": 3, "observed": 2, "recovered": 1, "inconsistent": 1, "insufficient_data": 1}
    assert len(rep["eclipses"]) == 3
    assert {r["verdict"] for r in rep["eclipses"]} == set(gp.VERDICTS)
    assert rep["by_grade"]["VALIDATED"]["observed"] == 2 and rep["by_grade"]["UNVALIDATED"]["observed"] == 0
    assert rep["recovered_among_observed"]["k"] == 1 and rep["recovered_among_observed"]["n"] == 2


def test_unknown_and_duplicate_measurements_are_errors():
    with pytest.raises(ValueError):
        gp.grade(PRED, meas([[9, 1, True, 1.0, 1.0, "SPOC"]]))
    with pytest.raises(ValueError):
        gp.grade(PRED, meas([[1, 10, True, 4000.0, 1.0, "SPOC"], [1, 10, True, 4000.0, 1.0, "SPOC"]]))


def test_loads_predictions_from_a_zip_and_rejects_ambiguous_bundles(tmp_path):
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("bundle/predictions.json", json.dumps(PRED))
    assert gp.load_predictions(z)["stars"][0]["tic"] == 1
    z2 = tmp_path / "b2.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("a/predictions.json", "{}")
        zf.writestr("b/predictions.json", "{}")
    with pytest.raises(ValueError):
        gp.load_predictions(z2)


@pytest.mark.skipif(not (ROOT / "site/public/data/predictions.json").exists(), reason="no predictions")
def test_real_frozen_rule_matches_the_constants_this_module_applies():
    pred = json.loads((ROOT / "site/public/data/predictions.json").read_text(encoding="utf-8"))
    rule = pred["conventions"]["outcome_rule"]
    assert "within 3 sigma" in rule and "3 minutes" in rule and "quadrature" in rule
    assert gp.NSIGMA == 3.0 and gp.QLP_SYSTEMATIC_MIN == 3.0
    rep = gp.grade(pred, meas([]))          # no data at all: everything insufficient, nothing silently dropped
    assert rep["counts"]["predicted"] == 21 and rep["counts"]["insufficient_data"] == 21     # 21 eclipses, though fewer (tic, sector) pairs
