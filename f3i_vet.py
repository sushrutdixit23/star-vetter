import sys
import csv
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.timeseries import BoxLeastSquares

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# search range matches the documented range of the vetted catalog itself
# (table3: Per column documented as [0.64/39.8] days)
MIN_PERIOD_DAYS = 0.65
MAX_PERIOD_DAYS = 39.8
N_PERIOD_GRID = 15000
N_DURATION_GRID = 10
MIN_DURATION_DAYS = 0.02
MAX_DURATION_DAYS = 0.5

ODD_EVEN_ALIAS_THRESHOLD = 3.0
SECONDARY_DETECTION_SIGMA = 5.0

FLUX_MIN_PHYSICAL = 0.0
FLUX_MAX_PHYSICAL = 2.5

MAX_PLAUSIBLE_DEPTH = 0.95
MAX_PLAUSIBLE_SECONDARY_PPT = 500

MAX_FRAC_DROPPED_PHYSICAL = 0.30
MIN_INTRANSIT_POINTS = 10
MIN_SNR_THRESHOLD = 10.0
MAX_FRAC_ABOVE_1_2 = 0.02

SEGMENT_GAP_DAYS = 1.0
MIN_SEGMENT_POINTS = 20
MAX_SEGMENT_MEDIAN_OFFSET_SIGMA = 3.0
MAX_SEGMENT_SCATTER_RATIO = 3.0

# --- gap #6, found scaling from 69 to 500 stars ---
#
# (6) TIC 411513993 (this batch) had bls_depth = 5.1e-11 with bls_snr = 387
# - a "detection" reported as essentially zero depth (10 orders of
# magnitude below the shallowest real detection anywhere in this project,
# TIC 17361 at 4700 ppm) paired with a very high SNR. Checked depth_err/
# depth for this star (0.0026) against the whole 361-star sample
# (median 0.0094): NOT an outlier by that ratio - it is exactly what
# 1/snr predicts, so BLS's internal error propagation is self-consistent.
# The actual problem is simpler and more direct: a depth this many orders
# of magnitude below TESS's own photometric noise floor (single-cadence
# precision is ~1e-4 to 1e-3 for anything but the very brightest targets,
# and every real eclipse/transit found across both batches of this
# project - including a published one, WASP-32b at 8600 ppm - sits far
# above 1e-5) cannot be a resolvable astrophysical signal, whatever SNR
# the formal statistic reports. This is the same "trust the physical
# quantity, not just the derived statistic" principle behind
# MAX_PLAUSIBLE_DEPTH, applied to the other end of the scale.
#
# A second real case found in the same diagnostic (TIC 451043397, depth
# ~1.6e-311, snr = -inf) is a genuine floating-point underflow from an
# essentially-empty in-transit bin - but it was ALREADY caught by the
# existing MIN_INTRANSIT_POINTS gate (n_in_transit=1) and the noise-floor
# gate (snr=-inf < 10), so no new gate was needed for that one. It's
# checked here anyway as a second, independent line of defense: a
# non-finite depth/depth_err/snr should never silently pass regardless of
# what triggered it.
MIN_PLAUSIBLE_DEPTH = 1e-5  # 10 ppm - ~470x below the shallowest real
                             # detection found so far (TIC 17361, 4700 ppm),
                             # ~5 orders of magnitude above the degenerate case

# --- gap #7, found by diag_epochs.py on the 569-target run ---
#
# (7) NOVEL periods piled up at 13-14.5 d (31 stars, ~10x the neighbouring
# density) and 26-28.5 d - TESS's 13.7 d orbit and ~27 d sector length,
# and for single-sector stars the BLS search ceiling (span/2). The
# diagnostic showed these are overwhelmingly 1-2 "eclipse" fits to data
# gaps, not periodic signals:
#   - 29/32 (13-14.5 d) and 8/9 (26-28.5 d) had < 3 observed eclipses,
#     vs 23/116 outside those bands.
#   - In the 26-28.5 d band, the median fraction of in-transit points
#     within 0.5 d of a data-gap edge was 1.00 (chance level: 0.07); in the
#     13-14.5 d band 0.23 (chance 0.06); outside both bands 0.046 vs 0.047
#     chance - i.e. real signals show no gap preference, which is what
#     makes this a clean discriminator.
#   - The #1 and #2 NOVEL candidates by SNR (TIC 398499986, 401120789)
#     were each a single "eclipse" sitting 100% on gap edges.
#   - Control: WASP-32 (published transiting planet) - 5 eclipses, passes.
# A periodic signal needs >= 3 observed events to establish its period
# (the standard requirement in transit/EB surveys), so fewer is now a hard
# gate. Gap-edge excess among stars that DO pass is kept as a caution flag
# only: with just 3-4 eclipses, one landing on a gap edge by chance moves
# the fraction a lot, so it is reported, not used to exclude.
MIN_ECLIPSES_OBSERVED = 3
MIN_PTS_PER_ECLIPSE = 3       # an epoch counts as observed only with >= 3 in-transit points
GAP_DAYS = 0.5                # a gap in time coverage longer than this is a data gap
NEAR_GAP_DAYS = 0.5           # in-transit point this close to a gap edge counts as near a gap
GAP_EDGE_MIN_FRAC = 0.3       # caution flag: > 30% of in-transit points near gap edges...
GAP_EDGE_CHANCE_RATIO = 3.0   # ...AND > 3x this star's own chance level

