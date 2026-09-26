import sys
import csv
import json
import re
import time
import threading
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import lightkurve as lk
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Catalogs
except ImportError as exc:
    print("Missing package: " + str(exc))
    sys.exit(1)

# Pixel-level source check (difference imaging). For each candidate, download
# a small TESS full-frame-image cutout (TESScut) for one sector, then for
# every pixel compare its brightness OUT of eclipse with IN eclipse. The
# pixels that dim the most show where the eclipsing star really is:
#   difference image = median(out-of-eclipse) - median(in-eclipse)
# Its flux-weighted centroid is compared with the target's catalogued pixel
# position and with every neighbour bright enough to cause the dip (the same
# brightness test as diag_blend.py).
#
# Verdicts:
#   ON_TARGET       - dimming centred within 1 pixel (21") of the target, and
#                     no other capable star is closer to it
#   OFF_TARGET      - dimming centred > 1 pixel from the target
#   UNRESOLVED      - within 1 px of the target, but a capable neighbour is
#                     just as close: TESS cannot separate them (21" pixels)
#   INCONCLUSIVE    - light curve shows no clear eclipse in the chosen sector,
#                     difference image too weak (peak SNR < 5) or spread out
#                     rather than star-shaped (compactness < 0.5), or no
#                     usable cutout
# 1 pixel is conservative for TESS difference-image centroids (typical
# systematics 0.1-0.3 px at good SNR). The two built-in controls calibrate
# it on every run: WASP-32 (a published planet, must be ON_TARGET) and
# TIC 158329671 (its dip matches a known EB 40" away, must be OFF_TARGET).
#
# v2 fixes, from the first real 20-star run:
#  (a) EPHEMERIS DRIFT. A multi-year light curve's BLS period is anchored by
#      the sectors with the most data; in a sparse sector years away, small
#      period errors accumulate (TIC 136191877: its own light curve shows NO
#      dip at the predicted phase in sector 15, but 40% at phase -0.18). Now:
#      pick the cutout sector where the light curve has the MOST points, and
#      re-find the eclipse time inside that sector from the light curve itself.
#  (b) The eclipse was required to show in the TARGET's own 3x3 pixels before
#      the difference image was trusted. But a dip that is really on a
#      neighbour need not show there - that is exactly what the difference
#      image is for. The target-pixel dip is now reported, not gated on.
#  (c) BACKGROUND GRADIENTS. A flat per-cadence background left scattered-
#      light slopes (TIC 118352931: a smooth ramp over the whole cutout, not
#      a star). Now a plane is fitted per cadence to the faintest pixels, and
#      a difference image whose significant pixels are not concentrated
#      around one spot (compactness < 0.5) is INCONCLUSIVE, not OFF_TARGET.

N_TOP = 20
CONTROLS = {427332229: "ON_TARGET expected (WASP-32, published planet)",
            158329671: "OFF_TARGET expected (known TESS EB 40 arcsec away)"}

# site dark-theme colors (must match site/src/app/globals.css --panel-2 etc.)
PLOT_BG = "#0e131d"
PLOT_LINE = "#1a2130"
PLOT_FG = "#e8eaf0"
PLOT_MUTED = "#9aa3b2"
CUTOUT_SIZE = 11
PIX_ARCSEC = 21.0
ON_TARGET_MAX_PX = 1.0
MIN_DIFF_SNR = 5.0
MIN_DIP_SIGMA = 3.0
IN_CORE_FRAC = 0.35     # in-eclipse = |dt| < 0.35 x duration (eclipse core), max 0.1 P
OUT_GAP_FRAC = 0.75     # out-of-eclipse must also be > 0.75 x duration from primary
QUAD_LO, QUAD_HI = 0.15, 0.35   # out-of-eclipse = quadrature phases (see difference_image)
NBR_RADIUS_ARCSEC = 105.0  # 5 pixels - covers the whole useful cutout area
MAX_SECTOR_TRIES = 3
SATURATION_TMAG = 7.5   # TESS pixels saturate around Tmag 6.8; warn a bit fainter
MIN_LC_DIP_SIGMA = 5.0  # the light curve itself must show the eclipse in the chosen sector
MIN_LC_PTS_IN_SECTOR = 50
MIN_COMPACTNESS = 0.5   # share of significant difference flux within 1 px of its peak
SIG_PIX_SNR = 3.0       # pixels counted as "significant" for compactness

