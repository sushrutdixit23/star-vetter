import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ncx2

# Neighbour contamination, made quantitative.
#
# diag_blend.py asks one brightness question with deliberately generous
# assumptions (a neighbour's light counts 100% however far away it is), so 261
# of the 307 on-target stars come back "blend possible". diag_pixel.py measures
# where the dimming sits in the difference image. This module combines the two
# the way a vetter would:
#
#   1. A neighbour is BRIGHT ENOUGH if, with only the fraction of its light that
#      lands in the aperture (a Gaussian PSF and a circular aperture, both
#      approximate), the eclipse it would need on itself is at most 100%:
#          d_required = d_obs * F_target / (F_neighbour * f_aperture(sep)) <= 1
#   2. A neighbour is CONSISTENT WITH THE CENTROID if, were the eclipse on it,
#      the difference-image centroid would sit about `sep` from the target:
#          | sep - measured_offset | <= tolerance
#      The tolerance is the larger of a systematic floor and 3 sigma of the
#      centroid (PSF size / difference-image SNR). The floor is an assumption,
#      so the result is shown for several floors.
#   3. A neighbour that is both is VIABLE. Zero viable neighbours means no known
#      star could be the source. A viable neighbour within the floor of the
#      target cannot be separated by TESS pixels at all and needs ground-based
#      follow-up to settle.
#
# Only the TIC (which carries Gaia positions) neighbours cached by diag_blend are
# used; no new queries. Unknown neighbours (not in the TIC) are not addressed.

PIXEL_ARCSEC = 21.0
PSF_SIGMA_ARCSEC = 0.8 * PIXEL_ARCSEC       # Gaussian sigma of the TESS PSF, approximate
APERTURE_RADIUS_ARCSEC = 1.5 * PIXEL_ARCSEC # circular aperture, approximate
CENTROID_FLOORS_ARCSEC = (3.0, 6.0, 10.0)   # systematic centroid tolerance, assumed
HEADLINE_FLOOR_ARCSEC = 6.0
BAD_DISPOSITIONS = {"ARTIFACT", "DUPLICATE", "SPLIT"}


def aperture_fraction(sep, sigma=PSF_SIGMA_ARCSEC, radius=APERTURE_RADIUS_ARCSEC):
    """Fraction of a point source's light inside a circle of `radius` centred on
    the target, when the source is `sep` away and the PSF is a circular Gaussian
    of width `sigma`. (Noncentral chi-square with 2 degrees of freedom.)"""
    sep = np.asarray(sep, dtype=float)
    return ncx2.cdf((radius / sigma) ** 2, 2, (sep / sigma) ** 2)


def required_depth(d_obs, tmag_target, tmag_nbr, sep):
    """Eclipse depth the neighbour would need on itself to give d_obs on the
    target. > 1 is impossible."""
    flux_ratio = 10.0 ** (-0.4 * (np.asarray(tmag_target, dtype=float) - np.asarray(tmag_nbr, dtype=float)))
    f = np.maximum(aperture_fraction(sep), 1e-12)
    return d_obs * flux_ratio / f


def centroid_tolerance(diff_snr, floor):
    """max(floor, 3 sigma): sigma ~ PSF width / difference-image SNR."""
    snr = diff_snr if diff_snr and np.isfinite(diff_snr) and diff_snr > 0 else 1.0
    return max(float(floor), 3.0 * PSF_SIGMA_ARCSEC / float(snr))


def assess_star(d_obs, tmag_t, offset, diff_snr, nbrs, floor):
    """nbrs: DataFrame with nbr_Tmag, sep_arcsec, nbr_TIC. Returns a dict."""
    if len(nbrs) == 0:
        return {"bright_enough": 0, "viable": 0, "closest_viable": None, "unseparable": 0}
    sep = nbrs["sep_arcsec"].to_numpy(dtype=float)
    dreq = required_depth(d_obs, tmag_t, nbrs["nbr_Tmag"].to_numpy(dtype=float), sep)
    bright = dreq <= 1.0
    tol = centroid_tolerance(diff_snr, floor)
    consistent = np.abs(sep - offset) <= tol
    viable = bright & consistent
    closest = None
    if viable.any():
        i = int(np.argmin(np.where(viable, sep, np.inf)))
        closest = {"tic": int(nbrs["nbr_TIC"].iloc[i]), "sep_arcsec": float(sep[i]),
                   "delta_tmag": float(nbrs["nbr_Tmag"].iloc[i] - tmag_t), "required_depth": float(dreq[i])}
    return {"bright_enough": int(bright.sum()), "viable": int(viable.sum()), "closest_viable": closest,
            "unseparable": int((viable & (sep <= max(floor, tol))).sum())}


