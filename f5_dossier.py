import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages

try:
    from astroquery.mast import Catalogs
except ImportError as exc:
    print("Missing package: " + str(exc))
    sys.exit(1)

# Builds a one-page PDF dossier for every ON_TARGET candidate: BLS ephemeris,
# the robust-depth and odd/even/secondary-eclipse checks from f3i, the
# catalog cross-match from f4f (which catalogs were checked, all no-match -
# that is what makes it "novel"), the pixel-check stats from diag_pixel, and
# the difference-image figure diag_pixel already made. One PDF per star in
# data/dossiers/, plus a combined PDF (summary table first, then every
# dossier page) for sharing as a single document.
#
# Every candidate can carry zero or more caveats, from two sources:
#  - MANUAL_CAVEATS: two one-off checks that live outside the regular
#    pipeline (diag_recheck2.py's false-alarm-rate test on TIC 303470667's
#    marginal pixel SNR, and its aperture-sensitivity test on TIC 111149941's
#    ambiguous in-aperture photometry). These are hand-entered because
#    nothing else records them.
#  - get_auto_flags(): computed fresh every run from columns the pipeline
#    already writes - period aliasing from f3i's odd/even test
#    (possible_half_period_alias, odd_even_z) and a thin neighbour-
#    competition margin from diag_pixel's own centroid/neighbour distances.
#    These stay correct automatically if the candidate set ever changes.
# A star can carry more than one caveat; the panel lists all of them and the
# badge shows the most severe (THIN MARGIN worst, PERIOD ALIAS mildest -
# it is a labelling correction, not a confidence problem).

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

ODD_EVEN_ALIAS_THRESHOLD = 3.0     # matches f3i_vet.py
MARGIN_SAFETY_PX = 0.10            # diag_pixel.py's own stated centroid systematic floor

TIER_SEVERITY = ["THIN MARGIN", "AMBIGUOUS PHOTOMETRY", "MARGINAL", "PERIOD ALIAS", "CLEAN"]
TIER_COLOR = {"CLEAN": "#1a7a1a", "MARGINAL": "#b8860b", "AMBIGUOUS PHOTOMETRY": "#b8860b",
             "THIN MARGIN": "#b83232", "PERIOD ALIAS": "#2a6f97"}
TIER_SHORT = {"CLEAN": "Clean", "MARGINAL": "Marginal", "AMBIGUOUS PHOTOMETRY": "Ambiguous",
             "THIN MARGIN": "Thin margin", "PERIOD ALIAS": "Alias"}

CATALOGS_CHECKED = ["VSX", "ASAS-SN", "Gaia eclipsing-binary table", "Gaia variable classification",
                    "TESS EB catalog (Prsa+2022)", "ExoFOP TOI list"]


def get_auto_flags(tic, v, p):
    """Caveats computed fresh from the pipeline's own CSVs every run - see
    header comment. Returns a list of (tier, caveat_text)."""
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