# --- gap #8, found by the pixel-level check (diag_pixel.py) ---
#
# (8) The #1 and #5 NOVEL candidates (TIC 180251856, BLS depth 35%, SNR 3428;
# TIC 22206966, depth 10%) had NO eclipse: median flux inside and outside the
# BLS box was identical. BLS had fitted its widest allowed box (0.5 d, over
# half of these sub-day orbits) and its inverse-variance weighted means were
# dominated by a few time-clustered low points with small error bars. Gap #7's
# eclipse count was fooled too: a box covering most of every orbit always
# holds >= 3 points per cycle.
# Cross-check: the MEDIAN-based depth, median(out of box) - median(in box),
# which a handful of outliers cannot move. diag_robust.py on all 361 vetted
# stars: real signals cluster at depth_ratio (median depth / BLS depth)
# 0.7-1.5; a second population sits below 0.1 (20 of 121 trustworthy; 17 of
# those used the 0.5 d max box, 16 had duty cycle > 30%). All 4 published /
# known controls (WASP-32, TOI-3555.01, TOI-6485.01, TIC 158329671's real
# neighbour EB signal) have ratio 0.99-1.04; the weakest is 12 sigma.
# Gate: ratio < 0.5 (midway between the populations) OR robust significance
# < 7 sigma (below the weakest control with margin; close to the classic
# 7.1 sigma transit-survey threshold). Known cost: a few stars with REAL but
# much smaller variability than BLS claimed (e.g. TIC 355981677: 1.6% at 35
# sigma vs BLS 20.6%) are excluded rather than reported with a wrong depth.
MIN_DEPTH_RATIO = 0.5
MIN_ROBUST_SIGMA = 7.0


def clean_light_curve(t, flux, flux_err):
    valid = np.isfinite(t) & np.isfinite(flux)
    t, flux = t[valid], flux[valid]
    flux_err = flux_err[valid] if len(flux_err) == len(valid) else np.full_like(flux, np.nan)

    physical = (flux > FLUX_MIN_PHYSICAL) & (flux < FLUX_MAX_PHYSICAL)
    n_dropped_physical = int((~physical).sum())
    t, flux, flux_err = t[physical], flux[physical], flux_err[physical]

    if len(flux) == 0:
        return t, flux, flux_err, n_dropped_physical

    bad_err = ~np.isfinite(flux_err) | (flux_err <= 0)
    if bad_err.any():
        fallback = np.std(flux) if np.isfinite(np.std(flux)) and np.std(flux) > 0 else 1e-6
        flux_err = np.where(bad_err, fallback, flux_err)

    return t, flux, flux_err, n_dropped_physical


