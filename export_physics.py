"""Figure data for the Physics page (site/public/data/physics.json).

For every star with a physical-model fit (f26_ebfit.json) and for the AI Phe validation target this
rebuilds the exact binned data the fit used, takes the fitted parameters as a starting point for a short
bounded least-squares polish (so the drawn model is a best-fit curve, not a curve through posterior
medians that can sit off the data when parameters are correlated), and writes:

  - the phase-folded data, binned for display (inverse-variance means, finer inside the eclipses),
  - the best-fit ellc model on a phase grid that is fine inside the eclipses,
  - the binned residuals and their rms,
  - the secondary-eclipse phase implied by (e, omega), computed from Kepler's equation and checked
    against the minimum of the ellc curve, so the page's orbit animation uses the same convention,
  - the Gaia radial-velocity population (depth against velocity range, with the f28 verdict),
  - the total-mass consistency points.

Nothing here is fitted for show: the same data, model and priors as f26, only the plotting bins differ.

Usage:  python export_physics.py <root>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import f26_ebfit as f26

PHASE_LO, PHASE_HI = -0.25, 0.75
MODEL_STEP_OUT = 0.006            # model grid step outside the eclipses (phase)
DISPLAY_STEP_OUT = 0.012          # display-bin width outside the eclipses (phase)
EDGE_TOLERANCE = 0.012            # allowed disagreement between Kepler and ellc secondary phase


# ---------------------------------------------------------------- orbit geometry (mirrored in the page)

def kepler_E(M, e):
    M = np.mod(M, 2 * np.pi)
    E = M + e * np.sin(M) if e < 0.8 else np.pi * np.ones_like(M)
    for _ in range(60):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    return E


def true_anomaly(M, e):
    E = kepler_E(np.asarray(M, float), e)
    return 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))


def mean_anomaly(nu, e):
    E = 2 * np.arctan2(np.sqrt(1 - e) * np.sin(nu / 2), np.sqrt(1 + e) * np.cos(nu / 2))
    return E - e * np.sin(E)


def secondary_phase_kepler(e, omega):
    """Phase of mid-secondary-eclipse when mid-primary is phase 0. Primary: true anomaly + omega = 90 deg."""
    m1 = mean_anomaly(np.pi / 2 - omega, e)
    m2 = mean_anomaly(3 * np.pi / 2 - omega, e)
    return float(np.mod((m2 - m1) / (2 * np.pi), 1.0))


def sky_position(phase, e, omega, incl_deg):
    """Star 2 relative to star 1, in units of the semi-major axis: (x, y) on the sky and z toward the
    observer (z > 0 means star 2 is in front, i.e. star 1 is being eclipsed)."""
    m = mean_anomaly(np.pi / 2 - omega, e) + 2 * np.pi * np.asarray(phase, float)
    nu = true_anomaly(m, e)
    r = (1 - e * e) / (1 + e * np.cos(nu))
    u = nu + omega
    i = np.radians(incl_deg)
    return r * np.cos(u), r * np.sin(u) * np.cos(i), r * np.sin(u) * np.sin(i)


# ---------------------------------------------------------------- the fitted data and model

def _round(a, n=5):
    return [round(float(x), n) for x in a]


def display_edges(dur_phase, sec_phase):
    win = 1.6 * dur_phase
    fine_w = max(dur_phase / 26.0, 0.0008)
    centres = (0.0, sec_phase)
    coarse = [x for x in np.arange(PHASE_LO, PHASE_HI + 1e-9, DISPLAY_STEP_OUT) if all(abs(x - c) >= win for c in centres)]
    fine = [x for c in centres for x in np.arange(c - win, c + win + 1e-9, fine_w)]
    return np.array(sorted(set(np.round(coarse + fine, 6))))


def model_grid(dur_phase, sec_phase):
    win = 2.0 * dur_phase
    fine = max(dur_phase / 70.0, 0.0004)
    pts = list(np.arange(PHASE_LO, PHASE_HI + 1e-9, MODEL_STEP_OUT))
    for c in (0.0, sec_phase):
        pts += list(np.arange(c - win, c + win + 1e-9, fine))
    return np.array(sorted(set(np.round(pts, 6))))


def theta_from_summary(res, period_in, t0_in, truth=None):
    p = res["params"]
    e = p["e"]["median"]
    w = np.radians(p["omega_deg"]["median"])
    x = np.zeros(len(f26.PARAMS))
    P = f26.PARAMS
    x[P.index("dt0")] = res.get("t0_btjd", t0_in) - t0_in
    x[P.index("rsum")] = p["rsum"]["median"]
    x[P.index("k")] = p["k"]["median"]
    x[P.index("cosi")] = np.cos(np.radians(p["incl"]["median"]))
    x[P.index("J")] = p["J"]["median"]
    x[P.index("fc")] = np.sqrt(e) * np.cos(w)
    x[P.index("fs")] = np.sqrt(e) * np.sin(w)
    x[P.index("l3")] = p["l3"]["median"]
    x[P.index("u1")] = f26.U1_PRIOR[0]
    x[P.index("u1b")] = f26.U1_PRIOR[0]
    x[P.index("dP")] = res.get("period_days", period_in) - period_in
    return x


def _binned(groups, theta, period_in, t0_in, dur_phase, noise0):
    """Display bins of the data and of the model at the data's own phases, for one parameter vector."""
    pb = f26.unpack(theta, t0_in)
    ph_all, y_all, e_all, m_all = [], [], [], []
    for g in groups:
        m = f26.ellc_lc(g["t"], pb, period_in, g["t_exp"], g["n_int"], g.get("cycle", 0.0))
        w = 1.0 / g["e"] ** 2
        norm = float(np.sum(w * g["y"] * m) / np.sum(w * m * m))
        shift = (pb["dt0"] + g.get("cycle", 0.0) * pb["dP"]) / period_in
        ph = (g["t"] - t0_in) / period_in - shift
        ph = np.where(ph > PHASE_HI, ph - 1.0, ph)
        ph = np.where(ph < PHASE_LO, ph + 1.0, ph)
        ph_all.append(ph)
        y_all.append(g["y"] / norm)
        e_all.append(g["e"] / norm)
        m_all.append(m)
    ph, y, e, m = (np.concatenate(a) for a in (ph_all, y_all, e_all, m_all))
    ecw = (pb["fc"] ** 2 + pb["fs"] ** 2) * np.cos(np.arctan2(pb["fs"], pb["fc"]))
    sec_phase = (0.5 + 2.0 * ecw / np.pi) % 1.0
    if sec_phase > 0.75:
        sec_phase -= 1.0
    edges = display_edges(dur_phase, sec_phase)
    idx = np.digitize(ph, edges)
    bx, by, be, bm = [], [], [], []
    for b in np.unique(idx):
        mm = idx == b
        if mm.sum() < 2 and not (len(ph) < 400):
            continue
        w = 1.0 / np.maximum(e[mm], 1e-9) ** 2
        bx.append(float(np.sum(w * ph[mm]) / np.sum(w)))
        by.append(float(np.sum(w * y[mm]) / np.sum(w)))
        bm.append(float(np.sum(w * m[mm]) / np.sum(w)))
        be.append(float(noise0 / np.sqrt(np.sum(w))))
    order = np.argsort(bx)
    return tuple(np.array(a)[order] for a in (bx, by, be, bm)), sec_phase


