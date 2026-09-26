import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Exports the confirmed candidates (same set f5_dossier.py builds PDFs for) as
# JSON for the Next.js showcase site, plus copies the pixel-check images into
# the site's public folder. Read-only against the pipeline's own CSVs - never
# re-runs or changes anything the pipeline produced.
#
# The tier/caveat logic below is a direct copy of f5_dossier.py's
# get_auto_flags/get_all_flags (not imported, to avoid pulling in
# matplotlib/astroquery here) - keep the two in sync if either changes.

MANUAL_CAVEATS = {
    303470667: [("MARGINAL", "Pixel-check SNR is right at the gate (5.02 vs >= 5.0). A "
                "150-trial false-alarm check on this star's own data found only a 3.3% "
                "chance of reaching this SNR at a random phase - the detection looks real, "
                "just faint. Weakest SNR margin of the confirmed set.")],
    111149941: [("AMBIGUOUS PHOTOMETRY", "The difference-image detection is strong (peak SNR "
                "9.7, compactness 0.75) but the star's own simple-aperture photometry shows "
                "no dip, and aperture/quality-mask sensitivity tests were inconsistent. "
                "Confirmed by pixel imaging; not independently confirmed by simple photometry.")],
}

ODD_EVEN_ALIAS_THRESHOLD = 3.0
MARGIN_SAFETY_PX = 0.10
TIER_SEVERITY = ["THIN MARGIN", "AMBIGUOUS PHOTOMETRY", "MARGINAL", "PERIOD ALIAS", "CLEAN"]

CATALOGS_CHECKED = [
    ("VSX", "vsx_match"), ("ASAS-SN", "asassn_match"),
    ("Gaia eclipsing-binary table", "gaia_veb_match"),
    ("Gaia variable classification", "gaia_class_match"),
    ("TESS EB catalog (Prsa+2022)", "tess_eb_match"),
    ("ExoFOP TOI list", "toi_match"),
]


def get_auto_flags(tic, v, p):
    flags = []
    z = v.get("odd_even_z")
    if pd.notna(z) and z > ODD_EVEN_ALIAS_THRESHOLD:
        true_period = v["bls_period"] * 2
        flags.append(("PERIOD ALIAS",
                      f"Odd/even eclipse-depth z-score is {z:.2f} (gate > {ODD_EVEN_ALIAS_THRESHOLD}): "
                      f"alternating eclipses differ significantly in depth, the signature of a true "
                      f"period double what BLS found. Pixel-check confirmation and eclipse timing are "
                      f"unaffected - report the corrected period, {true_period:.6f} d, in any write-up."))
    if pd.notna(p.get("nearest_capable_TIC")):
        margin = p["nearest_capable_dist_px"] - p["centroid_offset_px"]
        if margin < MARGIN_SAFETY_PX:
            flags.append(("THIN MARGIN",
                          f"The ON_TARGET call rests on a neighbour-competition margin of just "
                          f"{margin:.3f} px (dimming centroid {p['centroid_offset_px']:.3f} px from "
                          f"target vs {p['nearest_capable_dist_px']:.3f} px from the nearest "
                          f"bright-enough neighbour) - inside diag_pixel.py's own stated centroid "
                          f"systematic of {MARGIN_SAFETY_PX:.2f}-0.3 px. TESS's resolution cannot "
                          f"confidently separate this star from that neighbour."))
    return flags


def get_all_flags(tic, v, p):
    flags = MANUAL_CAVEATS.get(tic, []) + get_auto_flags(tic, v, p)
    if not flags:
        return "CLEAN", [("CLEAN", "Passed every gate with a comfortable margin. No caveats.")]
    worst = min(flags, key=lambda f: TIER_SEVERITY.index(f[0]))[0]
    return worst, flags