def segment_quality_check(t, flux, gap_days=SEGMENT_GAP_DAYS, min_pts=MIN_SEGMENT_POINTS,
                           median_offset_sigma=MAX_SEGMENT_MEDIAN_OFFSET_SIGMA,
                           scatter_ratio_limit=MAX_SEGMENT_SCATTER_RATIO):
    if len(t) < 2:
        return {"n_segments": len(t), "max_segment_median_offset": np.nan,
                "max_segment_scatter_ratio": np.nan, "min_segment_scatter_ratio": np.nan,
                "inhomogeneous_photometry": False}

    order = np.argsort(t)
    t_sorted, flux_sorted = t[order], flux[order]

    gaps = np.diff(t_sorted)
    breaks = np.where(gaps > gap_days)[0] + 1
    segments = np.split(np.arange(len(t_sorted)), breaks)

    global_median = np.median(flux_sorted)
    global_mad = np.median(np.abs(flux_sorted - global_median))
    global_sigma = 1.4826 * global_mad if global_mad > 0 else np.std(flux_sorted)
    if not np.isfinite(global_sigma) or global_sigma <= 0:
        global_sigma = 1e-6

    seg_medians, seg_sigmas = [], []
    for seg_idx in segments:
        if len(seg_idx) < min_pts:
            continue
        seg_flux = flux_sorted[seg_idx]
        m = np.median(seg_flux)
        mad = np.median(np.abs(seg_flux - m))
        s = 1.4826 * mad if mad > 0 else np.std(seg_flux)
        seg_medians.append(m)
        seg_sigmas.append(s)

    n_valid_segments = len(seg_medians)
    if n_valid_segments < 2:
        return {"n_segments": n_valid_segments, "max_segment_median_offset": np.nan,
                "max_segment_scatter_ratio": np.nan, "min_segment_scatter_ratio": np.nan,
                "inhomogeneous_photometry": False}

    seg_medians = np.array(seg_medians)
    seg_sigmas = np.array(seg_sigmas)

    max_offset = float(np.max(np.abs(seg_medians - global_median) / global_sigma))

    positive_sigmas = seg_sigmas[seg_sigmas > 0]
    if len(positive_sigmas) > 0:
        median_seg_sigma = np.median(positive_sigmas)
        if median_seg_sigma > 0:
            max_scatter_ratio = float(np.max(seg_sigmas) / median_seg_sigma)
            min_scatter_ratio = float(np.min(seg_sigmas) / median_seg_sigma)
        else:
            max_scatter_ratio, min_scatter_ratio = 1.0, 1.0
    else:
        max_scatter_ratio, min_scatter_ratio = 1.0, 1.0

    flagged = bool(
        max_offset > median_offset_sigma
        or max_scatter_ratio > scatter_ratio_limit
        or min_scatter_ratio < 1.0 / scatter_ratio_limit
    )

    return {
        "n_segments": n_valid_segments,
        "max_segment_median_offset": max_offset,
        "max_segment_scatter_ratio": max_scatter_ratio,
        "min_segment_scatter_ratio": min_scatter_ratio,
        "inhomogeneous_photometry": flagged,
    }


def bls_result_sanity_check(bls, min_plausible_depth=MIN_PLAUSIBLE_DEPTH):
    """See gap #6 above. Two independent, cheap checks on the raw BLS
    output before it is trusted any further: a depth that is not
    plausibly resolvable given any real photometric precision, or any of
    depth/depth_err/snr coming back non-finite (which a degenerate
    near-empty bin can produce)."""
    depth, depth_err, snr = bls["depth"], bls["depth_err"], bls["snr"]
    non_finite = not (np.isfinite(depth) and np.isfinite(depth_err) and np.isfinite(snr))
    depth_too_small = bool(np.isfinite(depth) and 0 < depth < min_plausible_depth)
    return {
        "depth_too_small": depth_too_small,
        "non_finite_bls_result": bool(non_finite),
    }


def eclipse_coverage_check(t, period, t0, duration):
    """See gap #7 above. Counts distinct observed eclipse epochs and measures
    whether in-transit points cluster on data-gap edges beyond chance."""
    phase = ((t - t0 + period / 2) % period) / period - 0.5
    in_tr = np.abs(phase) < (duration / period) / 2
    epochs = np.round((t - t0) / period).astype(int)
    counts = pd.Series(epochs[in_tr]).value_counts()
    n_ecl = int((counts >= MIN_PTS_PER_ECLIPSE).sum())

    ts = np.sort(t)
    idx = np.where(np.diff(ts) > GAP_DAYS)[0]
    interior = np.sort(np.concatenate([ts[idx], ts[idx + 1]])) if len(idx) else np.array([])

    def frac_near(sel_t):
        if len(interior) == 0 or len(sel_t) == 0:
            return 0.0
        pos = np.searchsorted(interior, sel_t)
        left = interior[np.clip(pos - 1, 0, len(interior) - 1)]
        right = interior[np.clip(pos, 0, len(interior) - 1)]
        d = np.minimum(np.abs(sel_t - left), np.abs(sel_t - right))
        return float((d < NEAR_GAP_DAYS).mean())

    f_in = frac_near(t[in_tr])
    f_all = frac_near(t)
    too_few = n_ecl < MIN_ECLIPSES_OBSERVED
    gap_suspect = bool(f_in > GAP_EDGE_MIN_FRAC and f_in > GAP_EDGE_CHANCE_RATIO * f_all)
    return {
        "n_eclipses_observed": n_ecl,
        "too_few_eclipses": bool(too_few),
        "frac_intransit_near_gap": f_in,
        "frac_all_near_gap": f_all,
        "gap_edge_suspect": gap_suspect,
    }


