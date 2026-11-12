import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Turns the eccentricity (f22) and timing-drift (f23) results into one findings file for the site
# and a short markdown summary. Every number in the markdown is computed here from the data
# files, so the text cannot drift from them.
#
# Claims allowed: e cos(omega) lower limits for stars that pass every veto, which of them ZTF
# re-measures independently, how eccentric systems are distributed in period, and the outcome of
# the timing-drift search (including a null result). Claims NOT allowed: true eccentricities
# (only e cos omega is measured), third bodies, or anything about masses and radii.

PERIOD_BINS = [(0.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 1000.0)]
E_MIN_SIGNIFICANT = 0.05           # |e cos omega| at which the offset is far beyond systematics


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def e_reliable(q, f22):
    if q["rsum"]["median"] > 0.25:
        return False
    if f22.get("verdict") not in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS") or f22.get("ecosw") is None:
        return False
    tol = max(3.0 * float(f22.get("ecosw_sigma") or 0.0), 0.01)
    return bool(abs(q["ecosw"]["median"] - float(f22["ecosw"])) <= tol)


def e_reason(q, f22):
    if q["rsum"]["median"] > 0.25:
        return "close pair: spheres misjudge the durations"
    if f22.get("verdict") not in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS") or f22.get("ecosw") is None:
        return "secondary eclipse too weak to measure independently"
    return "e cos w disagrees with the independent measurement"


def _q(p, name, nd=4):
    v = p.get(name) or {}
    return {"median": round(float(v["median"]), nd), "lo": round(float(v["lo"]), nd), "hi": round(float(v["hi"]), nd)} if v else None