RESULT_COLUMNS = ["TIC", "role", "verdict", "sector", "lc_pts_in_sector", "t0_shift_phase",
                  "lc_dip_sigma", "compactness", "n_in", "n_out", "dip_sigma",
                  "diff_peak_snr", "centroid_offset_px", "centroid_offset_arcsec",
                  "nearest_capable_TIC", "nearest_capable_dist_px", "nearest_capable_dTmag",
                  "n_capable_in_cutout", "note"]

# A remote query or download can stall forever with no exception at all if
# the server just stops responding - invisible on a machine someone is
# watching (they notice and interrupt), but it hangs an unattended GitHub
# Actions job for its entire time budget. These wrap every such call in a
# hard wall-clock deadline so a stall becomes a normal, logged failure
# instead of blocking the whole run.
TESSCUT_SEARCH_TIMEOUT_SEC = 90
TESSCUT_DOWNLOAD_TIMEOUT_SEC = 180
CATALOG_TIMEOUT_SEC = 120


def call_with_timeout(fn, args=(), kwargs=None, timeout=60):
    """
    Run fn(*args, **kwargs) with a hard wall-clock deadline. Raises
    TimeoutError if it does not finish in time.

    Uses a plain threading.Thread with daemon=True rather than
    concurrent.futures.ThreadPoolExecutor: ThreadPoolExecutor registers an
    atexit hook that joins every worker thread it ever created before the
    interpreter exits, so a genuinely stuck call would still stall the
    whole script at shutdown even after "timing out". A daemon thread
    carries no such obligation - Python exits without waiting for it.
    """
    kwargs = kwargs or {}
    box = {"value": None, "error": None}

    def runner():
        try:
            box["value"] = fn(*args, **kwargs)
        except Exception as e:
            box["error"] = e

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"call did not finish within {timeout}s")
    if box["error"] is not None:
        raise box["error"]
    return box["value"]


def sector_of(mission_str):
    m = re.search(r"Sector (\d+)", str(mission_str))
    return int(m.group(1)) if m else None


def approx_sector_range(sector):
    # linear approximation of TESS sector start times in BTJD (sector 1 starts
    # ~1325.3, ~27.36 d per sector). Only used to RANK which cutout to try
    # first; the downloaded cutout's real time range is checked afterwards.
    start = 1325.3 + (sector - 1) * 27.36
    return start, start + 27.4


def pick_cutout(tic, lc_times):
    """Download the cutout for the sector where the light curve has the MOST
    data points - the sector that anchors the BLS ephemeris (fix (a))."""
    try:
        sr = call_with_timeout(lk.search_tesscut, args=(f"TIC {tic}",),
                                timeout=TESSCUT_SEARCH_TIMEOUT_SEC)
    except TimeoutError:
        return None, f"search_tesscut did not respond within {TESSCUT_SEARCH_TIMEOUT_SEC}s"
    except Exception as exc:
        return None, f"search_tesscut failed: {repr(exc)[:120]}"
    if len(sr) == 0:
        return None, "no TESScut data"
    cands = []
    for i in range(len(sr)):
        s = sector_of(sr.mission[i])
        if s is None:
            continue
        a, b = approx_sector_range(s)
        n_lc = int(((lc_times >= a) & (lc_times <= b)).sum())
        cands.append((n_lc, -s, i, s))
    cands.sort(reverse=True)
    last_note = "no sector with light-curve data"
    for n_lc, _, i, s in cands[:MAX_SECTOR_TRIES]:
        if n_lc < MIN_LC_PTS_IN_SECTOR:
            break
        try:
            tpf = call_with_timeout(sr[i].download, kwargs={"cutout_size": CUTOUT_SIZE, "quality_bitmask": "default"},
                                     timeout=TESSCUT_DOWNLOAD_TIMEOUT_SEC)
        except TimeoutError:
            last_note = f"download did not finish within {TESSCUT_DOWNLOAD_TIMEOUT_SEC}s (sector {s})"
            continue
        except Exception as exc:
            last_note = f"download failed sector {s}: {repr(exc)[:120]}"
            continue
        if tpf is None:
            continue
        t = tpf.time.value
        n_real = int(((lc_times >= np.nanmin(t)) & (lc_times <= np.nanmax(t))).sum())
        if n_real < MIN_LC_PTS_IN_SECTOR:
            last_note = f"sector {s}: only {n_real} light-curve points inside it"
            continue
        return (tpf, s), ""
    return None, last_note