def robust_depth_check(t, flux, period, t0, duration):
    """See gap #8 above. Median-based depth and its significance, compared
    with the BLS (weighted-mean) depth."""
    dt = ((t - t0 + period / 2) % period) - period / 2
    inn = np.abs(dt) < duration / 2
    if inn.sum() < 3 or (~inn).sum() < 3:
        return {"robust_depth": np.nan, "robust_sigma": np.nan, "depth_ratio": np.nan,
                "robust_depth_mismatch": True}
    f_out = flux[~inn]
    rd = float(np.median(f_out) - np.median(flux[inn]))
    mad = 1.4826 * np.median(np.abs(f_out - np.median(f_out)))
    err = mad * np.sqrt(np.pi / 2 / inn.sum()) if mad > 0 else np.nan
    rsig = float(rd / err) if np.isfinite(err) and err > 0 else np.nan
    return {"robust_depth": rd, "robust_sigma": rsig, "depth_ratio": np.nan,
            "robust_depth_mismatch": False}


def odd_even_test(t, flux, period, t0, duration):
    phase = ((t - t0 + period / 2) % period) / period - 0.5
    half_dur_phase = (duration / period) / 2
    in_eclipse = np.abs(phase) < half_dur_phase * 1.2
    epoch = np.round((t - t0) / period).astype(int)

    odd_mask = in_eclipse & (epoch % 2 != 0)
    even_mask = in_eclipse & (epoch % 2 == 0)

    out_of_eclipse = ~in_eclipse
    if out_of_eclipse.sum() < 10:
        return {"depth_odd": np.nan, "depth_even": np.nan, "odd_even_z": np.nan,
                "possible_half_period_alias": False, "n_odd": int(odd_mask.sum()),
                "n_even": int(even_mask.sum())}

    baseline = np.median(flux[out_of_eclipse])
    baseline_std = np.std(flux[out_of_eclipse])

    n_odd, n_even = int(odd_mask.sum()), int(even_mask.sum())
    if n_odd < 3 or n_even < 3:
        return {"depth_odd": np.nan, "depth_even": np.nan, "odd_even_z": np.nan,
                "possible_half_period_alias": False, "n_odd": n_odd, "n_even": n_even}

    depth_odd = baseline - np.median(flux[odd_mask])
    depth_even = baseline - np.median(flux[even_mask])
    err_odd = baseline_std / np.sqrt(n_odd)
    err_even = baseline_std / np.sqrt(n_even)
    z = abs(depth_odd - depth_even) / np.sqrt(err_odd ** 2 + err_even ** 2)

    return {
        "depth_odd": float(depth_odd), "depth_even": float(depth_even),
        "odd_even_z": float(z), "possible_half_period_alias": bool(z > ODD_EVEN_ALIAS_THRESHOLD),
        "n_odd": n_odd, "n_even": n_even,
    }


def secondary_eclipse_search(t, flux, period, t0, duration, n_bins=100, min_bin_pts=5):
    phase = ((t - t0 + period / 2) % period) / period - 0.5
    half_dur_phase = (duration / period) / 2
    mask_primary = np.abs(phase) < half_dur_phase * 2

    bin_edges = np.linspace(-0.5, 0.5, n_bins + 1)
    bin_idx = np.digitize(phase, bin_edges) - 1
    bin_flux = np.full(n_bins, np.nan)

    for b in range(n_bins):
        sel = (bin_idx == b) & (~mask_primary)
        if sel.sum() >= min_bin_pts:
            bin_flux[b] = np.median(flux[sel])

    valid = ~np.isnan(bin_flux)
    if valid.sum() < 10:
        return {"secondary_phase": np.nan, "secondary_depth": np.nan,
                "secondary_sigma": np.nan, "secondary_detected": False,
                "secondary_flagged_implausible": False}

    oot_std = np.nanstd(bin_flux[valid])
    oot_median = np.nanmedian(bin_flux[valid])
    sec_bin = np.nanargmin(bin_flux)
    sec_phase = (bin_edges[sec_bin] + bin_edges[sec_bin + 1]) / 2
    sec_depth = oot_median - bin_flux[sec_bin]
    sec_sigma = sec_depth / oot_std if oot_std > 0 else 0.0

    implausible = bool(abs(sec_depth) * 1000 > MAX_PLAUSIBLE_SECONDARY_PPT)

    return {
        "secondary_phase": float(sec_phase), "secondary_depth": float(sec_depth),
        "secondary_sigma": float(sec_sigma),
        "secondary_detected": bool(sec_sigma > SECONDARY_DETECTION_SIGMA and not implausible),
        "secondary_flagged_implausible": implausible,
    }


