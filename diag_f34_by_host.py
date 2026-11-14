"""Where do the v2 injection intervals fail? Per-host calibration and error correlations from the registered v2 injection results.

Reads data/processed/f30_injection_v2.json (or the path given) and writes data/benchmarks/f34_diagnosis/by_host.json.
For every fitted injection, z = (fitted median - injected truth) / (half the quoted 68% interval). A calibrated interval
has median |z| near 0.67 and a 95% interval that contains the truth 95% of the time. Also writes the Spearman correlation
between the errors (fit - truth) of the geometry parameters: strong correlations mean the fit slides along a degenerate
direction. Usage: python diag_f34_by_host.py [results.json]
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent
QUANTITIES = ("e", "ecosw", "esinw", "r1", "r2", "rsum", "incl", "l3", "J")
CORR = ("r1", "r2", "rsum", "incl", "J", "l3", "e")


def zscore(row, q):
    f = row["fit"][q]
    return (f["median"] - row["truth"][q]) / (0.5 * (f["lo"] + f["hi"]))


def summarise(rows):
    out = {"n": len(rows), "by_quantity": {}}
    for q in QUANTITIES:
        z = np.array([zscore(r, q) for r in rows])
        cov95 = float(np.mean([r["fit"][q]["p2.5"] <= r["truth"][q] <= r["fit"][q]["p97.5"] for r in rows]))
        out["by_quantity"][q] = {"median_abs_z": float(np.median(np.abs(z))), "fraction_abs_z_below_1": float(np.mean(np.abs(z) < 1)),
                                 "coverage_95": cov95,
                                 "median_error": float(np.median([r["fit"][q]["median"] - r["truth"][q] for r in rows]))}
    return out


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "processed" / "f30_injection_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"]
    out = {"source": path.name, "noise_model": data.get("noise_model"), "status_by_host": {}, "hosts": {}}
    for h in sorted({r["host"] for r in rows}):
        sub = [r for r in rows if r["host"] == h]
        counts = {}
        for r in sub:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        out["status_by_host"][str(h)] = counts
        ok = [r for r in sub if r["status"] == "OK"]
        out["hosts"][str(h)] = summarise(ok) if ok else {"n": 0}
    ok = [r for r in rows if r["status"] == "OK"]
    out["all_fitted"] = summarise(ok)
    err = {q: np.array([r["fit"][q]["median"] - r["truth"][q] for r in ok]) for q in CORR}
    out["error_correlation_spearman"] = {a: {b: float(spearmanr(err[a], err[b])[0]) for b in CORR} for a in CORR}
    dest = ROOT / "data" / "benchmarks" / "f34_diagnosis"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "by_host.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    for h, v in out["hosts"].items():
        if v["n"]:
            print("host %s n=%d  median|z| r2 %.2f rsum %.2f incl %.2f e %.2f  cov95 r2 %.2f incl %.2f e %.2f" % (
                h, v["n"], v["by_quantity"]["r2"]["median_abs_z"], v["by_quantity"]["rsum"]["median_abs_z"], v["by_quantity"]["incl"]["median_abs_z"],
                v["by_quantity"]["e"]["median_abs_z"], v["by_quantity"]["r2"]["coverage_95"], v["by_quantity"]["incl"]["coverage_95"], v["by_quantity"]["e"]["coverage_95"]))
        else:
            print("host %s: no fitted injections (%s)" % (h, out["status_by_host"][h]))


if __name__ == "__main__":
    main()
