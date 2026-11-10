import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Preparation for Gaia DR4 (due 2 December 2026).
#
# Gaia's epoch photometry resolves the target to about 0.7 arcsec and covers the whole
# sky, including the far south where ZTF does not reach. It is the strongest remaining
# blend test available without a telescope. But Gaia observed each star only about 70
# times over 66 months (2014-2020), so a period search is hopeless; the useful test is
# a likelihood test at a FIXED ephemeris: are the Gaia points that fall inside the
# predicted eclipses fainter than the rest?
#
# That only works if the ephemeris is precise enough to be carried back to the Gaia
# epoch. This module (1) works out which survivors have such an ephemeris today, from
# the phase-connected timing fits (f13), (2) provides the fixed-ephemeris test, checked
# on synthetic data here, and (3) writes the list of stars to run on release day.
#
# NOT DONE and cannot be before release: loading the DR4 epoch photometry itself. The
# DR3 epoch photometry came through a separate retrieval service rather than a table,
# and the DR4 layout is not public yet. `load_epoch_photometry` is the one function to
# finish on the day; everything after it is tested.

GAIA_DR4_START_MJD = 56880.0     # 2014-07-25, start of Gaia science operations
GAIA_DR4_END_MJD = 58870.0       # 2020-01-20, end of the DR4 data window (66 months)
GAIA_MID_MJD = 0.5 * (GAIA_DR4_START_MJD + GAIA_DR4_END_MJD)
TYPICAL_TRANSITS = 70            # per source (ESA: about 70 for DR4)
MAX_TIMING_FRAC = 0.25           # ephemeris error at the Gaia epoch must be below this x duration
MIN_EXPECTED_IN_ECLIPSE = 3.0
BTJD_TO_MJD = 56999.5            # MJD = BTJD + 2457000 - 2400000.5
GAIA_TIME_OFFSET = 2455197.5     # Gaia times are BJD(TCB) - 2455197.5


def timing_error_at(epoch_mjd, period, sigma_period, t0_mjd, sigma_t0_days):
    """1-sigma error on the predicted time of an eclipse near `epoch_mjd`, days."""
    n_cycles = abs((epoch_mjd - t0_mjd) / period)
    return float(np.hypot(sigma_t0_days, n_cycles * sigma_period))


def gaia_testable(period, sigma_period, t0_btjd, sigma_t0_min, duration):
    """(testable, info) for one star from its timing fit."""
    t0_mjd = t0_btjd + BTJD_TO_MJD
    sig_mid = timing_error_at(GAIA_MID_MJD, period, sigma_period, t0_mjd, sigma_t0_min / 1440.0)
    sig_far = max(timing_error_at(GAIA_DR4_START_MJD, period, sigma_period, t0_mjd, sigma_t0_min / 1440.0),
                  timing_error_at(GAIA_DR4_END_MJD, period, sigma_period, t0_mjd, sigma_t0_min / 1440.0))
    expected_in = TYPICAL_TRANSITS * min(1.0, duration / period)
    ok = sig_far <= MAX_TIMING_FRAC * duration and expected_in >= MIN_EXPECTED_IN_ECLIPSE
    return bool(ok), {"timing_error_mid_days": sig_mid, "timing_error_worst_days": sig_far,
                      "duration_days": duration, "expected_in_eclipse_points": expected_in}


