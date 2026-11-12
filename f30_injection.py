"""Injection-recovery test of the light-curve model on the candidates' own noise (design registered in
data/benchmarks/f29_preregistration.json before any injection was run).

For a host candidate: its light curve divided by its own best-fit model leaves the real noise, gaps, trends and
cadence. A synthetic eclipsing binary with known geometry is multiplied in, and the whole candidate path is run
on it: duration measured from the fold, secondary assessed by f22, model fitted by f26, trust rule applied
(export_findings.e_reliable). The output says how biased the fits are, whether the quoted 68% intervals
contain the truth about 68% of the time, and whether the trust rule separates good from bad eccentricities.

Usage:
  python f30_injection.py <root> --host TIC --seed S --n N [--start K] [--max-steps 6000] [--lc-dir D] [--out FILE]
  python f30_injection.py <root> --merge DIR     -> data/processed/f30_injection.json
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import f26_ebfit as f26
import f29_benchmark as fb
from export_findings import e_reliable

HOSTS = (370553309, 318887646, 43785616)       # 30-min; 10+30-min; 2-min (registered: span the cadences)
QUANTITIES = ("e", "ecosw", "r1", "r2", "incl")


def smear_args(dt_days):
    """Exposure smearing for long cadences, as the fit itself assumes."""
    if dt_days < 0.004:
        return None, 1
    return float(dt_days), int(max(5, round(dt_days / 0.0014)) | 1)


def model_flux(t, s, p, period):
    out = np.ones_like(t)
    for v in np.unique(s):
        m = s == v
        dt = float(np.median(np.diff(np.sort(t[m])))) if m.sum() > 2 else 0.0014
        te, ni = smear_args(dt)
        out[m] = f26.ellc_lc(t[m], p, period, t_exp=te, n_int=ni)
    return out


def host_model_params(res):
    q = res["params"]
    e, w = q["e"]["median"], np.radians(q["omega_deg"]["median"])
    return {"t0": res["t0_btjd"], "rsum": q["rsum"]["median"], "k": q["k"]["median"], "cosi": np.cos(np.radians(q["incl"]["median"])),
            "J": q["J"]["median"], "fc": np.sqrt(e) * np.cos(w), "fs": np.sqrt(e) * np.sin(w), "l3": q["l3"]["median"],
            "u1": f26.U1_PRIOR[0], "u1b": f26.U1_PRIOR[0], "dP": 0.0}


def draw(rng):
    """One detached system with both eclipses: the registered ranges."""
    while True:
        rsum = rng.uniform(0.08, 0.30)
        k = rng.uniform(0.6, 1.0)
        e = rng.uniform(0.0, 0.4)
        w = rng.uniform(0, 2 * np.pi)
        if 1 - e < 1.5 * rsum:                       # keep the pair detached at periastron
            continue
        rho = max((1 - e * e) / (1 + e * np.sin(w)), (1 - e * e) / (1 - e * np.sin(w)))
        cosi = rng.uniform(0.0, 0.7 * rsum / rho)     # both eclipses at impact below 0.7 of the radius sum
        return {"rsum": rsum, "k": k, "cosi": cosi, "J": rng.uniform(0.4, 1.0), "fc": np.sqrt(e) * np.cos(w),
                "fs": np.sqrt(e) * np.sin(w), "l3": rng.uniform(0.0, 0.15), "u1": f26.U1_PRIOR[0], "u1b": f26.U1_PRIOR[0], "dP": 0.0}


def truth_summary(p):
    e = p["fc"] ** 2 + p["fs"] ** 2
    w = np.arctan2(p["fs"], p["fc"])
    r1 = p["rsum"] / (1 + p["k"])
    return {"e": float(e), "ecosw": float(e * np.cos(w)), "esinw": float(e * np.sin(w)), "r1": float(r1), "r2": float(p["rsum"] - r1),
            "rsum": float(p["rsum"]), "incl": float(np.degrees(np.arccos(p["cosi"]))), "J": float(p["J"]), "l3": float(p["l3"]),
            "omega_deg": float(np.degrees(w) % 360)}


def run(root, host, seed, n, start=0, max_steps=6000, lc_dir=None):
    fits = json.loads((root / "data" / "processed" / "f26_ebfit.json").read_text(encoding="utf-8"))["stars"]
    res = fits[str(host)]
    period, t0 = res["period_days"], res["t0_btjd"]
    t, f, s = f26.load_star(root, host, lc_dir)
    f = fb.per_sector_norm(f, s)
    noise = f / model_flux(t, s, host_model_params(res), period)
    rng = np.random.default_rng(seed)
    draws = [draw(rng) for _ in range(start + n)][start:]
    rows = []
    for j, p in enumerate(draws, start=start):
        p = dict(p, t0=t0)
        truth = truth_summary(p)
        row = {"host": host, "seed": seed, "index": j, "truth": truth}
        t1 = time.time()
        try:
            finj = noise * model_flux(t, s, p, period)
            inp = fb.prepare(t, finj, s, period, t0)
            if inp is None:
                row["status"] = "NO_PRIMARY_MEASURED"
            else:
                r = f26.fit_star(t, finj, s, period, t0, inp["duration_days"], inp["ecosw_input"], inp["depth_ratio"],
                                 steps=1500, until_converged=True, max_steps=max_steps)
                row["status"] = r["status"]
                row["inputs"] = inp
                if r["status"] == "OK":
                    q = r["params"]
                    row["fit"] = {k: q[k] for k in ("e", "ecosw", "esinw", "r1", "r2", "rsum", "incl", "l3", "J")}
                    row["trusted"] = bool(e_reliable(q, inp["f22"]))
                    row["converged"] = r["converged"]
                    row["steps"] = r["steps"]
                    row["flags"] = r["flags"]
        except Exception as e:  # noqa: BLE001 - visible, never silent
            row["status"] = "ERROR"
            row["error"] = repr(e)
        row["seconds"] = round(time.time() - t1, 1)
        rows.append(row)
        print("host %d #%d %s truth e=%.3f rsum=%.3f fit e=%s trusted=%s (%.0fs)" % (
            host, j, row["status"], truth["e"], truth["rsum"], row.get("fit", {}).get("e", {}).get("median"), row.get("trusted"), row["seconds"]), flush=True)
    return rows


def metrics(rows):
    ok = [r for r in rows if r.get("status") == "OK"]
    out = {"n_injected": len(rows), "n_fitted": len(ok), "by_quantity": {}}
    for q in QUANTITIES:
        err = np.array([r["fit"][q]["median"] - r["truth"][q] for r in ok])
        cover = np.array([r["fit"][q]["median"] - r["fit"][q]["lo"] <= r["truth"][q] <= r["fit"][q]["median"] + r["fit"][q]["hi"] for r in ok])
        cover95 = np.array([r["fit"][q]["p2.5"] <= r["truth"][q] <= r["fit"][q]["p97.5"] for r in ok])
        rel = q in ("r1", "r2")
        e_rel = np.array([(r["fit"][q]["median"] / r["truth"][q] - 1) for r in ok]) if rel else None
        out["by_quantity"][q] = {"median_error": float(np.median(err)) if len(err) else None,
                                 "median_abs_error": float(np.median(np.abs(err))) if len(err) else None,
                                 "median_abs_fractional_error": float(np.median(np.abs(e_rel))) if rel and len(ok) else None,
                                 "coverage_68": float(cover.mean()) if len(cover) else None,
                                 "coverage_95": float(cover95.mean()) if len(cover95) else None}
    good = lambda r: abs(r["fit"]["e"]["median"] - r["truth"]["e"]) <= 0.03  # noqa: E731
    acc = [r for r in ok if r.get("trusted")]
    rej = [r for r in ok if not r.get("trusted")]
    out["trust_rule"] = {"accepted": len(acc), "rejected": len(rej),
                         "accepted_good_fraction": float(np.mean([good(r) for r in acc])) if acc else None,
                         "rejected_good_fraction": float(np.mean([good(r) for r in rej])) if rej else None}
    # registered recalibration: does an rsum threshold separate good from bad e better than 0.25?
    best = None
    for thr in np.arange(0.12, 0.31, 0.01):
        a = [r for r in ok if r.get("inputs", {}).get("f22", {}).get("verdict") in ("ECCENTRIC", "CIRCULAR_WITHIN_ERRORS") and r["fit"]["rsum"]["median"] <= thr]
        if len(a) < 5:
            continue
        frac = float(np.mean([good(r) for r in a]))
        if frac >= 0.8 and (best is None or len(a) > best["n_accepted"]):
            best = {"rsum_max": round(float(thr), 2), "n_accepted": len(a), "good_fraction": frac}
    out["trust_rule"]["largest_rsum_threshold_with_80pc_good"] = best
    return out


def merge(root, parts_dir):
    rows = []
    for p in sorted(Path(parts_dir).rglob("f30_*.json")):
        rows.extend(json.loads(p.read_text(encoding="utf-8"))["rows"])
    rows.sort(key=lambda r: (r["host"], r["index"]))
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "design": "data/benchmarks/f29_preregistration.json, injection_recovery (commit e186551)",
           "e_good_definition": "|fitted e - injected e| <= 0.03",
           "overall": metrics(rows), "by_host": {str(h): metrics([r for r in rows if r["host"] == h]) for h in sorted({r["host"] for r in rows})},
           # not registered in advance, added when it became clear few injections reach the trust rule's f22 step:
           "by_true_rsum": {"rsum_le_0.25": metrics([r for r in rows if r["truth"]["rsum"] <= 0.25]),
                            "rsum_gt_0.25": metrics([r for r in rows if r["truth"]["rsum"] > 0.25])},
           "rows": rows}
    (root / "data" / "processed" / "f30_injection.json").write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")
    return out


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    if "--merge" in args:
        out = merge(root, args[args.index("--merge") + 1])
        print(json.dumps(out["overall"], indent=1))
        return
    host = int(args[args.index("--host") + 1])
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 29
    n = int(args[args.index("--n") + 1]) if "--n" in args else 4
    start = int(args[args.index("--start") + 1]) if "--start" in args else 0
    max_steps = int(args[args.index("--max-steps") + 1]) if "--max-steps" in args else 6000
    lc_dir = args[args.index("--lc-dir") + 1] if "--lc-dir" in args else None
    rows = run(root, host, seed, n, start, max_steps, lc_dir)
    out_p = Path(args[args.index("--out") + 1]) if "--out" in args else root / "data" / "processed" / ("f30_%d_%d.json" % (host, start))
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps({"rows": rows}, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