def difference_image(tpf, period, t0, duration):
    t = tpf.time.value
    flux = np.array(tpf.flux.value, dtype=float)       # (n_cad, ny, nx)
    good = np.isfinite(t) & np.all(np.isfinite(flux.reshape(len(t), -1)), axis=1)
    t, flux = t[good], flux[good]

    # per-cadence background: a PLANE (a + b*x + c*y) least-squares fitted to
    # the faintest 30% of pixels, so scattered-light slopes are removed too
    # (fix (c)); a flat median would leave the slope in the difference image
    med_img = np.nanmedian(flux, axis=0)
    bkg_mask = med_img <= np.nanpercentile(med_img, 30)
    yy, xx = np.mgrid[0:med_img.shape[0], 0:med_img.shape[1]]
    A = np.column_stack([np.ones(bkg_mask.sum()), xx[bkg_mask], yy[bkg_mask]])
    coef, *_ = np.linalg.lstsq(A, flux[:, bkg_mask].T, rcond=None)      # (3, n_cad)
    plane = (coef[0][:, None, None] + coef[1][:, None, None] * xx[None]
             + coef[2][:, None, None] * yy[None])
    flux = flux - plane

    dt = ((t - t0 + period / 2) % period) - period / 2
    ph = np.abs(dt) / period                             # 0 = primary, 0.5 = secondary
    # in-eclipse: the core of the primary eclipse
    in_m = np.abs(dt) < min(IN_CORE_FRAC * duration, 0.1 * period)
    # out-of-eclipse: the QUADRATURE bands (phase 0.15-0.35), which avoid both
    # the primary (phase 0) and the secondary eclipse (phase 0.5) of a
    # circular orbit, and are the brightness maxima of contact/ellipsoidal
    # binaries. Simply taking "everything far from the primary" would, for
    # short periods, land on the secondary minimum and cancel the signal.
    quad = (ph >= QUAD_LO) & (ph <= QUAD_HI)
    out_m = quad & (np.abs(dt) > OUT_GAP_FRAC * duration)
    if out_m.sum() < 20:          # very long eclipse relative to the period
        out_m = quad
    return t, flux, in_m, out_m


def core_vs_quadrature(t, f, period, t0, duration):
    """Median dip (quadrature minus eclipse core) and its significance."""
    dt = ((t - t0 + period / 2) % period) - period / 2
    ph = np.abs(dt) / period
    inn = np.abs(dt) < min(IN_CORE_FRAC * duration, 0.1 * period)
    q = (ph >= QUAD_LO) & (ph <= QUAD_HI)
    if inn.sum() < 3 or q.sum() < 5:
        return np.nan, np.nan
    dip = np.median(f[q]) - np.median(f[inn])
    mad = 1.4826 * np.median(np.abs(f[q] - np.median(f[q])))
    err = mad * np.sqrt(np.pi / 2 / inn.sum())
    return float(dip), float(dip / err) if err > 0 else np.nan