def clean(x):
    """Make a value JSON-safe: NaN/inf -> None, numpy scalars -> python."""
    if x is None:
        return None
    if isinstance(x, (np.floating, np.integer)):
        x = x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def phase_fold_for_web(t, flux, period, t0, n_bins=60, max_raw_points=2500, seed=42):
    phase = ((t - t0 + period / 2) % period) / period - 0.5
    order = np.argsort(phase)
    phase, flux = phase[order], flux[order]

    edges = np.linspace(-0.5, 0.5, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    binned = np.full(n_bins, np.nan)
    for b in range(n_bins):
        sel = (phase >= edges[b]) & (phase < edges[b + 1])
        if sel.sum() >= 2:
            binned[b] = np.median(flux[sel])

    # subsample the raw scatter for the browser - a real light curve can have
    # tens of thousands of points, no need to ship them all to render a chart
    n = len(phase)
    if n > max_raw_points:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(n, size=max_raw_points, replace=False))
        raw_phase, raw_flux = phase[idx], flux[idx]
    else:
        raw_phase, raw_flux = phase, flux

    return {
        "raw": [[round(float(p), 5), round(float(f), 6)] for p, f in zip(raw_phase, raw_flux)],
        "binned": [[round(float(c), 5), (round(float(b), 6) if np.isfinite(b) else None)]
                   for c, b in zip(centers, binned)],
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: py export_site_data.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    lc_dir = root / "data" / "lightcurves"
    pixel_dir = root / "data" / "pixel_check"
    site_data_dir = root / "site" / "public" / "data" / "candidates"
    site_img_dir = root / "site" / "public" / "images" / "pixel_check"
    site_data_dir.mkdir(parents=True, exist_ok=True)
    site_img_dir.mkdir(parents=True, exist_ok=True)

    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    nov = pd.read_csv(proc / "f4f_novelty_results.csv").set_index("TIC")
    pix = pd.read_csv(proc / "diag_pixel_results_v2.csv")

    targets = pix[(pix["role"] == "candidate") & (pix["verdict"] == "ON_TARGET")]["TIC"].astype(int).tolist()
    if not targets:
        print("No ON_TARGET candidates found. Nothing to export.")
        sys.exit(1)
    n_checked = int((pix["role"] == "candidate").sum())
    pix = pix.set_index("TIC")

    print(f"Exporting {len(targets)} confirmed candidate(s) for the site...")

    index_rows = []
    n_missing_lc = 0
    for tic in targets:
        v, n, p = vet.loc[tic], nov.loc[tic], pix.loc[tic]
        tier, flags = get_all_flags(tic, v, p)

        # data/lightcurves/ is regenerated fresh by each pipeline run and is
        # not committed to git (see .gitignore) - only stars fetched THIS
        # run have their raw light curve on disk. A confirmed candidate from
        # an earlier run has no light curve here, but the phase-folded chart
        # data this same script exported for it back then is still sitting
        # in the committed site/public/data/candidates/TIC{tic}.json - reuse
        # that instead of dropping the candidate from the site every run it
        # isn't re-fetched (this is the same class of fix export_dashboard.py
        # and f5_dossier.py already apply for the same underlying reason).
        lc_path = lc_dir / f"TIC{tic}.csv"
        existing_path = site_data_dir / f"TIC{tic}.json"
        if lc_path.exists():
            lc = pd.read_csv(lc_path)
            folded = phase_fold_for_web(lc["time"].values, lc["flux"].values, v["bls_period"], v["bls_t0"])
        elif existing_path.exists():
            folded = json.loads(existing_path.read_text(encoding="utf-8"))["light_curve"]
            print(f"  TIC {tic}: light curve not present this run - reusing previously exported chart data")
        else:
            print(f"  TIC {tic}: SKIPPED, no light curve file and no prior export to reuse")
            n_missing_lc += 1
            continue

        alias_active = any(t == "PERIOD ALIAS" for t, _ in flags)

        candidate = {
            "tic": tic,
            "tier": tier,
            "caveats": [{"tier": t, "text": c} for t, c in flags],
            "ephemeris": {
                "period_days": clean(v["bls_period"]),
                "corrected_period_days": clean(v["bls_period"] * 2) if alias_active else None,
                "aliased": bool(alias_active),
                "t0_btjd": clean(v["bls_t0"]),
                "duration_days": clean(v["bls_duration"]),
                "depth_frac": clean(v["bls_depth"]),
                "depth_ppm": clean(v["bls_depth"] * 1e6) if pd.notna(v["bls_depth"]) else None,
                "bls_snr": clean(v["bls_snr"]),
            },
            "gates": {
                "eclipses_observed": clean(v["n_eclipses_observed"]),
                "depth_ratio": clean(v["depth_ratio"]),
                "robust_sigma": clean(v["robust_sigma"]),
                "odd_even_z": clean(v["odd_even_z"]),
                "secondary_detected": bool(v.get("secondary_detected", False)),
                "secondary_phase": clean(v.get("secondary_phase")),
                "secondary_sigma": clean(v.get("secondary_sigma")),
            },
            "novelty": {
                "verdict": n["verdict"],
                "catalogs": [{"name": label, "matched": bool(n.get(col, False))}
                             for label, col in CATALOGS_CHECKED],
            },
            "pixel_check": {
                "sector": clean(p["sector"]),
                "lc_dip_sigma": clean(p["lc_dip_sigma"]),
                "t0_shift_phase": clean(p["t0_shift_phase"]),
                "diff_peak_snr": clean(p["diff_peak_snr"]),
                "compactness": clean(p["compactness"]),
                "centroid_offset_px": clean(p["centroid_offset_px"]),
                "centroid_offset_arcsec": clean(p["centroid_offset_arcsec"]),
                "nearest_neighbour": (
                    {
                        "tic": clean(p["nearest_capable_TIC"]),
                        "dist_px": clean(p["nearest_capable_dist_px"]),
                        "dtmag": clean(p["nearest_capable_dTmag"]),
                    } if pd.notna(p.get("nearest_capable_TIC")) else None
                ),
                "image": f"/images/pixel_check/TIC{tic}_pixel.png",
            },
            "light_curve": folded,
        }

        (site_data_dir / f"TIC{tic}.json").write_text(
            json.dumps(candidate, indent=None, separators=(",", ":")), encoding="utf-8", newline="\n")

        src_png = pixel_dir / f"TIC{tic}_pixel.png"
        if src_png.exists():
            shutil.copyfile(src_png, site_img_dir / f"TIC{tic}_pixel.png")
        else:
            print(f"  TIC {tic}: WARNING, pixel-check image not found at {src_png}")

        index_rows.append({
            "tic": tic,
            "tier": tier,
            "period_days": clean(v["bls_period"]),
            "depth_frac": clean(v["bls_depth"]),
            "bls_snr": clean(v["bls_snr"]),
            "pixel_snr": clean(p["diff_peak_snr"]),
            "offset_arcsec": clean(p["centroid_offset_arcsec"]),
        })
        print(f"  TIC {tic}: {tier}")

    index = {
        "generated_stats": {
            "n_confirmed": len(index_rows),
            "n_pixel_checked": n_checked,
        },
        "candidates": index_rows,
    }
    index_path = root / "site" / "public" / "data" / "index.json"
    index_path.write_text(json.dumps(index, indent=None, separators=(",", ":")),
                           encoding="utf-8", newline="\n")

    print(f"\nExported {len(index_rows)} candidate(s) to {site_data_dir}")
    if n_missing_lc:
        print(f"({n_missing_lc} skipped - no light curve file on disk)")
    print(f"Index written: {index_path}")


if __name__ == "__main__":
    main()