def physical(d, ecc, sky):
    """Light-curve model fits (f26), their validation, and archival spectroscopy (f28)."""
    fp, vp, sp = d / "f26_ebfit.json", d / "f26_validation.json", d / "f28_physical.json"
    if not fp.exists() and not sp.exists():
        return None
    out = {"validation": [], "fits": [], "spectroscopy": None}
    if vp.exists():
        vals = load(vp)
        for v in (vals if isinstance(vals, list) else [vals]):
            if "fit" not in v:
                continue
            out["validation"].append({"star": v["star"], "reference": v["reference"], "cadence_min": v.get("cadence_min", 2),
                                      "passed": v["passed"], "checks": v["checks"], "truth": v["truth"],
                                      "fit": {k: round(v["fit"][k]["median"], 4) for k in ("e", "esinw", "ecosw", "r1", "r2", "incl", "l3")}})
    spec = load(sp)["stars"] if sp.exists() else {}
    if fp.exists():
        for t, r in sorted(load(fp)["stars"].items(), key=lambda kv: float(sky[int(kv[0])]["period_days"])):
            if r.get("status") != "OK":
                out["fits"].append({"tic": int(t), "status": r.get("status")})
                continue
            q = r["params"]
            row = {"tic": int(t), "status": "OK", "period_days": round(r["period_days"], 6),
                   "e": _q(q, "e"), "omega_deg": _q(q, "omega_deg", 1), "ecosw": _q(q, "ecosw"), "esinw": _q(q, "esinw"),
                   "incl_deg": _q(q, "incl", 2), "r1": _q(q, "r1"), "r2": _q(q, "r2"), "k": _q(q, "k", 3), "J": _q(q, "J", 3),
                   "l3": _q(q, "l3", 3), "l3_p97_5": round(float(q["l3"]["p97.5"]), 3), "light_ratio": _q(q, "light_ratio", 3),
                   "converged": r.get("converged"),
                   "flags": r.get("flags", []), "f22_ecosw": (ecc["stars"].get(t) or {}).get("ecosw"),
                   # e is trusted only when (1) the pair is not too close for spheres, (2) the secondary was measured
                   # independently by f22 and (3) both e cos w agree; otherwise e sin w (from the duration ratio) is
                   # not constrained -- shown on TIC 43785616, where a weak secondary gave e=0.25 against Gaia's 0.05
                   "e_reliable": e_reliable(q, (ecc["stars"].get(t) or {})),
                   # third light: is the posterior narrower than the half-normal prior (median 0.067, 84th pct 0.141)?
                   # constrained by the data when the posterior is much narrower than the half-normal prior (16-84%
                   # width about 0.13)
                   "l3_constrained": bool(q["l3"]["lo"] + q["l3"]["hi"] < 0.06)}
            if not row["e_reliable"]:
                row["e_note"] = e_reason(q, ecc["stars"].get(t) or {})
            sc = (spec.get(t) or {}).get("scale")
            if sc and row["e_reliable"]:
                row["total_mass_msun"] = round(sc["total_mass_msun"], 2)
                row["total_mass_rel_sigma"] = round(sc["total_mass_rel_sigma"], 2)
                row["total_mass_plausible"] = sc["plausible"]
                row["total_mass_ms_consistent"] = sc.get("ms_consistent")
                row["total_mass_ms_expected"] = round(sc["ms_expected_total_msun"], 2) if sc.get("ms_expected_total_msun") else None
            out["fits"].append(row)
    if sp.exists():
        sm = load(sp)
        ratios = [v["scale"]["ms_ratio"] for v in sm["stars"].values() if (v.get("scale") or {}).get("ms_ratio") is not None]
        out["mass_check"] = {"n": len(ratios), "median_ratio": round(float(np.median(ratios)), 2) if ratios else None,
                             "n_consistent": sum(1 for v in sm["stars"].values() if (v.get("scale") or {}).get("ms_consistent"))}
        orbits = []
        for t, s_ in sm["stars"].items():
            o = s_.get("gaia_orbit")
            if o:
                orbits.append({"tic": int(t), **{k: o.get(k) for k in ("type", "gaia_period_days", "period_ratio", "same_period", "outer_orbit", "gaia_e",
                                                                       "gaia_e_sigma", "gaia_ecosw", "gaia_k1_kms", "photometric_ecosw")}})
        apo = []
        for t, s_ in sm["stars"].items():
            a = s_.get("apogee")
            if a:
                flagged = sum(1 for v in a["visits"] if v.get("flag"))
                apo.append({"tic": int(t), "n": a["n"], "k1_kms": round(a["k1_kms"], 1), "k1_sigma_kms": round(a["k1_sigma_kms"], 1),
                            "chi2": round(a["chi2"], 1), "dof": a["dof"], "chi2_constant": round(a["chi2_constant"], 1),
                            "flagged_visits": flagged, "orbit_from": a["orbit_from"]})
        static = []
        for t, s_ in sm["stars"].items():
            g = s_.get("gaia_rv") or {}
            if g.get("static_star_verdict") in ("BLEND_INDICATED", "SUBSTELLAR_OR_BLEND", "STATIC_OR_TWIN"):
                static.append({"tic": int(t), "verdict": g["static_star_verdict"], "k1_upper_kms": round(g["k1_upper_kms"], 2),
                               "m2_max_msun": round(g["m2_max_msun"], 3), "eclipse_depth": g["eclipse_depth"],
                               "n_transits": g["n_transits"], "m1_source": g["m1_source"]})
        static.sort(key=lambda r: ({"BLEND_INDICATED": 0, "SUBSTELLAR_OR_BLEND": 1, "STATIC_OR_TWIN": 2}[r["verdict"]], -(r["eclipse_depth"] or 0)))
        # independent check of the light-curve e against Gaia spectroscopic orbits (trusted or not)
        echeck = []
        fits_by = {r["tic"]: r for r in out["fits"] if r.get("status") == "OK"}
        for o in orbits:
            fr = fits_by.get(o["tic"])
            if fr and o.get("same_period") and o.get("gaia_e") is not None:
                echeck.append({"tic": o["tic"], "fit_e": fr["e"]["median"], "fit_e_err": max(fr["e"]["lo"], fr["e"]["hi"]),
                               "gaia_e": o["gaia_e"], "gaia_e_sigma": o["gaia_e_sigma"], "trusted": fr["e_reliable"],
                               "difference_sigma": round(abs(fr["e"]["median"] - o["gaia_e"]) / max(float(np.hypot(max(fr["e"]["lo"], fr["e"]["hi"]), o["gaia_e_sigma"] or 0.0)), 1e-3), 1)})
        out["spectroscopy"] = {"e_check_vs_gaia": echeck, "summary": sm["summary"], "gaia_orbits": sorted(orbits, key=lambda r: r["tic"]),
                               "apogee": sorted(apo, key=lambda r: r["tic"]), "static": static}
    return out