def refine_t0(lc, a, b, period, t0, duration):
    """Re-find the eclipse time inside [a, b] from the light curve itself
    (fix (a)): scan phase offsets over one full period, keep the deepest."""
    w = lc[(lc["time"] >= a) & (lc["time"] <= b)]
    t, f = w["time"].values, w["flux"].values
    offsets = np.linspace(-0.5, 0.5, 401) * period
    dips = np.array([core_vs_quadrature(t, f, period, t0 + o, duration)[0] for o in offsets])
    if not np.isfinite(dips).any():
        return t0, 0.0, np.nan, len(w)
    k = int(np.nanargmax(dips))
    new_t0 = t0 + offsets[k]
    _, sig = core_vs_quadrature(t, f, period, new_t0, duration)
    return new_t0, float(offsets[k] / period), sig, len(w)


def neighbours_in_pixels(tpf, ra, dec, tic, target_tmag, depth):
    r = call_with_timeout(
        Catalogs.query_region, args=(SkyCoord(ra * u.deg, dec * u.deg),),
        kwargs={"radius": NBR_RADIUS_ARCSEC * u.arcsec, "catalog": "TIC"},
        timeout=CATALOG_TIMEOUT_SEC,
    )
    df = r[["ID", "ra", "dec", "Tmag"]].to_pandas().dropna(subset=["Tmag"])
    df["ID"] = df["ID"].astype(int)
    # capable = bright enough to produce the observed dip (same test as diag_blend)
    dm_max = -2.5 * np.log10(depth) if depth > 0 else 99
    df["capable"] = (df["Tmag"] - target_tmag <= dm_max) | (df["ID"] == tic)
    x, y = tpf.wcs.world_to_pixel_values(df["ra"].values, df["dec"].values)
    df["px"], df["py"] = x, y
    return df


