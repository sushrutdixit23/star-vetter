import sys
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Grades the frozen eclipse predictions once TESS Year 9 data exist.
#
# This implements, and only implements, the outcome rule that was frozen on 2026-11-10
# (doi:10.5281/zenodo.24115848), read from the frozen predictions.json itself:
#
#   RECOVERED          measured mid-eclipse within 3 sigma of the prediction, where sigma combines
#                      the prediction's own 1-sigma, the measurement error and, for QLP light
#                      curves only, a 3-minute systematic term, all in quadrature
#   INCONSISTENT       the eclipse was observed and the measured time is outside that
#   INSUFFICIENT_DATA  the eclipse was not covered, or could not be timed
#
# It is fail-closed: every frozen prediction appears in the output exactly once, nothing is
# dropped, a duplicate or unknown measurement is an error, and the report always lists the
# misses next to the hits.
#
# NOT DONE and cannot be before the data exist: the step that times each eclipse in the new
# light curves. The rule says it uses "the same code" as the predictions, i.e. the eclipse-timing
# routines of f13_ephemeris.py; wiring that to Year 9 downloads is a task for March 2027 and
# needs real data to test. This module takes its output as a CSV:
#   tic, sector, cycle, covered (true/false), t_btjd, sigma_min, source (SPOC, TESS-SPOC, QLP, other)
# One row per predicted eclipse: a star can have several eclipses in one sector, so the key is (tic, cycle).
#
# Usage: py grade_predictions.py <frozen-zip-or-predictions.json> <measurements.csv> <out.json>

NSIGMA = 3.0
QLP_SYSTEMATIC_MIN = 3.0
VERDICTS = ("RECOVERED", "INCONSISTENT", "INSUFFICIENT_DATA")


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"k": k, "n": n, "rate": p, "lo": max(0.0, c - h), "hi": min(1.0, c + h)}


def verdict(t_pred_btjd, sigma_pred_min, covered, t_meas_btjd=None, sigma_meas_min=None, source=None):
    """(verdict, detail) for one predicted eclipse under the frozen rule."""
    if not covered or t_meas_btjd is None or sigma_meas_min is None:
        return "INSUFFICIENT_DATA", {}
    if not (math.isfinite(t_meas_btjd) and math.isfinite(sigma_meas_min)) or sigma_meas_min < 0:
        return "INSUFFICIENT_DATA", {}
    qlp = (source or "").upper() == "QLP"
    sigma = math.sqrt(sigma_pred_min ** 2 + sigma_meas_min ** 2 + (QLP_SYSTEMATIC_MIN ** 2 if qlp else 0.0))
    dt = (t_meas_btjd - t_pred_btjd) * 1440.0
    z = dt / sigma if sigma > 0 else math.inf
    return ("RECOVERED" if abs(z) <= NSIGMA else "INCONSISTENT"), {"offset_min": dt, "sigma_total_min": sigma, "z": z}


def load_predictions(path):
    """predictions.json from the frozen zip (preferred) or a plain json file."""
    p = Path(path)
    if p.suffix == ".zip":
        with zipfile.ZipFile(p) as zf:
            names = [n for n in zf.namelist() if n.endswith("predictions.json")]
            if len(names) != 1:
                raise ValueError("expected exactly one predictions.json in the bundle, found %d" % len(names))
            return json.loads(zf.read(names[0]).decode("utf-8"))
    return json.loads(p.read_text(encoding="utf-8"))


def grade(pred, meas):
    """pred: frozen predictions.json payload. meas: DataFrame with the documented columns.
    Returns the report dict. Raises on duplicate or unknown (tic, sector) measurements."""
    expected = {}
    for s in pred["stars"]:
        for e in s["predictions"]:
            expected[(int(s["tic"]), int(e["cycle"]))] = (s, e)
    m = {}
    for _, r in meas.iterrows():
        key = (int(r["tic"]), int(r["cycle"]))
        if key not in expected:
            raise ValueError("measurement for %s is not a frozen prediction" % (key,))
        if key in m:
            raise ValueError("duplicate measurement for %s" % (key,))
        m[key] = r
    rows = []
    for key, (s, e) in sorted(expected.items()):
        r = m.get(key)
        covered = bool(r is not None and str(r["covered"]).strip().lower() in ("true", "1", "yes"))
        t = None if r is None or pd.isna(r.get("t_btjd")) else float(r["t_btjd"])
        sg = None if r is None or pd.isna(r.get("sigma_min")) else float(r["sigma_min"])
        src = None if r is None else str(r.get("source"))
        v, det = verdict(float(e["t_btjd"]), float(e["sigma_min"]), covered, t, sg, src)
        rows.append({"tic": key[0], "cycle": key[1], "sector": int(e["sector"]), "grade": s["grade"], "t_pred_btjd": e["t_btjd"], "sigma_pred_min": e["sigma_min"],
                     "t_meas_btjd": t, "sigma_meas_min": sg, "source": src, "verdict": v, **det})
    obs = [r for r in rows if r["verdict"] != "INSUFFICIENT_DATA"]
    rec = [r for r in obs if r["verdict"] == "RECOVERED"]
    by_grade = {}
    for g in sorted({r["grade"] for r in rows}):
        o = [r for r in obs if r["grade"] == g]
        by_grade[g] = {"predicted": sum(1 for r in rows if r["grade"] == g), "observed": len(o),
                       "recovered": wilson(sum(1 for r in o if r["verdict"] == "RECOVERED"), len(o))}
    zs = [r["z"] for r in obs if "z" in r]
    return {"graded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule": pred["conventions"]["outcome_rule"],
            "counts": {"predicted": len(rows), "observed": len(obs), "recovered": len(rec),
                       "inconsistent": len(obs) - len(rec), "insufficient_data": len(rows) - len(obs)},
            "recovered_among_observed": wilson(len(rec), len(obs)),
            "by_grade": by_grade,
            "z_scores": {"n": len(zs), "mean": (sum(zs) / len(zs)) if zs else None,
                         "rms": math.sqrt(sum(z * z for z in zs) / len(zs)) if zs else None,
                         "note": "An rms near 1 means the quoted uncertainties are right; well above 1 means they are too small."},
            "eclipses": rows}


def main():
    if len(sys.argv) < 4:
        print("Usage: py grade_predictions.py <frozen-zip-or-predictions.json> <measurements.csv> <out.json>")
        sys.exit(1)
    pred = load_predictions(sys.argv[1])
    rep = grade(pred, pd.read_csv(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    c = rep["counts"]
    print("predicted %d, observed %d, recovered %d, inconsistent %d, insufficient data %d" % (
        c["predicted"], c["observed"], c["recovered"], c["inconsistent"], c["insufficient_data"]))
    print("Written: %s" % sys.argv[3])


if __name__ == "__main__":
    main()
