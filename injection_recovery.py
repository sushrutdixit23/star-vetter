import sys
import json
import time
import argparse
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Injection-recovery for the Star Vetter gates.
#
# Question: if a real eclipsing binary of known period and depth sat in one of
# the stars of the sample, how often would this pipeline's own statistical
# gates (f3i_vet.process_one_star, unchanged) let it through?
#
# Method, per star:
#   1. Fetch the light curve with the survey's own code (f2c process_one_target)
#      so it is flattened and cleaned exactly like the survey's.
#   2. Keep only stars where the UNMODIFIED light curve fails the gates, i.e.
#      the situation in which a hidden binary would have to be found.
#   3. Multiply in a synthetic eclipsing binary (trapezoid eclipses, circular
#      orbit, optional secondary at phase 0.5) drawn from the prior below, and
#      run the real vetting function. A star "passes" under exactly the rule the
#      survey uses to forward stars to the novelty step:
#      status == OK and depth_flagged_implausible is False.
#   4. Also run the same function on a BLOCK-SHUFFLED copy of the real light
#      curve (1-day chunks put in random order). That keeps the real noise and
#      systematics but destroys periodicity, so its pass rate is the rate at
#      which the gates let through something that is not a periodic signal.
#
# What this does NOT test: the pixel check (it needs pixel data), eccentric
# orbits, limb-darkened eclipse shapes, and anything the injection prior does
# not cover. Recall depends on the prior (period, depth), so it is reported in
# bins, not as one number. Results are for the stars actually drawn.

PRIOR = {
    "period_days": [0.65, 39.8],         # the pipeline's own BLS search range
    "primary_depth": [0.002, 0.5],       # 2-500 ppt, log-uniform (Kostov table 3 spans 1-848 ppt)
    "total_mass_msun": [0.8, 3.0],
    "radius_sum_rsun": [0.8, 3.0],
    "impact_parameter": [0.0, 0.9],
    "ingress_fraction": [0.2, 1.0],      # 1.0 = V-shaped
    "secondary_probability": 0.5,
    "secondary_depth_ratio": [0.1, 1.0],
}
RECOVERY_TOL = 0.02                       # period match tolerance (relative)
SHUFFLE_BLOCK_DAYS = 1.0
MAX_POINTS = 60000                        # keeps one BLS run under a minute
SEED = 20261108
PERIOD_EDGES = [0.0, 1.0, 2.0, 5.0, 10.0, 40.0]
PERIOD_LABELS = ["<1 d", "1-2 d", "2-5 d", "5-10 d", ">10 d"]
DEPTH_EDGES = [0.0, 0.005, 0.02, 0.1, 1.0]
DEPTH_LABELS = ["<0.5%", "0.5-2%", "2-10%", ">10%"]
GATE_FLAGS = ["too_few_eclipses", "insufficient_intransit_points", "below_noise_floor",
              "robust_depth_mismatch", "noisy_photometry", "inhomogeneous_photometry",
              "depth_too_small", "non_finite_bls_result"]
RESULT_COLUMNS = ["tic", "stratum", "tmag", "author", "n_points", "span_days", "kind", "k", "seed",
                  "period", "t0", "depth1", "depth2", "duration", "ingress_frac", "searchable",
                  "status", "passed", "bls_period", "bls_snr", "n_eclipses", "outcome"] + GATE_FLAGS


def z95():
    return 1.959964


def wilson(k, n, z=None):
    z = z or z95()
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2.0 * n)) / d
    h = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / d
    return (float(max(0.0, c - h)), float(min(1.0, c + h)))


def rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": int(k), "n": int(n), "rate": (float(k / n) if n else None), "lo": lo, "hi": hi}


# --------------------------------------------------------------------------
# pure functions (unit-tested without any network)
# --------------------------------------------------------------------------