def _model_curve(theta, groups, period_in, t0_in, dur_phase, sec_phase):
    pb = f26.unpack(theta, t0_in)
    dom = max(groups, key=lambda g: len(g["y"]))
    grid = model_grid(dur_phase, sec_phase)
    p0 = dict(pb)
    p0["t0"] = t0_in
    p0["dP"] = 0.0
    return grid, f26.ellc_lc(t0_in + grid * period_in, p0, period_in, dom["t_exp"], dom["n_int"], 0.0)


def _chi2(theta, groups, period_in, t0_in):
    r = f26.residuals(theta, groups, period_in, t0_in)
    return float(np.sum(r[:-3] ** 2))


def refit_published(groups, period_in, t0_in, truth, x_ours):
    """Hold the geometry at the published values and refit only the nuisance parameters (surface-brightness
    ratio, third light, limb darkening, timing). If the published geometry then fits the data as well as ours,
    the two solutions are the same solution."""
    from scipy.optimize import least_squares
    P = f26.PARAMS
    e = float(np.hypot(truth["ecosw"], truth["esinw"]))
    w = float(np.arctan2(truth["esinw"], truth["ecosw"]))
    base = np.array(x_ours, float)
    base[P.index("rsum")] = truth["r1"] + truth["r2"]
    base[P.index("k")] = truth["r2"] / truth["r1"]
    base[P.index("cosi")] = float(np.cos(np.radians(truth["incl"])))
    base[P.index("fc")] = float(np.sqrt(e) * np.cos(w))
    base[P.index("fs")] = float(np.sqrt(e) * np.sin(w))
    free = [P.index(k) for k in ("dt0", "J", "l3", "u1", "u1b", "dP")]
    xs = np.array([1e-3, 0.1, 0.05, 0.1, 0.1, 1e-5])

    def fun(z):
        x = base.copy()
        x[free] = z
        return f26.residuals(x, groups, period_in, t0_in)

    lo, hi = f26.LOWER[free] + 1e-9, f26.UPPER[free] - 1e-9
    r = least_squares(fun, np.clip(base[free], lo, hi), bounds=(lo, hi), x_scale=xs, max_nfev=300)
    x = base.copy()
    x[free] = r.x
    return x


