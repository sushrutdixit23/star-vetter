"""Release-day runner for the Gaia DR4 fixed-ephemeris test (see f21_gaia_dr4_ready.py).

Gaia DR4 is due 2 December 2026. What is NOT known before release is how the epoch photometry is
delivered. This script therefore does not download anything: it reads epoch-photometry tables that
you have saved from the Gaia archive (one file per star, named by the Gaia source id, as CSV, ECSV,
a VOTable or FITS) and recognises the column layout of DR3 and the obvious variants. If the layout
is not recognised it stops and says which columns it found; it never guesses.

The decision rule is fixed here, before any DR4 data are seen:
  SUPPORTED     the in-eclipse points are fainter than the rest, z >= 3 and permutation p <= 0.01
  CONTRADICTED  the TESS eclipse depth would have been seen at z >= 5 with these Gaia errors, but the
                measured depth is below a quarter of it at 3 sigma (an eclipse on the TESS aperture that
                is absent on the Gaia target points to a blend)
  INCONCLUSIVE  everything else, including too few in-eclipse points. Silence is not evidence.

Epoch radial velocities (new in DR4) are tested for EVERY survivor that has a file <gaia_source_id>_rv.<ext>
in the same folder: a sinusoid at the TESS period with free phase, decided by a rule also fixed here
(see run_rv). A bright star that moves at the eclipse period carries the eclipses; one that stays still
while the eclipse is deep points to a blend.

Usage:  py f25_gaia_dr4_run.py <root> <folder_with_epoch_tables>
Writes: data/processed/f25_gaia_dr4_results.json
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import f21_gaia_dr4_ready as f21

Z_SUPPORT, P_SUPPORT = 3.0, 0.01
Z_POWER, FRACTION_ABSENT = 5.0, 0.25

# column names seen in Gaia epoch photometry (DR3 first), tried in order
TIME_COLS = ["g_transit_time", "time", "obs_time", "transit_time", "g_obs_time"]
FLUX_COLS = ["g_transit_flux", "flux", "g_flux", "phot_g_flux"]
ERR_COLS = ["g_transit_flux_error", "flux_error", "g_flux_error", "phot_g_flux_error"]
FLAG_COLS = ["variability_flag_g_reject", "rejected_by_variability", "rejected_by_photometry", "photometry_flag_noisy_data"]
TIME_OFFSET = f21.GAIA_TIME_OFFSET


class UnknownLayout(Exception):
    pass


def _pick(cols, names):
    low = {c.lower(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    return None


def read_table(path):
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".csv":
        return pd.read_csv(path, comment="#")
    from astropy.table import Table
    fmt = {".ecsv": "ascii.ecsv", ".vot": "votable", ".xml": "votable", ".fits": "fits"}.get(suf)
    if fmt is None:
        raise UnknownLayout("unsupported file type %s" % suf)
    return Table.read(path, format=fmt).to_pandas()


def epoch_arrays(df):
    """(t_mjd, flux, flux_err) from an epoch-photometry table, with flagged points removed.
    Times are taken as BJD(TCB) - 2455197.5 days, as in DR3; a table whose times look like full JDs or MJDs
    is converted by size so that a changed convention is caught instead of silently mis-folded."""
    t_c, f_c, e_c = _pick(df.columns, TIME_COLS), _pick(df.columns, FLUX_COLS), _pick(df.columns, ERR_COLS)
    if not (t_c and f_c and e_c):
        raise UnknownLayout("could not find time/flux/error columns; found: %s" % ", ".join(map(str, df.columns)))
    t = pd.to_numeric(df[t_c], errors="coerce").to_numpy(float)
    f = pd.to_numeric(df[f_c], errors="coerce").to_numpy(float)
    e = pd.to_numeric(df[e_c], errors="coerce").to_numpy(float)
    ok = np.isfinite(t) & np.isfinite(f) & np.isfinite(e) & (e > 0)
    for c in FLAG_COLS:
        col = _pick(df.columns, [c])
        if col is not None:
            ok &= ~df[col].astype(str).str.lower().isin(["true", "1", "1.0"]).to_numpy()
    t, f, e = t[ok], f[ok], e[ok]
    if not len(t):
        raise UnknownLayout("no usable rows after removing flagged and non-finite points")
    med = float(np.median(t))
    if 1000 < med < 5000:            # Gaia days from BJD - 2455197.5 (2014-2020 is about 0 to 2000)
        mjd = t + TIME_OFFSET - 2400000.5
    elif 50000 < med < 70000:        # already MJD
        mjd = t
    elif 2400000 < med < 2600000:    # full Julian date
        mjd = t - 2400000.5
    else:
        raise UnknownLayout("time column has an unexpected scale (median %g)" % med)
    return mjd, f, e


def decide(res, expected_depth_frac, flux, err):
    """Apply the fixed rule. `expected_depth_frac` is the TESS eclipse depth as a fraction of the flux."""
    if res.get("depth") is None:
        return "INCONCLUSIVE", "too few in-eclipse or out-of-eclipse points"
    if res["z"] >= Z_SUPPORT and res["p_value"] is not None and res["p_value"] <= P_SUPPORT:
        return "SUPPORTED", "in-eclipse points are fainter, z=%.1f p=%.3f" % (res["z"], res["p_value"])
    if expected_depth_frac and expected_depth_frac > 0:
        base = float(np.median(flux))
        expected = expected_depth_frac * base
        sigma = res["depth"] / res["z"] if res["z"] not in (0, None) and res["z"] != 0 else None
        if sigma is None or not np.isfinite(sigma) or sigma <= 0:
            sigma = float(np.median(err)) / np.sqrt(max(res["n_in"], 1))
        if expected / sigma >= Z_POWER and res["depth"] + 3 * sigma < FRACTION_ABSENT * expected:
            return "CONTRADICTED", "TESS depth would give z=%.1f here; measured depth is below a quarter of it" % (expected / sigma)
    return "INCONCLUSIVE", "no clear detection and no strong power to rule one out"


# ---------------------------------------------------------------------------------------------
# Epoch radial velocities (Gaia DR4 publishes them; DR3 gave only summaries). Same rule-first idea:
# fit a sinusoid AT THE TESS PERIOD with free phase (linear, so no ephemeris has to be carried back
# to 2014-2020), and decide with thresholds fixed here.
RV_TIME_COLS = ["rv_obs_time", "obs_time", "time", "transit_time", "rv_time", "epoch"]
RV_COLS = ["radial_velocity", "rv", "rv_obs", "vrad", "rv_value"]
RV_ERR_COLS = ["radial_velocity_error", "rv_error", "e_rv", "vrad_error", "rv_value_error"]
DCHI2_MOVES = 30.0          # constant vs sinusoid, 2 extra parameters: p about 3e-7
DCHI2_STATIC = 6.0
SUBSTELLAR_MSUN = 0.08
DEEP_ECLIPSE = 0.02


def rv_epoch_arrays(df):
    """(t_mjd, rv, rv_err) from an epoch radial-velocity table; same time conventions as the photometry."""
    t_c, v_c, e_c = _pick(df.columns, RV_TIME_COLS), _pick(df.columns, RV_COLS), _pick(df.columns, RV_ERR_COLS)
    if not (t_c and v_c and e_c):
        raise UnknownLayout("could not find time/rv/error columns; found: %s" % ", ".join(map(str, df.columns)))
    d = pd.DataFrame({"time": df[t_c], "flux": df[v_c], "flux_error": df[e_c]})
    return epoch_arrays(d)


def rv_sinusoid(t_mjd, v, ev, period):
    """Constant and free-phase sinusoid at `period`, both by weighted linear least squares."""
    t, v, ev = (np.asarray(x, float) for x in (t_mjd, v, ev))
    w = 1.0 / ev
    ph = 2 * np.pi * t / period
    A = np.vstack([np.ones_like(t), np.cos(ph), np.sin(ph)]).T
    co, *_ = np.linalg.lstsq(A * w[:, None], v * w, rcond=None)
    cov = np.linalg.inv((A * w[:, None]).T @ (A * w[:, None]))
    chi_sin = float(np.sum(((v - A @ co) / ev) ** 2))
    mean = float(np.average(v, weights=w ** 2))
    chi_const = float(np.sum(((v - mean) / ev) ** 2))
    k = float(np.hypot(co[1], co[2]))
    # propagate to K (delta method); at small K this is approximate, which only matters for the upper limit
    g = np.array([0.0, co[1] / max(k, 1e-9), co[2] / max(k, 1e-9)])
    sk = float(np.sqrt(max(g @ cov @ g, 0.0))) if k > 0 else float(np.sqrt(cov[1, 1]))
    return {"n": int(len(t)), "k_kms": k, "k_sigma_kms": sk, "gamma_kms": float(co[0]),
            "chi2_sinusoid": chi_sin, "chi2_constant": chi_const, "delta_chi2": chi_const - chi_sin}


def rv_decide(fit, period_days, m1_msun, depth, depth_ratio=None):
    import f28_physical as f28
    if fit["n"] < 5:
        return "INCONCLUSIVE", "fewer than 5 epochs"
    if fit["delta_chi2"] >= DCHI2_MOVES:
        return "MOVES", "the bright star moves at the TESS period (delta chi2 %.0f, K=%.1f km/s): eclipses on the target" % (fit["delta_chi2"], fit["k_kms"])
    if fit["delta_chi2"] <= DCHI2_STATIC:
        k_up = fit["k_kms"] + 3.0 * fit["k_sigma_kms"]
        m2 = f28.max_companion_mass(k_up, period_days, m1_msun)
        if m2 < SUBSTELLAR_MSUN:
            if depth_ratio is not None and depth_ratio >= 0.5:
                return "STATIC_OR_TWIN", "no motion (K < %.1f km/s), but near-equal eclipses allow blended twin lines" % k_up
            if depth is not None and depth >= DEEP_ECLIPSE:
                return "BLEND_INDICATED", "no motion (K < %.1f km/s, companion < %.3f Msun) yet a %.1f%% eclipse" % (k_up, m2, 100 * depth)
            return "SUBSTELLAR_OR_BLEND", "no motion (K < %.1f km/s, companion < %.3f Msun)" % (k_up, m2)
    return "INCONCLUSIVE", "neither clear motion nor a tight limit"


def run_rv(root, folder):
    """Epoch-RV test for every survivor with a file named <gaia_source_id>_rv.<ext> in `folder`."""
    root, folder = Path(root), Path(folder)
    sky = {int(r["tic"]): r for r in json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    g3 = json.loads((root / "site" / "public" / "data" / "gaia_dr3.json").read_text(encoding="utf-8"))["stars"]
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    cache = root / "data" / "processed" / "f27_cache"
    out = {}
    for tic, r in sorted(sky.items()):
        sid = (g3.get(str(tic)) or {}).get("source_id")
        if not sid:
            continue
        files = list(folder.glob("%d_rv.*" % int(sid)))
        if not files:
            continue
        try:
            t, v, ev = rv_epoch_arrays(read_table(files[0]))
        except UnknownLayout as ex:
            out[str(tic)] = {"verdict": "UNKNOWN_LAYOUT", "gaia_source_id": int(sid), "detail": str(ex)}
            continue
        P = float(r["period_days"])
        fit = rv_sinusoid(t, v, ev, P)
        m1 = 1.0
        cp = cache / ("TIC%d.json" % tic)
        if cp.exists():
            ap = (json.loads(cp.read_text(encoding="utf-8")).get("gaia") or {}).get("ap") or {}
            m1 = float(ap.get("mass_flame") or 1.0)
        depth = float(vet.loc[tic, "bls_depth"]) if tic in vet.index else None
        sd = float(vet.loc[tic, "secondary_depth"]) if tic in vet.index and np.isfinite(vet.loc[tic, "secondary_depth"]) else None
        ratio = sd / depth if (sd is not None and depth) else None
        verdict, why = rv_decide(fit, P, m1, depth, ratio)
        out[str(tic)] = {"verdict": verdict, "why": why, "gaia_source_id": int(sid), "period_days": P, **fit}
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule": "Sinusoid at the TESS period, free phase. MOVES: delta chi2 >= %.0f. If delta chi2 <= %.0f and the companion mass "
                    "allowed by K + 3 sigma is below %.2f Msun: BLEND_INDICATED for eclipses >= %.0f%% deep (unless near-equal eclipses: "
                    "STATIC_OR_TWIN), otherwise SUBSTELLAR_OR_BLEND. Otherwise INCONCLUSIVE." % (DCHI2_MOVES, DCHI2_STATIC, SUBSTELLAR_MSUN, 100 * DEEP_ECLIPSE),
            "stars": out}


def run(root, folder):
    root, folder = Path(root), Path(folder)
    plan = json.loads((root / "site" / "public" / "data" / "gaia_dr4_plan.json").read_text(encoding="utf-8"))
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    eph = pd.read_csv(root / "data" / "processed" / "f13_ephemerides.csv").set_index("tic")
    out = {}
    for s in plan["stars"]:
        if not s["testable"] or not s.get("gaia_source_id"):
            continue
        tic, sid = s["tic"], int(s["gaia_source_id"])
        files = [p for p in folder.glob("%d.*" % sid)]
        if not files:
            out[str(tic)] = {"verdict": "NO_FILE", "gaia_source_id": sid}
            continue
        try:
            t, f, e = epoch_arrays(read_table(files[0]))
        except UnknownLayout as ex:
            out[str(tic)] = {"verdict": "UNKNOWN_LAYOUT", "gaia_source_id": sid, "detail": str(ex)}
            continue
        t0_mjd = float(s["t0_btjd"]) + f21.BTJD_TO_MJD
        res = f21.fold_test(t, f, e, float(s["period_days"]), t0_mjd, float(s["duration_days"]))
        depth_frac = None
        if tic in vet.index and "bls_depth" in vet.columns and np.isfinite(vet.loc[tic, "bls_depth"]):
            depth_frac = float(vet.loc[tic, "bls_depth"])
        verdict, why = decide(res, depth_frac, f, e)
        out[str(tic)] = {"verdict": verdict, "why": why, "gaia_source_id": sid, "n_points": int(len(t)),
                         "tess_depth_fraction": depth_frac, **res}
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule": "SUPPORTED: z>=%.0f and p<=%.2f. CONTRADICTED: TESS depth detectable at z>=%.0f but measured depth < %.0f%% of it at 3 sigma. "
                    "Otherwise INCONCLUSIVE." % (Z_SUPPORT, P_SUPPORT, Z_POWER, 100 * FRACTION_ABSENT),
            "stars": out}


def main():
    if len(sys.argv) < 3:
        print("Usage: py f25_gaia_dr4_run.py <project_root> <folder_with_epoch_tables>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    rep = run(root, sys.argv[2])
    rv = run_rv(root, sys.argv[2])
    rep["epoch_rv"] = rv
    path = root / "data" / "processed" / "f25_gaia_dr4_results.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    for name, block in (("photometry", rep["stars"]), ("epoch RV", rv["stars"])):
        counts = {}
        for v in block.values():
            counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        print(name, counts)
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