def analyse_one(tic, role, vet_row, lc_path, target_info, plot_dir):
    res = {"TIC": tic, "role": role, "verdict": "INCONCLUSIVE", "note": ""}
    lc = pd.read_csv(lc_path)
    got, note = pick_cutout(tic, lc["time"].values)
    if got is None:
        res["note"] = note
        return res
    tpf, sector = got
    res["sector"] = sector

    period, t0, dur = vet_row["bls_period"], vet_row["bls_t0"], vet_row["bls_duration"]
    depth = vet_row["bls_depth"]
    tt = tpf.time.value
    t0, shift, lc_sig, n_lc = refine_t0(lc, np.nanmin(tt), np.nanmax(tt), period, t0, dur)
    res["t0_shift_phase"], res["lc_dip_sigma"], res["lc_pts_in_sector"] = shift, lc_sig, n_lc
    if not np.isfinite(lc_sig) or lc_sig < MIN_LC_DIP_SIGMA:
        res["note"] = "the light curve itself shows no clear eclipse in this sector"
        return res
    t, flux, in_m, out_m = difference_image(tpf, period, t0, dur)
    res["n_in"], res["n_out"] = int(in_m.sum()), int(out_m.sum())
    if in_m.sum() < 5 or out_m.sum() < 20:
        res["note"] = "too few in/out-of-eclipse cadences in this sector"
        return res

    ra, dec, tmag = target_info["ra"], target_info["dec"], target_info["Tmag"]
    tx, ty = tpf.wcs.world_to_pixel_values(ra, dec)
    tx, ty = float(tx), float(ty)

    # 1) is the eclipse even visible in the cutout? (3x3 pixels around target)
    iy, ix = int(round(ty)), int(round(tx))
    ys = slice(max(iy - 1, 0), iy + 2)
    xs = slice(max(ix - 1, 0), ix + 2)
    ap = flux[:, ys, xs].sum(axis=(1, 2))
    ap_out, ap_in = ap[out_m], ap[in_m]
    sig = 1.4826 * np.median(np.abs(ap_out - np.median(ap_out)))
    dip = np.median(ap_out) - np.median(ap_in)
    dip_sigma = dip / (sig * np.sqrt(np.pi / 2 / in_m.sum())) if sig > 0 else 0.0
    res["dip_sigma"] = float(dip_sigma)

    # 2) difference image and its per-pixel SNR
    out_med = np.median(flux[out_m], axis=0)
    in_med = np.median(flux[in_m], axis=0)
    diff = out_med - in_med
    pix_sig = 1.4826 * np.median(np.abs(flux[out_m] - out_med), axis=0)
    noise = 1.2533 * pix_sig * np.sqrt(1.0 / in_m.sum() + 1.0 / out_m.sum())
    snr = np.where(noise > 0, diff / noise, 0.0)
    peak_snr = float(np.nanmax(snr))
    res["diff_peak_snr"] = peak_snr

    # 3) centroid of the dimming: flux-weighted over positive diff in the 3x3
    #    box around the pixel that dims the MOST (difference-image flux peak -
    #    the standard choice; the SNR peak can sit on a quiet edge pixel)
    py0, px0 = np.unravel_index(np.nanargmax(diff), diff.shape)
    yy, xx = np.mgrid[0:diff.shape[0], 0:diff.shape[1]]
    box = (np.abs(yy - py0) <= 1) & (np.abs(xx - px0) <= 1) & (diff > 0)
    w = diff[box]
    cx, cy = float((xx[box] * w).sum() / w.sum()), float((yy[box] * w).sum() / w.sum())
    off = float(np.hypot(cx - tx, cy - ty))
    res["centroid_offset_px"], res["centroid_offset_arcsec"] = off, off * PIX_ARCSEC

    # compactness (fix (c)): of all significantly-dimming pixels, what share of
    # their dimming lies within 1 px of the peak? A star gives most of it; a
    # background ramp spreads it over the whole cutout.
    sigpix = (snr > SIG_PIX_SNR) & (diff > 0)
    near = sigpix & (np.abs(yy - py0) <= 1) & (np.abs(xx - px0) <= 1)
    tot = diff[sigpix].sum()
    compact = float(diff[near].sum() / tot) if tot > 0 else 0.0
    res["compactness"] = compact

    nb = neighbours_in_pixels(tpf, ra, dec, tic, tmag, depth)
    inside = nb[(nb["px"] > -0.5) & (nb["px"] < diff.shape[1] - 0.5) &
                (nb["py"] > -0.5) & (nb["py"] < diff.shape[0] - 0.5)]
    cap = inside[inside["capable"] & (inside["ID"] != tic)].copy()
    res["n_capable_in_cutout"] = len(cap)
    sat = inside[inside["Tmag"] < SATURATION_TMAG]
    sat_note = (f"saturated star in cutout (TIC {int(sat.iloc[0]['ID'])}, Tmag "
                f"{sat.iloc[0]['Tmag']:.1f}) - bleed trails can carry its variability; "
                if len(sat) else "")
    if len(cap):
        cap["d"] = np.hypot(cap["px"] - cx, cap["py"] - cy)
        c0 = cap.sort_values("d").iloc[0]
        res["nearest_capable_TIC"] = int(c0["ID"])
        res["nearest_capable_dist_px"] = float(c0["d"])
        res["nearest_capable_dTmag"] = float(c0["Tmag"] - tmag)

    if peak_snr < MIN_DIFF_SNR:
        res["note"] = "difference image too weak to locate the source"
    elif compact < MIN_COMPACTNESS:
        res["note"] = ("dimming is spread across the cutout rather than one star "
                       "(background/systematics) - source cannot be located")
    elif off > ON_TARGET_MAX_PX:
        res["verdict"] = "OFF_TARGET"
    elif len(cap) and res["nearest_capable_dist_px"] <= off:
        res["verdict"] = "UNRESOLVED"
        res["note"] = "a capable neighbour is as close to the dimming as the target"
    else:
        res["verdict"] = "ON_TARGET"
    if sat_note:
        res["note"] = (sat_note + res["note"]).strip()

    # raw maps for the website, which draws its own out/in/difference panels
    # from these numbers (in-eclipse = out - diff). The PNG below stays as the
    # dossier figure. Non-finite pixels are written as null.
    try:
        def grid(a):
            return [[round(float(x), 3) if np.isfinite(x) else None for x in row] for row in a]
        maps = {
            "tic": int(tic), "sector": int(sector),
            "out": grid(out_med), "diff": grid(diff), "snr": grid(snr),
            "target": [round(tx, 3), round(ty, 3)],
            "centroid": [round(cx, 3), round(cy, 3)],
            "neighbours": [{"tic": int(r.ID), "x": round(float(r.px), 3), "y": round(float(r.py), 3),
                            "tmag": round(float(r.Tmag), 2), "capable": bool(r.capable)}
                           for r in inside.itertuples() if int(r.ID) != int(tic)],
        }
        (plot_dir / f"TIC{tic}_pixel.json").write_text(
            json.dumps(maps, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass

    # figure: out-of-eclipse image | difference image | SNR map
    # styled to match the site's dark panel (site/src/app/globals.css) so the
    # dossier image sits on the same background as the page around it,
    # instead of a plain white matplotlib canvas.
    try:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=PLOT_BG)
        for ax, img, title in [(axes[0], out_med, f"Out of eclipse (sector {sector})"),
                               (axes[1], diff, "Difference: out - in (where it dims)"),
                               (axes[2], snr, f"Difference SNR (peak {peak_snr:.0f})")]:
            ax.set_facecolor(PLOT_BG)
            if ax is axes[0]:
                im = ax.imshow(np.log10(np.clip(img, np.nanpercentile(img, 5), None) + 1),
                               origin="lower", cmap="gray")
            else:
                im = ax.imshow(img, origin="lower", cmap="inferno")
            cbar = fig.colorbar(im, ax=ax, fraction=0.046)
            cbar.ax.yaxis.set_tick_params(color=PLOT_MUTED, labelcolor=PLOT_MUTED)
            cbar.outline.set_edgecolor(PLOT_LINE)
            ax.scatter(inside["px"], inside["py"], s=12, facecolors="none", edgecolors="cyan", lw=0.6)
            if len(cap):
                ax.scatter(cap["px"], cap["py"], marker="x", s=50, c="lime", lw=1.5,
                           label="neighbour bright enough")
            ax.scatter([tx], [ty], marker="+", s=220, c="red", lw=2, label="target")
            ax.scatter([cx], [cy], marker="o", s=160, facecolors="none", edgecolors="yellow",
                       lw=2, label="dimming centroid")
            ax.set_xlim(-0.5, diff.shape[1] - 0.5)
            ax.set_ylim(-0.5, diff.shape[0] - 0.5)
            ax.set_title(title, fontsize=10, color=PLOT_FG)
            ax.tick_params(colors=PLOT_MUTED)
            for spine in ax.spines.values():
                spine.set_color(PLOT_LINE)
        axes[0].legend(loc="upper left", fontsize=7, facecolor=PLOT_BG,
                       edgecolor=PLOT_LINE, labelcolor=PLOT_FG)
        fig.suptitle(f"TIC {tic} [{role}] - {res['verdict']} - centroid offset "
                     f"{off:.2f} px ({off * PIX_ARCSEC:.0f} arcsec) - compactness {compact:.2f}",
                     fontsize=11, color=PLOT_FG)
        fig.tight_layout()
        fig.savefig(plot_dir / f"TIC{tic}_pixel.png", dpi=90, facecolor=fig.get_facecolor())
        plt.close(fig)
    except Exception:
        pass
    return res


def append_row(path, row, write_header):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in RESULT_COLUMNS})
        f.flush()