def figure_for(t, f, s, period_in, t0_in, res, published_truth=None):
    """Display data and best-fit model for one star. `res` is an OK entry of f26_ebfit.json (or the
    equivalent built for AI Phe)."""
    from scipy.optimize import least_squares
    p = res["params"]
    ecosw = p["ecosw"]["median"]
    dur = res["duration_used_days"]
    sec_guess = (0.5 + 2.0 * ecosw / np.pi) % 1.0
    td, fd, sd = f26.detrend_local(t, f, period_in, t0_in, dur, sec_guess, s)
    groups = f26.bin_groups(td, fd, sd, period_in, t0_in, dur, sec_guess)
    x0 = theta_from_summary(res, period_in, t0_in)
    x0 = np.clip(x0, f26.LOWER + 1e-9, f26.UPPER - 1e-9)
    xs = np.array([1e-3, 1e-2, 0.1, 1e-2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.1, 1e-5])
    r = least_squares(f26.residuals, x0, bounds=(f26.LOWER, f26.UPPER), args=(groups, period_in, t0_in), x_scale=xs, max_nfev=250)
    r0 = f26.residuals(x0, groups, period_in, t0_in)
    best = r.x if r.cost <= 0.5 * float(np.sum(r0 ** 2)) else x0
    pb = f26.unpack(best, t0_in)
    dur_phase = dur / period_in
    noise0 = float(res["noise_scale"][0])
    (bx, by, be, bm), sec_phase = _binned(groups, best, period_in, t0_in, dur_phase, noise0)
    grid, mg = _model_curve(best, groups, period_in, t0_in, dur_phase, sec_phase)
    amin = float(np.min(mg))
    sec_model = None
    sel = (grid > sec_phase - 1.5 * dur_phase) & (grid < sec_phase + 1.5 * dur_phase)
    if sel.any():
        sec_model = float(grid[sel][np.argmin(mg[sel])])
    e_fit = pb["fc"] ** 2 + pb["fs"] ** 2
    omega = float(np.arctan2(pb["fs"], pb["fc"]))
    sec_kepler = secondary_phase_kepler(e_fit, omega)
    if sec_kepler > 0.75:
        sec_kepler -= 1.0
    rms = float(np.sqrt(np.mean((by - bm) ** 2)))
    out = {
        "period_days": float(period_in + pb["dP"]),
        "t0_btjd": float(t0_in + pb["dt0"]),
        "cadence_min": int(max(groups, key=lambda g: len(g["y"]))["cadence_min"]),
        "n_display_bins": int(len(bx)),
        "n_fit_bins": int(sum(len(g["y"]) for g in groups)),
        "sectors": sorted({int(x) for g in groups for x in g["sectors"]}),
        "duration_phase": round(dur_phase, 5),
        "best_fit": {"rsum": float(pb["rsum"]), "k": float(pb["k"]), "incl": float(np.degrees(np.arccos(pb["cosi"]))),
                     "J": float(pb["J"]), "e": float(e_fit), "omega_deg": float(np.degrees(omega) % 360.0), "l3": float(pb["l3"])},
        "secondary_phase_kepler": round(sec_kepler, 5),
        "secondary_phase_ellc": None if sec_model is None else round(sec_model, 5),
        "min_flux": round(amin, 5),
        "rms_resid_ppt": round(rms * 1000.0, 3),
        "data": {"x": _round(bx), "y": _round(by, 6), "e": _round(be, 6)},
        "residual": _round(by - bm, 6),
        "model": {"x": _round(grid), "y": _round(mg, 6)},
        "_sec_ok": (sec_model is None) or abs(sec_model - sec_kepler) < EDGE_TOLERANCE or e_fit < 0.03,
    }
    if published_truth is not None:
        xp = refit_published(groups, period_in, t0_in, published_truth, best)
        (px, py, pe, pm), psec = _binned(groups, xp, period_in, t0_in, dur_phase, noise0)
        pgrid, pmg = _model_curve(xp, groups, period_in, t0_in, dur_phase, psec)
        pp = dict(zip(f26.PARAMS, xp))
        out["published_refit"] = {
            "model": {"x": _round(pgrid), "y": _round(pmg, 6)},
            "rms_resid_ppt": round(float(np.sqrt(np.mean((py - pm) ** 2))) * 1000.0, 3),
            "chi2": _chi2(xp, groups, period_in, t0_in), "chi2_ours": _chi2(best, groups, period_in, t0_in),
            "n_bins": out["n_fit_bins"], "J": float(pp["J"]), "l3": float(pp["l3"]),
            "refitted": ["surface-brightness ratio", "third light", "limb darkening", "timing"],
        }
    return out



