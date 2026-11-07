import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Audit of the Kostov et al. 2025 UNVETTED eclipsing-binary list.
#
# What this answers: of the stars in that list, what fraction yield a usable
# light curve, pass this pipeline's statistical gates, and are confirmed
# on-target at the pixel level - with 95% intervals, per brightness stratum
# and for the whole list.
#
# Sampling frame: every TIC in f2c_manifest.csv (the one row per star ever
# drawn). The draw is a seeded random sample stratified by Tmag (f1b_sample.py,
# near-equal allocation per brightness fifth), so the sample is NOT
# proportional to the list. Population-wide figures therefore weight each
# stratum by its share of the full list (table2_unvetted.parquet), with the
# strata fixed here from the full list's own Tmag quintiles.
#
# Two honest limits, repeated in audit.json:
#  - a rate here is a rate of what THIS pipeline recovers, not of real
#    eclipsing binaries; the recall on known EBs is low (benchmark.json), so
#    the raw rates are lower bounds;
#  - the recall-corrected figure uses the 60-star benchmark and assumes the
#    unvetted stars are as easy to recover as the vetted benchmark stars,
#    which is probably optimistic. It is provisional; recovery.json gives a second
#    estimate from injected binaries.

Z95 = 1.959964
N_STRATA = 5
PERIOD_EDGES = [0.0, 1.0, 2.0, 5.0, 10.0, 20.0, float("inf")]
PERIOD_LABELS = ["<1 d", "1-2 d", "2-5 d", "5-10 d", "10-20 d", ">20 d"]
MC_DRAWS = 20000
MC_SEED = 20261108


def wilson(k, n, z=Z95):
    """Wilson score interval for k successes in n trials. (0, 1) if n == 0."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * np.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))


def strata_edges(pop_tmag, n_strata=N_STRATA):
    """Inner cut points: the population's own Tmag quantiles."""
    qs = np.linspace(0.0, 1.0, n_strata + 1)[1:-1]
    return [float(x) for x in np.quantile(np.asarray(pop_tmag, dtype=float), qs)]


def assign_stratum(tmag, edges):
    """0..len(edges). A value on an edge belongs to the lower stratum."""
    return np.searchsorted(np.asarray(edges, dtype=float), np.asarray(tmag, dtype=float), side="left")


def stratum_label(i, edges):
    lo = None if i == 0 else edges[i - 1]
    hi = None if i == len(edges) else edges[i]
    if lo is None:
        return "Tmag <= %.2f" % hi
    if hi is None:
        return "Tmag > %.2f" % lo
    return "Tmag %.2f-%.2f" % (lo, hi)


def posterior_draws(counts, sizes, weights, rng, draws=MC_DRAWS):
    """Draws of the population rate sum_h W_h p_h with p_h ~ Beta(k+.5, n-k+.5)
    (Jeffreys prior), one independent beta per stratum."""
    total = np.zeros(draws)
    for k, n, w in zip(counts, sizes, weights):
        total += w * rng.beta(k + 0.5, n - k + 0.5, size=draws)
    return total


def summarize(draws):
    lo, med, hi = np.percentile(draws, [2.5, 50.0, 97.5])
    return {"median": float(med), "lo": float(lo), "hi": float(hi)}


