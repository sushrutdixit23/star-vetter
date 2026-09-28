"""
benchmark_report.py

Aggregates every stage of the benchmark harness (f2c fetch manifest, f3i
vetting results, f4f novelty results, diag_pixel results) into one
end-to-end recall report for the pilot sample of known eclipsing binaries
drawn from Kostov et al. 2025's table3_new_ebs.parquet (the "new EBs"
table - not previously catalogued elsewhere, which is why the novelty
cross-match correctly finds nothing for them).

Excludes the 2 calibration control stars (WASP-32 / TIC 427332229 and
TIC 158329671) from every funnel and recall statistic below - they exist
only to validate diag_pixel.py's on-target/off-target method on this run
(see diag_pixel.py's own CONTROLS dict) and are not part of the
ground-truth recall sample.

Usage:
  py benchmark_report.py <project_root>
"""

import sys
from pathlib import Path

import pandas as pd


def pct(n, d):
    return f"{n}/{d} ({100.0 * n / d:.1f}%)" if d else f"{n}/0 (n/a)"


def to_bool(s):
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def main():
    if len(sys.argv) != 2:
        print("Usage: py benchmark_report.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"

    gt = pd.read_csv(proc / "benchmark_ground_truth.csv")
    gt["TIC"] = gt["TIC"].astype(int)
    gt_tics = set(gt["TIC"])
    n_sampled = len(gt)

    print("=" * 72)
    print(f"BENCHMARK RECALL REPORT: {n_sampled} known EBs from Kostov et al. 2025 table3")
    print("(2 calibration control stars excluded from all stats below)")
    print("=" * 72)

    # --- Stage 1: fetch ---
    manifest = pd.read_csv(proc / "f2c_manifest.csv")
    manifest["TIC"] = manifest["TIC"].astype(int)
    manifest = manifest[manifest["TIC"].isin(gt_tics)]
    fetch_ok = manifest[manifest["status"] == "OK"]
    n_fetch_ok = len(fetch_ok)
    print(f"\n1. FETCH: {pct(n_fetch_ok, n_sampled)} light curves retrieved")
    for status, grp in manifest.groupby("status"):
        print(f"     {status}: {len(grp)}")

    # --- Stage 2: f3i vetting ---
    f3i = pd.read_csv(proc / "f3i_vetting_results.csv")
    f3i["TIC"] = f3i["TIC"].astype(int)
    f3i = f3i[f3i["TIC"].isin(gt_tics)].copy()
    vet_ok = f3i[f3i["status"] == "OK"].copy()
    unreliable = f3i[f3i["status"] == "UNRELIABLE_DATA"]
    n_vet_ok = len(vet_ok)
    print(f"\n2. VET (f3i_vet.py): {pct(n_vet_ok, n_fetch_ok)} of fetched stars vetted OK")
    print(f"     UNRELIABLE_DATA (excluded before gates): {len(unreliable)}")

    vet_ok["depth_flagged_implausible"] = to_bool(vet_ok["depth_flagged_implausible"])
    trustworthy = vet_ok[~vet_ok["depth_flagged_implausible"]]
    excluded = vet_ok[vet_ok["depth_flagged_implausible"]]
    n_trustworthy = len(trustworthy)
    print(f"\n   TRUSTWORTHY PRIMARY DETECTIONS: {pct(n_trustworthy, n_vet_ok)} of vetted-OK stars")
    print(f"   Excluded by at least one gate: {len(excluded)}")

    gate_cols = [
        ("insufficient_intransit_points", "< 10 in-transit points"),
        ("below_noise_floor", "SNR < 10"),
        ("noisy_photometry", "noisy photometry (>2% above 1.2x baseline)"),
        ("inhomogeneous_photometry", "inhomogeneous photometry segments"),
        ("depth_too_small", "depth < 10 ppm"),
        ("non_finite_bls_result", "non-finite BLS result"),
        ("too_few_eclipses", "< 3 eclipses observed"),
        ("robust_depth_mismatch", "median/BLS depth mismatch"),
    ]
    print("\n   Per-gate flag counts (a star can trip more than one gate):")
    for col, label in gate_cols:
        if col in vet_ok.columns:
            n = int(to_bool(vet_ok[col]).sum())
            print(f"     {col:30s} {n:3d}  ({label})")
    depth_oor = vet_ok[(vet_ok["bls_depth"] < 0) | (vet_ok["bls_depth"] > 0.95)]
    print(f"     {'depth_out_of_range [0,0.95]':30s} {len(depth_oor):3d}")

    if "robust_depth_mismatch" in vet_ok.columns:
        rdm = vet_ok[to_bool(vet_ok["robust_depth_mismatch"])]
        nan_sigma = rdm[rdm["robust_sigma"].isna()]
        real_mismatch = rdm[rdm["robust_sigma"].notna()]
        print(f"\n   Of the {len(rdm)} robust_depth_mismatch flags:")
        print(f"     {len(nan_sigma)} could not be computed at all (too few points, robust_sigma is NaN)")
        print(f"     {len(real_mismatch)} were genuinely computed and found mismatched")

    if "too_few_eclipses" in vet_ok.columns:
        merged = vet_ok.merge(gt[["TIC", "true_period_days"]], on="TIC", how="left")
        tfe_mask = to_bool(merged["too_few_eclipses"])
        tfe = merged[tfe_mask]
        not_tfe = merged[~tfe_mask]
        print(f"\n   too_few_eclipses stars: median true period {tfe['true_period_days'].median():.2f}d "
              f"(n={len(tfe)}) vs {not_tfe['true_period_days'].median():.2f}d for the rest (n={len(not_tfe)})")
        print("   (a longer true period with only ~27 days of single-sector coverage naturally")
        print("   yields fewer observed eclipses - this gate may be partly a coverage artifact,")
        print("   not a vetting failure)")

    # --- Stage 3: novelty ---
    f4f = pd.read_csv(proc / "f4f_novelty_results.csv")
    f4f["TIC"] = f4f["TIC"].astype(int)
    f4f = f4f[f4f["TIC"].isin(gt_tics)]
    print(f"\n3. NOVELTY (f4f_novelty.py): {len(f4f)} trustworthy detections checked")
    for verdict, grp in f4f.groupby("verdict"):
        print(f"     {verdict}: {len(grp)}")
    n_novel = int((f4f["verdict"] == "NOVEL").sum())
    non_novel = f4f[f4f["verdict"] != "NOVEL"]
    if len(non_novel):
        print(f"   NOTE: diag_pixel.py only pixel-checks NOVEL-verdict candidates, so the")
        print(f"   {len(non_novel)} non-NOVEL star(s) below would never reach the final list in")
        print(f"   production, regardless of how real they are:")
        print(non_novel[["TIC", "verdict"]].to_string(index=False))

    # --- Stage 4: pixel check ---
    pix = pd.read_csv(proc / "diag_pixel_results_v2.csv")
    pix["TIC"] = pix["TIC"].astype(int)
    pix = pix[(pix["TIC"].isin(gt_tics)) & (pix["role"] == "candidate")]
    print(f"\n4. PIXEL CHECK (diag_pixel.py): {len(pix)} NOVEL candidates checked")
    for verdict, grp in pix.groupby("verdict"):
        print(f"     {verdict}: {len(grp)}")
    n_on_target = int((pix["verdict"] == "ON_TARGET").sum())

    # --- Final funnel ---
    print("\n" + "=" * 72)
    print("END-TO-END FUNNEL")
    print("=" * 72)
    print(f"  {n_sampled} known EBs sampled")
    print(f"  -> {n_fetch_ok} fetched OK ({pct(n_fetch_ok, n_sampled)})")
    print(f"  -> {n_vet_ok} vetted OK ({pct(n_vet_ok, n_fetch_ok)} of fetched)")
    print(f"  -> {n_trustworthy} trustworthy primary detections ({pct(n_trustworthy, n_vet_ok)} of vetted)")
    print(f"  -> {n_novel} NOVEL verdict ({pct(n_novel, n_trustworthy)} of trustworthy)")
    print(f"  -> {n_on_target} ON_TARGET at pixel check ({pct(n_on_target, n_novel)} of NOVEL)")
    print(f"\n  *** END-TO-END RECALL: {pct(n_on_target, n_sampled)} of sampled known EBs")
    print(f"      reach final ON_TARGET status ***")

    # --- Recall by brightness bin ---
    print("\n" + "=" * 72)
    print("RECALL BY Tmag BIN")
    print("=" * 72)
    gt2 = gt.copy()
    gt2["on_target"] = gt2["TIC"].isin(set(pix[pix["verdict"] == "ON_TARGET"]["TIC"]))
    bins = [0, 12, 13, 14, 20]
    labels = ["<12", "12-13", "13-14", "14+"]
    gt2["tmag_bin"] = pd.cut(gt2["Tmag"], bins=bins, labels=labels, right=False)
    for label, grp in gt2.groupby("tmag_bin", observed=True):
        print(f"  Tmag {str(label):6s}: {pct(int(grp['on_target'].sum()), len(grp))} reach ON_TARGET "
              f"(n={len(grp)} sampled)")

    # --- Depth-pri units cross-check ---
    print("\n" + "=" * 72)
    print("Depth-pri UNITS CROSS-CHECK (against f3i's independently measured bls_depth)")
    print("=" * 72)
    dchk = vet_ok.merge(gt[["TIC", "true_depth_pri_kostov_units"]], on="TIC", how="left")
    dchk = dchk[dchk["true_depth_pri_kostov_units"].notna() & dchk["bls_depth"].notna()]
    for divisor, hyp in [(1000.0, "parts-per-thousand (Depth-pri / 1000)"),
                         (100.0, "percent (Depth-pri / 100)"),
                         (1e6, "ppm (Depth-pri / 1e6)")]:
        ratio = dchk["bls_depth"] / (dchk["true_depth_pri_kostov_units"] / divisor)
        print(f"\n  If Depth-pri is {hyp}:")
        print(f"    bls_depth / implied_true_depth ratio: "
              f"median={ratio.median():.3f}  mean={ratio.mean():.3f}  n={len(ratio)}")

    print(f"\nFull per-star intermediate tables are in {proc}")
    export_site_json(root, proc, gt, manifest, f3i, vet_ok, trustworthy, f4f, pix, gt2, gate_cols,
                     n_sampled, n_fetch_ok, n_vet_ok, n_trustworthy, n_novel, n_on_target)


def export_site_json(root, proc, gt, manifest, f3i, vet_ok, trustworthy, f4f, pix, gt2, gate_cols,
                     n_sampled, n_fetch_ok, n_vet_ok, n_trustworthy, n_novel, n_on_target):
    # Additive: also save this report as JSON for the website's reliability
    # page. Uses only the frames main() already computed; changes nothing it
    # prints. root is the benchmark_run folder, so the site's data folder is
    # root.parent / site / public / data. Durations and depths are left out:
    # their units in the source table are not yet confirmed.
    import json
    import math
    from datetime import datetime, timezone

    site_dir = root.parent / "site" / "public" / "data"
    if not site_dir.is_dir():
        print(f"(site data folder not found at {site_dir} - benchmark.json not written)")
        return

    def num(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(v) or math.isinf(v) else v

    def counts(frame, col):
        if len(frame) == 0 or col not in frame.columns:
            return []
        return [{"key": str(k), "count": int(len(g))} for k, g in frame.groupby(col)]

    gates = []
    gates_by_tic = {}
    for col, label in gate_cols:
        if col in vet_ok.columns:
            flagged = to_bool(vet_ok[col])
            gates.append({"gate": col, "label": label, "count": int(flagged.sum())})
            for t in vet_ok[flagged]["TIC"]:
                gates_by_tic.setdefault(int(t), []).append(label)

    tfe = None
    if "too_few_eclipses" in vet_ok.columns:
        merged = vet_ok.merge(gt[["TIC", "true_period_days"]], on="TIC", how="left")
        mask = to_bool(merged["too_few_eclipses"])
        tfe = {
            "n_flagged": int(mask.sum()),
            "median_period_flagged": num(merged[mask]["true_period_days"].median()) if mask.any() else None,
            "n_rest": int((~mask).sum()),
            "median_period_rest": num(merged[~mask]["true_period_days"].median()) if (~mask).any() else None,
        }

    by_tmag = []
    for label, grp in gt2.groupby("tmag_bin", observed=True):
        by_tmag.append({"bin": str(label), "recovered": int(grp["on_target"].sum()), "n": int(len(grp))})

    controls = []
    try:
        allpix = pd.read_csv(proc / "diag_pixel_results_v2.csv")
        ctl = allpix[allpix["role"] != "candidate"]
        keep = [c for c in ["TIC", "role", "verdict", "expected", "expected_verdict", "note", "reason"] if c in ctl.columns]
        for _, row in ctl[keep].iterrows():
            entry = {}
            for k in keep:
                v = row[k]
                if pd.isna(v):
                    entry[k] = None
                elif k == "TIC":
                    entry[k] = int(v)
                else:
                    entry[k] = str(v)
            controls.append(entry)
    except Exception as exc:
        print(f"(could not read calibration controls for benchmark.json: {exc})")

    fetched = set(manifest[manifest["status"] == "OK"]["TIC"])
    fetch_status = dict(zip(manifest["TIC"], manifest["status"].astype(str)))
    vet_status = dict(zip(f3i["TIC"], f3i["status"].astype(str)))
    vetted = set(vet_ok["TIC"])
    trusted = set(trustworthy["TIC"])
    novelty = dict(zip(f4f["TIC"], f4f["verdict"].astype(str)))
    pixel = dict(zip(pix["TIC"], pix["verdict"].astype(str)))
    stars = []
    for _, r in gt.iterrows():
        t = int(r["TIC"])
        if t not in fetched:
            stage, outcome = "fetch", fetch_status.get(t, "not attempted")
        elif t not in vetted:
            stage, outcome = "vetting", vet_status.get(t, "not vetted")
        elif t not in trusted:
            stage, outcome = "vetting", "failed a vetting gate"
        elif novelty.get(t) != "NOVEL":
            stage, outcome = "novelty", novelty.get(t, "not checked")
        elif t not in pixel:
            stage, outcome = "pixel", "not pixel-checked"
        else:
            stage, outcome = "pixel", pixel[t]
        stars.append({
            "tic": t,
            "tmag": num(r["Tmag"]),
            "true_period_days": num(r["true_period_days"]),
            "stage": stage,
            "outcome": outcome,
            "recovered": pixel.get(t) == "ON_TARGET",
            "gates": gates_by_tic.get(t, []),
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample": {
            "source": "Kostov et al. 2025, table 3 (newly catalogued eclipsing binaries)",
            "n": int(n_sampled),
            "selection": "Drawn at random, stratified by TESS magnitude quartile so the sample spans the real brightness range",
        },
        "definition": "A known eclipsing binary counts as recovered if it passes every stage and the pixel check returns ON_TARGET. The period the pipeline finds is not yet compared with the catalogue period.",
        "controls_note": "Two calibration stars with known answers are run alongside to validate the pixel check; they are excluded from every count.",
        "funnel": [
            {"label": "Known eclipsing binaries sampled", "count": int(n_sampled)},
            {"label": "Light curve fetched", "count": int(n_fetch_ok)},
            {"label": "Vetted (reliable data)", "count": int(n_vet_ok)},
            {"label": "Passed every vetting gate", "count": int(n_trustworthy)},
            {"label": "Novel (no catalog match)", "count": int(n_novel)},
            {"label": "On-target at the pixel check", "count": int(n_on_target)},
        ],
        "recall": {"recovered": int(n_on_target), "sampled": int(n_sampled)},
        "fetch_status": counts(manifest, "status"),
        "gates": gates,
        "novelty": counts(f4f, "verdict"),
        "pixel": counts(pix, "verdict"),
        "too_few_eclipses": tfe,
        "by_tmag": by_tmag,
        "controls": controls,
        "stars": stars,
    }
    out = site_dir / "benchmark.json"
    out.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()