def _q3(d, nd=4):
    return {"median": round(float(d["median"]), nd), "lo": round(float(d["lo"]), nd), "hi": round(float(d["hi"]), nd)}


def validation_extras(root):
    """Blind benchmarks (f29), injection-recovery (f30), chain convergence before/after, and the mass-method
    calibration (f31), trimmed for the page. Each is skipped if its file is missing."""
    proc = root / "data" / "processed"
    out = {}
    p = proc / "f29_benchmarks.json"
    if p.exists():
        b = json.loads(p.read_text(encoding="utf-8"))
        rows = []
        for r in b["rows"]:
            row = {"name": r["name"], "tic": r["tic"], "cadence_min": r["cadence_min"], "status": r.get("status"), "passed": bool(r.get("passed")),
                   "reference": r.get("reference"), "truth": r["truth"]}
            if r.get("status") == "OK":
                row.update({"checks": r["checks"], "differences": {k: round(float(v), 4) for k, v in r["differences"].items()},
                            "fit": {k: _q3(r["fit"][k]) for k in ("e", "esinw", "ecosw", "r1", "r2", "incl", "l3")},
                            "trusted": bool(r.get("trusted")), "converged": bool(r["run"]["converged"]), "steps": int(r["run"]["steps"]),
                            "f22_verdict": (r.get("inputs") or {}).get("f22", {}).get("verdict")})
            rows.append(row)
        out["benchmarks"] = {"rows": rows, "pass_rule": b["pass_rule"], "summary": b["summary"], "preregistration": b["preregistration"]}
    p = proc / "f30_injection.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        pts = []
        for r in d["rows"]:
            if r.get("status") != "OK":
                continue
            pts.append({"host": r["host"], "i": r["index"], "trusted": bool(r.get("trusted")), "converged": bool(r.get("converged")),
                        "t": {k: round(float(r["truth"][k]), 4) for k in ("e", "ecosw", "r1", "r2", "rsum", "incl")},
                        "f": {k: _q3(r["fit"][k]) for k in ("e", "ecosw", "r1", "r2", "incl")}, "rsum_fit": round(float(r["fit"]["rsum"]["median"]), 4)})
        out["injection"] = {"overall": d["overall"], "by_host": d["by_host"], "points": pts, "e_good_definition": d["e_good_definition"],
                            "n_rows": len(d["rows"])}
    old_p, new_p = proc / "f26_ebfit_1500steps.json", proc / "f26_ebfit.json"
    if old_p.exists() and new_p.exists():
        old = json.loads(old_p.read_text(encoding="utf-8"))["stars"]
        new = json.loads(new_p.read_text(encoding="utf-8"))["stars"]
        conv = []
        for tic, n in new.items():
            o = old.get(tic)
            if not o or n.get("status") != "OK" or o.get("status") != "OK":
                continue
            conv.append({"tic": int(tic), "before": _q3(o["params"]["e"]), "after": _q3(n["params"]["e"]), "steps_before": int(o["steps"]),
                         "steps_after": int(n["steps"]), "converged_after": bool(n["converged"]),
                         "tau_after": round(float(n["autocorr_steps"] or 0), 1),
                         "rsum_after": round(float(n["params"]["rsum"]["median"]), 4)})
        out["convergence"] = sorted(conv, key=lambda r: r["tic"])
    p = proc / "f31_mass_calibration.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        out["mass_calibration"] = {"rows": [{k: r.get(k) for k in ("name", "status", "R1_ratio", "mass_ratio", "gaia_radius_flame", "R1_from_gaia",
                                                                    "kepler_mass_from_gaia", "published_total_mass", "ruwe", "non_single_star")}
                                            | {"ms_ratio_gaia": (r.get("ms_check_on_gaia_inputs") or {}).get("ms_ratio"),
                                               "ms_ratio_true": (r.get("ms_check_on_true_mass_and_radius") or {}).get("ms_ratio"),
                                               "published": r.get("published")}
                                            for r in d["rows"]], "summary": d["summary"]}
    return out