def classify(res):
    if res["viable"] == 0:
        return "NO_VIABLE_NEIGHBOUR"
    if res["unseparable"] > 0:
        return "UNSEPARABLE_NEIGHBOUR"
    return "VIABLE_NEIGHBOUR_AT_OFFSET"


def build(blend, nbrs, pixel, tics, now=None):
    b = blend[blend["TIC"].isin(tics)].set_index("TIC")
    p = pixel[(pixel["role"] == "candidate") & pixel["TIC"].isin(tics)].drop_duplicates("TIC").set_index("TIC")
    n = nbrs[nbrs["target_TIC"].isin(tics)]
    n = n[~n["nbr_disposition"].fillna("").isin(BAD_DISPOSITIONS)]
    n = n[n["sep_arcsec"] > 0.05]                   # the target itself
    groups = {int(k): v for k, v in n.groupby("target_TIC")}
    empty = n.iloc[0:0]
    stars = {}
    for tic in sorted(tics):
        if tic not in b.index or tic not in p.index:
            continue
        d_obs = float(b.loc[tic, "bls_depth"])
        tmag = float(b.loc[tic, "target_Tmag"])
        off = float(p.loc[tic, "centroid_offset_arcsec"])
        snr = float(p.loc[tic, "diff_peak_snr"])
        g = groups.get(tic, empty)
        row = {"offset_arcsec": off, "diff_snr": snr, "depth": d_obs, "n_neighbours": int(len(g)), "by_floor": {}}
        for fl in CENTROID_FLOORS_ARCSEC:
            r = assess_star(d_obs, tmag, off, snr, g, fl)
            r["status"] = classify(r)
            row["by_floor"]["%g" % fl] = r
        h = row["by_floor"]["%g" % HEADLINE_FLOOR_ARCSEC]
        row["status"] = h["status"]
        row["viable"] = h["viable"]
        row["closest_viable"] = h["closest_viable"]
        stars[str(tic)] = row
    summary = {}
    for fl in CENTROID_FLOORS_ARCSEC:
        key = "%g" % fl
        counts = {}
        for s in stars.values():
            st = s["by_floor"][key]["status"]
            counts[st] = counts.get(st, 0) + 1
        summary[key] = counts
    return {
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": {
            "psf_sigma_arcsec": PSF_SIGMA_ARCSEC, "aperture_radius_arcsec": APERTURE_RADIUS_ARCSEC,
            "centroid_floors_arcsec": list(CENTROID_FLOORS_ARCSEC), "headline_floor_arcsec": HEADLINE_FLOOR_ARCSEC,
            "neighbour_source": "TIC v8 neighbours within 63 arcsec cached by diag_blend.py",
            "assumptions": "Gaussian PSF and circular aperture are approximate; the centroid floor is an assumption, so results are shown for several floors.",
            "not_covered": "sources not in the TIC; neighbours beyond 63 arcsec; the target's own companions",
        },
        "stars_assessed": len(stars),
        "summary_by_floor": summary,
        "statuses": {
            "NO_VIABLE_NEIGHBOUR": "No known star is both bright enough and consistent with the measured centroid.",
            "UNSEPARABLE_NEIGHBOUR": "A bright-enough neighbour sits so close that TESS pixels cannot tell it from the target. Needs ground-based follow-up.",
            "VIABLE_NEIGHBOUR_AT_OFFSET": "A bright-enough neighbour matches the measured offset.",
        },
        "stars": stars,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: py f15_neighbours.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    dash = json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))
    tics = {int(s["tic"]) for s in dash["sky"]}
    out = build(pd.read_csv(proc / "diag_blend_results.csv"), pd.read_csv(proc / "diag_blend_neighbours.csv"),
                pd.read_csv(proc / "diag_pixel_results_v2.csv"), tics)
    path = root / "site" / "public" / "data" / "neighbours.json"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("Assessed %d stars" % out["stars_assessed"])
    for fl, c in out["summary_by_floor"].items():
        print("  centroid floor %s arcsec: %s" % (fl, c))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
