import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f21_gaia_dr4_ready as f21  # noqa: E402
import f25_gaia_dr4_run as f25  # noqa: E402


def synthetic(period=2.0, t0_mjd=57500.0, duration=0.2, depth=0.2, n=70, seed=3, sigma=0.01):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(56900, 58800, n))
    ph = ((t - t0_mjd) / period + 0.5) % 1.0 - 0.5
    flux = 1.0 - depth * (np.abs(ph) <= 0.5 * duration / period) + rng.normal(0, sigma, n)
    return t, flux, np.full(n, sigma), (period, t0_mjd, duration)


def table_dr3(t_mjd, flux, err):
    return pd.DataFrame({"g_transit_time": t_mjd - (f21.GAIA_TIME_OFFSET - 2400000.5), "g_transit_flux": flux,
                         "g_transit_flux_error": err, "variability_flag_g_reject": [False] * len(t_mjd)})


def test_dr3_layout_and_time_scale_round_trip():
    t, f, e, _ = synthetic()
    mjd, ff, ee = f25.epoch_arrays(table_dr3(t, f, e))
    assert np.allclose(mjd, t, atol=1e-6) and len(ff) == len(t)


def test_other_time_conventions_are_converted_not_guessed():
    t, f, e, _ = synthetic()
    df = pd.DataFrame({"time": t, "flux": f, "flux_error": e})          # already MJD
    assert np.allclose(f25.epoch_arrays(df)[0], t)
    df = pd.DataFrame({"time": t + 2400000.5, "flux": f, "flux_error": e})   # full JD
    assert np.allclose(f25.epoch_arrays(df)[0], t)
    df = pd.DataFrame({"time": t * 0 + 7.0, "flux": f, "flux_error": e})      # nonsense scale
    with pytest.raises(f25.UnknownLayout):
        f25.epoch_arrays(df)


def test_unknown_columns_stop_with_the_column_list():
    with pytest.raises(f25.UnknownLayout) as ex:
        f25.epoch_arrays(pd.DataFrame({"a": [1.0], "b": [2.0]}))
    assert "a, b" in str(ex.value)


def test_flagged_points_are_dropped():
    t, f, e, _ = synthetic(n=20)
    df = table_dr3(t, f, e)
    df.loc[:4, "variability_flag_g_reject"] = True
    assert len(f25.epoch_arrays(df)[0]) == 15


def test_rule_supports_a_real_eclipse_and_refuses_noise():
    t, f, e, (P, t0, d) = synthetic(depth=0.2)
    res = f21.fold_test(t, f, e, P, t0, d)
    assert f25.decide(res, 0.2, f, e)[0] == "SUPPORTED"
    t, f, e, (P, t0, d) = synthetic(depth=0.0, seed=9)
    res = f21.fold_test(t, f, e, P, t0, d)
    assert f25.decide(res, None, f, e)[0] == "INCONCLUSIVE"        # no tess depth given: never CONTRADICTED


def test_absent_eclipse_is_contradicted_only_when_it_would_have_been_seen():
    t, f, e, (P, t0, d) = synthetic(depth=0.0, sigma=0.01, seed=5)
    res = f21.fold_test(t, f, e, P, t0, d)
    assert f25.decide(res, 0.2, f, e)[0] == "CONTRADICTED"         # a 20% eclipse would be obvious
    t, f, e, (P, t0, d) = synthetic(depth=0.0, sigma=0.3, seed=5)
    res = f21.fold_test(t, f, e, P, t0, d)
    assert f25.decide(res, 0.02, f, e)[0] == "INCONCLUSIVE"        # a 2% eclipse in 30% noise would not


def test_run_reads_files_and_reports_missing_ones(tmp_path):
    root = tmp_path / "root"
    (root / "site" / "public" / "data").mkdir(parents=True)
    (root / "data" / "processed").mkdir(parents=True)
    t, f, e, (P, t0, d) = synthetic(depth=0.2)
    t0_btjd = t0 - f21.BTJD_TO_MJD
    plan = {"stars": [
        {"tic": 1, "gaia_source_id": 111, "testable": True, "period_days": P, "t0_btjd": t0_btjd, "duration_days": d},
        {"tic": 2, "gaia_source_id": 222, "testable": True, "period_days": P, "t0_btjd": t0_btjd, "duration_days": d},
        {"tic": 3, "gaia_source_id": 333, "testable": False, "period_days": P, "t0_btjd": t0_btjd, "duration_days": d}]}
    (root / "site" / "public" / "data" / "gaia_dr4_plan.json").write_text(json.dumps(plan))
    pd.DataFrame({"TIC": [1, 2], "bls_depth": [0.2, 0.2]}).to_csv(root / "data" / "processed" / "f3i_vetting_results.csv", index=False)
    pd.DataFrame({"tic": [1, 2]}).to_csv(root / "data" / "processed" / "f13_ephemerides.csv", index=False)
    folder = tmp_path / "tables"
    folder.mkdir()
    table_dr3(t, f, e).to_csv(folder / "111.csv", index=False)
    out = f25.run(root, folder)["stars"]
    assert out["1"]["verdict"] == "SUPPORTED"
    assert out["2"]["verdict"] == "NO_FILE"
    assert "3" not in out


def test_false_alarm_rate_on_pure_noise_is_small():
    hits = 0
    for seed in range(150):
        t, f, e, (P, t0, d) = synthetic(depth=0.0, seed=seed)
        res = f21.fold_test(t, f, e, P, t0, d)
        hits += f25.decide(res, None, f, e)[0] == "SUPPORTED"
    assert hits <= 4