def draw_injection(rng, span_days):
    """One synthetic binary from PRIOR. Returns a dict of parameters."""
    pr = PRIOR
    period = float(np.exp(rng.uniform(np.log(pr["period_days"][0]), np.log(pr["period_days"][1]))))
    depth1 = float(np.exp(rng.uniform(np.log(pr["primary_depth"][0]), np.log(pr["primary_depth"][1]))))
    mtot = float(rng.uniform(*pr["total_mass_msun"]))
    a_rsun = 4.2084 * (mtot * period ** 2) ** (1.0 / 3.0)
    for _ in range(100):
        rsum = float(rng.uniform(*pr["radius_sum_rsun"]))
        if rsum < 0.9 * a_rsun:
            break
    else:
        rsum = 0.5 * a_rsun
    b = float(rng.uniform(*pr["impact_parameter"]))
    arg = min(1.0, (rsum / a_rsun) * np.sqrt(max(1e-6, 1.0 - b * b)))
    duration = float(period / np.pi * np.arcsin(arg))
    ingress = float(rng.uniform(*pr["ingress_fraction"]))
    depth2 = 0.0
    if rng.uniform() < pr["secondary_probability"]:
        depth2 = float(depth1 * rng.uniform(*pr["secondary_depth_ratio"]))
    t0_frac = float(rng.uniform())
    return {"period": period, "depth1": depth1, "depth2": depth2, "duration": duration,
            "ingress_frac": ingress, "t0_frac": t0_frac,
            "searchable": bool(period <= span_days / 2.0)}


def eclipse_model(t, period, t0, duration, ingress_frac, depth1, depth2=0.0):
    """Fractional dimming (>= 0) of a circular-orbit binary: trapezoid eclipses
    of full duration `duration`, ingress and egress each ingress_frac x half the
    duration, secondary at phase 0.5."""
    t = np.asarray(t, dtype=float)
    half = duration / 2.0
    ti = max(ingress_frac * half, 1e-9)
    out = np.zeros_like(t)
    for centre, depth in ((t0, depth1), (t0 + period / 2.0, depth2)):
        if depth <= 0:
            continue
        x = np.abs(((t - centre + period / 2.0) % period) - period / 2.0)
        out += depth * np.clip((half - x) / ti, 0.0, 1.0)
    return out


def inject(flux, t, params, t_start):
    """flux x (1 - model). t0 is placed inside the first period of the data."""
    t0 = t_start + params["t0_frac"] * params["period"]
    model = eclipse_model(t, params["period"], t0, params["duration"], params["ingress_frac"],
                          params["depth1"], params["depth2"])
    return np.asarray(flux, dtype=float) * (1.0 - model), float(t0)


def block_shuffle(flux, t, rng, block_days=SHUFFLE_BLOCK_DAYS):
    """Cut the flux sequence into chunks that span ~block_days each and put the
    chunks in random order; the times stay as they were. Same values, same
    local noise, no periodicity."""
    flux = np.asarray(flux, dtype=float)
    t = np.asarray(t, dtype=float)
    dt = np.median(np.diff(t)) if len(t) > 1 else 1.0
    n = int(max(5, round(block_days / dt)))
    chunks = [flux[i:i + n] for i in range(0, len(flux), n)]
    order = rng.permutation(len(chunks))
    return np.concatenate([chunks[i] for i in order])


def classify_outcome(passed, bls_period, true_period, tol=RECOVERY_TOL):
    """missed / exact / alias (half or double) / wrong (passed, unrelated period)."""
    if not passed:
        return "missed"
    if not (bls_period and np.isfinite(bls_period) and true_period > 0):
        return "wrong"
    r = bls_period / true_period
    if abs(r - 1.0) < tol:
        return "exact"
    if abs(r - 2.0) < 2.0 * tol or abs(r - 0.5) < 0.5 * tol:
        return "alias"
    return "wrong"


def passes_gates(res):
    return bool(res.get("status") == "OK" and res.get("depth_flagged_implausible") is False)


def star_rng(seed, tic, salt=0):
    return np.random.default_rng([int(seed), int(tic), int(salt)])


