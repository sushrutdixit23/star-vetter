"""
f13_ephemeris.py - dated, falsifiable eclipse-time predictions for the
pixel-localised candidates, plus a leave-one-sector-out timing test.

WHAT IT DOES (per candidate)
  1. Downloads every TESS sector of light curve from MAST (the pipeline does
     not keep light curves between runs).
  2. Times every observed primary eclipse on its own: the star's mean eclipse
     profile is slid across the eclipse and chi-square minimised, with a free
     baseline and depth scale. (Same idea as export_dashboard.eclipse_timings,
     which only returns residuals; this returns absolute times and the sector
     of each eclipse.)
  3. Fits a straight-line ephemeris T = T0 + P*E by generalised least squares
     and keeps the full covariance, so the error on a prediction grows honestly
     with distance from the data. Two noise scales are estimated (REML): extra
     scatter of single eclipses (formal errors are optimistic) and an offset
     shared by all eclipses of one TESS sector, never below R_FLOOR_DAYS. A
     star whose excess scatter is more than twice its timing error is flagged
     TIMING_EXCESS (third body, apsidal motion, or systematics: worth a look,
     and its predictions carry the larger uncertainty).
  4. Two retrospective tests, both testing where the held-out sector's mean
     eclipse time falls against the prediction: leave-one-sector-out (hide a
     sector, predict it from the rest) and rolling-origin (fit the earliest
     k sectors, predict every later one: the way a forecast is really used).
     The grade is VALIDATED only if the test reached a comparable distance with
     comparable precision (prediction_grade), else UNVALIDATED; a failed test
     is REJECTED.
  5. Predicts primary eclipses in TESS Year 9 sectors that tess-point says
     observe the star, with 1-sigma uncertainty and a UTC time.

IMPORTANT LIMITS (state these wherever the numbers are shown)
  * The hold-out tests are RETROSPECTIVE. The BLS period and epoch that defined
    each candidate were found using all sectors, so a pass shows the timing is
    self-consistent, not that the star is an eclipsing binary. The only blind
    test is a sector observed after the predictions are frozen.
  * Primary eclipses only. A linear ephemeris cannot see apsidal motion or
    third-body timing changes; the held-out z-scores are where those would
    show up.
  * Times are BTJD (BJD_TDB - 2457000), the system TESS uses. UTC is the
    geocentric time of the same eclipse, converted with astropy.
  * Year 9 sector dates come from the TESS Year 9 table; the boundaries of
    sectors 117-121 are interpolated and marked approximate. tess-point's
    future pointings may be revised by the TESS team.

OUTPUTS (data/processed/)
  f13_ephemerides.csv   one row per candidate
  f13_holdout.csv       one row per (candidate, hold-out test)
  f13_predictions.csv   one row per predicted eclipse
  f13_cache/TIC*.json   measured eclipse times, so a re-run does not re-download

USAGE
  py f13_ephemeris.py <project_root> [--tiers CLEAN] [--limit N]
                      [--only TIC,TIC] [--refresh]
Needs:  pip install lightkurve tess-point astroquery
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BTJD_OFFSET = 2457000.0
MIN_SIGMA_DAYS = 15.0 / 86400.0   # floor on one eclipse's timing error: 15 s
HOLDOUT_FAMILY_ALPHA = 0.01   # family-wise false-FAIL rate across the sectors of one star
CLIP_SIGMA = 4.0
EXCESS_FACTOR = 2.0           # excess scatter above this x the median timing error = TIMING_EXCESS
# Floor on the sector-to-sector timing offset: 1 minute. Set with calibrate_f13_holdout.py on known
# binaries (Prsa+2022): tuned on 24 (seed 11), where 22 passed the hold-out at 1 min; then checked on
# 25 DISJOINT ones (seed 23), where 24 passed. The one that failed has 15 minutes of timing scatter.
R_FLOOR_DAYS = 1.0 / 1440.0
MEASURE_VERSION = 5           # bump when measurement changes; older cache files are re-measured
CONNECT_PERIOD_FRAC = 0.35    # connect a new sector only if 4 x predicted sigma < this x the PERIOD
DIRECT_WINDOW_FRAC = 0.5      # below 4 sigma < this x duration the normal search window suffices; above, scan
SCAN_STEP_FRAC = 0.2          # offset-scan step, in eclipse durations
TEST_POWER_RATIO = 3.0        # a hold-out counts toward validation only if its own prediction error was at most this x the published one
MAX_EXTRAPOLATION_FACTOR = 3.0   # VALIDATED only if the prediction reaches at most this x the distance the hold-out tested
SCAN_UNIQUE_DCHI2 = 25.0      # best alignment must beat any distinct alternative by this much
PRIOR_SIGMA_P_REL = 3e-4      # period prior (relative) when too few eclipses exist to fit one
SECTOR_OFFSET_FRAC = 0.4      # a connected sector's median |O-C| must stay below this x duration
MIN_DCHI2 = 25.0              # an eclipse must beat "no eclipse" by this much chi-square (~5 sigma)
AMP_RANGE = (0.4, 2.5)        # fitted depth relative to the template must be plausible
COVERAGE_MIN_FRAC = 0.75      # an eclipse needs this fraction of the points a gap-free cadence gives
COVERAGE_MAX_GAP_FRAC = 0.30  # ... and no hole longer than this fraction of its duration

# TESS Year 9 sector windows, UTC (tess.mit.edu/tess-year-9-observations).
# 117-121 are interpolated across 10 May - 19 Sep 2027 and are APPROXIMATE.
YEAR9_SECTORS = {
    111: ("2026-11-26", "2026-12-22", False),
    112: ("2026-12-22", "2027-01-17", False),
    113: ("2027-01-17", "2027-02-13", False),
    114: ("2027-02-13", "2027-03-14", False),
    115: ("2027-03-14", "2027-04-12", False),
    116: ("2027-04-12", "2027-05-10", False),
}
for _i, _s in enumerate(range(117, 122)):
    _start = pd.Timestamp("2027-05-10") + pd.Timedelta(days=_i * 132 / 5)
    _end = pd.Timestamp("2027-05-10") + pd.Timedelta(days=(_i + 1) * 132 / 5)
    YEAR9_SECTORS[_s] = (_start.strftime("%Y-%m-%d"), _end.strftime("%Y-%m-%d"), True)


# --------------------------------------------------------------------------
# core maths (pure functions, unit-tested without any network)
# --------------------------------------------------------------------------

def binned_median(x, y, edges, min_n=3):
    out = []
    idx = np.digitize(x, edges)
    for k in range(1, len(edges)):
        m = idx == k
        if m.sum() >= min_n:
            out.append((float(np.median(x[m])), float(np.median(y[m]))))
    return out


def symmetry_center(x, y, dur, max_offset=1.4):
    """Centre of an eclipse profile, in the units of x.

    Coarse then fine. Coarse: the minimum of the profile smoothed over about
    half an eclipse duration, searched within +/- max_offset x dur (this finds
    the dip wherever it sits). Fine: within +/- 0.5 dur of that, the c that makes
    y(c - u) most like y(c + u) over |u| < 0.75 dur (reflection symmetry).
    The coarse step matters: with the symmetry test alone, any c far from the
    dip compares flat baseline with flat baseline and looks perfectly symmetric.

    This fixes the ZERO POINT of eclipse times. A profile folded on a nominal
    ephemeris is centred wherever that ephemeris happens to sit, and a
    template-shift fit then reports times on the same arbitrary zero. Centring
    the template on its own symmetry axis makes the reported time the physical
    mid-eclipse, whatever epoch the search started from."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    k = 5
    ysm = np.convolve(np.pad(y, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")
    inside = np.abs(x) <= max_offset * dur
    c0 = float(x[inside][np.argmin(ysm[inside])]) if inside.any() else 0.0
    grid = np.linspace(c0 - 0.5 * dur, c0 + 0.5 * dur, 801)
    u = np.linspace(0.0, 0.75 * dur, 60)
    cost = np.array([np.mean((np.interp(c - u, x, y) - np.interp(c + u, x, y)) ** 2) for c in grid])
    j = int(np.argmin(cost))
    if 0 < j < len(grid) - 1:
        a2, b2, _ = np.polyfit(grid[j - 1:j + 2], cost[j - 1:j + 2], 2)
        if a2 > 0:
            return float(np.clip(-b2 / (2 * a2), grid[0], grid[-1]))
    return float(grid[j])


def raw_profile(t, f, P, t0, dur):
    """Median-binned fold (bins of dur/12) within +/- 2 durations of the
    NOMINAL mid-eclipse, not re-centred. Returns (x, y) or None."""
    dt = ((t - t0 + P / 2) % P) - P / 2
    win = np.abs(dt) < 2 * dur
    if win.sum() < 20:
        return None
    edges = np.arange(-2 * dur, 2 * dur + dur / 12, dur / 12)
    tb = binned_median(dt[win], f[win], edges, min_n=3)
    if len(tb) < 10:
        return None
    return np.array([b[0] for b in tb]), np.array([b[1] for b in tb])


def fold_offset(t, f, P, t0, dur):
    """How far (days) the folded eclipse sits from the nominal epoch t0, found
    by reflection symmetry within +/- 1.4 durations. None if no profile."""
    prof = raw_profile(t, f, P, t0, dur)
    return None if prof is None else symmetry_center(prof[0], prof[1], dur)


def build_template(t, f, P, t0, dur):
    """Mean primary-eclipse profile (raw_profile) re-centred on its symmetry
    axis (see symmetry_center). Returns (x, y) with x = 0 at mid-eclipse, or
    None. Callers should first move t0 onto the eclipse (fold_offset) so the
    dip lies within the +/- 0.5 duration search used here."""
    prof = raw_profile(t, f, P, t0, dur)
    if prof is None:
        return None
    x, y = prof
    return x - symmetry_center(x, y, dur), y


def eclipse_covered(d, dur, min_frac=COVERAGE_MIN_FRAC, max_gap_frac=COVERAGE_MAX_GAP_FRAC):
    """True only if the eclipse (|d| < dur around mid-eclipse) is well sampled.
    d: offsets in days of the points near this eclipse. A template slid across
    a half-hidden eclipse locks onto the visible half and returns a confident
    but biased time, so partial eclipses are rejected: the window needs at
    least min_frac of the points a gap-free cadence would give, and no hole
    longer than max(max_gap_frac * dur, 4 cadences)."""
    d = np.sort(np.asarray(d, float))
    if len(d) < 4:
        return False
    cad = float(np.median(np.diff(d)))       # median is robust to the gaps
    if not cad > 0:
        return False
    w = d[np.abs(d) < dur]
    if len(w) < min_frac * (2 * dur / cad):
        return False
    edges = np.r_[-dur, w, dur]
    return bool(np.max(np.diff(edges)) <= max(max_gap_frac * dur, 4 * cad))


def robust_line(E, T, clip=3.5, floor_days=30.0 / 86400.0):
    """Outlier-resistant straight line T = T0 + P*E for the INTERMEDIATE
    ephemeris used to re-centre windows and sharpen the template. Unweighted
    on purpose: a few eclipses with absurdly small formal errors must not be
    able to drag the line (that is what produced a saw-tooth O-C in the first
    version). Clips at `clip` robust sigmas, iterating. Returns dict or None."""
    E = np.asarray(E, float)
    T = np.asarray(T, float)
    keep = np.ones(len(E), bool)
    slope = icpt = None
    for _ in range(6):
        if keep.sum() < 2 or len(np.unique(E[keep])) < 2:
            return None if slope is None else {"P": float(slope), "T0": float(icpt), "keep": keep}
        slope, icpt = np.polyfit(E[keep], T[keep], 1)
        r = T - (icpt + slope * E)
        mad = max(1.4826 * float(np.median(np.abs(r[keep] - np.median(r[keep])))), floor_days)
        new = np.abs(r) < clip * mad
        if new.sum() < 2 or (new == keep).all():
            break
        keep = new
    return {"P": float(slope), "T0": float(icpt), "keep": keep}


def measure_eclipses(t, f, ferr, sector, P, t0, dur, template):
    """Time every fully covered primary eclipse (see eclipse_covered). Returns a list of dicts:
    E (cycle), T (BTJD), sigma (days), n (points), sector."""
    tx, ty = template
    base = float(np.median(np.r_[ty[:3], ty[-3:]]))
    scatter = 1.4826 * np.median(np.abs(f - np.median(f)))
    shifts = np.linspace(-0.75 * dur, 0.75 * dur, 301)
    epochs = np.round((t - t0) / P).astype(int)
    out = []
    for E in np.unique(epochs):
        tc = t0 + E * P
        dt = t - tc
        sel = np.abs(dt) < 2 * dur
        if sel.sum() < 12:
            continue
        d = dt[sel]
        if (np.abs(d) < 0.5 * dur).sum() < 5:
            continue
        if ((d > -dur) & (d < -0.2 * dur)).sum() < 2 or ((d > 0.2 * dur) & (d < dur)).sum() < 2:
            continue
        if not eclipse_covered(d, dur):
            continue
        y = f[sel]
        s = ferr[sel] if ferr is not None else np.full(sel.sum(), scatter)
        s = np.where(np.isfinite(s) & (s > 0), s, scatter)
        if not (np.isfinite(s).all() and scatter > 0):
            continue
        w = 1.0 / s ** 2
        chi_null = float((w * (y - (w * y).sum() / w.sum()) ** 2).sum())   # "no eclipse here"
        chi = np.full(len(shifts), np.inf)
        amp = np.full(len(shifts), np.nan)
        for k, sh in enumerate(shifts):
            m = np.interp(d - sh, tx, ty, left=np.nan, right=np.nan) - base
            ok = np.isfinite(m)
            if ok.sum() < 8:
                continue
            ww, mm, yy = w[ok], m[ok], y[ok]
            # y = c0 + a*m, weighted least squares in closed form
            sw, swm, swy = ww.sum(), (ww * mm).sum(), (ww * yy).sum()
            swmm, swmy = (ww * mm * mm).sum(), (ww * mm * yy).sum()
            det = sw * swmm - swm ** 2
            if det <= 0:
                continue
            a = (sw * swmy - swm * swy) / det
            c0 = (swy - a * swm) / sw
            if a <= 0:
                continue
            chi[k] = (ww * (yy - c0 - a * mm) ** 2).sum()
            amp[k] = a
        k = int(np.argmin(chi))
        if not np.isfinite(chi[k]) or k == 0 or k == len(shifts) - 1:
            continue
        # a real eclipse must be significant and about the template's depth;
        # otherwise the "best shift" is just where some noise happened to fit
        if chi_null - chi[k] < MIN_DCHI2 or not (AMP_RANGE[0] < amp[k] < AMP_RANGE[1]):
            continue
        x3, y3 = shifts[k - 1:k + 2], chi[k - 1:k + 2]
        if not np.isfinite(y3).all():
            continue
        qa, qb, _ = np.polyfit(x3, y3, 2)
        if qa <= 0:
            continue
        best = -qb / (2 * qa)
        err = 1.0 / np.sqrt(qa)
        red = chi[k] / max(int(sel.sum()) - 3, 1)
        if red > 1:
            err *= np.sqrt(red)
        err = max(err, MIN_SIGMA_DAYS)
        sec_vals = sector[sel]
        sec = int(pd.Series(sec_vals).mode().iloc[0])
        out.append({"E": int(E), "T": float(tc + best), "sigma": float(err),
                    "n": int(sel.sum()), "sector": sec,
                    "depth_scale": float(amp[k]), "dchi2": float(chi_null - chi[k])})
    return out


def _cov_matrix(S, groups, white, shared):
    """Data covariance. Independent measurement errors S plus an extra
    per-eclipse scatter `white` (spots, template mismatch: the formal error is
    optimistic), plus an offset of scatter `shared` common to all eclipses in
    the same group (one TESS sector moves together)."""
    V = np.diag(S ** 2 + white ** 2)
    if shared > 0:
        V = V + shared ** 2 * (groups[:, None] == groups[None, :])
    return V


def _gls(E, T, V, Eref):
    A = np.vstack([np.ones_like(E), E - Eref]).T
    Vi = np.linalg.inv(V)
    cov = np.linalg.inv(A.T @ Vi @ A)
    beta = cov @ (A.T @ Vi @ T)
    res = T - A @ beta
    return beta, cov, res, float(res @ Vi @ res)


def _reml_noise(E, T, S, g, Eref):
    """Restricted maximum likelihood for the two noise scales (white, shared),
    in days. Residuals within a sector tell us the white scatter; the
    sector-to-sector residuals tell us the shared one. Both are estimated
    together because either one alone mistakes the other for itself."""
    from scipy.optimize import minimize
    s0 = float(np.median(S))
    A = np.vstack([np.ones_like(E), E - Eref]).T
    Tn, Sn = T / s0, S / s0
    G = (g[:, None] == g[None, :]).astype(float)
    base = np.diag(Sn ** 2)
    lo = np.log(1e-4)

    def obj(th):
        w2, r2 = np.exp(2 * th[0]), np.exp(2 * th[1])
        V = base + w2 * np.eye(len(Tn)) + r2 * G
        try:
            L = np.linalg.cholesky(V)
        except np.linalg.LinAlgError:
            return 1e30
        ViA = np.linalg.solve(V, A)
        ViT = np.linalg.solve(V, Tn)
        M = A.T @ ViA
        beta = np.linalg.solve(M, A.T @ ViT)
        res = Tn - A @ beta
        return (2 * np.log(np.diag(L)).sum() + np.linalg.slogdet(M)[1]
                + float(res @ (ViT - ViA @ beta)))

    best = None
    for w0, r0 in ((1.0, 1.0), (4.0, 1.0), (1.0, 4.0), (1e-3, 1e-3)):
        out = minimize(obj, [np.log(w0), np.log(r0)], method="L-BFGS-B", bounds=[(lo, 7.0), (lo, 7.0)])
        if best is None or out.fun < best.fun:
            best = out
    w, r = (float(np.exp(x)) * s0 for x in best.x)
    return (0.0 if w < 2e-3 * s0 else w), (0.0 if r < 2e-3 * s0 else r)


def fit_line(E, T, S, groups=None):
    """Generalised least squares T = T0 + P*(E - Eref) with excess timing
    noise: an extra per-eclipse scatter `white` and, when sector labels are
    given (>= 3 sectors, >= 6 eclipses), a scatter `shared` common to every
    eclipse of a sector, both found by REML. The shared term never falls below
    R_FLOOR_DAYS, the systematic floor on sector-to-sector offsets. With fewer
    than 3 sectors only `white` can be estimated (by matching chi2 to dof) and
    the shared term is the floor. fit["jitter_mode"] says which.
    fit["jitter"] = hypot(white, shared), the total excess scatter.
    Eref is the weighted mean cycle, which decorrelates T0 and P.
    Returns a dict or None."""
    E = np.asarray(E, float)
    T = np.asarray(T, float)
    S = np.asarray(S, float)
    if len(E) < 2 or len(np.unique(E)) < 2:
        return None
    has_g = groups is not None
    g = np.asarray(groups) if has_g else np.arange(len(E))
    floor = R_FLOOR_DAYS if has_g else 0.0
    W = 1.0 / S ** 2
    Eref = float(np.round(np.sum(W * E) / np.sum(W)))
    beta, cov, res, chi2 = _gls(E, T, _cov_matrix(S, g, 0.0, floor), Eref)
    dof = len(E) - 2
    red0 = chi2 / dof if dof > 0 else None
    white, shared = 0.0, floor
    if has_g and len(np.unique(g)) >= 3 and len(E) >= 6:
        mode = "sector"
        white, r_hat = _reml_noise(E, T, S, g, Eref)
        shared = max(r_hat, floor)
    else:
        mode = "white"
        if dof > 0 and red0 > 1:
            lo, hi = 0.0, float(np.max(np.abs(res))) * 3 + 1e-9
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if _gls(E, T, _cov_matrix(S, g, mid, floor), Eref)[3] > dof:
                    lo = mid
                else:
                    hi = mid
            white = 0.5 * (lo + hi)
    beta, cov, res, chi2 = _gls(E, T, _cov_matrix(S, g, white, shared), Eref)
    return {"Eref": Eref, "T0": float(beta[0]), "P": float(beta[1]), "cov": cov,
            "chi2_red": red0, "dof": dof, "n": len(E), "white": float(white), "shared": float(shared),
            "jitter": float(np.hypot(white, shared)),
            "jitter_mode": mode, "rms": float(np.sqrt(np.mean(res ** 2)))}


def predict(fit, E, total=False):
    """Predicted time and 1-sigma uncertainty (days) at cycle(s) E. With
    total=True the uncertainty also includes the excess-timing-noise term, i.e.
    the scatter to expect for eclipses in a new sector."""
    E = np.atleast_1d(np.asarray(E, float))
    x = E - fit["Eref"]
    c = fit["cov"]
    T = fit["T0"] + fit["P"] * x
    var = c[0, 0] + x ** 2 * c[1, 1] + 2 * x * c[0, 1]
    if total:
        var = var + fit["white"] ** 2 + fit["shared"] ** 2
    return T, np.sqrt(np.maximum(var, 0.0))


def clip_outliers(E, T, S, groups=None):
    """Boolean keep-mask: drop eclipses more than CLIP_SIGMA from the line,
    measured against the measurement error PLUS the fitted excess noise, so a
    real timing wobble is not clipped away."""
    keep = np.ones(len(E), bool)
    for _ in range(2):
        g = None if groups is None else np.asarray(groups)[keep]
        fit = fit_line(E[keep], T[keep], S[keep], g)
        if fit is None or keep.sum() <= 3:
            break
        pred, _ = predict(fit, E)
        z = np.abs(T - pred) / np.sqrt(S ** 2 + fit["white"] ** 2 + fit["shared"] ** 2)
        new = z < CLIP_SIGMA
        if new.sum() < 3 or (new == keep).all():
            break
        keep = new
    return keep


def _offset_test(fit, test):
    """Do the held-out eclipses sit where the ephemeris says? The statistic is
    the weighted mean residual of each held-out SECTOR, because that is what a
    drifting clock shifts, and it does not depend on how noisy individual
    eclipses happen to be in that sector (the noise differs from sector to
    sector, and a test built on every eclipse fails on it, not on timing).

    Each sector's mean has three independent error sources: its own scatter
    (the measured scatter of its eclipses, if that exceeds the formal errors;
    Birge ratio), the shared per-sector offset, and the ephemeris uncertainty,
    which is common to all sectors and enters through the full covariance:
        C = diag(var_mean + shared^2) + Xbar cov Xbar'
    One held-out sector: Student t with n-1 dof. Several: chi-square with one
    dof per sector (slightly lenient, calibrated on known binaries)."""
    from scipy.stats import chi2 as chi2dist, norm, t as tdist
    secs = sorted({e["sector"] for e in test})
    M, Xb, var, ns = [], [], [], []
    for sec in secs:
        es = [e for e in test if e["sector"] == sec]
        Et = np.array([e["E"] for e in es], float)
        Tm = np.array([e["T"] for e in es])
        Sm = np.array([e["sigma"] for e in es])
        w = 1.0 / (Sm ** 2 + fit["white"] ** 2)
        r = Tm - predict(fit, Et)[0]
        m = float(np.sum(w * r) / np.sum(w))
        v = 1.0 / float(np.sum(w))
        if len(es) >= 2:
            v *= max(1.0, float(np.sum(w * (r - m) ** 2)) / (len(es) - 1))
        M.append(m)
        Xb.append([1.0, float(np.sum(w * (Et - fit["Eref"])) / np.sum(w))])
        var.append(v + fit["shared"] ** 2)
        ns.append(len(es))
    M, Xb = np.array(M), np.array(Xb)
    C = np.diag(var) + Xb @ fit["cov"] @ Xb.T
    stat = float(M @ np.linalg.solve(C, M))
    if len(secs) == 1 and ns[0] >= 2:
        pval = float(2 * tdist.sf(np.sqrt(stat), ns[0] - 1))
    else:
        pval = float(chi2dist.sf(stat, len(secs)))
    return {"chi2": stat, "p_value": pval, "z_equiv": float(norm.isf(max(pval, 1e-300) / 2)),
            "resid_min_mean": float(np.mean(M) * 1440),
            "pred_sigma_min_mean": float(np.mean(np.sqrt(np.diag(C))) * 1440),
            "n_sectors_tested": len(secs)}


def leave_one_sector_out(ecl):
    """For every sector: fit on the other sectors, predict the held-out
    sector, and test its offset (see _offset_test). Returns one dict per
    sector with the statistic, p-value and the distance predicted."""
    rows = []
    for s in sorted({e["sector"] for e in ecl}):
        test = [e for e in ecl if e["sector"] == s]
        train = [e for e in ecl if e["sector"] != s]
        fit = fit_line([e["E"] for e in train], [e["T"] for e in train],
                       [e["sigma"] for e in train], [e["sector"] for e in train])
        if fit is None:
            continue
        Et = np.array([e["E"] for e in test], float)
        Tm = np.array([e["T"] for e in test])
        Etr = np.array([e["E"] for e in train], float)
        gap = float(np.min(np.abs(Et[:, None] - Etr[None, :])))
        forward = bool(Et.min() > Etr.max())          # a later sector predicted from earlier ones
        reach = float(np.max(Tm) - np.max([e["T"] for e in train])) if forward else gap * float(fit["P"])
        rows.append({
            "sector": int(s), "n_eclipses": len(test), "n_train": len(train),
            **_offset_test(fit, test),
            "jitter_min": float(fit["jitter"] * 1440),
            "cycles_from_training": gap,
            "lag_days": reach,
            "forward": forward,
            "kind": "loso",
            "train_sectors": len({e["sector"] for e in train}),
        })
    return rows


def rolling_origin(ecl):
    """Forecast test, the way it is used: train on the EARLIEST k sectors and
    predict every later sector at once, for k = 1 .. n-2 (k = n-1 is the
    leave-one-out of the last sector, already done). This is the only test that
    asks a long-baseline ephemeris to reach far beyond its data, e.g. fit on
    2021 and predict 2024-2025, which is the situation of a Year 9 prediction.

    Same statistic as leave_one_sector_out. lag_days is the REACH: from the
    last training eclipse to the last held-out eclipse."""
    order = sorted({e["sector"] for e in ecl}, key=lambda sec: np.mean([e["T"] for e in ecl if e["sector"] == sec]))
    rows = []
    for k in range(1, len(order) - 1):
        tr_secs, te_secs = set(order[:k]), set(order[k:])
        train = [e for e in ecl if e["sector"] in tr_secs]
        test = [e for e in ecl if e["sector"] in te_secs]
        fit = fit_line([e["E"] for e in train], [e["T"] for e in train],
                       [e["sigma"] for e in train], [e["sector"] for e in train])
        if fit is None:
            continue
        Et = np.array([e["E"] for e in test], float)
        Tm = np.array([e["T"] for e in test])
        rows.append({
            "sector": int(order[k]), "n_eclipses": len(test), "n_train": len(train),
            **_offset_test(fit, test),
            "jitter_min": float(fit["jitter"] * 1440),
            "cycles_from_training": float(np.min(Et) - np.max([e["E"] for e in train])),
            "lag_days": float(np.max(Tm) - np.max([e["T"] for e in train])),
            "forward": True, "kind": "rolling", "train_sectors": k,
        })
    return rows


def holdout_status(rows):
    """FAIL if any held-out sector is predicted worse than chance allows, with
    a family-wise false-alarm rate of HOLDOUT_FAMILY_ALPHA across the sectors
    tested. NOT_TESTABLE if there was nothing to hold out."""
    if not rows:
        return "NOT_TESTABLE"
    thresh = HOLDOUT_FAMILY_ALPHA / len(rows)
    return "FAIL" if any(r["p_value"] < thresh for r in rows) else "PASS"


def prediction_grade(status, rows, horizon_days, sigma_pub_min=None):
    """What a prediction may be called, from the retrospective hold-out, how far
    the prediction reaches compared with how far the hold-out tested, and how
    precise the hold-out was.

    status         holdout_status(rows)
    rows           hold-out rows (leave_one_sector_out + rolling_origin)
    horizon_days   days from the last measured eclipse to the NEAREST predicted one
    sigma_pub_min  best 1-sigma uncertainty among the published predictions, minutes

    Two ways a passed test can mean little. (1) DISTANCE: a linear ephemeris that
    predicts the next sector (27 days away) says nothing about four years out,
    because real eclipse timing drifts. (2) PRECISION: a test whose own prediction
    was good to +/-19 hours passes whatever the clock does, and cannot back up a
    prediction good to +/-4 minutes. So only FORWARD tests whose mean predicted
    uncertainty was at most TEST_POWER_RATIO x the published one count, and
    VALIDATED needs the horizon to be at most MAX_EXTRAPOLATION_FACTOR x the
    longest such test.
      REJECTED     failed to predict a held-out sector: do not publish
      VALIDATED    passed, over a comparable distance, with comparable precision
      UNVALIDATED  not tested (one connected sector), or tested only over a much
                   shorter distance, or only too coarsely
    Returns dict: grade, tested_lag_days, extrapolation_factor, note."""
    fwd = [r for r in rows if r.get("forward")]
    if sigma_pub_min is not None:
        fwd = [r for r in fwd if r["pred_sigma_min_mean"] <= TEST_POWER_RATIO * sigma_pub_min]
    tested = float(max((r["lag_days"] for r in fwd), default=0.0))
    factor = (float(horizon_days) / tested) if (tested > 0 and horizon_days is not None) else None
    out = {"tested_lag_days": tested if rows else None, "extrapolation_factor": factor}
    if status == "FAIL":
        out.update(grade="REJECTED", note="Failed to predict a TESS sector it had not been shown.")
    elif status != "PASS":
        out.update(grade="UNVALIDATED", note="Only one sector is phase-connected, so nothing could be held out.")
    elif horizon_days is None:
        out.update(grade="UNVALIDATED", note="Passed the hold-out, but no prediction horizon to compare.")
    elif tested <= 0:
        out.update(grade="UNVALIDATED",
                   note="Passed the hold-out, but no test was precise enough to check predictions this tight.")
    elif factor <= MAX_EXTRAPOLATION_FACTOR:
        out.update(grade="VALIDATED",
                   note=f"Predicted later sectors it had not seen, up to {tested:.0f} days beyond its data, "
                        f"with comparable precision; these predictions reach {horizon_days:.0f} days.")
    else:
        out.update(grade="UNVALIDATED",
                   note=f"Passed the hold-out over {tested:.0f} days, but these predictions reach {horizon_days:.0f} days "
                        f"({factor:.0f}x farther than tested).")
    return out


def sector_window_btjd(sector):
    a, b, approx = YEAR9_SECTORS[sector]
    ja = (pd.Timestamp(a) - pd.Timestamp("1858-11-17")).total_seconds() / 86400.0 + 2400000.5 - BTJD_OFFSET
    jb = (pd.Timestamp(b) - pd.Timestamp("1858-11-17")).total_seconds() / 86400.0 + 2400000.5 - BTJD_OFFSET
    return ja, jb, approx


def btjd_to_utc_iso(btjd, ra, dec):
    """Geocentric UTC of the eclipse whose barycentric (BJD_TDB) time is btjd."""
    from astropy.coordinates import EarthLocation, SkyCoord
    from astropy.time import Time
    t_bary = Time(btjd + BTJD_OFFSET, format="jd", scale="tdb")
    ltt = t_bary.light_travel_time(SkyCoord(ra, dec, unit="deg"), kind="barycentric",
                                   location=EarthLocation.from_geocentric(0, 0, 0, unit="m"))
    return (t_bary - ltt).utc.strftime("%Y-%m-%d %H:%M:%S")


def predict_future(fit, tic, ra, dec, observed_sectors):
    """Primary eclipses inside the Year 9 sector windows the star is on
    silicon for. observed_sectors: sector numbers from tess-point."""
    rows = []
    for s in sorted(set(observed_sectors) & set(YEAR9_SECTORS)):
        lo, hi, approx = sector_window_btjd(s)
        E0 = int(np.ceil((lo - fit["T0"]) / fit["P"])) + int(fit["Eref"])
        E1 = int(np.floor((hi - fit["T0"]) / fit["P"])) + int(fit["Eref"])
        for E in range(E0, E1 + 1):
            T, S = predict(fit, [E], total=True)
            if lo <= T[0] <= hi:
                rows.append({
                    "tic": tic, "sector": int(s), "sector_dates_approx": approx,
                    "cycle": int(E), "t_btjd": float(T[0]),
                    "sigma_min": float(S[0] * 1440),
                    "utc": btjd_to_utc_iso(float(T[0]), ra, dec),
                })
    return rows


# --------------------------------------------------------------------------
# data acquisition and orchestration
# --------------------------------------------------------------------------

def eligibility(tier, detail):
    """Why a candidate is or is not fit for a published prediction. The rules
    are deliberately mechanical so they can be stated in a pre-registration."""
    if tier != "CLEAN":
        return False, "TIER_" + str(tier).replace(" ", "_")
    if detail is None:
        return False, "NO_DETAIL_FILE"
    if detail.get("aliased"):
        return False, "PERIOD_ALIAS"
    ep = detail.get("epochs") or {}
    if ep.get("absent", 0) > 0:
        return False, "PREDICTED_ECLIPSE_MISSING"      # e.g. TIC 437150434: 2 of 4 absent
    if detail.get("checks"):
        return False, "PIPELINE_CHECK_FLAGGED"
    return True, ""


def fetch_sector_lightcurves(tic, author, log):
    """One normalised, eclipse-masked-flattened light curve per TESS sector.
    Returns list of (sector, t, f, ferr) or []."""
    import lightkurve as lk
    from upstream import call_with_timeout

    kw = {"author": author} if author else {}
    sr = call_with_timeout(lk.search_lightcurve, args=(f"TIC {tic}",), kwargs=kw, timeout=90)
    if len(sr) == 0:
        return []
    tab = sr.table.to_pandas()
    keep = []
    for seq, grp in tab.groupby("sequence_number"):
        keep.append(int(grp["exptime"].astype(float).idxmin()))   # best cadence per sector
    sr = sr[sorted(keep)]
    lcc = call_with_timeout(sr.download_all, timeout=300)
    out = []
    for lc in lcc:
        sector = lc.meta.get("SECTOR") or lc.meta.get("sector")
        if sector is None:
            continue
        lc = lc.remove_nans().normalize()
        if len(lc) < 50:
            continue
        out.append((int(sector), lc))
    return out


def flatten_sector(lc, P, t0, dur):
    t = np.asarray(lc.time.value, float)
    dt = ((t - t0 + P / 2) % P) - P / 2
    mask = np.abs(dt) < 1.5 * dur           # keep the eclipses out of the trend fit
    cad = float(np.median(np.diff(t)))
    wl = int(max(6 * dur, 1.0) / cad) | 1
    wl = min(wl, (len(t) - 1) | 1)
    flat = lc.flatten(window_length=wl, polyorder=2, mask=mask)
    f = np.asarray(flat.flux.value, float)
    e = np.asarray(flat.flux_err.value, float) if flat.flux_err is not None else np.full(len(f), np.nan)
    ok = np.isfinite(t) & np.isfinite(f)
    return t[ok], f[ok], e[ok]


def load_or_fetch_lightcurves(tic, author, log, lc_dir=None):
    """fetch_sector_lightcurves with an on-disk copy, so changing the
    measurement code never needs MAST again. Cached: normalised time, flux,
    flux error and sector (before flattening)."""
    import lightkurve as lk

    path = None if lc_dir is None else Path(lc_dir) / f"TIC{tic}.npz"
    if path is not None and path.exists():
        z = np.load(path)
        return [(int(s), lk.LightCurve(time=z["t"][z["sector"] == s], flux=z["f"][z["sector"] == s],
                                       flux_err=z["e"][z["sector"] == s]))
                for s in np.unique(z["sector"])]
    lcs = fetch_sector_lightcurves(tic, author, log)
    if lcs and path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            t=np.concatenate([np.asarray(lc.time.value, float) for _, lc in lcs]),
            f=np.concatenate([np.asarray(lc.flux.value, np.float32) for _, lc in lcs]),
            e=np.concatenate([np.asarray(lc.flux_err.value, np.float32) for _, lc in lcs]),
            sector=np.concatenate([np.full(len(lc), s) for s, lc in lcs]))
    return lcs


def refine_ephemeris(t, f, e, sec, P_use, t0_use, dur, passes=3):
    """Re-centre windows and sharpen the template on a ROBUST interim
    ephemeris (see robust_line). Returns (P_use, t0_use, template) or None if
    no template can be built."""
    for _ in range(3):                       # put the nominal epoch on the actual dip
        c = fold_offset(t, f, P_use, t0_use, dur)
        if c is None:
            return None
        t0_use += c
        if abs(c) < 0.05 * dur:
            break
    for _ in range(passes):
        tpl = build_template(t, f, P_use, t0_use, dur)
        if tpl is None:
            return None
        ecl = measure_eclipses(t, f, e, sec, P_use, t0_use, dur, tpl)
        if len(ecl) < 3:
            break
        E = np.array([x["E"] for x in ecl], float)
        line = robust_line(E, np.array([x["T"] for x in ecl]))
        if line is None:
            break
        moved = abs(line["P"] - P_use) * (E.max() - E.min())
        P_use, t0_use = line["P"], line["T0"]
        if moved < 0.05 * dur:
            break
    tpl = build_template(t, f, P_use, t0_use, dur)
    return None if tpl is None else (P_use, t0_use, tpl)


def connectable(sigma, P):
    """May a sector whose eclipses are predicted with 1-sigma `sigma` (days) be
    connected to the ephemeris? Only if 4 sigma stays well inside half a period
    (CONNECT_PERIOD_FRAC x P). Cycles are interchangeable by a whole period, so
    a looser prediction could place the eclipses one or more cycles from where
    they belong (a cycle slip), corrupting the period with no visible symptom."""
    return 4.0 * sigma <= CONNECT_PERIOD_FRAC * P


def scan_offset(t, f, e, P, t0, dur, tpl, span):
    """Locate this sector's eclipses when the prediction is looser than the
    search window: slide the ephemeris by delta over +/- span and keep the
    delta where the template explains the data best. Joint over every eclipse
    in the sector (they share the offset to well within an eclipse width).

    Returns delta (days) or None. None unless the best alignment is a real
    detection (chi-square improvement >= MIN_DCHI2, plausible depth) AND is
    unique: any alignment more than 1.5 durations away must be worse by at
    least SCAN_UNIQUE_DCHI2. A window of a whole period or more is refused
    outright (shifting by one period reproduces the same data exactly)."""
    if 2.0 * span >= P:
        return None       # the window holds a whole cycle: every eclipse has a twin, no unique answer
    tx, ty = tpl
    base = float(np.median(np.r_[ty[:3], ty[-3:]]))
    scatter = 1.4826 * np.median(np.abs(f - np.median(f)))
    sig = np.where(np.isfinite(e) & (e > 0), e, scatter)
    w_all = 1.0 / sig ** 2
    step = SCAN_STEP_FRAC * dur
    deltas = np.arange(-span, span + step / 2, step)
    dchi = np.full(len(deltas), -np.inf)
    amp = np.full(len(deltas), np.nan)
    for k, d in enumerate(deltas):
        ph = ((t - t0 - d + P / 2) % P) - P / 2
        sel = np.abs(ph) < 2 * dur
        if sel.sum() < 20:
            continue
        x = np.interp(ph[sel], tx, ty, left=np.nan, right=np.nan) - base
        y, w = f[sel], w_all[sel]
        ok = np.isfinite(x)
        if ok.sum() < 20:
            continue
        x, y, w = x[ok], y[ok], w[ok]
        sw, sx, sy = w.sum(), (w * x).sum(), (w * y).sum()
        sxx, sxy = (w * x * x).sum(), (w * x * y).sum()
        det = sw * sxx - sx ** 2
        if det <= 0:
            continue
        a = (sw * sxy - sx * sy) / det
        if a <= 0:
            continue
        dchi[k] = a * a * det / sw
        amp[k] = a
    if not np.isfinite(dchi).any():
        return None
    k = int(np.argmax(dchi))
    if dchi[k] < MIN_DCHI2 or not (AMP_RANGE[0] < amp[k] < AMP_RANGE[1]):
        return None
    far = np.abs(deltas - deltas[k]) > 1.5 * dur
    if far.any() and dchi[k] - float(np.max(dchi[far])) < SCAN_UNIQUE_DCHI2:
        return None
    return float(deltas[k])


def predicted_sigma(block, E_far, P, dur):
    """Conservative 1-sigma (days) of the predicted time of cycle E_far from
    the eclipses already measured (`block`). Twice the formal fit error
    including excess noise; with too few eclipses to fit a period it falls
    back to a prior on the BLS period error."""
    E = np.array([x["E"] for x in block], float)
    if len(block) >= 3 and len(np.unique(E)) >= 3:
        fit = fit_line(E, [x["T"] for x in block], [x["sigma"] for x in block],
                       [x["sector"] for x in block])
        return 2.0 * float(predict(fit, [E_far], total=True)[1][0]), fit
    return PRIOR_SIGMA_P_REL * P * max(abs(E_far - float(np.mean(E))), 1.0) + 0.1 * dur, None


def measure_star(tic, author, P, t0, dur, log, lc_dir=None):
    """Download (or load), flatten, and time all eclipses, PHASE-CONNECTING
    sector by sector.

    A coarse search period times hundreds of cycles is more than an eclipse
    width, so measuring every sector against it fails for long baselines.
    Instead: start from the sector nearest the search epoch, then repeatedly
    add the nearest sector whose eclipses the current ephemeris predicts well
    enough to count cycles without ambiguity (4 sigma inside CONNECT_PERIOD_FRAC
    of a period). If the prediction is looser than the eclipse search window,
    the eclipses are first located by an offset scan that must be significant
    and unique. Each addition re-fits the ephemeris, so the reach grows
    geometrically. A sector that cannot be connected unambiguously is left out
    and reported, never guessed. Finally everything connected is re-measured on
    the converged ephemeris."""
    lcs = load_or_fetch_lightcurves(tic, author, log, lc_dir)
    if not lcs:
        return {"status": "NO_DATA"}
    parts = [flatten_sector(lc, P, t0, dur) + (np.full(len(lc), s),) for s, lc in lcs]
    t = np.concatenate([p[0] for p in parts])
    f = np.concatenate([p[1] for p in parts])
    e = np.concatenate([p[2] for p in parts])
    sec = np.concatenate([np.full(len(p[0]), lcs[i][0]) for i, p in enumerate(parts)])
    order = np.argsort(t)
    t, f, e, sec = t[order], f[order], e[order], sec[order]
    sectors = sorted({int(s) for s in sec})
    tmed = {s: float(np.median(t[sec == s])) for s in sectors}

    anchor = min(sectors, key=lambda s: float(np.min(np.abs(t[sec == s] - t0))))
    block_sectors = [anchor]
    m = sec == anchor
    ref = refine_ephemeris(t[m], f[m], e[m], sec[m], P, t0, dur)
    if ref is None:
        return {"status": "NO_TEMPLATE", "sectors": sectors}
    P_use, t0_use, tpl = ref
    block = measure_eclipses(t[m], f[m], e[m], sec[m], P_use, t0_use, dur, tpl)

    while True:
        added = False
        rest = [s for s in sectors if s not in block_sectors]
        rest.sort(key=lambda s: min(abs(tmed[s] - tmed[b]) for b in block_sectors))
        for s in rest:
            E_far = int(round((tmed[s] - t0_use) / P_use))
            sig, fit = predicted_sigma(block, E_far, P_use, dur)
            if not connectable(sig, P_use):
                continue                      # prediction too loose to be unambiguous (yet)
            if fit is not None:               # use the block's own fitted line to place windows
                P_try = fit["P"]
                t0_try = fit["T0"] - fit["P"] * fit["Eref"]
            else:
                P_try, t0_try = P_use, t0_use
            ms = sec == s
            if 4.0 * sig > DIRECT_WINDOW_FRAC * dur:
                # looser than the search window: find the eclipses first
                delta = scan_offset(t[ms], f[ms], e[ms], P_try, t0_try, dur, tpl, 4.0 * sig)
                if delta is None:
                    continue
                t0_try = t0_try + delta
            new = measure_eclipses(t[ms], f[ms], e[ms], sec[ms], P_try, t0_try, dur, tpl)
            if not new:
                continue
            off = np.array([x["T"] - (t0_try + x["E"] * P_try) for x in new])
            if float(np.median(np.abs(off))) > SECTOR_OFFSET_FRAC * dur:
                continue                      # eclipses not where predicted: do not trust
            block = block + new
            block_sectors.append(s)
            ba = np.array([x["E"] for x in block], float)
            line = robust_line(ba, np.array([x["T"] for x in block]))
            if line is not None:
                P_use, t0_use = line["P"], line["T0"]
            added = True
            break
        if not added:
            break

    # final pass: flatten the connected sectors again with the eclipses masked at
    # their TRUE positions (the first flatten used the search ephemeris, which
    # drifts away from the eclipses in distant sectors), then re-measure
    kept = [(s, lc) for s, lc in lcs if s in block_sectors]
    parts = [flatten_sector(lc, P_use, t0_use, dur) + (np.full(len(lc), s),) for s, lc in kept]
    t = np.concatenate([q[0] for q in parts])
    f = np.concatenate([q[1] for q in parts])
    e = np.concatenate([q[2] for q in parts])
    sec = np.concatenate([np.full(len(q[0]), kept[i][0]) for i, q in enumerate(parts)])
    order = np.argsort(t)
    t, f, e, sec = t[order], f[order], e[order], sec[order]
    mc = np.ones(len(t), bool)
    ref = refine_ephemeris(t[mc], f[mc], e[mc], sec[mc], P_use, t0_use, dur)
    if ref is None:
        return {"status": "NO_TEMPLATE", "sectors": sectors}
    P_use, t0_use, tpl = ref
    ecl = measure_eclipses(t[mc], f[mc], e[mc], sec[mc], P_use, t0_use, dur, tpl)
    out = {"sectors": sectors, "sectors_connected": sorted(block_sectors),
           "sectors_unconnected": [s for s in sectors if s not in block_sectors],
           "measure_version": MEASURE_VERSION}
    if len(ecl) < 2:
        return {**out, "status": "TOO_FEW_ECLIPSES", "n_eclipses": len(ecl)}
    return {**out, "status": "OK", "eclipses": ecl, "P_used": P_use, "t0_used": t0_use,
            "n_points": int(mc.sum())}


def observed_year9_sectors(tic, ra, dec):
    """Sectors tess-point says put the star on silicon. None if tess-point is
    not installed (coverage unknown, so no predictions are made)."""
    try:
        import tess_stars2px as tsp
    except ImportError:
        return None
    res = tsp.tess_stars2px_function_entry(int(tic), float(ra), float(dec))
    return sorted({int(s) for s in res[3]})


def analyse_star(tic, meas, ra, dec, P_pipeline):
    """From cached measurements to the three output tables."""
    allecl = meas["eclipses"]
    keep = clip_outliers(np.array([x["E"] for x in allecl], float),
                         np.array([x["T"] for x in allecl]), np.array([x["sigma"] for x in allecl]),
                         np.array([x["sector"] for x in allecl]))
    ecl = [x for x, k in zip(allecl, keep) if k]
    row = {"tic": tic, "n_eclipses": len(ecl), "n_clipped": len(allecl) - len(ecl),
           "n_sectors_measured": len({x["sector"] for x in ecl}),
           "sectors_downloaded": ",".join(str(s) for s in meas["sectors"]),
           "sectors_connected": ",".join(str(s) for s in meas.get("sectors_connected", meas["sectors"])),
           "sectors_unconnected": ",".join(str(s) for s in meas.get("sectors_unconnected", []))}
    if len(ecl) < 2 or len({x["E"] for x in ecl}) < 2:
        row["status"] = "TOO_FEW_ECLIPSES"
        return row, [], []
    fit = fit_line([x["E"] for x in ecl], [x["T"] for x in ecl], [x["sigma"] for x in ecl],
                   [x["sector"] for x in ecl])
    sigP = float(np.sqrt(fit["cov"][1, 1]))
    row.update({
        "status": "OK", "period_days": fit["P"], "period_sigma_days": sigP,
        "t0_btjd": fit["T0"], "t0_sigma_min": float(np.sqrt(fit["cov"][0, 0]) * 1440),
        "cycle_ref": int(fit["Eref"]), "chi2_red_before_jitter": fit["chi2_red"],
        "timing_jitter_min": fit["jitter"] * 1440, "timing_jitter_mode": fit["jitter_mode"],
        "timing_excess": bool(fit["jitter"] > EXCESS_FACTOR * float(np.median([x["sigma"] for x in ecl]))),
        "timing_rms_min": fit["rms"] * 1440,
        "baseline_days": float(max(x["T"] for x in ecl) - min(x["T"] for x in ecl)),
        "period_pipeline_days": P_pipeline,
        "period_vs_pipeline_sigma": float((fit["P"] - P_pipeline) / sigP) if sigP > 0 else None,
    })
    ho = leave_one_sector_out(ecl) + rolling_origin(ecl)
    row["holdout_status"] = holdout_status(ho)
    row["holdout_sectors_tested"] = len(ho)
    row["holdout_min_p_value"] = min((r["p_value"] for r in ho), default=None)
    row["holdout_max_z_equiv"] = max((r["z_equiv"] for r in ho), default=None)
    ho_rows = [dict(tic=tic, **r) for r in ho]

    sectors = observed_year9_sectors(tic, ra, dec)
    row["year9_sectors_observed"] = ("unknown" if sectors is None else
                                     ",".join(str(s) for s in sectors if s in YEAR9_SECTORS))
    preds = [] if sectors is None else predict_future(fit, tic, ra, dec, sectors)
    last_t = float(max(x["T"] for x in ecl))
    horizon = (min(p_["t_btjd"] for p_ in preds) - last_t) if preds else None
    g = prediction_grade(row["holdout_status"], ho, horizon, min((p_["sigma_min"] for p_ in preds), default=None))
    row["prediction_grade"] = g["grade"]
    row["grade_note"] = g["note"]
    row["holdout_tested_lag_days"] = g["tested_lag_days"]
    row["prediction_horizon_days"] = horizon
    row["extrapolation_factor"] = g["extrapolation_factor"]
    for pr_ in preds:
        pr_["grade"] = row["prediction_grade"]
        pr_["horizon_days"] = pr_["t_btjd"] - last_t
    row["n_predicted_eclipses"] = len(preds)
    row["first_pred_sigma_min"] = preds[0]["sigma_min"] if preds else None
    row["min_pred_sigma_min"] = min((p["sigma_min"] for p in preds), default=None)
    return row, ho_rows, preds


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    root = Path(args[0]).resolve()
    opts = {"tiers": "CLEAN", "limit": None, "only": None, "refresh": False, "max_minutes": None}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--refresh":
            opts["refresh"] = True
        elif a in ("--tiers", "--limit", "--only", "--max-minutes"):
            opts[a[2:].replace("-", "_")] = args[i + 1]
            i += 1
        i += 1
    tiers = {x.strip().upper() for x in opts["tiers"].split(",")}
    proc = root / "data" / "processed"
    cache_dir = proc / "f13_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads((root / "site/public/data/index.json").read_text(encoding="utf-8"))
    cands = [c for c in index["candidates"] if str(c["tier"]).upper() in tiers]
    if opts["only"]:
        want = {int(x) for x in opts["only"].split(",")}
        cands = [c for c in cands if int(c["tic"]) in want]
    if opts["limit"]:
        cands = cands[: int(opts["limit"])]
    manifest = pd.read_csv(proc / "f2c_manifest.csv")
    manifest["TIC"] = manifest["TIC"].astype(int)
    author_of = dict(zip(manifest["TIC"], manifest["author_used"]))

    print(f"F13 ephemerides: {len(cands)} candidate(s), tiers {sorted(tiers)}")
    t_start = time.time()
    rows, ho_all, pred_all = [], [], []
    for n, c in enumerate(cands, start=1):
        if opts["max_minutes"] and (time.time() - t_start) / 60 > float(opts["max_minutes"]):
            print(f"Time budget of {opts['max_minutes']} min reached; cached work is kept. Re-run to continue.")
            break
        tic = int(c["tic"])
        dpath = root / "site" / "public" / "data" / "detail" / f"TIC{tic}.json"
        detail = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else None
        ok, why = eligibility(c["tier"], detail)
        base = {"tic": tic, "tier": c["tier"], "eligible": ok, "exclusion_reason": why}
        if not ok:
            rows.append({**base, "status": "NOT_ELIGIBLE"})
            print(f"[{n}/{len(cands)}] TIC {tic}: not eligible ({why})")
            continue
        P, t0, dur = float(detail["period_true_days"]), float(detail["t0_btjd"]), float(detail["duration_days"])
        ra, dec = float(detail["catalog"]["ra"]), float(detail["catalog"]["dec"])
        cpath = cache_dir / f"TIC{tic}.json"
        meas = None
        if cpath.exists() and not opts["refresh"]:
            meas = json.loads(cpath.read_text(encoding="utf-8"))
            if meas.get("measure_version") != MEASURE_VERSION:
                meas = None                      # measured by older code: do it again
        if meas is None:
            try:
                meas = measure_star(tic, author_of.get(tic), P, t0, dur, print, proc / "f13_lc_cache")
            except Exception as exc:  # noqa: BLE001 - one bad star must not stop the batch
                meas = {"status": "ERROR", "error": str(exc)[:200]}
            cpath.write_text(json.dumps(meas), encoding="utf-8", newline="\n")
        if meas.get("status") != "OK":
            rows.append({**base, "status": meas.get("status"), "note": meas.get("error", "")})
            print(f"[{n}/{len(cands)}] TIC {tic}: {meas.get('status')} {meas.get('error', '')}")
            continue
        row, ho_rows, preds = analyse_star(tic, meas, ra, dec, P)
        rows.append({**base, **row})
        ho_all += ho_rows
        pred_all += preds
        print(f"[{n}/{len(cands)}] TIC {tic}: P={row.get('period_days', float('nan')):.6f} "
              f"+/- {row.get('period_sigma_days', float('nan')):.1e} d, {row['n_eclipses']} eclipses in "
              f"{row['n_sectors_measured']} sector(s), holdout {row.get('holdout_status')}, "
              f"{row.get('n_predicted_eclipses', 0)} predicted")

    pd.DataFrame(rows).to_csv(proc / "f13_ephemerides.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(ho_all).to_csv(proc / "f13_holdout.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(pred_all).to_csv(proc / "f13_predictions.csv", index=False, encoding="utf-8", lineterminator="\n")
    df = pd.DataFrame(rows)
    print("\n" + "=" * 70)
    print("F13 SUMMARY")
    print("=" * 70)
    print(df["status"].value_counts().to_string())
    if "holdout_status" in df:
        print("\nHold-out (retrospective):", df["holdout_status"].value_counts().to_dict())
    print(f"Predicted eclipses written: {len(pred_all)} across {len({p['tic'] for p in pred_all})} candidate(s)")
    print(f"Wrote {proc / 'f13_ephemerides.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