def make_plot(tic, t, flux, bls, plot_path):
    period, t0, duration = bls["period"], bls["t0"], bls["duration"]
    phase = ((t - t0 + period / 2) % period) / period - 0.5

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].scatter(t, flux, s=2, alpha=0.5)
    axes[0].set_xlabel("Time (BTJD)")
    axes[0].set_ylabel("Normalized flux")
    axes[0].set_title(f"TIC {tic} - full light curve (cleaned)")

    axes[1].scatter(phase, flux, s=3, alpha=0.4)
    axes[1].set_xlim(-0.5, 0.5)
    axes[1].set_xlabel("Phase")
    axes[1].set_title(f"Folded at P={period:.4f}d  depth={bls['depth']*1000:.1f}ppt  SNR={bls['snr']:.0f}")

    fig.tight_layout()
    fig.savefig(plot_path, dpi=100)
    plt.close(fig)


def process_one_star(tic, lc_path, plot_dir):
    df = pd.read_csv(lc_path)
    t_raw = df["time"].values
    flux_raw = df["flux"].values
    flux_err_raw = df["flux_err"].values

    t, flux, flux_err, n_dropped_physical = clean_light_curve(t_raw, flux_raw, flux_err_raw)

    frac_dropped = n_dropped_physical / len(t_raw) if len(t_raw) > 0 else 0.0
    result = {
        "TIC": tic, "n_points_raw": len(t_raw), "n_points": len(t), "status": None, "error": "",
        "n_dropped_physical": n_dropped_physical, "frac_dropped_physical": frac_dropped,
    }

    if frac_dropped > MAX_FRAC_DROPPED_PHYSICAL:
        result["status"] = "UNRELIABLE_DATA"
        return result

    if len(t) < 50:
        result["status"] = "TOO_FEW_POINTS"
        return result

    span = t.max() - t.min()
    max_period = min(MAX_PERIOD_DAYS, span / 2)
    if max_period <= MIN_PERIOD_DAYS:
        result["status"] = "BASELINE_TOO_SHORT"
        return result

    seg = segment_quality_check(t, flux)
    result.update(seg)

    try:
        model = BoxLeastSquares(t, flux, dy=flux_err)
        durations = np.geomspace(MIN_DURATION_DAYS, MAX_DURATION_DAYS, N_DURATION_GRID)
        periods = np.geomspace(MIN_PERIOD_DAYS, max_period, N_PERIOD_GRID)
        bls_result = model.power(periods, durations, objective="snr")
        best_idx = np.argmax(bls_result.power)
        bls = {
            "period": float(bls_result.period[best_idx]),
            "t0": float(bls_result.transit_time[best_idx]),
            "duration": float(bls_result.duration[best_idx]),
            "depth": float(bls_result.depth[best_idx]),
            "depth_err": float(bls_result.depth_err[best_idx]),
            "snr": float(bls_result.power[best_idx]),
        }
    except Exception as e:
        result["status"] = "BLS_ERROR"
        result["error"] = str(e)[:200]
        return result

    result.update({f"bls_{k}": v for k, v in bls.items()})

    sanity = bls_result_sanity_check(bls)
    result.update(sanity)

    phase_at_best = ((t - bls["t0"] + bls["period"] / 2) % bls["period"]) / bls["period"] - 0.5
    half_dur_phase_best = (bls["duration"] / bls["period"]) / 2
    n_in_transit = int((np.abs(phase_at_best) < half_dur_phase_best).sum())
    result["n_in_transit"] = n_in_transit
    insufficient = n_in_transit < MIN_INTRANSIT_POINTS

    below_noise_floor = bool(np.isfinite(bls["snr"]) and bls["snr"] < MIN_SNR_THRESHOLD) or sanity["non_finite_bls_result"]
    result["below_noise_floor"] = bool(below_noise_floor)

    frac_above_1_2 = float((flux > 1.2).mean())
    noisy_photometry = frac_above_1_2 > MAX_FRAC_ABOVE_1_2
    result["frac_above_1_2"] = frac_above_1_2
    result["noisy_photometry"] = bool(noisy_photometry)

    cov = eclipse_coverage_check(t, bls["period"], bls["t0"], bls["duration"])
    result.update(cov)

    rob = robust_depth_check(t, flux, bls["period"], bls["t0"], bls["duration"])
    if np.isfinite(rob["robust_depth"]) and bls["depth"] > 0:
        rob["depth_ratio"] = rob["robust_depth"] / bls["depth"]
    rob["robust_depth_mismatch"] = bool(
        rob["robust_depth_mismatch"]
        or not np.isfinite(rob["depth_ratio"]) or rob["depth_ratio"] < MIN_DEPTH_RATIO
        or not np.isfinite(rob["robust_sigma"]) or rob["robust_sigma"] < MIN_ROBUST_SIGMA)
    result.update(rob)

    # gap_edge_suspect deliberately NOT in this list - caution flag only (see gap #7)
    result["depth_flagged_implausible"] = bool(
        (np.isfinite(bls["depth"]) and (bls["depth"] > MAX_PLAUSIBLE_DEPTH or bls["depth"] < 0))
        or insufficient or below_noise_floor or noisy_photometry
        or seg["inhomogeneous_photometry"]
        or sanity["depth_too_small"] or sanity["non_finite_bls_result"]
        or cov["too_few_eclipses"]
        or rob["robust_depth_mismatch"]
    )
    result["insufficient_intransit_points"] = bool(insufficient)

    oe = odd_even_test(t, flux, bls["period"], bls["t0"], bls["duration"])
    result.update(oe)

    sec = secondary_eclipse_search(t, flux, bls["period"], bls["t0"], bls["duration"])
    result.update(sec)

    try:
        make_plot(tic, t, flux, bls, plot_dir / f"TIC{tic}_folded.png")
    except Exception:
        pass

    result["status"] = "OK"
    return result