def choose_stars(manifest, vetting, edges, per_stratum, seed=SEED, max_points=MAX_POINTS):
    """Seeded draw of stars per Tmag stratum from usable stars whose unmodified
    light curve is reliable but fails the gates."""
    m = manifest[manifest["status"] == "OK"].copy()
    m["TIC"] = m["TIC"].astype(int)
    v = vetting.copy()
    v["TIC"] = v["TIC"].astype(int)
    v = v[v["status"] == "OK"]
    v = v.assign(base_pass=(v["depth_flagged_implausible"] == False))   # noqa: E712
    m = m.merge(v[["TIC", "base_pass"]], on="TIC", how="inner")
    m = m[(~m["base_pass"].astype(bool)) & (m["n_points"] <= max_points)]
    m["stratum"] = np.searchsorted(np.asarray(edges, dtype=float), m["Tmag"].astype(float), side="left")
    rng = np.random.default_rng(seed)
    picks = []
    for h in sorted(m["stratum"].unique()):
        pool = m[m["stratum"] == h]
        take = min(per_stratum, len(pool))
        idx = rng.choice(pool.index.to_numpy(), size=take, replace=False)
        picks.append(pool.loc[np.sort(idx)])
    return pd.concat(picks).reset_index(drop=True)


def build_report(res, now=None):
    """results DataFrame (RESULT_COLUMNS) -> JSON-able report."""
    inj = res[res["kind"] == "inject"]
    shuf = res[res["kind"] == "shuffle"]
    srch = inj[inj["searchable"].astype(bool)].copy()
    srch["detected"] = srch["outcome"].isin(["exact", "alias"])
    srch["exact"] = srch["outcome"] == "exact"

    def cell(df):
        return {"n": int(len(df)),
                "detected": rate(int(df["detected"].sum()), len(df)),
                "exact_period": rate(int(df["exact"].sum()), len(df))}

    by_stratum = []
    for h, g in srch.groupby("stratum"):
        row = cell(g)
        row["stratum"] = int(h)
        row["stars"] = int(g["tic"].nunique())
        by_stratum.append(row)

    srch["pbin"] = pd.cut(srch["period"], PERIOD_EDGES, labels=PERIOD_LABELS, right=False)
    srch["dbin"] = pd.cut(srch["depth1"], DEPTH_EDGES, labels=DEPTH_LABELS, right=False)
    by_period = [dict(cell(srch[srch["pbin"] == b]), bin=b) for b in PERIOD_LABELS]
    by_depth = [dict(cell(srch[srch["dbin"] == b]), bin=b) for b in DEPTH_LABELS]

    missed = srch[(srch["outcome"] == "missed") & (srch["status"] == "OK")]
    miss_reasons = []
    for g in GATE_FLAGS:
        if g in missed.columns:
            k = int(missed[g].fillna(False).astype(bool).sum())
            miss_reasons.append({"gate": g, "missed_flagged": rate(k, int(len(missed)))})
    wrong = int((inj["outcome"] == "wrong").sum())
    null_pass = int(shuf["passed"].astype(bool).sum())
    out = {
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prior": PRIOR,
        "method": {
            "gates": "f3i_vet.process_one_star, unchanged; pass = status OK and not depth_flagged_implausible",
            "stars": "usable, reliable, unmodified light curve fails the gates, at most %d points" % MAX_POINTS,
            "recovery": "detected = passed with BLS period within %.0f percent of the true period or of half / double it; exact = true period only" % (100 * RECOVERY_TOL),
            "shuffle": "real light curve cut into %.1f-day chunks placed in random order" % SHUFFLE_BLOCK_DAYS,
            "not_tested": ["pixel check", "eccentric orbits", "limb-darkened eclipse shapes", "periods beyond half the data span"],
        },
        "counts": {
            "stars": int(res["tic"].nunique()),
            "injections": int(len(inj)),
            "searchable_injections": int(len(srch)),
            "shuffle_runs": int(len(shuf)),
        },
        "searchable_fraction": rate(int(len(srch)), int(len(inj))),
        "recall_overall": cell(srch),
        "recall_by_tmag_stratum": by_stratum,
        "recall_by_period": by_period,
        "recall_by_depth": by_depth,
        "miss_reasons": miss_reasons,
        "passed_with_unrelated_period": rate(wrong, int(len(inj))),
        "false_alarm_shuffle": rate(null_pass, int(len(shuf))),
        "notes": [
            "Recall depends on the injection prior; compare bins, do not quote the overall figure as 'the' recall.",
            "Injections beyond half the data span cannot be found by construction and are excluded from recall (see searchable_fraction).",
            "False-alarm rate is for gate passes from non-periodic noise in these real light curves; it does not count real non-eclipsing variables.",
        ],
    }
    return out


