import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_independent as ei  # noqa: E402


def _r(tic, status, **kw):
    base = {"tic": tic, "tier": "CLEAN", "status": status, "n_points": 500, "tess_period": 3.0, "p_value": 0.003, "power": 0.9,
            "depth_ratio": 1.0, "depth_ratio_err": 0.1, "ztf_span_days": 2000.0, "epochs_with_points": 6,
            "obs": {"period": 3.001, "snr": 12.0}, "odd_even_at_2P": {"z": 0.4}, "secondary": None}
    base.update(kw)
    return base


def test_compact_flattens_and_tolerates_missing_parts():
    c = ei.compact(_r(1, "CONFIRMED"))
    assert c["refined_period"] == 3.001 and c["odd_even_z"] == 0.4 and c["secondary_z"] is None
    n = ei.compact({"tic": 2, "status": "NO_DATA", "n_points": 0})
    assert n["status"] == "NO_DATA" and n["refined_period"] is None and n["power"] is None


def test_build_counts_and_documents_the_method():
    out = ei.build([_r(1, "CONFIRMED"), _r(2, "NOT_SEEN"), _r(3, "INCONCLUSIVE"), {"tic": 4, "status": "NO_DATA", "tier": "CLEAN", "n_points": 0}])
    s = out["summary"]
    assert s["stars"] == 4 and s["testable"] == 2 and s["confirmed_among_testable"]["k"] == 1
    assert set(out["stars"]) == {"1", "2", "3", "4"} and "controls" in out["method"]["null"]