def build_audit(manifest, vetting, novelty, pixel, pop_tmag, benchmark, now=None):
    """Pure function: DataFrames in, JSON-able dict out.

    manifest: TIC, Tmag, status          (the sampling frame)
    vetting:  TIC, status                (f3i; status OK = reliable data)
    novelty:  TIC, verdict, bls_period   (f4f; one row per star that passed the gates)
    pixel:    TIC, role, verdict         (diag_pixel_results_v2)
    pop_tmag: Tmag of every star in the full list
    benchmark: dict from benchmark.json (funnel + by_tmag)
    """
    pop_tmag = np.asarray(pop_tmag, dtype=float)
    pop_tmag = pop_tmag[np.isfinite(pop_tmag)]
    edges = strata_edges(pop_tmag)
    n_s = len(edges) + 1
    pop_counts = np.bincount(assign_stratum(pop_tmag, edges), minlength=n_s)
    weights = pop_counts / pop_counts.sum()

    frame = manifest.copy()
    frame["TIC"] = frame["TIC"].astype(int)
    frame = frame.drop_duplicates("TIC")
    frame = frame[np.isfinite(frame["Tmag"].astype(float))].copy()
    frame["stratum"] = assign_stratum(frame["Tmag"].astype(float), edges)
    frame["usable"] = frame["status"] == "OK"

    tics_usable = set(frame.loc[frame["usable"], "TIC"])

    vet = vetting.copy()
    vet["TIC"] = vet["TIC"].astype(int)
    reliable = set(vet.loc[vet["status"] == "OK", "TIC"]) & tics_usable

    nov = novelty.copy()
    nov["TIC"] = nov["TIC"].astype(int)
    nov = nov[nov["TIC"].isin(tics_usable)]
    passed = set(nov["TIC"])
    novel = set(nov.loc[nov["verdict"] == "NOVEL", "TIC"])
    outside_frame = int(len(set(novelty["TIC"].astype(int)) - tics_usable))

    pix = pixel.copy()
    pix["TIC"] = pix["TIC"].astype(int)
    pix = pix[pix["role"] == "candidate"]
    pix = pix[pix["TIC"].isin(tics_usable)]
    pixel_checked = set(pix["TIC"])
    on_target = set(pix.loc[pix["verdict"] == "ON_TARGET", "TIC"])

    frame["reliable"] = frame["TIC"].isin(reliable)
    frame["passed"] = frame["TIC"].isin(passed)
    frame["novel"] = frame["TIC"].isin(novel)
    frame["pixel_checked"] = frame["TIC"].isin(pixel_checked)
    frame["on_target"] = frame["TIC"].isin(on_target)

    rows = []
    for h in range(n_s):
        f = frame[frame["stratum"] == h]
        n = int(len(f))
        u = int(f["usable"].sum())
        g = int(f["passed"].sum())
        o = int(f["on_target"].sum())
        rows.append({
            "stratum": h,
            "label": stratum_label(h, edges),
            "population": int(pop_counts[h]),
            "weight": float(weights[h]),
            "sampled": n,
            "usable": u,
            "reliable": int(f["reliable"].sum()),
            "passed_gates": g,
            "novel": int(f["novel"].sum()),
            "pixel_checked": int(f["pixel_checked"].sum()),
            "on_target": o,
            "usable_rate": _rate(u, n),
            "passed_per_usable": _rate(g, u),
            "on_target_per_usable": _rate(o, u),
        })

    sizes = [r["sampled"] for r in rows]
    w = [r["weight"] for r in rows]
    rng = np.random.default_rng(MC_SEED)
    d_usable = posterior_draws([r["usable"] for r in rows], sizes, w, rng)
    d_pass = posterior_draws([r["passed_gates"] for r in rows], sizes, w, rng)
    d_ot = posterior_draws([r["on_target"] for r in rows], sizes, w, rng)

    # benchmark recall, conditional on a usable light curve
    bf = {x["label"]: x["count"] for x in benchmark.get("funnel", [])}
    b_usable = int(bf.get("Light curve fetched", 0))
    b_rec = int(benchmark.get("recall", {}).get("recovered", 0))
    recall = {
        "source": "benchmark.json: Kostov et al. 2025 table 3 (vetted new EBs), random sample stratified by Tmag",
        "recovered": b_rec,
        "usable": b_usable,
        "sampled": int(benchmark.get("recall", {}).get("sampled", 0)),
        "given_usable": _rate(b_rec, b_usable),
        "by_tmag": [{"bin": x["bin"], "recovered": x["recovered"], "n": x["n"], "rate": _rate(x["recovered"], x["n"])}
                    for x in benchmark.get("by_tmag", [])],
    }

    out_rates = {
        "usable_per_sampled": summarize(d_usable),
        "passed_gates_per_sampled": summarize(d_pass),
        "on_target_per_sampled": summarize(d_ot),
        "passed_gates_per_usable": summarize(d_pass / d_usable),
        "on_target_per_usable": summarize(d_ot / d_usable),
    }

    provisional = None
    if b_usable > 0:
        d_rec = rng.beta(b_rec + 0.5, b_usable - b_rec + 0.5, size=MC_DRAWS)
        provisional = {
            "label": "Provisional recall-corrected on-target rate per usable star",
            "value": summarize(np.minimum(1.0, (d_ot / d_usable) / d_rec)),
            "assumption": "The unvetted stars are as easy for this pipeline to recover as the vetted benchmark stars. "
                          "Probably optimistic (unvetted signals are weaker), so this is likely a LOWER bound on the true "
                          "eclipsing-binary fraction. Injected-binary recovery (recovery.json) is a second, independent estimate of recall.",
        }

    periods = _period_table(nov, on_target)

    pass_tot = int(frame["passed"].sum())
    notes = [
        "Sampling frame is the %d stars in f2c_manifest.csv; rates are conditional on the pipeline, not on truth." % len(frame),
        "Stars with no usable light curve (%d of %d sampled) are counted in 'usable_per_sampled' and excluded from the per-usable rates." %
        (int((~frame["usable"]).sum()), len(frame)),
        "%d star(s) in the novelty file are not in the sampling frame (earlier hand-run batches) and are excluded here." % outside_frame,
        "Pixel checking was run only on stars with no catalog match, so 'on_target' cannot be computed for catalogued stars; "
        "the on-target rate is a lower bound for that reason too.",
        "All %d on-target stars are entries in the Kostov et al. 2025 unvetted list: this is an independent vetting of that list, not a discovery of new detections." % len(on_target),
    ]

    return {
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame": {
            "list": "Kostov et al. 2025 TESS Ten Thousand Catalog, unvetted list (VizieR J/ApJS/279/50 table 2)",
            "population": int(pop_counts.sum()),
            "sampled": int(len(frame)),
            "sampled_fraction": float(len(frame) / pop_counts.sum()),
            "design": "Seeded random sample stratified by Tmag; near-equal allocation per fifth of the list, so population figures are re-weighted by stratum share.",
            "strata_inner_edges": edges,
            "intervals": "Per-stratum: Wilson 95 percent. Population and derived figures: 95 percent interval from %d Jeffreys-prior beta draws (seed %d)." % (MC_DRAWS, MC_SEED),
        },
        "funnel": [
            {"key": "sampled", "label": "Sampled", "count": int(len(frame))},
            {"key": "usable", "label": "Usable light curve", "count": int(frame["usable"].sum())},
            {"key": "reliable", "label": "Reliable data (not flagged unreliable)", "count": int(frame["reliable"].sum())},
            {"key": "passed", "label": "Passed statistical gates", "count": pass_tot},
            {"key": "novel", "label": "No catalog match", "count": int(frame["novel"].sum())},
            {"key": "pixel_checked", "label": "Pixel-checked", "count": int(frame["pixel_checked"].sum())},
            {"key": "on_target", "label": "Confirmed on-target", "count": int(frame["on_target"].sum())},
        ],
        "strata": rows,
        "rates": out_rates,
        "recall": recall,
        "provisional_correction": provisional,
        "periods": periods,
        "notes": notes,
    }


