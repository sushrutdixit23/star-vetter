"""Does the v2 likelihood itself prefer the wrong geometry, and how wide is the honest interval? (diagnosis, not a fix)

Regenerates one registered injection exactly (same host, seed and index as f30_injection.py) and either
  lnl      compares ln P at the optimiser's best fit with ln P at the TRUE geometry, with timing and noise parameters
           re-optimised at both, so the comparison is a fair profile;
  profile  maximises ln P over every other parameter on a grid of the radius sum, from four starts (best, truth and an
           inverted-ratio start for each: k -> 1/k, J -> 1/J; whether that is an exact symmetry twin is not tested here).
Noise mode "real" keeps the host's own residual noise (as the registered injections do); "white" replaces it by exactly
Gaussian noise at the same scatter, which is the closed-loop test: there the likelihood is correct by construction.
Nothing here changes f26_ebfit.py, which the registration freezes.

Usage: python diag_f34_likelihood.py lnl|profile HOST SEED INDEX real|white
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

import f26_ebfit as f26
import f29_benchmark as fb
import f30_injection as f30

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "benchmarks" / "f34_diagnosis"


def build(host, seed, index, mode):
    res = json.loads((ROOT / "data" / "processed" / "f26_ebfit.json").read_text(encoding="utf-8"))["stars"][str(host)]
    period, t0 = res["period_days"], res["t0_btjd"]
    t, f, s = f26.load_star(ROOT, host, ROOT / "data" / "physics_inputs")
    f = fb.per_sector_norm(f, s)
    noise = f / f30.model_flux(t, s, f30.host_model_params(res), period)
    rng = np.random.default_rng(seed)
    draws = [f30.draw(rng) for _ in range(index + 1)]
    p = dict(draws[index], t0=t0)
    truth = f30.truth_summary(p)
    if mode == "white":
        noise = 1.0 + np.random.default_rng(1000 + seed * 100 + index).normal(0, np.std(noise - 1.0), size=len(t))
    finj = noise * f30.model_flux(t, s, p, period)
    inp = fb.prepare(t, finj, s, period, t0)
    sec_phase = (0.5 + 2.0 * inp["ecosw_input"] / np.pi) % 1.0
    dur = inp["duration_days"]
    groups = f26.event_groups(f26.cut_events(t, finj, s, period, t0, dur, sec_phase), dur, gp=True)
    td, fd, sd = f26.detrend_local(t, finj, period, t0, dur, sec_phase, s)
    g1 = f26.bin_groups(td, fd, sd, period, t0, dur, sec_phase)
    b1 = f26.optimise(g1, period, t0, dur, inp["ecosw_input"], inp["depth_ratio"], noise="v1")
    best = f26.optimise(groups, period, t0, dur, inp["ecosw_input"], inp["depth_ratio"], noise="v2", x_init=[b1.x[:len(f26.PARAMS)]])
    npar = len(f26.PARAMS)
    tp = {"dt0": 0.0, "rsum": p["rsum"], "k": p["k"], "cosi": p["cosi"], "J": p["J"], "fc": p["fc"], "fs": p["fs"], "l3": p["l3"],
          "u1": p["u1"], "u1b": p["u1b"], "dP": 0.0}
    x_true = np.array([tp[k] for k in f26.PARAMS] + list(best.x[npar:]))
    return {"groups": groups, "period": period, "t0": t0, "truth": truth, "x_best": best.x, "x_true": x_true, "npar": npar}


NAN_FAILURES = [0]


def lnp(x, c):
    """ln P, or a large negative number where the model is impossible. f26 itself is frozen; its event model turns ellc's finite
    error sentinel (-DBL_MAX, overlapping stars) into NaN and the Cholesky solve then raises ValueError, so it is caught here and
    counted (see tests/test_ellc_overlap_sentinel.py)."""
    try:
        v = f26.log_prob_events(x, c["groups"], c["period"], c["t0"])
    except ValueError:
        NAN_FAILURES[0] += 1
        return -1e12
    return v if np.isfinite(v) else -1e12


def reoptimise(x, free, c, maxiter=600):
    def neg(v):
        y = x.copy()
        y[free] = v
        return -lnp(y, c)
    r = minimize(neg, x[free], method="Nelder-Mead", options={"maxiter": maxiter, "xatol": 1e-6, "fatol": 1e-4, "adaptive": True})
    y = x.copy()
    y[free] = r.x
    return -r.fun, y


def cmd_lnl(host, seed, index, mode):
    c = build(host, seed, index, mode)
    npar = c["npar"]
    free = [0, 10] + list(range(npar, len(c["x_best"])))              # timing and noise only; geometry fixed
    ll_best, _ = reoptimise(c["x_best"], free, c)
    ll_true, _ = reoptimise(c["x_true"], free, c)
    bp = dict(zip(f26.PARAMS, c["x_best"][:npar]))
    out = {"host": host, "seed": seed, "index": index, "mode": mode, "truth": c["truth"],
           "best_geometry": {k: float(bp[k]) for k in ("rsum", "k", "cosi", "J", "l3")},
           "lnP_best": float(ll_best), "lnP_truth": float(ll_true), "delta_lnP_best_minus_truth": float(ll_best - ll_true),
           "note": "about 5.5 (+-2.3) is what 11 free parameters give on correct data; much more means the data prefer another geometry"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ("lnl_%d_%d_%d_%s.json" % (host, seed, index, mode))).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))


def cmd_profile(host, seed, index, mode):
    c = build(host, seed, index, mode)
    npar = c["npar"]
    iR = f26.PARAMS.index("rsum")
    free = [f26.PARAMS.index(k) for k in ("k", "cosi", "J", "fc", "fs", "l3")] + list(range(npar, len(c["x_best"])))

    def swapped(x):
        y = x.copy()
        y[f26.PARAMS.index("k")] = 1.0 / x[f26.PARAMS.index("k")]
        y[f26.PARAMS.index("J")] = 1.0 / max(x[f26.PARAMS.index("J")], 1e-3)
        return y

    grid = [float(v) for v in np.round(np.linspace(0.04, 0.30, 14), 4)]
    prof = []
    for rs in grid:
        top = -np.inf
        for x0 in (c["x_best"], c["x_true"], swapped(c["x_best"]), swapped(c["x_true"])):
            x0 = x0.copy()
            x0[iR] = rs
            val, _ = reoptimise(x0, free, c, maxiter=450)
            top = max(top, val)
        prof.append((rs, float(top)))
        print("rsum %.4f  profile lnP %.2f" % (rs, top), flush=True)
    m = max(v for _, v in prof)
    out = {"host": host, "seed": seed, "index": index, "mode": mode, "truth": c["truth"], "profile": prof, "max_lnP": m,
           "rsum_within_0.5": [r for r, v in prof if v >= m - 0.5], "rsum_within_2": [r for r, v in prof if v >= m - 2.0],
           "rsum_within_9": [r for r, v in prof if v >= m - 9.0],
           "nan_failures_caught": NAN_FAILURES[0], "note": "Nelder-Mead from four starts: a lower bound on the profile; dips between high points are optimiser misses, not data"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ("profile_%d_%d_%d_%s.json" % (host, seed, index, mode))).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("likelihood evaluations that hit the NaN bug and were caught:", NAN_FAILURES[0])
    print("rsum within 0.5 / 2 / 9 of the maximum:", out["rsum_within_0.5"], out["rsum_within_2"], out["rsum_within_9"])


if __name__ == "__main__":
    t_start = time.time()
    cmd, host, seed, index, mode = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    {"lnl": cmd_lnl, "profile": cmd_profile}[cmd](host, seed, index, mode)
    print("seconds %.0f" % (time.time() - t_start))