def main():
    if len(sys.argv) != 2:
        print("Usage: py diag_pixel.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    lc_dir = root / "data" / "lightcurves"
    plot_dir = root / "data" / "pixel_check"
    plot_dir.mkdir(parents=True, exist_ok=True)

    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    nov = pd.read_csv(proc / "f4f_novelty_results.csv")
    blend_path = proc / "diag_blend_results.csv"
    excluded = set()
    if blend_path.exists():
        b = pd.read_csv(blend_path)
        excluded = set(b.loc[b["blend_status"] == "LIKELY_CONTAMINATION", "TIC"].astype(int))
    top = (nov[(nov["verdict"] == "NOVEL") & (~nov["TIC"].isin(excluded))]
           .sort_values("bls_snr", ascending=False).head(N_TOP)["TIC"].astype(int).tolist())
    targets = [(t, "control") for t in CONTROLS if t in vet.index] + [(t, "candidate") for t in top]

    try:
        info = call_with_timeout(Catalogs.query_criteria, kwargs={"catalog": "Tic", "ID": [t for t, _ in targets]},
                                  timeout=CATALOG_TIMEOUT_SEC)
    except TimeoutError:
        print(f"\nMAST TIC catalog did not respond within {CATALOG_TIMEOUT_SEC}s.")
        print("Check your connection (and firewall/proxy settings if any) and try again.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nCould not reach the MAST TIC catalog: {exc}")
        print("This needs outbound internet access to mast.stsci.edu. Check your connection and try again.")
        sys.exit(1)
    info = info[["ID", "ra", "dec", "Tmag"]].to_pandas()
    info["ID"] = info["ID"].astype(int)
    info = info.set_index("ID")

    out_path = proc / "diag_pixel_results_v2.csv"   # v1 results kept for comparison
    done = set()
    if out_path.exists():
        done = set(pd.read_csv(out_path)["TIC"].astype(int))
    write_header = not out_path.exists()

    print("=" * 72)
    print(f"PIXEL-LEVEL SOURCE CHECK: {len(targets) - len([1 for _, r in targets if r == 'control'])} "
          f"top NOVEL candidates + {len([1 for _, r in targets if r == 'control'])} controls "
          f"({len(done)} already done, skipped)")
    print("=" * 72)
    for i, (tic, role) in enumerate(targets):
        if tic in done:
            continue
        print(f"[{i + 1}/{len(targets)}] TIC {tic} ({role}) ... ", end="", flush=True)
        try:
            res = analyse_one(tic, role, vet.loc[tic], lc_dir / f"TIC{tic}.csv",
                              info.loc[tic], plot_dir)
        except Exception as exc:
            res = {"TIC": tic, "role": role, "verdict": "INCONCLUSIVE",
                   "note": f"error: {repr(exc)[:150]}"}
        append_row(out_path, res, write_header)
        write_header = False
        off = res.get("centroid_offset_arcsec")
        extra = f"offset {off:.0f} arcsec, diff SNR {res.get('diff_peak_snr', 0):.0f}" if off is not None else ""
        print(f"{res['verdict']}  {extra}  {res.get('note', '')}")

    r = pd.read_csv(out_path)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print("\n" + "=" * 72)
    print("CONTROLS (these calibrate the method - check them first)")
    print("=" * 72)
    for tic, expect in CONTROLS.items():
        row = r[r["TIC"] == tic]
        got = row["verdict"].iloc[0] if len(row) else "not run"
        ok = "PASS" if expect.split(" ")[0] == got else "FAIL"
        print(f"  TIC {tic}: got {got:13s} | {expect} -> {ok}")

    c = r[r["role"] == "candidate"]
    print("\n" + "=" * 72)
    print(f"CANDIDATES ({len(c)})")
    print("=" * 72)
    print(c["verdict"].value_counts().to_string())
    print()
    print(c[["TIC", "verdict", "sector", "t0_shift_phase", "lc_dip_sigma", "dip_sigma",
             "diff_peak_snr", "compactness", "centroid_offset_arcsec",
             "nearest_capable_TIC", "nearest_capable_dist_px", "nearest_capable_dTmag", "note"]]
          .to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"\nResults: {out_path}")
    print(f"Images (out-of-eclipse / difference / SNR, target=red +, dimming centroid=yellow o, "
          f"capable neighbours=green x): {plot_dir}")


if __name__ == "__main__":
    main()