def build(root):
    d = Path(root) / "data" / "processed"
    ecc = load(d / "f22_eccentricity.json")
    sky = {int(r["tic"]): r for r in load(Path(root) / "site" / "public" / "data" / "dashboard.json")["sky"]}
    evid = load(Path(root) / "site" / "public" / "data" / "evidence.json")["stars"]
    etv = load(d / "f23_etv.json") if (d / "f23_etv.json").exists() else None

    rows, measured = [], []
    for t, s in ecc["stars"].items():
        if s["verdict"] not in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS"):
            continue
        P = float(sky[int(t)]["period_days"])
        measured.append({"tic": int(t), "period_days": P, "ecosw_abs": abs(float(s["ecosw"])), "eccentric": s["verdict"] == "ECCENTRIC"})
        if s["verdict"] != "ECCENTRIC":
            continue
        z = s.get("ztf") or {}
        e = evid.get(t, {})
        rows.append({
            "tic": int(t), "period_days": P, "ecosw": float(s["ecosw"]), "ecosw_sigma": float(s["ecosw_sigma"]),
            "e_lower_limit": abs(float(s["ecosw"])),
            "secondary_phase": float(s["secondary_phase"]), "secondary_depth": float(s["secondary_depth"]),
            "secondary_snr": float(s["secondary_snr"]),
            "half_a_phase": s["half_a"]["phase"], "half_b_phase": s["half_b"]["phase"], "halves": s["halves"],
            "ztf_coverage": s.get("ztf_coverage"),
            "marginal": abs(float(s["ecosw"])) < E_MIN_SIGNIFICANT,
            "ztf_confirmed": bool(z.get("confirmed")) if z and "confirmed" in z else None,
            "ztf_p_value": z.get("p_value") if z else None,
            "evidence_tier": e.get("evidence_tier"), "novelty": e.get("novelty"), "caveats": e.get("caveats", []),
        })
    rows.sort(key=lambda r: r["period_days"])

    bins = []
    for lo, hi in PERIOD_BINS:
        m = [x for x in measured if lo < x["period_days"] <= hi]
        bins.append({"p_min": lo, "p_max": hi, "n_measured": len(m),
                     "n_offset": int(sum(1 for x in m if x["ecosw_abs"] >= E_MIN_SIGNIFICANT))})
    short = [x for x in measured if x["period_days"] <= 2.0]
    longer = [x for x in measured if x["period_days"] > 2.0]
    k_short = sum(1 for x in short if x["ecosw_abs"] >= E_MIN_SIGNIFICANT)
    k_long = sum(1 for x in longer if x["ecosw_abs"] >= E_MIN_SIGNIFICANT)
    rate_long = k_long / len(longer) if longer else None
    p_none = float((1.0 - rate_long) ** len(short)) if rate_long is not None and not k_short else None

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict_counts": ecc["counts"],
        "candidates": rows,
        "period_bins": bins,
        "circularisation": {"threshold_ecosw": E_MIN_SIGNIFICANT, "n_short": len(short), "k_short": k_short,
                            "n_longer": len(longer), "k_longer": k_long,
                            "chance_of_none_if_same_rate_as_longer": p_none},
        "timing_drift": None,
        "limits": ["Only e cos(omega) is measured, so each value is a lower limit on the eccentricity.",
                   "Eclipses are on the TESS aperture, not proven to be on the target (see the evidence tier).",
                   "Selection: a secondary must be detectable, which favours deep, well-separated eclipses."],
    }
    if etv:
        c = etv["counts"]
        sig = [{"tic": int(t), "period_days": st["period_days"], "n_tess": st["n_tess"], "n_ztf": st["n_ztf"],
                "chi2_line": st["chi2_line"], "dof_line": st["dof_line"], "chi2_parabola": st.get("chi2_quad"),
                "dof_parabola": st.get("dof_quad"), **st["period_change"]}
               for t, st in etv["stars"].items() if st["verdict"] == "PERIOD_CHANGE_SMOOTH"]
        cal = None
        cp = d / "f23_calibration.json"
        if cp.exists():
            cal = load(cp)
        lp = d / "f23_ltte.json"
        ltte = None
        if lp.exists():
            ltte = [{"tic": int(t), **{k: v[k] for k in ("period_days", "chi2_parabola", "best_chi2", "best_p3_years", "allowed_p3_years",
                     "statistically_allowed_p3_years", "max_plausible_m3_msun", "amplitude_min_range", "m3_min_msun_range",
                     "fits_as_well_as_parabola", "extra_parameters_vs_parabola", "gaia_dr3_orbit_sensitive_below_years")}}
                    for t, v in load(lp).items()]
        out["timing_drift"] = {"counts": c, "period_change": sig, "floors_min": etv.get("floors_min"), "calibration": cal, "ltte": ltte}
    out["physical"] = physical(d, ecc, sky)
    vp = d / "f22_validation_prsa_summary.json"
    out["validation"] = None
    if vp.exists():
        v = load(vp)
        out["validation"] = {k: v.get(k) for k in ("n_tested", "n_with_measurement", "median_abs_phase_error", "circular_truth",
                             "false_positive_eccentric", "eccentric_truth", "recovered_eccentric", "eccentric_truth_verdicts",
                             "circular_truth_verdicts")}
        out["validation"]["fraction_within_0.01"] = v.get("fraction_within_0.010")
    return out