def cross_validate(vet_df, known_dir: Path):
    checks = []
    for name, period_col in [("table3_new_ebs", "Per"), ("table4_known_ebs", "Per-TESS")]:
        path = known_dir / f"{name}.parquet"
        if not path.exists():
            continue
        ref = pd.read_parquet(path)[["TIC", period_col]].rename(columns={period_col: "published_period"})
        merged = vet_df.merge(ref, on="TIC", how="inner")
        if len(merged) == 0:
            continue

        merged["period_ratio"] = merged["bls_period"] / merged["published_period"]
        merged["agrees"] = np.isclose(merged["period_ratio"], 1.0, rtol=0.01) | \
                            np.isclose(merged["period_ratio"], 0.5, rtol=0.01) | \
                            np.isclose(merged["period_ratio"], 2.0, rtol=0.01)
        merged["source_catalog"] = name
        checks.append(merged[["TIC", "source_catalog", "bls_period", "published_period",
                               "period_ratio", "agrees"]])

    if not checks:
        return None
    return pd.concat(checks, ignore_index=True)


RESULT_COLUMNS = [
    "TIC", "n_points_raw", "n_points", "status", "error",
    "n_dropped_physical", "frac_dropped_physical",
    "n_segments", "max_segment_median_offset", "max_segment_scatter_ratio",
    "min_segment_scatter_ratio", "inhomogeneous_photometry",
    "bls_period", "bls_t0", "bls_duration", "bls_depth", "bls_depth_err", "bls_snr",
    "depth_too_small", "non_finite_bls_result",
    "n_in_transit", "below_noise_floor", "frac_above_1_2", "noisy_photometry",
    "n_eclipses_observed", "too_few_eclipses", "frac_intransit_near_gap",
    "frac_all_near_gap", "gap_edge_suspect",
    "robust_depth", "robust_sigma", "depth_ratio", "robust_depth_mismatch",
    "depth_flagged_implausible", "insufficient_intransit_points",
    "depth_odd", "depth_even", "odd_even_z", "possible_half_period_alias", "n_odd", "n_even",
    "secondary_phase", "secondary_depth", "secondary_sigma", "secondary_detected",
    "secondary_flagged_implausible",
]


def append_result_row(results_path: Path, row: dict, write_header: bool):
    with open(results_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in RESULT_COLUMNS})
        f.flush()