def fold_test(t_mjd, flux, err, period, t0_mjd, duration, n_shifts=2000, seed=1):
    """Fixed-ephemeris test. Returns depth (out-of-eclipse mean minus in-eclipse mean, in the
    flux units given), its z-score from the errors, and a permutation p-value from shifting the
    eclipse window to other phases (which absorbs red noise and a wrong error scale)."""
    t = np.asarray(t_mjd, float)
    f = np.asarray(flux, float)
    e = np.asarray(err, float)
    ph = ((t - t0_mjd) / period + 0.5) % 1.0 - 0.5            # -0.5..0.5, eclipse at 0
    half = 0.5 * duration / period

    def stat(shift):
        d = np.abs(((ph - shift + 0.5) % 1.0) - 0.5)
        inn = d <= half
        out = d >= 1.5 * half
        if inn.sum() < 2 or out.sum() < 5:
            return None
        w_in, w_out = 1.0 / e[inn] ** 2, 1.0 / e[out] ** 2
        din = np.average(f[inn], weights=w_in)
        dout = np.average(f[out], weights=w_out)
        sig = np.hypot(1.0 / np.sqrt(w_in.sum()), 1.0 / np.sqrt(w_out.sum()))
        return dout - din, (dout - din) / sig, int(inn.sum())

    obs = stat(0.0)
    if obs is None:
        return {"n_in": int((np.abs(ph) <= half).sum()), "depth": None, "z": None, "p_value": None}
    rng = np.random.default_rng(seed)
    nulls = []
    for s in rng.uniform(0, 1, n_shifts):
        if min(abs(s), 1 - abs(s)) < 2.5 * half or abs(abs(s) - 0.5) < 1.5 * half:
            continue
        r = stat(s)
        if r is not None:
            nulls.append(r[0])
    p = float((1 + np.sum(np.array(nulls) >= obs[0])) / (1 + len(nulls))) if nulls else None
    return {"n_in": obs[2], "depth": float(obs[0]), "z": float(obs[1]), "p_value": p}


def load_epoch_photometry(source_id):
    """TO BE WRITTEN ON RELEASE DAY (2 December 2026). Must return (t_mjd, flux, flux_err)
    for the Gaia G-band epoch photometry of `source_id`, with times converted from
    BJD(TCB) - 2455197.5 to MJD: mjd = t + 2455197.5 - 2400000.5 (TCB-TDB differences are
    seconds, negligible against eclipses of hours)."""
    raise NotImplementedError("Gaia DR4 epoch photometry layout is not public before release")


def build(root):
    eph = pd.read_csv(root / "data" / "processed" / "f13_ephemerides.csv")
    v = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv")[["TIC", "bls_duration"]].set_index("TIC")
    g = json.loads((root / "site" / "public" / "data" / "gaia_dr3.json").read_text(encoding="utf-8"))["stars"]
    out = []
    for _, r in eph[eph["status"] == "OK"].iterrows():
        tic = int(r["tic"])
        if tic not in v.index or not np.isfinite(r["period_sigma_days"]):
            continue
        ok, info = gaia_testable(float(r["period_days"]), float(r["period_sigma_days"]), float(r["t0_btjd"]),
                                 float(r["t0_sigma_min"]), float(v.loc[tic, "bls_duration"]))
        out.append(dict(info, tic=tic, gaia_source_id=(g.get(str(tic)) or {}).get("source_id"), period_days=float(r["period_days"]),
                        t0_btjd=float(r["t0_btjd"]), testable=ok))
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "release": "Gaia DR4, 2 December 2026",
            "criterion": "ephemeris timing error at both ends of the Gaia window below %.0f%% of the eclipse duration, and at least %.0f expected in-eclipse points at %d transits" %
                         (100 * MAX_TIMING_FRAC, MIN_EXPECTED_IN_ECLIPSE, TYPICAL_TRANSITS),
            "stars_with_precise_ephemeris": len(out), "testable": sum(o["testable"] for o in out),
            "stars": sorted(out, key=lambda o: (not o["testable"], o["timing_error_worst_days"]))}


def main():
    if len(sys.argv) < 2:
        print("Usage: py f21_gaia_dr4_ready.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    rep = build(root)
    path = root / "site" / "public" / "data" / "gaia_dr4_plan.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("%d stars have a precise ephemeris; %d are testable with a fixed-ephemeris Gaia fold" % (rep["stars_with_precise_ephemeris"], rep["testable"]))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
