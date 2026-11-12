"""Physical parameters from photometry plus archival spectroscopy (no new telescope time).

Combines, per star:
  * the light-curve model (f26): r1, r2, i, e, omega, light ratio;
  * Gaia DR3 radius (FLAME, else GSP-Phot) of the combined light;
  * Gaia DR3 spectroscopic orbits (nss_two_body_orbit), compared with the photometric orbit;
  * Gaia DR3 rv_amplitude_robust, turned into a LOWER limit on the semi-amplitude K1;
  * APOGEE DR17 visit velocities, fitted for K1 and gamma at the photometric ephemeris.

What comes out and how much to trust it:
  1. Orbit check (Gaia SB1 vs light curve): period ratio, e, omega. A spectroscopic orbit that agrees
     is independent evidence that the eclipsing binary IS the bright Gaia star.
  2. RV evidence: a peak-to-peak velocity well above the noise means the bright star moves, i.e. the
     eclipses are very probably on the target, not on a faint blended neighbour.
  2b. A star that does NOT move (small range over >= 10 Gaia transits) gives an upper limit on K1 and so on
     the companion mass. If that limit is substellar while the eclipse is deep (>= 2%), the eclipses very
     probably come from another star in the aperture (BLEND_INDICATED); a shallow eclipse could instead be
     a substellar companion (SUBSTELLAR_OR_BLEND). Near-equal eclipses (secondary at least half the primary
     depth) get STATIC_OR_TWIN instead: two similar stars blend their lines and can look static to Gaia.
  3. Total mass from Kepler's third law, a = R1 / r1 with R1 from the Gaia radius corrected for the
     companion's light. MODEL-DEPENDENT: Gaia's radius assumes a single star, and the light split uses
     the TESS-band ratio as if it were bolometric. Reported as an estimate with that caveat; a value far
     outside 0.3-8 Msun is a warning that the eclipses are not on the Gaia star (or the radius is wrong).
  4. With a fitted K1 and the total mass, the two masses follow (also model-dependent through the radius).

Usage:  python f28_physical.py <root>
Writes: data/processed/f28_physical.json
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

G_SI = 6.67430e-11
MSUN = 1.98847e30
RSUN = 6.957e8
AU = 1.495978707e11
DAY = 86400.0
YEAR_DAYS = 365.25

# Approximate Gaia DR3 per-transit RV precision against G_RVS (Katz et al. 2023, A&A 674, A5, fig. of
# epoch precision; rounded). Used only to decide how much of a peak-to-peak range noise alone can make.
RVS_EPOCH_SIGMA = [(6.0, 0.4), (9.0, 0.9), (10.0, 1.5), (11.0, 3.0), (12.0, 6.0), (12.7, 9.0)]
NOISE_RANGE_SIGMAS = 5.0        # peak-to-peak of ~20 Gaussian epochs rarely exceeds 5 sigma
APOGEE_FLOOR_KMS = 0.5          # added in quadrature to the APOGEE visit errors


def epoch_sigma(grvs):
    xs, ys = zip(*RVS_EPOCH_SIGMA)
    return float(np.interp(grvs, xs, ys)) if grvs is not None and np.isfinite(grvs) else None


def k_lower_from_amplitude(amp, grvs):
    """Lower limit on K1 (km/s) from Gaia's peak-to-peak epoch RV range: the noise contribution
    (5 sigma of the per-transit precision) is removed before halving. None when no information."""
    if amp is None or not np.isfinite(amp):
        return None, None
    sig = epoch_sigma(grvs)
    if sig is None:
        return None, None
    return float(max(0.0, amp - NOISE_RANGE_SIGMAS * sig) / 2.0), sig


SINUSOID_COVERAGE = 0.9         # with >= 10 random phases, the sampled range of a sinusoid is >= 1.8 K (rarely less)
MIN_TRANSITS_FOR_UPPER = 10
SUBSTELLAR_MSUN = 0.08
DEEP_ECLIPSE = 0.02
TWIN_DEPTH_RATIO = 0.5          # secondary at least half the primary depth: similar stars, lines may blend


def k_upper_from_amplitude(amp, grvs, n_transits):
    """Upper limit on K1 (km/s) for a star whose epoch RVs barely change: with many random phases the
    observed range covers at least 2 * 0.9 K, so K <= (range + 2 sigma) / 1.8."""
    if amp is None or not np.isfinite(amp) or not n_transits or n_transits < MIN_TRANSITS_FOR_UPPER:
        return None
    sig = epoch_sigma(grvs) or 0.0
    return float((amp + 2.0 * sig) / (2.0 * SINUSOID_COVERAGE))


def max_companion_mass(k_up, period_days, m1, sini=1.0):
    """Largest m2 allowed by K1 <= k_up (circular orbit, which gives the largest m2 for a given K)."""
    return min_companion_mass(mass_function(k_up, period_days, 0.0), m1, sini)


def mass_function(k_kms, period_days, e=0.0):
    """f(M) = (1 - e^2)^1.5 K^3 P / (2 pi G), in Msun."""
    k = k_kms * 1e3
    return float((1 - e * e) ** 1.5 * k ** 3 * period_days * DAY / (2 * np.pi * G_SI) / MSUN)


def min_companion_mass(fm, m1, sini=1.0):
    """Smallest m2 with (m2 sin i)^3 / (m1 + m2)^2 = f(M), by bisection."""
    lo, hi = 0.0, 200.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (mid * sini) ** 3 / (m1 + mid) ** 2 < fm:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


R1_SYSTEMATIC = 0.10
MS_RATIO_RANGE = (0.6, 1.6)


def main_sequence_check(m_kepler, r1_rsun, light_ratio, m1_flame=None):
    """Does the Kepler total mass fit two main-sequence stars? Primary mass from Gaia FLAME when given,
    else M = R^(1/0.8) (dwarfs); mass ratio from the TESS light ratio as L ~ M^4. Crude by design: a ratio far
    from 1 means the radius, the light split or the fractional radii are biased, not new physics."""
    if r1_rsun is None or not np.isfinite(r1_rsun):
        return {}
    if m1_flame:
        m1, how = float(m1_flame), "Gaia FLAME mass"
    elif r1_rsun < 1.5:
        m1, how = float(r1_rsun ** (1 / 0.8)), "main-sequence mass from the radius"
    else:
        return {"ms_check": "not applied (primary larger than 1.5 Rsun, may be evolved)"}
    q = float(max(light_ratio, 0.0) ** 0.25)
    expect = m1 * (1 + q)
    ratio = m_kepler / expect
    return {"ms_expected_total_msun": expect, "ms_ratio": ratio, "ms_basis": how,
            "ms_consistent": bool(MS_RATIO_RANGE[0] <= ratio <= MS_RATIO_RANGE[1])}


def total_mass(a_rsun, period_days):
    return float((a_rsun * RSUN / AU) ** 3 / (period_days / YEAR_DAYS) ** 2)


def rv_shape(t_bjd, period, t0_bjd, e, omega_rad):
    """g(t) with v1(t) = gamma + K1 g(t); g = cos(nu + omega) + e cos(omega).
    Primary eclipse (star 1 behind star 2) is at nu = pi/2 - omega."""
    nu_ecl = np.pi / 2 - omega_rad
    E_ecl = 2 * np.arctan(np.sqrt((1 - e) / (1 + e)) * np.tan(nu_ecl / 2))
    M_ecl = E_ecl - e * np.sin(E_ecl)
    M = M_ecl + 2 * np.pi * (np.asarray(t_bjd, float) - t0_bjd) / period
    E = M.copy()
    for _ in range(60):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    return np.cos(nu + omega_rad) + e * np.cos(omega_rad)


def fit_k_gamma(t_bjd, v, ev, period, t0_bjd, e, omega_rad):
    """Linear least squares for (gamma, K1) at a fixed orbit. K1 < 0 means the measured lines move
    like star 2 (the star eclipsed at the secondary), not star 1."""
    g = rv_shape(t_bjd, period, t0_bjd, e, omega_rad)
    A = np.vstack([np.ones_like(g), g]).T
    w = 1.0 / np.asarray(ev, float)
    co, *_ = np.linalg.lstsq(A * w[:, None], np.asarray(v, float) * w, rcond=None)
    cov = np.linalg.inv((A * w[:, None]).T @ (A * w[:, None]))
    resid = (np.asarray(v) - A @ co) / np.asarray(ev)
    chi2 = float(np.sum(resid ** 2))
    const = float(np.sum(((np.asarray(v) - np.average(v, weights=w ** 2)) / np.asarray(ev)) ** 2))
    return {"gamma_kms": float(co[0]), "k1_kms": float(co[1]), "k1_sigma_kms": float(np.sqrt(cov[1, 1])),
            "chi2": chi2, "dof": int(len(v) - 2), "chi2_constant": const, "n": int(len(v))}


def apogee_visits(rec):
    rows = (rec.get("surveys", {}).get("apogee_dr17") or {}).get("III_286_allvis") or []
    out = []
    for r in rows:
        if r.get("JD") is None or r.get("VHelio") is None:
            continue
        ev = r.get("e_RV")
        if ev is None or not np.isfinite(ev) or ev <= 0:
            continue
        out.append({"jd": float(r["JD"]), "v": float(r["VHelio"]), "e": float(np.hypot(ev, APOGEE_FLOOR_KMS)),
                    "snr": r.get("SNR"), "ncomp": r.get("Ncomp"), "flag": r.get("FlRV"), "tel": r.get("Tel")})
    return out


def gaia_radius(gaia):
    ap = (gaia or {}).get("ap") or {}
    if ap.get("radius_flame") is not None:
        lo, hi = ap.get("radius_flame_lower"), ap.get("radius_flame_upper")
        return float(ap["radius_flame"]), (float(lo) if lo else None), (float(hi) if hi else None), "FLAME"
    return None, None, None, None


def orbit_check(nss, period, ecc_fit):
    """Compare a Gaia spectroscopic orbit with the photometric one."""
    if not nss or nss.get("period") is None:
        return None
    p = float(nss["period"])
    ratio = p / period
    out = {"type": nss.get("nss_solution_type"), "gaia_period_days": p, "period_ratio": ratio,
           "same_period": bool(abs(ratio - 1) < 0.01)}
    out["outer_orbit"] = bool(ratio > 5.0)        # an astrometric orbit far longer than the eclipses: a third body
    if nss.get("eccentricity") is not None:
        e, se = float(nss["eccentricity"]), float(nss.get("eccentricity_error") or np.nan)
        w = nss.get("arg_periastron")
        out.update({"gaia_e": e, "gaia_e_sigma": se, "gaia_omega_deg": None if w is None else float(w),
                    "gaia_ecosw": None if w is None else e * np.cos(np.radians(float(w))),
                    "gaia_k1_kms": nss.get("semi_amplitude_primary"), "gaia_k1_sigma_kms": nss.get("semi_amplitude_primary_error")})
        if ecc_fit and out["same_period"] and out["gaia_ecosw"] is not None:
            ef = ecc_fit
            out["photometric_e"] = ef.get("e")
            out["photometric_ecosw"] = ef.get("ecosw")
            if ef.get("ecosw") is not None and np.isfinite(se) and se > 0:
                out["ecosw_difference_sigma"] = float(abs(out["gaia_ecosw"] - ef["ecosw"]) / max(se, 1e-3))
    return out


def build(root):
    root = Path(root)
    proc = root / "data" / "processed"
    sky = {int(r["tic"]): r for r in json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    ecc = json.loads((proc / "f22_eccentricity.json").read_text(encoding="utf-8"))["stars"]
    import pandas as pd
    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    fits = json.loads((proc / "f26_ebfit.json").read_text(encoding="utf-8"))["stars"] if (proc / "f26_ebfit.json").exists() else {}
    stars = {}
    for p in sorted((proc / "f27_cache").glob("TIC*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        tic = int(rec["tic"])
        if tic not in sky:
            continue
        P = float(sky[tic]["period_days"])
        gaia = rec.get("gaia") or {}
        src = gaia.get("source") or {}
        fit = fits.get(str(tic)) if fits.get(str(tic), {}).get("status") == "OK" else None
        e_fit = (fit or {}).get("params", {})
        ecc_fit = None
        if fit:
            ecc_fit = {"e": e_fit["e"]["median"], "ecosw": e_fit["ecosw"]["median"], "omega_deg": e_fit["omega_deg"]["median"]}
        elif ecc.get(str(tic), {}).get("ecosw") is not None and ecc[str(tic)]["verdict"] in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS"):
            ecc_fit = {"e": None, "ecosw": float(ecc[str(tic)]["ecosw"]), "omega_deg": None}
        out = {"period_days": P}
        # 1. Gaia orbit
        nss = [n for n in gaia.get("nss") or [] if n.get("period") is not None]
        if nss:
            out["gaia_orbit"] = orbit_check(nss[0], P, ecc_fit)
        # 2. Gaia RV range
        amp = src.get("rv_amplitude_robust")
        klo, sig = k_lower_from_amplitude(amp, src.get("grvs_mag"))
        if amp is not None:
            out["gaia_rv"] = {"amplitude_kms": amp, "n_transits": src.get("rv_nb_transits"), "epoch_sigma_kms_assumed": sig,
                              "k1_lower_kms": klo, "moves": bool(klo is not None and klo > 0),
                              "chisq_pvalue": src.get("rv_chisq_pvalue")}
            if klo:
                e0 = (ecc_fit or {}).get("e") or 0.0
                out["gaia_rv"]["mass_function_lower_msun"] = mass_function(klo, P, e0)
            kup = None if klo else k_upper_from_amplitude(amp, src.get("grvs_mag"), src.get("rv_nb_transits"))
            if kup is not None:
                ap = gaia.get("ap") or {}
                m1 = ap.get("mass_flame")
                m1_src = "Gaia FLAME"
                if m1 is None:
                    m1, m1_src = 1.0, "assumed 1 Msun (no FLAME mass)"
                depth = float(vet.loc[tic, "bls_depth"]) if tic in vet.index else None
                sdep = float(vet.loc[tic, "secondary_depth"]) if (tic in vet.index and np.isfinite(vet.loc[tic, "secondary_depth"])) else None
                ratio = (sdep / depth) if (sdep is not None and depth and depth > 0) else None
                m2max = max_companion_mass(kup, P, float(m1))
                verdict = "CONSISTENT"
                if m2max < SUBSTELLAR_MSUN:
                    if ratio is not None and ratio >= TWIN_DEPTH_RATIO:
                        # near-equal eclipses: two similar stars whose lines blend can look static to Gaia
                        verdict = "STATIC_OR_TWIN"
                    elif depth is not None and depth >= DEEP_ECLIPSE:
                        verdict = "BLEND_INDICATED"
                    else:
                        verdict = "SUBSTELLAR_OR_BLEND"
                out["gaia_rv"].update({"k1_upper_kms": kup, "m1_msun": float(m1), "m1_source": m1_src,
                                       "m2_max_msun": float(m2max), "eclipse_depth": depth, "secondary_to_primary_depth": ratio,
                                       "static_star_verdict": verdict})
        # 3. geometry + Gaia radius -> total mass
        R, Rlo, Rhi, Rsrc = gaia_radius(gaia)
        if fit and R:
            pr = fit["params"]
            lr = pr["light_ratio"]["median"]
            R1 = R / np.sqrt(1.0 + lr)
            r1 = pr["r1"]["median"]
            a = R1 / r1
            mt = total_mass(a, fit.get("period_days", P))
            # spread: radius interval and r1 posterior, combined in log space
            rel_R = ((Rhi - Rlo) / 2.0 / R) if (Rlo and Rhi) else 0.05
            rel_r1 = 0.5 * (pr["r1"]["hi"] + pr["r1"]["lo"]) / r1
            # a systematic floor of 10% on r1 (limb darkening and third light; AI Phe was recovered to 3% with
            # 2-minute data and well-defined eclipses, the survivors are usually worse)
            rel_m = 3.0 * float(np.sqrt(rel_R ** 2 + rel_r1 ** 2 + R1_SYSTEMATIC ** 2))
            out["scale"] = {"radius_source": "Gaia DR3 " + Rsrc, "gaia_radius_rsun": R, "light_ratio_tess": lr,
                            "r1_rsun": float(R1), "r2_rsun": float(R1 * pr["k"]["median"]), "a_rsun": float(a),
                            "total_mass_msun": mt, "total_mass_rel_sigma": float(rel_m),
                            "plausible": bool(0.3 <= mt <= 8.0),
                            **main_sequence_check(mt, float(R1), lr, (gaia.get("ap") or {}).get("mass_flame")),
                            "caveat": "Gaia radius assumes one star; companion light removed with the TESS-band ratio"}
        # 4. APOGEE visits at the photometric orbit
        vis = apogee_visits(rec)
        if len(vis) >= 3:
            t = np.array([v["jd"] for v in vis])
            if fit:
                e_ = fit["params"]["e"]["median"]
                w_ = np.radians(fit["params"]["omega_deg"]["median"])
                t0 = fit["t0_btjd"] + 2457000.0
                Pf = fit.get("period_days", P)
            else:
                t0v = float(vet.loc[tic, "bls_t0"]) if tic in vet.index else np.nan
                e_, w_, t0, Pf = 0.0, np.pi / 2, t0v + 2457000.0, P
            if np.isfinite(t0):
                r = fit_k_gamma(t, [v["v"] for v in vis], [v["e"] for v in vis], Pf, t0, e_, w_)
                r["visits"] = vis
                r["orbit_from"] = "f26 light-curve fit" if fit else "circular orbit at the pipeline ephemeris"
                r["note"] = "APOGEE JD is UTC mid-exposure; the difference from BJD (minutes) is negligible at these periods"
                out["apogee"] = r
        # 5. component masses: K1 (APOGEE fit with unflagged visits, else a Gaia SB1 orbit at the eclipse period)
        #    plus i and e from the light curve plus the Kepler total mass
        if "scale" in out and fit:
            k1, k1s, src_k = None, None, None
            a = out.get("apogee")
            if a and a["k1_kms"] > 3 * a["k1_sigma_kms"] and not any(v.get("flag") for v in a["visits"]) and a["chi2"] < 10 * max(a["dof"], 1):
                k1, k1s, src_k = a["k1_kms"], a["k1_sigma_kms"], "APOGEE visits"
            go = out.get("gaia_orbit") or {}
            if k1 is None and go.get("same_period") and go.get("gaia_k1_kms"):
                k1, k1s, src_k = float(go["gaia_k1_kms"]), float(go.get("gaia_k1_sigma_kms") or np.nan), "Gaia DR3 SB1 orbit"
            if k1 is not None:
                mt = out["scale"]["total_mass_msun"]
                close = fit["params"]["rsum"]["median"] > 0.25
                f22s = ecc.get(str(tic), {})
                trusted = (not close) and f22s.get("verdict") in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS") and f22s.get("ecosw") is not None \
                    and abs(fit["params"]["ecosw"]["median"] - float(f22s["ecosw"])) <= max(3.0 * float(f22s.get("ecosw_sigma") or 0.0), 0.01)
                # e from the light curve only when trusted (see export_findings.e_reliable); else a spectroscopic e if
                # Gaia has one, else |e cos w| (a lower limit)
                go_ = out.get("gaia_orbit") or {}
                if trusted:
                    e_ = fit["params"]["e"]["median"]
                elif go_.get("same_period") and go_.get("gaia_e") is not None:
                    e_ = float(go_["gaia_e"])
                else:
                    e_ = abs(fit["params"]["ecosw"]["median"])
                sini = np.sin(np.radians(fit["params"]["incl"]["median"]))
                Pf = fit.get("period_days", P)
                # K1 = (2 pi G / P)^(1/3) m2 sin i / M^(2/3) / sqrt(1 - e^2)
                m2 = k1 * 1e3 * np.sqrt(1 - e_ ** 2) * (Pf * DAY / (2 * np.pi * G_SI)) ** (1 / 3) * (mt * MSUN) ** (2 / 3) / sini / MSUN
                out["masses_estimate"] = {"k1_kms": k1, "k1_sigma_kms": k1s, "k1_source": src_k,
                                          "m1_msun": float(mt - m2), "m2_msun": float(m2), "total_msun": mt, "q": float(m2 / max(mt - m2, 1e-6)),
                                          "plausible": bool(0 < m2 < mt), "close_pair": bool(close), "e_used": float(e_),
                                          "caveat": "depends on the Gaia radius through the total mass; the TESS light ratio is used as if bolometric"}
        if len(out) > 1:
            stars[str(tic)] = out
    summary = {
        "with_gaia_orbit": sum(1 for s in stars.values() if s.get("gaia_orbit")),
        "gaia_outer_orbit": sum(1 for s in stars.values() if (s.get("gaia_orbit") or {}).get("outer_orbit")),
        "gaia_orbit_same_period": sum(1 for s in stars.values() if (s.get("gaia_orbit") or {}).get("same_period")),
        "with_gaia_rv_range": sum(1 for s in stars.values() if s.get("gaia_rv")),
        "gaia_rv_moves": sum(1 for s in stars.values() if (s.get("gaia_rv") or {}).get("moves")),
        "gaia_rv_static_blend_indicated": sum(1 for s in stars.values() if (s.get("gaia_rv") or {}).get("static_star_verdict") == "BLEND_INDICATED"),
        "gaia_rv_static_or_twin": sum(1 for s in stars.values() if (s.get("gaia_rv") or {}).get("static_star_verdict") == "STATIC_OR_TWIN"),
        "gaia_rv_static_substellar_or_blend": sum(1 for s in stars.values() if (s.get("gaia_rv") or {}).get("static_star_verdict") == "SUBSTELLAR_OR_BLEND"),
        "with_total_mass": sum(1 for s in stars.values() if s.get("scale")),
        "total_mass_implausible": sum(1 for s in stars.values() if s.get("scale") and not s["scale"]["plausible"]),
        "with_masses_estimate": sum(1 for s in stars.values() if s.get("masses_estimate")),
        "with_apogee_orbit": sum(1 for s in stars.values() if s.get("apogee")),
    }
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": summary, "stars": stars}


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    out = build(root)
    p = root / "data" / "processed" / "f28_physical.json"
    p.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["summary"], indent=1))
    print("Written: %s" % p)


if __name__ == "__main__":
    main()
