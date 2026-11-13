import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import f29_benchmark as fb  # noqa: E402
import f30_injection as fi  # noqa: E402


def test_preregistration_is_complete_and_unchanged_in_shape():
    pre = json.loads((ROOT / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"))
    rule = pre["pass_rule"]
    assert (rule["e_abs"], rule["abs_esinw_abs"], rule["r_frac"], rule["incl_deg"]) == (0.01, 0.02, 0.05, 0.5)
    names = [s["name"] for s in pre["systems"]]
    assert names == ["MU Cas", "V1022 Cas", "V454 Aur", "V505 Per"]
    for s in pre["systems"]:
        tr = s["truth"]
        assert abs(np.hypot(tr["ecosw"], tr["esinw"]) - tr["e"]) < 0.002
        assert tr["r1"] + tr["r2"] < 0.25


def test_primary_duration_is_measured_from_a_box_eclipse():
    period, t0, dur = 5.0, 1000.0, 0.3
    t = np.arange(1000.0, 1060.0, 2.0 / 1440)
    ph = ((t - t0) / period + 0.5) % 1.0 - 0.5
    f = np.where(np.abs(ph) * period < dur / 2, 0.8, 1.0) + np.random.default_rng(1).normal(0, 1e-4, len(t))
    depth, d = fb.measure_primary(t, f, period, t0)
    assert abs(depth - 0.2) < 0.01
    assert 0.3 <= d <= 0.4          # the measured width is padded by 15%


def test_judge_applies_the_registered_rule():
    q = lambda m: {"median": m, "lo": 0.01, "hi": 0.01, "p2.5": m - 0.02, "p97.5": m + 0.02}  # noqa: E731
    row = {"status": "OK", "truth": {"e": 0.2, "esinw": -0.1, "ecosw": 0.17, "r1": 0.1, "r2": 0.08, "incl": 87.0},
           "fit": {"e": q(0.205), "esinw": q(0.105), "ecosw": q(0.171), "r1": q(0.103), "r2": q(0.081), "incl": q(87.3)}}
    out = fb.judge(dict(row), {"e_abs": 0.01, "abs_esinw_abs": 0.02, "ecosw_abs": 0.005, "r_frac": 0.05, "incl_deg": 0.5})
    assert out["passed"] is True          # |e sin w| compared, so the sign convention does not matter
    row["fit"]["r1"] = q(0.11)
    out = fb.judge(dict(row), {"e_abs": 0.01, "abs_esinw_abs": 0.02, "ecosw_abs": 0.005, "r_frac": 0.05, "incl_deg": 0.5})
    assert out["passed"] is False and out["checks"]["r1"] is False


def test_injected_systems_are_detached_and_eclipse_twice():
    rng = np.random.default_rng(29)
    for _ in range(200):
        p = fi.draw(rng)
        e = p["fc"] ** 2 + p["fs"] ** 2
        w = np.arctan2(p["fs"], p["fc"])
        assert 1 - e >= 1.5 * p["rsum"]
        for sign in (1, -1):
            rho = (1 - e * e) / (1 + sign * e * np.sin(w))
            assert rho * p["cosi"] < 0.7 * p["rsum"] + 1e-12


def test_coverage_metrics():
    def row(truth, med, sig, trusted):
        q = {"median": med, "lo": sig, "hi": sig, "p2.5": med - 2 * sig, "p97.5": med + 2 * sig}
        fit = {k: dict(q) for k in fi.QUANTITIES}
        fit["rsum"] = {"median": 0.1}
        return {"status": "OK", "host": 1, "index": 0, "trusted": trusted, "fit": fit,
                "truth": {k: truth for k in fi.QUANTITIES}, "inputs": {"f22": {"verdict": "ECCENTRIC"}}}
    rows = [row(0.2, 0.2 + d, 0.01, True) for d in (0.0, 0.005, -0.005, 0.02)]
    m = fi.metrics(rows)
    assert m["by_quantity"]["e"]["coverage_68"] == 0.75
    assert m["trust_rule"]["accepted"] == 4 and m["trust_rule"]["accepted_good_fraction"] == 1.0


def _injection_row(host, seed, index, noise=None):
    q = {"median": 0.2, "lo": 0.01, "hi": 0.01, "p2.5": 0.18, "p97.5": 0.22}
    fit = {k: dict(q) for k in fi.QUANTITIES}
    fit["rsum"] = {"median": 0.1}
    return {"status": "OK", "host": host, "seed": seed, "index": index, "trusted": True, "fit": fit, "converged": True,
            "truth": dict({k: 0.2 for k in fi.QUANTITIES}, rsum=0.1), "inputs": {"f22": {"verdict": "ECCENTRIC"}}}


def test_v2_injection_results_merge_into_their_own_file_and_by_seed(tmp_path):
    root, parts = tmp_path / "root", tmp_path / "parts"
    (root / "data" / "processed").mkdir(parents=True)
    parts.mkdir()
    site_file = root / "data" / "processed" / "f30_injection.json"
    site_file.write_text('{"untouched": true}\n', encoding="utf-8")
    for name, rows in (("f30v2_1_29_0.json", [_injection_row(1, 29, 0)]), ("f30v2_1_33_0.json", [_injection_row(1, 33, 0), _injection_row(1, 33, 1)]),
                       ("f30_1_0.json", [_injection_row(1, 29, 7)])):          # a v1 part file in the same directory is ignored by the v2 merge
        (parts / name).write_text(json.dumps({"rows": rows}), encoding="utf-8")
    out = fi.merge(root, parts, "v2")
    assert site_file.read_text(encoding="utf-8") == '{"untouched": true}\n'
    saved = json.loads((root / "data" / "processed" / "f30_injection_v2.json").read_text(encoding="utf-8"))
    assert saved["noise_model"] == "v2" and out["overall"]["n_injected"] == 3
    assert saved["by_seed"]["29"]["n_injected"] == 1 and saved["by_seed"]["33"]["n_injected"] == 2


def test_v2_benchmark_results_merge_into_their_own_file(tmp_path):
    root, parts = tmp_path / "root", tmp_path / "parts"
    (root / "data" / "processed").mkdir(parents=True)
    (root / "data" / "benchmarks").mkdir(parents=True)
    parts.mkdir()
    (root / "data" / "benchmarks" / "f29_preregistration.json").write_text((ROOT / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"), encoding="utf-8")
    pre = json.loads((root / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"))
    s0 = pre["systems"][0]
    row = {"name": s0["name"], "tic": s0["tic"], "cadence_min": 2, "status": "ERROR", "truth": s0["truth"], "reference": s0["reference"]}
    (parts / "f29v2_a.json").write_text(json.dumps({"rows": [row]}), encoding="utf-8")
    out = fb.merge(root, parts, "v2")
    assert out["noise_model"] == "v2" and out["summary"]["runs"] == 1
    assert (root / "data" / "processed" / "f29_benchmarks_v2.json").exists()
    assert not (root / "data" / "processed" / "f29_benchmarks.json").exists()


def test_injection_run_passes_the_noise_model_name_not_the_host_noise_array(monkeypatch):
    """Regression: `run` once overwrote its noise-model argument with the host's noise array, so every v2 injection
    failed with 'truth value of an array is ambiguous' before any fit ran (Physics v2, first run)."""
    seen = []

    def fake_fit(t, f, s, period, t0, duration, ecosw, depth_ratio, **kw):
        seen.append(kw.get("noise"))
        return {"status": "TOO_FEW_ECLIPSES_WITH_BASELINE"}

    monkeypatch.setattr(fi.f26, "fit_star", fake_fit)
    monkeypatch.setattr(fb, "prepare", lambda t, f, s, period, t0: {"duration_days": 0.2, "ecosw_input": 0.0, "depth_ratio": 0.5, "f22": {}})
    rows = fi.run(ROOT, 43785616, 29, 2, 0, 50, str(ROOT / "data" / "physics_inputs"), "v2")
    assert seen == ["v2", "v2"]
    assert [r["status"] for r in rows] == ["TOO_FEW_ECLIPSES_WITH_BASELINE"] * 2
