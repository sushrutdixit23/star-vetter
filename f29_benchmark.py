"""Blind benchmark of the light-curve model (f26_ebfit.py) on published TESS eclipsing binaries.

The systems, their published geometry and the pass rule were committed in
data/benchmarks/f29_preregistration.json BEFORE any of them was fitted. This script only reads that file.

What the fit is given, per system: the TESS SPOC light curve, the published period and time of primary eclipse
(the candidates get these from the pipeline). The eclipse duration and the secondary-eclipse phase are measured
from the light curve here, with the same f22 code the candidates went through, so the trust rule
(export_findings.e_reliable) can be applied exactly as for a candidate.

Usage:
  python f29_benchmark.py <root> [--only "MU Cas"] [--cadence 2|30] [--max-steps 6000] [--out FILE]
  python f29_benchmark.py <root> --merge DIR [--tag v2]   combine per-job files into data/processed/f29_benchmarks[_v2].json
  (add --noise v2 to a run to use the v2 noise model of f26_ebfit.py; name its --out file f29v2_*.json)
Light curves: data/benchmarks/lc/TIC<n>.npz (fetched with f13_ephemeris.load_or_fetch_lightcurves).
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import f22_eccentricity as f22
import f26_ebfit as f26
from export_findings import e_reliable

BTJD = 2457000.0


def degrade(t, f, s, cadence_min):
    """Average 2-minute data into blocks, as a full-frame-image light curve would be (same as f26.validate)."""
    if cadence_min <= 2:
        return t, f, s
    blk = np.floor((t - t.min()) / (cadence_min / 1440.0)).astype(np.int64)
    df = pd.DataFrame({"b": blk, "t": t, "f": f, "s": s}).groupby("b").agg(t=("t", "mean"), f=("f", "mean"), s=("s", "first"), n=("t", "size"))
    df = df[df["n"] >= 0.8 * cadence_min / 2.0]
    return df["t"].to_numpy(), df["f"].to_numpy(), df["s"].to_numpy()


def per_sector_norm(f, s):
    out = np.asarray(f, float).copy()
    for v in np.unique(s):
        m = s == v
        out[m] = out[m] / np.nanmedian(out[m])
    return out


def measure_primary(t, f, period, t0):
    """Primary depth and total duration from the folded, binned light curve (a stand-in for the BLS duration
    the candidates come with). Duration: contiguous width around the minimum below 1 - 0.1 * depth."""
    ph = ((t - t0) / period + 0.5) % 1.0 - 0.5
    for half in (0.03, 0.1, 0.25):
        sel = np.abs(ph) < half
        if sel.sum() < 50:
            continue
        edges = np.linspace(-half, half, 801)
        idx = np.digitize(ph[sel], edges)
        y = np.full(len(edges) + 1, np.nan)
        for b in np.unique(idx):
            y[b] = np.median(f[sel][idx == b])
        y = y[1:len(edges)]
        x = 0.5 * (edges[1:] + edges[:-1])
        good = np.isfinite(y)
        if good.sum() < 20:
            continue
        x, y = x[good], y[good]
        ys = pd.Series(y).rolling(5, center=True, min_periods=1).median().to_numpy()
        far = np.abs(ph) > min(0.45, 1.5 * half)
        out_lvl = np.median(f[far]) if far.sum() > 50 else 1.0
        k = int(np.argmin(ys))
        depth = float(out_lvl - ys[k])
        if depth <= 0:
            continue
        thr = out_lvl - 0.1 * depth
        lo = k
        while lo > 0 and ys[lo - 1] < thr:
            lo -= 1
        hi = k
        while hi < len(ys) - 1 and ys[hi + 1] < thr:
            hi += 1
        width = float(x[hi] - x[lo]) + (x[1] - x[0])
        if width < half:                      # the eclipse fills at most half the window
            return depth, max(width * period * 1.15, 0.02)
    return None, None


def prepare(t, f, s, period, t0):
    """Measured inputs: duration, f22 secondary assessment, depth ratio. Returns (inputs, detrended arrays)."""
    f = per_sector_norm(f, s)
    depth, dur = measure_primary(t, f, period, t0)
    if dur is None:
        return None
    td, fd, sd = f22.detrend(t, f, period, t0, dur, s)
    depth2, dur2 = measure_primary(td, fd, period, t0)
    if dur2 is not None:
        depth, dur = depth2, dur2
        td, fd, sd = f22.detrend(t, f, period, t0, dur, s)
    sec = f22.assess(td, fd, period, t0, dur, sd)
    ecosw_in = float(sec.get("ecosw") or 0.0)
    sd_ = sec.get("secondary_depth") or (sec.get("secondary") or {}).get("depth")
    ratio = float(sd_ / depth) if sd_ and depth else 0.3
    f22_short = {k: sec.get(k) for k in ("verdict", "ecosw", "ecosw_sigma", "secondary_phase", "secondary_depth", "secondary_snr")}
    return {"duration_days": float(dur), "primary_depth": float(depth), "depth_ratio": float(np.clip(ratio, 0.01, 2.0)),
            "ecosw_input": ecosw_in, "f22": f22_short}


def run_one(root, system, cadence, max_steps=6000, lc_dir=None, noise=None):
    lc_dir = Path(lc_dir) if lc_dir else root / "data" / "benchmarks" / "lc"
    t, f, s = f26.load_star(root, system["tic"], lc_dir)
    t, f, s = degrade(t, f, s, cadence)
    period, t0 = system["period"], system["t0_bjd"] - BTJD
    inp = prepare(t, f, s, period, t0)
    out = {"name": system["name"], "tic": system["tic"], "cadence_min": cadence, "sectors": sorted(int(x) for x in np.unique(s)),
           "reference": system["reference"], "truth": system["truth"]}
    if inp is None:
        out["status"] = "NO_PRIMARY_MEASURED"
        return out
    out["inputs"] = inp
    t1 = time.time()
    res = f26.fit_star(t, f, s, period, t0, inp["duration_days"], inp["ecosw_input"], inp["depth_ratio"],
                       steps=1500, until_converged=True, max_steps=max_steps, noise=noise)
    out["status"] = res["status"]
    if res["status"] != "OK":
        return out
    p = res["params"]
    out["fit"] = {k: p[k] for k in ("e", "esinw", "ecosw", "r1", "r2", "rsum", "k", "incl", "l3", "J", "omega_deg")}
    out["run"] = {k: res[k] for k in ("chi2_best", "acceptance", "autocorr_steps", "steps", "converged", "flags", "n_bins")}
    out["run"]["seconds"] = round(time.time() - t1, 1)
    out["trusted"] = bool(e_reliable(p, inp["f22"]))
    out["noise_model"] = res.get("noise_model", "v1")
    return out


def judge(row, rule):
    if row.get("status") != "OK":
        row["passed"] = False
        return row
    p, tr = row["fit"], row["truth"]
    row["checks"] = {
        "e": abs(p["e"]["median"] - tr["e"]) <= rule["e_abs"],
        "abs_esinw": abs(abs(p["esinw"]["median"]) - abs(tr["esinw"])) <= rule["abs_esinw_abs"],
        "ecosw": abs(p["ecosw"]["median"] - tr["ecosw"]) <= rule["ecosw_abs"],
        "r1": abs(p["r1"]["median"] / tr["r1"] - 1) <= rule["r_frac"],
        "r2": abs(p["r2"]["median"] / tr["r2"] - 1) <= rule["r_frac"],
        "incl": abs(p["incl"]["median"] - tr["incl"]) <= rule["incl_deg"],
    }
    row["passed"] = bool(all(row["checks"].values()))
    row["differences"] = {
        "e": p["e"]["median"] - tr["e"], "abs_esinw": abs(p["esinw"]["median"]) - abs(tr["esinw"]),
        "ecosw": p["ecosw"]["median"] - tr["ecosw"], "r1_frac": p["r1"]["median"] / tr["r1"] - 1,
        "r2_frac": p["r2"]["median"] / tr["r2"] - 1, "incl": p["incl"]["median"] - tr["incl"],
        # how far off, in units of OUR quoted 1-sigma (does the error bar cover the published value?)
        "e_sigma": (p["e"]["median"] - tr["e"]) / max(0.5 * (p["e"]["lo"] + p["e"]["hi"]), 1e-9),
        "r1_sigma": (p["r1"]["median"] - tr["r1"]) / max(0.5 * (p["r1"]["lo"] + p["r1"]["hi"]), 1e-9),
        "r2_sigma": (p["r2"]["median"] - tr["r2"]) / max(0.5 * (p["r2"]["lo"] + p["r2"]["hi"]), 1e-9),
        "incl_sigma": (p["incl"]["median"] - tr["incl"]) / max(0.5 * (p["incl"]["lo"] + p["incl"]["hi"]), 1e-9),
    }
    return row


def merge(root, parts_dir, tag=""):
    """tag "" merges f29_*.json into f29_benchmarks.json (noise model v1); tag "v2" merges f29v2_*.json into
    f29_benchmarks_v2.json, so a new noise model never overwrites the numbers the site is built on."""
    pre = json.loads((root / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"))
    rows = []
    for p in sorted(Path(parts_dir).rglob("f29%s_*.json" % tag)):
        d = json.loads(p.read_text(encoding="utf-8"))
        rows.extend(d["rows"] if "rows" in d else [d])
    rows = [judge(r, pre["pass_rule"]) for r in rows]
    order = {s["name"]: i for i, s in enumerate(pre["systems"])}
    rows.sort(key=lambda r: (order.get(r["name"], 99), r["cadence_min"]))
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "preregistration": "data/benchmarks/f29_preregistration.json (commit e186551)",
           "noise_model": tag or "v1", "pass_rule": pre["pass_rule"], "rows": rows,
           "summary": {"runs": len(rows), "passed": sum(r.get("passed", False) for r in rows),
                       "systems_passing_both_cadences": sorted({r["name"] for r in rows if all(x.get("passed") for x in rows if x["name"] == r["name"])})}}
    dest = root / "data" / "processed" / ("f29_benchmarks%s.json" % (("_" + tag) if tag else ""))
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    if "--merge" in args:
        out = merge(root, args[args.index("--merge") + 1], args[args.index("--tag") + 1] if "--tag" in args else "")
        print(json.dumps(out["summary"], indent=1))
        return
    pre = json.loads((root / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"))
    only = args[args.index("--only") + 1] if "--only" in args else None
    cads = [int(args[args.index("--cadence") + 1])] if "--cadence" in args else pre["method"]["cadences"]
    max_steps = int(args[args.index("--max-steps") + 1]) if "--max-steps" in args else 6000
    lc_dir = args[args.index("--lc-dir") + 1] if "--lc-dir" in args else None
    noise = args[args.index("--noise") + 1] if "--noise" in args else None
    rows = []
    for sys_ in pre["systems"]:
        if only and sys_["name"] != only:
            continue
        for c in cads:
            try:
                r = run_one(root, sys_, c, max_steps, lc_dir, noise)
            except Exception as e:  # noqa: BLE001 - visible, never silent
                r = {"name": sys_["name"], "tic": sys_["tic"], "cadence_min": c, "status": "ERROR", "error": repr(e),
                     "truth": sys_["truth"], "reference": sys_["reference"]}
            r = judge(r, pre["pass_rule"])
            rows.append(r)
            print("%s %d-min: %s passed=%s %s" % (r["name"], c, r["status"], r.get("passed"),
                                                   json.dumps(r.get("differences", {}), default=float)), flush=True)
    out_p = Path(args[args.index("--out") + 1]) if "--out" in args else root / "data" / "processed" / "f29_benchmarks_partial.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps({"rows": rows}, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