# --------------------------------------------------------------------------
# running (network + CPU)
# --------------------------------------------------------------------------

def install_offline_resolver(pop):
    """Sandbox workaround: the MAST name resolver is unreachable from some
    networks. Resolve 'TIC <n>' from the survey's own list instead."""
    import astroquery.mast.utils as mu
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    t2 = pop.set_index("TIC")
    orig = mu.resolve_object

    def patched(name, *a, **k):
        n = str(name).strip()
        if n.upper().startswith("TIC"):
            r = t2.loc[int(n.split()[1])]
            return SkyCoord(float(r.RAJ2000) * u.deg, float(r.DEJ2000) * u.deg)
        return orig(name, *a, **k)

    mu.resolve_object = patched


def run_star(row, work, n_inj, n_null, f2, f3):
    tic, tmag = int(row.TIC), float(row.Tmag)
    lc_dir, pl_dir, tmp_dir = work / "lc", work / "plots", work / "tmp"
    for d in (lc_dir, pl_dir, tmp_dir):
        d.mkdir(parents=True, exist_ok=True)
    path = lc_dir / ("TIC%d.csv" % tic)
    if not path.exists():
        r = f2.process_one_target(tic, tmag, lc_dir, pl_dir)
        if r["status"] != "OK":
            return []
    df = pd.read_csv(path)
    t, flux, err = df["time"].to_numpy(), df["flux"].to_numpy(), df["flux_err"].to_numpy()
    span = float(t.max() - t.min())
    rows = []

    def vet(kind, k, flux_k, extra):
        tmp = tmp_dir / ("TIC%d_%s%d.csv" % (tic, kind, k))
        pd.DataFrame({"time": t, "flux": flux_k, "flux_err": err}).to_csv(tmp, index=False)
        res = f3.process_one_star(tic, tmp, pl_dir)
        tmp.unlink(missing_ok=True)
        passed = passes_gates(res)
        base = {"tic": tic, "stratum": int(row.stratum), "tmag": tmag, "author": row.author_used,
                "n_points": len(t), "span_days": span, "kind": kind, "k": k,
                "status": res.get("status"), "passed": passed,
                "bls_period": res.get("bls_period"), "bls_snr": res.get("bls_snr"),
                "n_eclipses": res.get("n_eclipses_observed")}
        for g in GATE_FLAGS:
            base[g] = res.get(g)
        base.update(extra)
        return base

    for k in range(n_inj):
        seed_k = int(star_rng(SEED, tic, k + 1).integers(1, 2 ** 31))
        rng = np.random.default_rng(seed_k)
        p = draw_injection(rng, span)
        f_inj, t0 = inject(flux, t, p, float(t.min()))
        r = vet("inject", k, f_inj, {"seed": seed_k, "period": p["period"], "t0": t0, "depth1": p["depth1"],
                                      "depth2": p["depth2"], "duration": p["duration"],
                                      "ingress_frac": p["ingress_frac"], "searchable": p["searchable"]})
        r["outcome"] = classify_outcome(r["passed"], r["bls_period"], p["period"])
        rows.append(r)
    for k in range(n_null):
        seed_k = int(star_rng(SEED, tic, 1000 + k).integers(1, 2 ** 31))
        rng = np.random.default_rng(seed_k)
        r = vet("shuffle", k, block_shuffle(flux, t, rng), {"seed": seed_k, "searchable": True})
        r["outcome"] = "pass" if r["passed"] else "clean"
        rows.append(r)
    return rows