def main():
    if len(sys.argv) != 2:
        print("Usage: py f3i_vet.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    lc_dir = project_root / "data" / "lightcurves"
    processed_dir = project_root / "data" / "processed"
    plot_dir = lc_dir / "folded_plots_v2"
    plot_dir.mkdir(parents=True, exist_ok=True)

    lc_files = sorted(lc_dir.glob("TIC*.csv"))
    if not lc_files:
        print(f"ERROR: no light curve CSVs found in {lc_dir}")
        sys.exit(1)

    # deliberately a NEW output file, not an extension of f3h_vetting_results.csv -
    # every star needs to be re-run under the new robust-depth gate, since a star
    # already marked trustworthy under the old logic might not be under this one.
    # Resuming from f3h's file here would silently keep those stale verdicts.
    results_path = processed_dir / "f3i_vetting_results.csv"
    already_done = set()
    if results_path.exists():
        prior = pd.read_csv(results_path)
        already_done = set(prior["TIC"].astype(int))
        print(f"Found existing f3i results with {len(already_done)} star(s) already vetted - "
              f"resuming, these will be skipped.")

    write_header = not results_path.exists()

    todo = [p for p in lc_files if int(p.stem.replace("TIC", "")) not in already_done]
    print(f"Found {len(lc_files)} light curve(s) total, {len(todo)} remaining to vet this run "
          f"(v9: same gates as f3h, plus a median-depth cross-check - see gap #8 "
          f"in this file's comments)")

    start_time = time.time()
    n_done_this_run = 0

    for i, lc_path in enumerate(todo):
        tic = int(lc_path.stem.replace("TIC", ""))
        print(f"[{i + 1}/{len(todo)}] TIC {tic} ... ", end="", flush=True)

        res = process_one_star(tic, lc_path, plot_dir)

        append_result_row(results_path, res, write_header)
        write_header = False
        n_done_this_run += 1

        if res["status"] == "OK":
            alias_flag = " [POSSIBLE ALIAS]" if res.get("possible_half_period_alias") else ""
            sec_flag = " [SECONDARY DETECTED]" if res.get("secondary_detected") else ""
            implaus_flag = " [EXCLUDED]" if res.get("depth_flagged_implausible") else ""
            thin_flag = " [TOO FEW IN-TRANSIT POINTS]" if res.get("insufficient_intransit_points") else ""
            noise_flag = " [BELOW NOISE FLOOR]" if res.get("below_noise_floor") else ""
            noisy_flag = " [NOISY PHOTOMETRY]" if res.get("noisy_photometry") else ""
            seg_flag = " [INHOMOGENEOUS SEGMENT]" if res.get("inhomogeneous_photometry") else ""
            tiny_flag = " [DEPTH TOO SMALL]" if res.get("depth_too_small") else ""
            nonfinite_flag = " [NON-FINITE BLS RESULT]" if res.get("non_finite_bls_result") else ""
            ecl_flag = (f" [ONLY {res.get('n_eclipses_observed')} ECLIPSE(S) OBSERVED]"
                        if res.get("too_few_eclipses") else "")
            gap_flag = " [CAUTION: GAP-EDGE]" if res.get("gap_edge_suspect") else ""
            rob_flag = (f" [MEDIAN DEPTH MISMATCH: ratio {res.get('depth_ratio', float('nan')):.2f}, "
                        f"{res.get('robust_sigma', float('nan')):.1f} sigma]"
                        if res.get("robust_depth_mismatch") else "")
            dropped = res.get("n_dropped_physical", 0)
            drop_note = f"  (dropped {dropped} bad cadences)" if dropped else ""
            print(f"P={res['bls_period']:.4f}d  SNR={res['bls_snr']:.0f}  "
                  f"depth={res['bls_depth']*1000:.1f}ppt  n_in_transit={res.get('n_in_transit')}"
                  f"{alias_flag}{sec_flag}{implaus_flag}{thin_flag}{noise_flag}{noisy_flag}"
                  f"{seg_flag}{tiny_flag}{nonfinite_flag}{ecl_flag}{gap_flag}{rob_flag}{drop_note}")
        elif res["status"] == "UNRELIABLE_DATA":
            frac = res.get("frac_dropped_physical", 0)
            print(f"UNRELIABLE_DATA  ({frac*100:.0f}% of cadences were physically invalid, skipping)")
        else:
            print(f"{res['status']}  {res.get('error', '')}")

        if n_done_this_run % 25 == 0 and n_done_this_run < len(todo):
            elapsed = time.time() - start_time
            rate = elapsed / n_done_this_run
            eta_remaining = rate * (len(todo) - n_done_this_run)
            print(f"    ... {n_done_this_run}/{len(todo)} done this run, "
                  f"{elapsed/60:.1f} min elapsed, ~{eta_remaining/60:.0f} min remaining "
                  f"at this rate (safe to stop anytime - resume by re-running this script)")

    elapsed = time.time() - start_time

    vet_df = pd.read_csv(results_path)
    print(f"\n{'=' * 70}")
    print("F3i VETTING SUMMARY (incremental, resumable)")
    print(f"{'=' * 70}")
    print(f"Vetted this run:          {n_done_this_run}")
    print(f"Time this run:            {elapsed / 60:.1f} min")
    print(f"Total in results so far:  {len(vet_df)} / {len(lc_files)}")
    print(f"\nStatus breakdown (all time):")
    print(vet_df["status"].value_counts().to_string())

    ok = vet_df[vet_df["status"] == "OK"]
    if len(ok) > 0:
        print(f"\nSuccessfully vetted: {len(ok)}/{len(vet_df)}")
        snr = ok["bls_snr"].replace([np.inf, -np.inf], np.nan)
        n_nonfinite_snr = int(snr.isna().sum())
        print(f"\nSNR distribution (finite values only; {n_nonfinite_snr} non-finite excluded):")
        print(snr.dropna().describe().to_string())
        print(f"\nbls_depth distribution (should be in [0,1)):")
        print(ok["bls_depth"].describe().to_string())

        print(f"\nExcluded by ANY gate below (combined 'depth_flagged_implausible'): "
              f"{int(ok['depth_flagged_implausible'].sum())}")
        print(f"Depths outside [0, {MAX_PLAUSIBLE_DEPTH}]: "
              f"{int(((ok['bls_depth'] > MAX_PLAUSIBLE_DEPTH) | (ok['bls_depth'] < 0)).sum())}")
        print(f"Results flagged for too few in-transit points (<{MIN_INTRANSIT_POINTS}): "
              f"{int(ok['insufficient_intransit_points'].sum())}")
        print(f"Results flagged below the noise floor (SNR < {MIN_SNR_THRESHOLD}): "
              f"{int(ok['below_noise_floor'].sum())}")
        print(f"Stars flagged noisy_photometry (>{MAX_FRAC_ABOVE_1_2*100:.0f}% of flux above 1.2x baseline): "
              f"{int(ok['noisy_photometry'].sum())}")
        print(f"Stars flagged inhomogeneous_photometry: {int(ok['inhomogeneous_photometry'].sum())}")
        print(f"Stars flagged depth_too_small (<{MIN_PLAUSIBLE_DEPTH*1e6:.0f} ppm): "
              f"{int(ok['depth_too_small'].sum())}")
        print(f"Stars flagged non_finite_bls_result: {int(ok['non_finite_bls_result'].sum())}")
        print(f"Stars flagged too_few_eclipses (<{MIN_ECLIPSES_OBSERVED} observed): "
              f"{int(ok['too_few_eclipses'].sum())}")
        print(f"Stars flagged robust_depth_mismatch (median/BLS depth < {MIN_DEPTH_RATIO} or "
              f"< {MIN_ROBUST_SIGMA:.0f} sigma): {int(ok['robust_depth_mismatch'].sum())}")

        n_unreliable = int((vet_df['status'] == 'UNRELIABLE_DATA').sum())
        print(f"\nStars excluded as UNRELIABLE_DATA (>{MAX_FRAC_DROPPED_PHYSICAL*100:.0f}% of "
              f"cadences physically invalid): {n_unreliable}")
        n_trustworthy = int((ok["depth_flagged_implausible"] == False).sum())
        print(f"\n*** TRUSTWORTHY PRIMARY DETECTIONS: {n_trustworthy} / {len(vet_df)} ***")
        tw = ok[ok["depth_flagged_implausible"] == False]
        print(f"    of which carry the gap-edge CAUTION flag (not excluded): "
              f"{int(tw['gap_edge_suspect'].sum())}")

        print(f"\nPossible half-period aliases flagged: {int(ok['possible_half_period_alias'].sum())}")
        print(f"Secondary eclipses detected: {int(ok['secondary_detected'].sum())}")

        print(f"\n{'=' * 70}")
        print("CROSS-VALIDATION AGAINST PUBLISHED CATALOGS")
        print(f"{'=' * 70}")
        cross = cross_validate(ok, processed_dir)
        if cross is None or len(cross) == 0:
            print("No overlap between vetted targets and table3/table4 (expected).")
        else:
            print(cross.to_string(index=False))
            print(f"\nAgreement rate: {cross['agrees'].sum()}/{len(cross)} "
                  f"({100 * cross['agrees'].mean():.1f}%)")
            cross_path = processed_dir / "f3i_cross_validation.csv"
            cross.to_csv(cross_path, index=False)
            print(f"Saved: {cross_path}")

    if len(vet_df) < len(lc_files):
        remaining = len(lc_files) - len(vet_df)
        print(f"\n{remaining} light curve(s) not yet vetted - re-run this script to continue.")

    print(f"\nResults saved: {results_path}")
    print(f"Folded-light-curve plots saved to: {plot_dir}")


if __name__ == "__main__":
    main()