def _rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": int(k), "n": int(n), "rate": float(k / n) if n else None, "lo": lo, "hi": hi}


def _period_table(nov, on_target):
    p = pd.to_numeric(nov["bls_period"], errors="coerce")
    cut = pd.cut(p, PERIOD_EDGES, labels=PERIOD_LABELS, right=False)
    out = []
    n_pass = int(p.notna().sum())
    for lab in PERIOD_LABELS:
        sel = cut == lab
        n_b = int(sel.sum())
        n_o = int((sel & nov["TIC"].isin(on_target)).sum())
        out.append({"bin": lab, "passed": n_b, "on_target": n_o,
                    "share_of_passed": _rate(n_b, n_pass)})
    return out


def read_csv_required(path):
    if not path.exists():
        print("ERROR: missing %s" % path)
        sys.exit(1)
    return pd.read_csv(path)


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_audit.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    out_path = root / "site" / "public" / "data" / "audit.json"

    manifest = read_csv_required(proc / "f2c_manifest.csv")
    vetting = read_csv_required(proc / "f3i_vetting_results.csv")
    novelty = read_csv_required(proc / "f4f_novelty_results.csv")
    pixel = read_csv_required(proc / "diag_pixel_results_v2.csv")
    bench_path = root / "site" / "public" / "data" / "benchmark.json"
    if not bench_path.exists():
        print("ERROR: missing %s (run export_site_data first)" % bench_path)
        sys.exit(1)
    benchmark = json.loads(bench_path.read_text(encoding="utf-8"))
    try:
        pop = pd.read_parquet(proc / "table2_unvetted.parquet", columns=["Tmag"])["Tmag"]
    except Exception as e:
        print("ERROR: could not read table2_unvetted.parquet: %s" % e)
        sys.exit(1)

    audit = build_audit(manifest, vetting, novelty, pixel, pop.to_numpy(), benchmark)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(audit, f, indent=2)
        f.write("\n")

    r = audit["rates"]
    print("Audit written: %s" % out_path)
    for fn in audit["funnel"]:
        print("  %-40s %7d" % (fn["label"], fn["count"]))
    ot = r["on_target_per_usable"]
    print("On-target per usable star: %.2f%% (95%% %.2f-%.2f%%)" % (100 * ot["median"], 100 * ot["lo"], 100 * ot["hi"]))
    pc = audit["provisional_correction"]
    if pc:
        v = pc["value"]
        print("Provisional recall-corrected: %.1f%% (95%% %.1f-%.1f%%)" % (100 * v["median"], 100 * v["lo"], 100 * v["hi"]))


if __name__ == "__main__":
    main()