def cmd_run(args):
    root = Path(args.root).resolve()
    proc = root / "data" / "processed"
    work = root / "data" / "injection"
    work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    edges = json.loads((root / "site" / "public" / "data" / "audit.json").read_text(encoding="utf-8"))["frame"]["strata_inner_edges"]
    manifest = pd.read_csv(proc / "f2c_manifest.csv")
    vetting = pd.read_csv(proc / "f3i_vetting_results.csv")
    stars = choose_stars(manifest, vetting, edges, args.stars_per_stratum)
    pop = pd.read_parquet(proc / "table2_unvetted.parquet", columns=["TIC", "RAJ2000", "DEJ2000"])
    if args.offline_resolver:
        install_offline_resolver(pop)
    import f2c_fetch_lightcurves as f2
    import f3i_vet as f3
    f3.make_plot = lambda *a, **k: None     # plots are not needed here

    shard, nshard = args.shard
    out_csv = work / ("results_shard%d.csv" % shard)
    done = set()
    if out_csv.exists():
        done = set(pd.read_csv(out_csv)["tic"].astype(int))
    mine = stars[(np.arange(len(stars)) % nshard) == shard]
    print("Shard %d/%d: %d stars (%d already done)" % (shard, nshard, len(mine), len(done & set(mine.TIC.astype(int)))))
    write_header = not out_csv.exists()
    for i, row in enumerate(mine.itertuples(index=False)):
        if int(row.TIC) in done:
            continue
        t0 = time.time()
        try:
            rows = run_star(row, work, args.injections, args.nulls, f2, f3)
        except Exception as e:     # one bad star must not stop the run
            print("  TIC %d failed: %s" % (row.TIC, str(e)[:120]))
            continue
        if rows:
            pd.DataFrame(rows).reindex(columns=RESULT_COLUMNS).to_csv(out_csv, mode="a", header=write_header, index=False,
                                                                    lineterminator="\n")
            write_header = False
        print("  [%d/%d] TIC %d stratum %d: %d runs in %.0fs" % (i + 1, len(mine), row.TIC, row.stratum, len(rows), time.time() - t0), flush=True)


def cmd_report(args):
    root = Path(args.root).resolve()
    work = root / "data" / "injection"
    shards = sorted(work.glob("results_shard*.csv"))
    if not shards:
        print("ERROR: no result shards under %s - run the 'run' step first." % work)
        sys.exit(1)
    res = pd.concat([pd.read_csv(p) for p in shards], ignore_index=True)
    res = res.drop_duplicates(["tic", "kind", "k"]).reindex(columns=RESULT_COLUMNS)
    res.to_csv(root / "data" / "processed" / "injection_results.csv", index=False, lineterminator="\n")
    rep = build_report(res)
    out = root / "site" / "public" / "data" / "recovery.json"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, indent=2)
        f.write("\n")
    c = rep["counts"]
    ro = rep["recall_overall"]
    fa = rep["false_alarm_shuffle"]
    print("Stars %d, injections %d (%d searchable), shuffled runs %d" % (c["stars"], c["injections"], c["searchable_injections"], c["shuffle_runs"]))
    print("Detected (searchable): %d/%d = %.1f%% (95%% %.1f-%.1f%%)" % (ro["detected"]["k"], ro["detected"]["n"], 100 * (ro["detected"]["rate"] or 0), 100 * ro["detected"]["lo"], 100 * ro["detected"]["hi"]))
    print("False alarm on shuffled light curves: %d/%d = %.1f%%" % (fa["k"], fa["n"], 100 * (fa["rate"] or 0)))
    print("Written: %s" % out)


def main():
    ap = argparse.ArgumentParser(description="Injection-recovery for the Star Vetter gates")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch light curves, inject, vet (resumable)")
    r.add_argument("root")
    r.add_argument("--stars-per-stratum", type=int, default=12)
    r.add_argument("--injections", type=int, default=6)
    r.add_argument("--nulls", type=int, default=2)
    r.add_argument("--shard", type=lambda s: tuple(int(x) for x in s.split("/")), default=(0, 1),
                   help="i/n: run every n-th star starting at i")
    r.add_argument("--offline-resolver", action="store_true", help="resolve TIC names from the survey list (for networks where the MAST resolver is unreachable)")
    r.set_defaults(fn=cmd_run)
    p = sub.add_parser("report", help="merge shards, write injection_results.csv and recovery.json")
    p.add_argument("root")
    p.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