def main():
    root = Path(sys.argv[1]).resolve()
    t_start = time.time()
    fits = json.loads((root / "data" / "processed" / "f26_ebfit.json").read_text(encoding="utf-8"))["stars"]
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    sky = {int(r["tic"]): r for r in json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    phys = json.loads((root / "data" / "processed" / "f28_physical.json").read_text(encoding="utf-8"))

    stars = {}
    for tic, res in sorted(fits.items(), key=lambda kv: int(kv[0])):
        if res.get("status") != "OK":
            continue
        tic_i = int(tic)
        v = vet.loc[tic_i]
        period_in, t0_in = res["period_input_days"], float(v["bls_t0"])
        t, f, s = f26.load_star(root, tic_i)
        fig = figure_for(t, f, s, period_in, t0_in, res)
        fig["tic"] = tic_i
        fig["depth_pct"] = round(float(v["bls_depth"]) * 100.0, 3) if np.isfinite(v["bls_depth"]) else None
        stars[tic] = fig
        print("TIC %s: bins=%d rms=%.2f ppt  sec Kepler=%.4f ellc=%s  ok=%s" % (
            tic, fig["n_display_bins"], fig["rms_resid_ppt"], fig["secondary_phase_kepler"], fig["secondary_phase_ellc"], fig["_sec_ok"]), flush=True)

    # AI Phe, 2-minute validation fit
    val = json.loads((root / "data" / "processed" / "f26_validation.json").read_text(encoding="utf-8"))
    v2 = [x for x in val if x.get("cadence_min") == 2][0]
    z = np.load(root / "data" / "processed" / "f13_lc_cache_validation" / "TIC102069549.npz")
    ok = np.isfinite(z["t"]) & np.isfinite(z["f"])
    t, f, s = z["t"][ok].astype(float), z["f"][ok].astype(float), z["sector"][ok]
    fit = {k: (x["median"] if isinstance(x, dict) else x) for k, x in v2["fit"].items()}    # f26_validation keeps summaries
    omega = float(np.degrees(np.arctan2(fit["esinw"], fit["ecosw"])) % 360.0)
    res_ai = {"params": {"e": {"median": fit["e"]}, "omega_deg": {"median": omega}, "ecosw": {"median": fit["ecosw"]},
                         "rsum": {"median": fit["r1"] + fit["r2"]}, "k": {"median": fit["r2"] / fit["r1"]},
                         "incl": {"median": fit["incl"]}, "J": {"median": fit["J"]}, "l3": {"median": fit["l3"]}},
              "duration_used_days": 0.45, "noise_scale": [1.0], "t0_btjd": f26.AI_PHE["t0_btjd"], "period_days": f26.AI_PHE["period"]}
    ai = figure_for(t, f, s, f26.AI_PHE["period"], f26.AI_PHE["t0_btjd"], res_ai, published_truth=f26.AI_PHE["truth"])
    ai["published_model"] = ai["published_refit"]["model"]
    ai["truth"] = f26.AI_PHE["truth"]
    ai["fit_summary"] = fit
    ai["checks"] = v2["checks"]
    ai["tolerance"] = v2["tolerance"]
    v30 = [x for x in val if x.get("cadence_min") == 30]
    if v30:
        ai["cadence30"] = {"fit": {k: (x["median"] if isinstance(x, dict) else x) for k, x in v30[0]["fit"].items()},
                           "checks": v30[0]["checks"], "passed": v30[0]["passed"]}
    ai["passed"] = v2["passed"]
    ai["reference"] = v2["reference"]
    print("AI Phe: bins=%d rms=%.2f ppt sec Kepler=%.4f ellc=%s" % (ai["n_display_bins"], ai["rms_resid_ppt"], ai["secondary_phase_kepler"], ai["secondary_phase_ellc"]))

    # population of stars with a Gaia RV range
    pop = []
    for tic, rec in phys["stars"].items():
        g = rec.get("gaia_rv")
        if not g or g.get("amplitude_kms") is None or int(tic) not in vet.index:
            continue
        dep = vet.loc[int(tic)]["bls_depth"]
        if not np.isfinite(dep):
            continue
        verdict = "moves" if g.get("moves") else str(g.get("static_star_verdict") or "consistent").lower()
        pop.append({"tic": int(tic), "period_days": round(float(rec["period_days"]), 4), "depth_pct": round(float(dep) * 100, 3),
                    "rv_range_kms": round(float(g["amplitude_kms"]), 2), "k1_lower_kms": round(float(g.get("k1_lower_kms") or 0.0), 2),
                    "n_transits": int(g.get("n_transits") or 0), "verdict": verdict})
    mass = []
    for tic, rec in phys["stars"].items():
        sc = rec.get("scale")
        if sc and sc.get("ms_ratio") is not None:
            mass.append({"tic": int(tic), "ratio": round(float(sc["ms_ratio"]), 3), "rel_sigma": round(float(sc.get("total_mass_rel_sigma") or 0), 3),
                         "consistent": bool(sc.get("ms_consistent")), "basis": sc.get("ms_basis")})

    for d in list(stars.values()) + [ai]:
        d.pop("_sec_ok", None)
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "Display bins and best-fit curves for the physical-model page. Same data, model and priors as f26_ebfit.py; the curves are a bounded least-squares polish started at the posterior medians.",
           "stars": stars, "ai_phe": ai, "rv_population": sorted(pop, key=lambda r: r["tic"]), "mass_check_points": sorted(mass, key=lambda r: r["tic"]),
           **validation_extras(root)}
    dst = root / "site" / "public" / "data" / "physics.json"
    dst.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print("wrote %s (%.0f kB) in %.0f s" % (dst, dst.stat().st_size / 1024, time.time() - t_start))


if __name__ == "__main__":
    main()
