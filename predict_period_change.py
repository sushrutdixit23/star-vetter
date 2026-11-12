import sys
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import f23_etv as f23

# Pre-registered test of a period change. For stars with verdict PERIOD_CHANGE_SMOOTH the eclipse
# times are fitted with a parabola (constant period change) and extrapolated to future eclipses,
# with the fit covariance plus the spread between model variants (TESS-only, cubic) as the error.
#
# Outcome rule, fixed before the data exist: a measured eclipse time within 3 sigma of the parabola
# is consistent with a constant rate of period change; more than 5 sigma away refutes it (for
# example a turnover of a long light-travel-time cycle); anything between is inconclusive. The
# first year of new data cannot tell a parabola from a continued straight line (the two differ by
# about one sigma), so a consistent result is a check, not a proof; the leverage grows with time.
#
# Times are BJD_TDB. Not a discovery claim; the cause (third body, mass exchange) is not tested.

HORIZON_JD_START = 2461375.5        # 2026-12-01
HORIZON_JD_END = 2461775.5          # 2028-01-05


def fit_design(E, deg):
    return np.vstack([E ** k for k in range(deg + 1)]).T


def predict(groups, P, t0, jd_start, jd_end):
    E = np.array([g["epoch"] for g in groups], float)
    y = np.array([g["oc_min"] for g in groups], float)
    s = np.array([g["err_min"] for g in groups], float)
    T = np.array([g["source"] == "TESS" for g in groups])
    w = 1.0 / s
    A = fit_design(E, 2)
    cov = np.linalg.inv((A * w[:, None]).T @ (A * w[:, None]))
    co, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
    chi2 = float((((y - A @ co) / s) ** 2).sum())
    scale = max(1.0, np.sqrt(chi2 / max(len(E) - 3, 1)))            # inflate if the parabola is not perfect
    # model variants for the systematic: TESS-only parabola and all-data cubic
    A3 = fit_design(E, 3)
    co3, *_ = np.linalg.lstsq(A3 * w[:, None], y * w, rcond=None)
    AT = fit_design(E[T], 2)
    coT, *_ = np.linalg.lstsq(AT * w[T][:, None], y[T] * w[T], rcond=None)
    A1 = fit_design(E, 1)
    co1, *_ = np.linalg.lstsq(A1 * w[:, None], y * w, rcond=None)
    first = int(np.ceil((jd_start - t0) / P))
    last = int(np.floor((jd_end - t0) / P))
    rows = []
    for e in range(first, last + 1):
        v = np.array([1.0, e, e * e])
        quad = float(v @ co)
        stat = float(np.sqrt(v @ cov @ v)) * scale
        var = [float(np.array([1.0, e, e * e, e ** 3]) @ co3), float(v @ coT)]
        syst = float(np.max(np.abs(np.array(var) - quad)))
        sig = float(np.hypot(stat, syst))
        line = float(np.array([1.0, e]) @ co1)
        base = t0 + e * P
        rows.append({"epoch": e, "bjd_tdb_parabola": float(base + quad / 1440.0), "sigma_min": sig,
                     "parabola_minus_line_min": float(quad - line)})
    return {"n_times": int(len(E)), "chi2_parabola": chi2, "dof": int(len(E) - 3), "error_scale": float(scale),
            "coefficients_min": [float(x) for x in co], "predictions": rows}


def build(root):
    d = root / "data" / "processed"
    etv = json.loads((d / "f23_etv.json").read_text(encoding="utf-8"))
    vet = pd.read_csv(d / "f3i_vetting_results.csv").set_index("TIC")
    stars = {}
    for t, s in etv["stars"].items():
        if s["verdict"] != "PERIOD_CHANGE_SMOOTH":
            continue
        P = float(s["period_days"])
        t0 = float(vet.loc[int(t), "bls_t0"]) + 2457000.0
        p = predict(s["groups"], P, t0, HORIZON_JD_START, HORIZON_JD_END)
        p.update({"tic": int(t), "period_days": P, "reference_epoch_bjd": t0, "period_change": s["period_change"]})
        stars[t] = p
    return {"rule": "Consistent: within 3 sigma of the parabola. Refuted: more than 5 sigma away. Else inconclusive.",
            "time_system": "BJD_TDB", "stars": stars}


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    out = build(root)
    body = json.dumps(out, indent=1, sort_keys=True) + "\n"
    out_path = root / "docs" / "period_change_predictions.json"
    out_path.write_text(body, encoding="utf-8", newline="\n")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    print("Written: %s" % out_path)
    print("sha256: %s" % sha)
    for t, s in out["stars"].items():
        r = s["predictions"]
        print("TIC%s: %d eclipses in window; first at BJD %.4f (+-%.1f min), last at BJD %.4f (+-%.1f min)" % (
            t, len(r), r[0]["bjd_tdb_parabola"], r[0]["sigma_min"], r[-1]["bjd_tdb_parabola"], r[-1]["sigma_min"]))


if __name__ == "__main__":
    main()