def markdown(o):
    L = ["# Findings from the survivor light curves", "",
         "Generated by `export_findings.py` from `data/processed/f22_eccentricity.json` and `f23_etv.json`. "
         "Do not edit by hand.", ""]
    c = o["verdict_counts"]
    L += ["## Eccentric orbits", "",
          "A displaced secondary eclipse gives e cos(omega) = (pi/2)(phase - 0.5), a lower limit on the eccentricity. "
          "A star is listed only when two independent halves of the TESS data each show the dip at the same phase, no third dip "
          "exists, and no fast periodic signal is present outside the eclipses.", "",
          "Verdicts: " + ", ".join("%s %d" % (k, v) for k, v in sorted(c.items())) + ".", "",
          "| TIC | Period (d) | e cos w | sigma | Secondary SNR | ZTF re-measure | Evidence tier | Prior work |",
          "|---|---|---|---|---|---|---|---|"]
    for r in o["candidates"]:
        cov = {"no_file": "no ZTF data", "insufficient_points": "too few ZTF points", "error": "error"}
        zt = cov.get(r["ztf_coverage"], "n/a") if r["ztf_confirmed"] is None else (
            "confirmed (p=%.3f)" % r["ztf_p_value"] if r["ztf_confirmed"] else "not confirmed")
        L.append("| %d%s | %.3f | %+.3f | %.4f | %.0f | %s | %s | %s |" % (
            r["tic"], " (marginal)" if r["marginal"] else "", r["period_days"], r["ecosw"], r["ecosw_sigma"], r["secondary_snr"], zt, r["evidence_tier"], r["novelty"]))
    ci = o["circularisation"]
    L += ["", "## Tidal circularisation check", "",
          "Close binaries are expected to be circular. Offsets of |e cos w| of at least %.2f: %d of %d measured systems at P of 2 d or less, "
          "%d of %d above 2 d." % (ci["threshold_ecosw"], ci["k_short"], ci["n_short"], ci["k_longer"], ci["n_longer"])]
    if ci["chance_of_none_if_same_rate_as_longer"] is not None:
        L.append("If the short systems had the same rate as the longer ones, the chance of seeing none is %.4f. "
                 "This reproduces known physics; it validates the measurement and is not a new result." % ci["chance_of_none_if_same_rate_as_longer"])
    L += ["", "| Period range (d) | Measured | Offset |", "|---|---|---|"]
    for b in o["period_bins"]:
        L.append("| %g to %g | %d | %d |" % (b["p_min"], min(b["p_max"], 999), b["n_measured"], b["n_offset"]))
    td = o["timing_drift"]
    if td:
        L += ["", "## Timing drift (third-body search)", "",
              "Eclipse times per TESS sector and per ZTF season come from one shared template. Counts: " +
              ", ".join("%s %d" % (k, v) for k, v in sorted(td["counts"].items())) + ".",
              "Many raw drift flags are measurement failures (template mismatch or cycle-count slips) and are rejected by amplitude, "
              "minimum-times and smoothness rules; only a parabola that fits well and has both instruments on one curve is kept."]
        cal = td.get("calibration")
        if cal:
            L.append("False-alarm rate of the full rule on %d synthetic constant-period light curves (real sampling and noise): %d flagged." % (
                cal["trials"], cal["flagged"]))
        if td["period_change"]:
            L += ["", "| TIC | Period (d) | TESS times | ZTF times | chi2 line | chi2 parabola | dP/dt (s/yr) |", "|---|---|---|---|---|---|---|"]
            for r in td["period_change"]:
                L.append("| %d | %.4f | %d | %d | %.0f (%d dof) | %.1f (%d dof) | %+.1f +- %.1f |" % (
                    r["tic"], r["period_days"], r["n_tess"], r["n_ztf"], r["chi2_line"], r["dof_line"], r["chi2_parabola"],
                    r["dof_parabola"], r["dP_dt_seconds_per_year"], r["dP_dt_sigma_seconds_per_year"]))
            L += ["", "The cause is not settled (a distant third body, mass exchange and others all produce a parabola over a few years). "
                  "Predictions of the next eclipses are in `docs/period_change_predictions.json`."]
            for r in td.get("ltte") or []:
                lo, hi = r["allowed_p3_years"]
                slo, shi = r["statistically_allowed_p3_years"]
                L += ["", "Light-travel-time test for TIC %d (circular third-body orbit, %d extra parameters over the parabola): "
                      "best fit P3 = %.1f yr with chi2 %.1f against %.1f for the parabola, so it %s the parabola. "
                      "Orbits with P3 from %.1f to %.1f yr are statistically allowed; capping the unseen companion at %.1f Msun leaves %.1f to %.1f yr, "
                      "light-time amplitude %.0f to %.0f min, minimum companion mass %.2f to %.2f Msun. "
                      "Orbits shorter than about %.1f yr are excluded by the data. This does not show a third body exists." % (
                          r["tic"], r["extra_parameters_vs_parabola"], r["best_p3_years"], r["best_chi2"], r["chi2_parabola"],
                          "does not improve on" if not r["fits_as_well_as_parabola"] else "improves on (not significantly, for two extra parameters)",
                          slo, shi, r["max_plausible_m3_msun"], lo, hi, r["amplitude_min_range"][0], r["amplitude_min_range"][1],
                          r["m3_min_msun_range"][0], r["m3_min_msun_range"][1], slo)]
                fit = next((x for x in (o.get("physical") or {}).get("fits", []) if x["tic"] == r["tic"] and x.get("status") == "OK"), None)
                if fit and fit.get("l3_p97_5") is not None:
                    L += ["", "The light-curve model of TIC %d puts the third light below %.2f of the TESS flux (95%%), with the companion in the "
                          "pair contributing %.2f. A main-sequence third star near the top of the allowed mass range would be about as bright as the "
                          "pair and is disfavoured; a low-mass (M-dwarf) or compact companion is not. This narrows, but does not settle, the "
                          "light-travel-time picture." % (r["tic"], fit["l3_p97_5"], fit["light_ratio"]["median"])]
        else:
            L.append("No star passed every rule.")
    ph = o.get("physical")
    if ph:
        L += ["", "## Physical light-curve model", "",
              "Detached-binary model (ellc, spheres, quadratic limb darkening, third light with a half-normal prior of width 0.10), "
              "fitted by MCMC to the TESS eclipses after per-eclipse detrending. The two eclipse durations give e sin w, so the true "
              "eccentricity e is measured, not only the lower limit e cos w. Masses need spectra (see below).",
              "Limits of the model: e is trusted only when the pair is not too close for spherical stars (r1 + r2 at most 0.25), the secondary "
              "eclipse was measured independently (f22) and the two values of e cos w agree; otherwise only e cos w is given. "
              "Third light marked (prior) is not constrained by the data; the value is the prior's. Chains marked 'no' under Converged ran "
              "for fewer than 20 autocorrelation times, so their uncertainties are indicative."]
        for v in ph["validation"]:
            L.append("Validation on %s (%s), %d-min cadence: e %.3f vs %.4f, r1 %.4f vs %.4f, r2 %.4f vs %.4f, i %.2f vs %.2f; %s." % (
                v["star"], v["reference"], v["cadence_min"], v["fit"]["e"], v["truth"]["e"], v["fit"]["r1"], v["truth"]["r1"],
                v["fit"]["r2"], v["truth"]["r2"], v["fit"]["incl"], v["truth"]["incl"], "passed every pre-set check" if v["passed"] else
                "FAILED: " + ", ".join(k for k, ok in v["checks"].items() if not ok)))
        if ph["fits"]:
            L += ["", "| TIC | Period (d) | e | omega (deg) | i (deg) | r1 | r2 | l3 | Converged | Total mass estimate (Msun, Gaia radius) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for r in ph["fits"]:
                if r["status"] != "OK":
                    L.append("| %d | | %s | | | | | | | |" % (r["tic"], r["status"]))
                    continue
                f = lambda q, nd=3: ("%.*f +%.*f/-%.*f" % ((4 if q["hi"] < 0.001 else nd), q["median"], (4 if q["hi"] < 0.001 else nd), q["hi"],
                                                           (4 if q["hi"] < 0.001 else nd), q["lo"])) if q else "n/a"  # noqa: E731
                if "total_mass_msun" not in r:
                    tm = "n/a"
                elif r.get("total_mass_ms_consistent") is False:
                    tm = "inconsistent (%.1f vs %.1f expected for two dwarfs): radius or light split biased" % (r["total_mass_msun"], r["total_mass_ms_expected"])
                else:
                    tm = "%.2f (+-%.0f%%)%s" % (r["total_mass_msun"], 100 * r["total_mass_rel_sigma"], "" if r["total_mass_plausible"] else " IMPLAUSIBLE")
                ee = f(r["e"]) if r["e_reliable"] else "not trusted (%s); e cos w %+.3f" % (r["e_note"], r["ecosw"]["median"])
                L.append("| %d | %.4f | %s | %s | %.2f | %.4f | %.4f | %.2f%s | %s | %s |" % (
                    r["tic"], r["period_days"], ee, "%.0f" % r["omega_deg"]["median"] if r["e_reliable"] else "n/a", r["incl_deg"]["median"],
                    r["r1"]["median"], r["r2"]["median"], r["l3"]["median"], "" if r["l3_constrained"] else " (prior)",
                    "yes" if r["converged"] else "no", tm))
        mc = ph.get("mass_check")
        if mc and mc["n"]:
            L += ["", "Total masses from Kepler's law and the Gaia radius came out a median %.1f times what two main-sequence stars of the implied "
                  "size and light ratio would weigh (%d of %d within a factor 1.6). The likely cause is the Gaia radius of a composite source. "
                  "These are therefore not usable as masses; real masses need double-lined spectra." % (mc["median_ratio"], mc["n_consistent"], mc["n"])]
        sp_ = ph.get("spectroscopy")
        if sp_:
            sm = sp_["summary"]
            L += ["", "## Archival spectroscopy", "",
                  "Gaia DR3 (radial-velocity summaries and spectroscopic orbits), APOGEE DR17 visits, GALAH, LAMOST and RAVE, queried for "
                  "every survivor. No new telescope time.", "",
                  "- Gaia orbits: %d; spectroscopic at the TESS period (within 1%%): %d; astrometric outer orbits: %d. A spectroscopic orbit at "
                  "the eclipse period is independent evidence that the eclipses belong to the bright Gaia star." % (
                      sm["with_gaia_orbit"], sm["gaia_orbit_same_period"], sm["gaia_outer_orbit"]),
                  "- Gaia RV range available: %d stars; the bright star clearly moves in %d." % (sm["with_gaia_rv_range"], sm["gaia_rv_moves"]),
                  "- Bright star static (upper limit on the companion mass below 0.08 Msun): %d BLEND_INDICATED (deep eclipse), %d SUBSTELLAR_OR_BLEND, "
                  "%d STATIC_OR_TWIN (near-equal eclipses; blended twin lines can look static)." % (
                      sm["gaia_rv_static_blend_indicated"], sm["gaia_rv_static_substellar_or_blend"], sm["gaia_rv_static_or_twin"]),
                  "- APOGEE visit orbits fitted at the photometric ephemeris: %d." % sm["with_apogee_orbit"]]
            inner = [r for r in sp_["gaia_orbits"] if r.get("same_period")]
            outer = [r for r in sp_["gaia_orbits"] if r.get("outer_orbit")]
            if inner:
                L += ["", "Gaia spectroscopic orbits at the eclipse period:", "",
                      "| TIC | Gaia solution | Gaia period (d) | P(Gaia)/P(TESS) | Gaia e | Gaia e cos w | photometric e cos w | Gaia K1 (km/s) |", "|---|---|---|---|---|---|---|---|"]
                for r in inner:
                    L.append("| %d | %s | %.4f | %.4f | %s | %s | %s | %s |" % (
                        r["tic"], r["type"], r["gaia_period_days"], r["period_ratio"],
                        "%.3f +- %.3f" % (r["gaia_e"], r["gaia_e_sigma"]) if r.get("gaia_e") is not None else "n/a",
                        "%+.3f" % r["gaia_ecosw"] if r.get("gaia_ecosw") is not None else "n/a",
                        "%+.3f" % r["photometric_ecosw"] if r.get("photometric_ecosw") is not None else "n/a",
                        "%.1f" % r["gaia_k1_kms"] if r.get("gaia_k1_kms") else "n/a"))
            if sp_.get("e_check_vs_gaia"):
                L += ["", "Light-curve e against the Gaia spectroscopic e (an independent check of the model): " + "; ".join(
                    "TIC %d: %.3f vs %.3f +- %.3f (%.1f sigma apart, light-curve e %s)" % (
                        r["tic"], r["fit_e"], r["gaia_e"], r["gaia_e_sigma"], r["difference_sigma"], "trusted" if r["trusted"] else "not trusted by the rule above")
                    for r in sp_["e_check_vs_gaia"]) + "."]
            if outer:
                L += ["", "Gaia astrometric orbits much longer than the eclipse period (candidate third bodies; Gaia orbit solutions for variable stars "
                      "can be spurious, so these need checking): " +
                      ", ".join("TIC %d (P = %.0f d, e = %.2f)" % (r["tic"], r["gaia_period_days"], r["gaia_e"]) for r in outer) + "."]
            if sp_["apogee"]:
                L += ["", "| TIC | APOGEE visits | K1 (km/s) | chi2 / dof | chi2 constant | flagged visits | orbit used |", "|---|---|---|---|---|---|---|"]
                for r in sp_["apogee"]:
                    L.append("| %d | %d | %.1f +- %.1f | %.1f / %d | %.1f | %d | %s |" % (r["tic"], r["n"], r["k1_kms"], r["k1_sigma_kms"], r["chi2"], r["dof"],
                                                                                    r["chi2_constant"], r["flagged_visits"], r["orbit_from"]))
            bl = [r for r in sp_["static"] if r["verdict"] == "BLEND_INDICATED"]
            if bl:
                L += ["", "Static bright star with a deep eclipse (eclipses very probably from another star): " + ", ".join(
                    "TIC %d (depth %.1f%%, K1 < %.1f km/s over %d Gaia transits)" % (r["tic"], 100 * r["eclipse_depth"], r["k1_upper_kms"], r["n_transits"]) for r in bl) + "."]
    v = o.get("validation")
    if v:
        L += ["", "## External check of the eccentricity measurement", "",
              "The same code was run on %d TESS eclipsing binaries from the Prsa et al. 2022 catalog (published secondary phases, fitted by other code), "
              "using only the published period and epoch as input and the first 26 sectors the catalog was fitted on." % v["n_tested"],
              "Measured secondary phase against the published phase: median absolute difference %s, %s of measured systems within 0.01 in phase." % (
                  "n/a" if v["median_abs_phase_error"] is None else "%.4f" % v["median_abs_phase_error"],
                  "n/a" if v.get("fraction_within_0.01") is None else "%.0f%%" % (100 * v["fraction_within_0.01"])),
              "Published as circular: %d systems, %d called eccentric (false positives). Published as eccentric: %d systems, %d recovered; "
              "the rest were vetoed or lacked enough secondary eclipses to test, which is by design (the rule prefers a miss to a false claim)." % (
                  v["circular_truth"], v["false_positive_eccentric"], v["eccentric_truth"], v["recovered_eccentric"]),
              "Verdicts for published-eccentric systems: " + ", ".join("%s %d" % (k, n) for k, n in sorted((v["eccentric_truth_verdicts"] or {}).items())) + "."]
    L += ["", "## Limits", ""] + ["- " + x for x in o["limits"]] + [""]
    return "\n".join(L)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    o = build(root)
    jp = root / "site" / "public" / "data" / "eccentric.json"
    jp.write_text(json.dumps(o, indent=1) + "\n", encoding="utf-8", newline="\n")
    pc = root / "docs" / "period_change_predictions.json"
    if pc.exists():
        (root / "site" / "public" / "data" / "period_change_predictions.json").write_bytes(pc.read_bytes())
    mp = root / "docs" / "novelty_findings.md"
    mp.write_text(markdown(o), encoding="utf-8", newline="\n")
    print("Written: %s and %s (%d candidates)" % (jp, mp, len(o["candidates"])))


if __name__ == "__main__":
    main()
