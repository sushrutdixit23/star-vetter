"""Can a distant third body explain a smooth eclipse-timing curve? (light-travel-time test)

For stars with verdict PERIOD_CHANGE_SMOOTH in f23_etv.json, the eclipse times are fitted with
a constant period plus a circular light-travel-time orbit, O-C(E) = a + b E + C cos(w t) + S sin(w t),
for a grid of third-body periods P3. For each P3 the linear terms are solved exactly, so the
result is a chi-square curve, not a single best fit: with a few years of data covering a fraction of
a cycle, the period is poorly constrained and the honest output is the range that stays allowed.

Reported per star:
  * chi-square versus P3 against the parabola (constant period change), so the two models can be compared;
  * for the allowed P3 range (chi-square within 4 of the best): the light-time amplitude, the projected
    orbit a12 sin i, the mass function, and the MINIMUM third-body mass (i = 90 degrees) for an assumed
    inner-binary mass range;
  * what the orbit would imply for the signal that Gaia DR3 could see (orbits shorter than its 34-month
    baseline), so the result can be checked against the astrometric noise statistic.

A circular orbit is assumed (eccentric orbits add parameters the data cannot constrain). Nothing here
shows a third body exists: a parabola fits equally well, and so would mass exchange.

Usage:  python fit_ltte.py <root>      Writes data/processed/f23_ltte.json
"""

import sys
import json
from pathlib import Path

import numpy as np

import f23_etv as f23

C_AU_PER_DAY = 173.1446        # speed of light in AU per day
INNER_MASS_RANGE = (0.9, 1.3)  # Msun, K dwarf plus a fainter companion (set by the caller if known)
DELTA_CHI2_ALLOWED = 4.0
MAX_PLAUSIBLE_M3 = 1.5         # Msun; a heavier unseen companion would show in the spectrum or the SED


def mass_function(a_au, p3_years):
    return a_au ** 3 / p3_years ** 2          # Msun, Kepler's third law with a in AU and P in years


def min_third_mass(f_msun, m12):
    """Smallest m3 (edge-on) with m3^3 / (m12 + m3)^2 = f, by bisection."""
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid ** 3 / (m12 + mid) ** 2 < f_msun:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def fit(groups, period_days, p3_grid_years, inner_mass=INNER_MASS_RANGE):
    E = np.array([g["epoch"] for g in groups], float)
    y = np.array([g["oc_min"] for g in groups], float)
    s = np.array([g["err_min"] for g in groups], float)
    t_years = E * period_days / 365.25
    w = 1.0 / s
    rows = []
    for p3 in p3_grid_years:
        om = 2.0 * np.pi / p3
        A = np.vstack([np.ones_like(E), E, np.cos(om * t_years), np.sin(om * t_years)]).T
        co, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
        chi2 = float((((y - A @ co) / s) ** 2).sum())
        amp_min = float(np.hypot(co[2], co[3]))                 # minutes of light time
        a_au = amp_min * 60.0 / 86400.0 * C_AU_PER_DAY          # a12 sin i in AU
        fm = mass_function(a_au, p3)
        rows.append({"p3_years": float(p3), "chi2": chi2, "amplitude_min": amp_min, "a12_sini_au": float(a_au),
                     "mass_function_msun": float(fm),
                     "m3_min_msun": [float(min_third_mass(fm, m)) for m in inner_mass]})
    return rows, None


def parabola_chi2(groups):
    E = np.array([g["epoch"] for g in groups], float)
    y = np.array([g["oc_min"] for g in groups], float)
    s = np.array([g["err_min"] for g in groups], float)
    _, chi2, _ = f23.fit_poly(E, y, s, 2)
    return float(chi2)


def summarise(rows, chi_parabola, n_times):
    best = min(rows, key=lambda r: r["chi2"])
    stat_ok = [r for r in rows if r["chi2"] <= best["chi2"] + DELTA_CHI2_ALLOWED]
    ok = [r for r in stat_ok if r["m3_min_msun"][0] <= MAX_PLAUSIBLE_M3] or stat_ok
    return {
        "statistically_allowed_p3_years": [min(r["p3_years"] for r in stat_ok), max(r["p3_years"] for r in stat_ok)],
        "max_plausible_m3_msun": MAX_PLAUSIBLE_M3,
        "allowed_set_is_mass_capped": ok is not stat_ok,
        "n_times": n_times,
        "chi2_parabola": chi_parabola,
        "best_p3_years": best["p3_years"], "best_chi2": best["chi2"], "extra_parameters_vs_parabola": 2,
        "allowed_p3_years": [min(r["p3_years"] for r in ok), max(r["p3_years"] for r in ok)],
        "amplitude_min_range": [min(r["amplitude_min"] for r in ok), max(r["amplitude_min"] for r in ok)],
        "m3_min_msun_range": [min(m for r in ok for m in r["m3_min_msun"]), max(m for r in ok for m in r["m3_min_msun"])],
        "gaia_dr3_orbit_sensitive_below_years": 2.85,
        "fits_as_well_as_parabola": bool(best["chi2"] <= chi_parabola + 1.0),
        "curve": [{"p3_years": r["p3_years"], "chi2": r["chi2"], "m3_min_msun": r["m3_min_msun"][0]} for r in rows[::4]],
    }


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    etv = json.loads((root / "data" / "processed" / "f23_etv.json").read_text(encoding="utf-8"))
    grid = np.exp(np.linspace(np.log(3.0), np.log(400.0), 240))
    out = {}
    for t, st in etv["stars"].items():
        if st["verdict"] != "PERIOD_CHANGE_SMOOTH":
            continue
        rows, _ = fit(st["groups"], st["period_days"], grid)
        out[t] = summarise(rows, parabola_chi2(st["groups"]), len(st["groups"]))
        out[t]["period_days"] = st["period_days"]
    path = root / "data" / "processed" / "f23_ltte.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    for t, o in out.items():
        print("TIC%s: parabola chi2 %.1f; best LTTE chi2 %.1f at P3=%.1f yr; allowed P3 %.1f to %.1f yr; "
              "amplitude %.0f to %.0f min; minimum m3 %.2f to %.2f Msun" % (
                  t, o["chi2_parabola"], o["best_chi2"], o["best_p3_years"], *o["allowed_p3_years"],
                  *o["amplitude_min_range"], *o["m3_min_msun_range"]))


if __name__ == "__main__":
    main()