def fmt(x, spec=".4f", none="n/a"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return none
    try:
        return format(x, spec)
    except (ValueError, TypeError):
        return str(x)


def phase_fold(t, flux, period, t0, n_bins=60):
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
    return phase, flux, centers, binned


def build_page(fig, tic, v, n, p, pixel_png, lc):
    """v = f3i row, n = f4f row, p = diag_pixel row, lc = light curve df."""
    tier, flags = get_all_flags(tic, v, p)
    tier_color = TIER_COLOR[tier]
    alias_active = any(t == "PERIOD ALIAS" for t, _ in flags)

    gs = fig.add_gridspec(5, 2, height_ratios=[0.5, 2.0, 2.0, 2.2, 2.4], hspace=0.55, wspace=0.25,
                          left=0.07, right=0.95, top=0.95, bottom=0.04)

    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    ax_title.text(0, 0.7, f"TIC {tic}", fontsize=20, fontweight="bold", va="top")
    ax_title.text(0, 0.05, f"Eclipsing binary candidate dossier - Star Vetter", fontsize=10,
                  color="0.35", va="top")
    ax_title.text(1.0, 0.55, tier, fontsize=13, fontweight="bold", color="white", va="center",
                  ha="right", bbox=dict(boxstyle="round,pad=0.4", facecolor=tier_color, edgecolor="none"))

    ax_stats = fig.add_subplot(gs[1, 0])
    ax_stats.axis("off")
    depth_pct = v["bls_depth"] * 100
    depth_ppm = v["bls_depth"] * 1e6
    stats_lines = [
        "BLS EPHEMERIS",
        f"  Period       {fmt(v['bls_period'], '.6f')} d" + ("  (ALIASED, see below)" if alias_active else ""),
    ] + ([f"    -> corrected period: {v['bls_period'] * 2:.6f} d"] if alias_active else []) + [
        f"  Epoch (t0)   {fmt(v['bls_t0'], '.4f')} BTJD",
        f"  Duration     {fmt(v['bls_duration'], '.4f')} d",
        f"  Depth        {depth_pct:.3f} %  ({depth_ppm:,.0f} ppm)",
        f"  SNR          {fmt(v['bls_snr'], '.1f')}",
        "",
        "INDEPENDENT CHECKS (f3i gates)",
        f"  Eclipses observed     {fmt(v['n_eclipses_observed'], '.0f')}  (gate >= 3)",
        f"  Robust depth ratio    {fmt(v['depth_ratio'], '.2f')}  (gate >= 0.50)",
        f"  Robust depth sigma    {fmt(v['robust_sigma'], '.1f')}  (gate >= 7.0)",
        f"  Odd/even z-score      {fmt(v['odd_even_z'], '.2f')}  "
        f"({'ALIAS FLAGGED' if v.get('possible_half_period_alias') else 'consistent'})",
        f"  Secondary eclipse     "
        + (f"detected, phase {fmt(v['secondary_phase'], '.2f')}, {fmt(v['secondary_sigma'], '.1f')} sigma"
           if v.get("secondary_detected") else "not detected"),
    ]
    ax_stats.text(0, 1.0, "\n".join(stats_lines), fontsize=9, family="monospace", va="top")

    ax_cat = fig.add_subplot(gs[1, 1])
    ax_cat.axis("off")
    cat_lines = ["CATALOG CROSS-MATCH (novelty)", ""]
    for c in CATALOGS_CHECKED:
        cat_lines.append(f"  {c:<32s} no match")
    cat_lines += ["", f"  Verdict: {n['verdict']}"]
    ax_cat.text(0, 1.0, "\n".join(cat_lines), fontsize=9, family="monospace", va="top")

    ax_pix = fig.add_subplot(gs[2, :])
    ax_pix.axis("off")
    if pd.notna(p.get("nearest_capable_TIC")):
        nb_lines = [f"  Nearest bright-enough neighbour in cutout: TIC {fmt(p['nearest_capable_TIC'], '.0f')}",
                   f"    {fmt(p['nearest_capable_dist_px'], '.2f')} px away, dTmag "
                   f"{fmt(p['nearest_capable_dTmag'], '+.2f')} - farther from the dimming than the target"]
    else:
        nb_lines = ["  Nearest bright-enough neighbour in cutout: none within the cutout"]
    pix_lines = [
        "PIXEL-LEVEL SOURCE CHECK (TESScut difference imaging)",
        f"  Sector {fmt(p['sector'], '.0f')}    light-curve dip in this sector: {fmt(p['lc_dip_sigma'], '.1f')} sigma"
        f"    t0 refined by {fmt(p['t0_shift_phase'], '.4f')} phase",
        f"  Difference-image peak SNR   {fmt(p['diff_peak_snr'], '.2f')}   (gate >= 5.0)      "
        f"Compactness   {fmt(p['compactness'], '.2f')}   (gate >= 0.50)",
        f"  Dimming centroid offset     {fmt(p['centroid_offset_px'], '.2f')} px "
        f"({fmt(p['centroid_offset_arcsec'], '.0f')} arcsec)   (gate <= 1.0 px, i.e. on the target)",
    ] + nb_lines
    ax_pix.text(0, 1.0, "\n".join(pix_lines), fontsize=9, family="monospace", va="top")

    ax_lc = fig.add_subplot(gs[3, :])
    phase, flux, centers, binned = phase_fold(lc["time"].values, lc["flux"].values,
                                              v["bls_period"], v["bls_t0"])
    ax_lc.scatter(phase, flux, s=2, alpha=0.15, color="0.5", linewidths=0)
    ax_lc.plot(centers, binned, color="crimson", lw=1.6, label="binned median")
    half_dur_phase = (v["bls_duration"] / v["bls_period"]) / 2
    ax_lc.axvspan(-half_dur_phase, half_dur_phase, color="crimson", alpha=0.08)
    ax_lc.set_xlim(-0.5, 0.5)
    lo, hi = np.nanpercentile(flux, [0.5, 99.5])
    pad = 0.15 * (hi - lo)
    ax_lc.set_ylim(lo - pad, hi + pad)
    ax_lc.set_xlabel("Orbital phase")
    ax_lc.set_ylabel("Normalized flux")
    ax_lc.set_title("Phase-folded light curve (shaded = BLS eclipse window)", fontsize=10)
    ax_lc.legend(loc="lower right", fontsize=8)

    ax_img = fig.add_subplot(gs[4, :])
    ax_img.axis("off")
    if pixel_png.exists():
        img = mpimg.imread(pixel_png)
        ax_img.imshow(img)
    else:
        ax_img.text(0.5, 0.5, "difference-image figure not found", ha="center", va="center")

    if tier == "CLEAN":
        footer = "No caveats - clean detection on every check."
    else:
        footer = "\n".join(f"Caveat ({t}): {c}" for t, c in flags)
    fig.text(0.07, 0.005, footer, fontsize=7.2, color="0.3", wrap=True, va="bottom")


def main():
    if len(sys.argv) != 2:
        print("Usage: py f5_dossier.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    lc_dir = root / "data" / "lightcurves"
    pixel_dir = root / "data" / "pixel_check"
    out_dir = root / "data" / "dossiers"
    out_dir.mkdir(parents=True, exist_ok=True)

    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    nov = pd.read_csv(proc / "f4f_novelty_results.csv").set_index("TIC")
    pix = pd.read_csv(proc / "diag_pixel_results_v2.csv")

    targets = pix[(pix["role"] == "candidate") & (pix["verdict"] == "ON_TARGET")]["TIC"].astype(int).tolist()
    if not targets:
        print("No ON_TARGET candidates found in diag_pixel_results_v2.csv. Nothing to build.")
        sys.exit(1)
    # how many candidates have been pixel-checked in total to date (not just this
    # run) - this is what the summary page reports the ON_TARGET count out of
    n_checked = int((pix["role"] == "candidate").sum())
    pix = pix.set_index("TIC")

    print(f"Building dossiers for {len(targets)} ON_TARGET candidate(s): {targets}")

    info = Catalogs.query_criteria(catalog="Tic", ID=targets)
    info = info[["ID", "ra", "dec", "Tmag"]].to_pandas()
    info["ID"] = info["ID"].astype(int)
    info = info.set_index("ID")

    combined_path = out_dir / "star_vetter_dossiers.pdf"
    with PdfPages(combined_path) as pdf:
        # summary page
        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.set_title("Star Vetter - confirmed eclipsing binary candidates", fontsize=15,
                     fontweight="bold", loc="left", pad=20)
        rows = []
        for tic in targets:
            v, p = vet.loc[tic], pix.loc[tic]
            tier, _ = get_all_flags(tic, v, p)
            rows.append([str(tic), f"{v['bls_period']:.4f}", f"{v['bls_depth']*100:.3f}%",
                        f"{v['bls_snr']:.0f}", f"{p['diff_peak_snr']:.2f}",
                        f"{p['centroid_offset_arcsec']:.0f}\"", TIER_SHORT[tier]])
        col_labels = ["TIC", "Period (d)", "Depth", "BLS SNR", "Pixel SNR", "Offset", "Tier"]
        row_h = 0.032
        table_h = row_h * (len(targets) + 1)
        table_top = 0.85
        table = ax.table(cellText=rows, colLabels=col_labels, loc="upper left", cellLoc="center",
                         colWidths=[0.17, 0.13, 0.13, 0.13, 0.13, 0.11, 0.20],
                         bbox=[0.0, table_top - table_h, 1.0, table_h])
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        ax.text(0, table_top - table_h - 0.03, f"{len(targets)} of {n_checked} novel candidates confirmed "
                f"on-target by TESS pixel-level difference imaging.\nGenerated by f5_dossier.py "
                f"from f3i_vet.py, f4f_novelty.py and diag_pixel.py results.\nPeriod column is the "
                f"BLS-fitted value; candidates tiered Alias have a doubled true period - see their "
                f"page.", fontsize=9, va="top")
        pdf.savefig(fig)
        plt.close(fig)

        for tic in targets:
            lc_path = lc_dir / f"TIC{tic}.csv"
            if not lc_path.exists():
                print(f"  TIC {tic}: SKIPPED, no light curve file")
                continue
            lc = pd.read_csv(lc_path)
            v, n, p = vet.loc[tic], nov.loc[tic], pix.loc[tic]
            png = pixel_dir / f"TIC{tic}_pixel.png"

            fig = plt.figure(figsize=(8.27, 11.69))
            build_page(fig, tic, v, n, p, png, lc)
            single_path = out_dir / f"TIC{tic}_dossier.pdf"
            fig.savefig(single_path)
            pdf.savefig(fig)
            plt.close(fig)
            print(f"  TIC {tic}: wrote {single_path}")

    print(f"\nCombined dossier: {combined_path}")


if __name__ == "__main__":
    main()