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
        out["timing_drift"] = {"counts": c, "period_change": sig, "floors_min": etv.get("floors_min"), "calibration": cal}
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
            L += ["", "The cause is not tested here (a distant third body, mass exchange and others all produce a parabola over a few years). "
                  "Predictions of the next eclipses are in `docs/period_change_predictions.json`."]
        else:
            L.append("No star passed every rule.")
    L += ["", "## Limits", ""] + ["- " + x for x in o["limits"]] + [""]
    return "\n".join(L)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    o = build(root)
    jp = root / "site" / "public" / "data" / "eccentric.json"
    jp.write_text(json.dumps(o, indent=1) + "\n", encoding="utf-8", newline="\n")
    mp = root / "docs" / "novelty_findings.md"
    mp.write_text(markdown(o), encoding="utf-8", newline="\n")
    print("Written: %s and %s (%d candidates)" % (jp, mp, len(o["candidates"])))


if __name__ == "__main__":
    main()
