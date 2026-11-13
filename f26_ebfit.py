"""Physical light-curve model for detached eclipsing binaries (ellc), fitted by MCMC.

What it measures, from the TESS light curve alone:
  r1 = R1/a, r2 = R2/a      fractional radii (star 1 is the star eclipsed at phase 0)
  i                         orbital inclination
  J                         TESS-band surface-brightness ratio (star 2 / star 1)
  e, omega                  from sqrt(e) cos(omega) and sqrt(e) sin(omega): the secondary-eclipse phase
                            fixes e cos(omega); the ratio of the two eclipse durations fixes e sin(omega),
                            so the TRUE eccentricity is measured, not only the lower limit e cos(omega)
  l3                        third light (TESS apertures are large, so it is free)

What it cannot measure without spectra: masses, absolute radii and the mass ratio. f28 adds the
absolute scale from Gaia (see there) and states how model-dependent that is.

Model choices (all stated in the output):
  * spheres (detached systems; a star filling much of its Roche lobe is flagged, not fitted better);
  * quadratic limb darkening, u2 fixed at 0.22 and u1 fitted separately for each star with a Gaussian prior
    0.40 +- 0.10 (TESS band, 4500-6500 K); the limb-darkening choice is a known systematic on the radii;
  * the time of primary eclipse and a small period correction are fitted (blocks of sectors years apart
    would otherwise be misaligned);
  * third light has a half-normal prior of width 0.10 (SPOC and QLP fluxes are already corrected for known
    neighbouring stars; a bound companion is not, so a large l3 can still be found and is flagged);
  * each eclipse is detrended on its own with a quadratic fitted to the data just outside it (eclipses
    without data on both sides are dropped); the eclipse windows are folded and binned in phase per block of
    sectors and cadence; long-cadence bins are modelled with exposure-time smearing;
  * one noise-scale parameter per cadence group absorbs under-estimated errors.

Noise model v2 (--noise v2, or F26_NOISE=v2): the likelihood of "event-wise" data. The v1 chain above divides each
eclipse by a baseline fitted to its own wings and then treats the result as exact, white and folded; the injection
test (data/processed/f30_injection.json) showed that quoted 68% intervals contain the truth about 40% of the time
on data the model can represent exactly, so the noise treatment, not the physics, was over-confident. v2:
  * keeps every eclipse event separate and undivided (flux normalised only by its own out-of-eclipse median);
  * gives each event a quadratic baseline that is INTEGRATED OUT of the likelihood analytically (flat prior,
    including the log-determinant term that makes the depth, duration and baseline uncertainties couple);
  * one white-noise scale per sector instead of per cadence;
  * a Matern-3/2 Gaussian process inside each event (amplitude and timescale shared by the star) for correlated
    noise, solved densely (events are binned to at most EVENT_MAX_POINTS points);
  * no light-ratio prior: without spectra it would feed an assumption back as a result.
v1 stays the default so every published number is unchanged until v2 is validated.

Usage:  python f26_ebfit.py <root> [--tics T1,T2] [--steps 2000] [--converge] [--max-steps 6000] [--lc-dir D] [--out F] [--validate]
        --converge extends each chain until it is 20 autocorrelation times long after burn-in (F26_PROCS=4 uses 4 processes)
        --validate fits AI Phe (TIC 102069549) and compares with Maxted et al. 2020 (MNRAS 498, 332).
Writes: data/processed/f26_ebfit.json (and f26_validation.json with --validate)
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

U1_PRIOR = (0.40, 0.10)
U2_FIXED = 0.22
ROCHE_WARN_RSUM = 0.25          # above this the spherical approximation is questionable
FINE_BINS_PER_DURATION = 40
MAX_UNBINNED = 1500             # groups with at most this many points are fitted point by point
COARSE_BIN_PHASE = 0.01
PARAMS = ["dt0", "rsum", "k", "cosi", "J", "fc", "fs", "l3", "u1", "u1b", "dP"]
NOISE_DEFAULT = os.environ.get("F26_NOISE", "v1")      # "v1": folded, white; "v2": event-wise, baselines integrated out, GP
EVENT_MAX_POINTS = 120          # v2: an event with more points is binned in time (bins stay far shorter than ingress)
EVENT_WINDOW = 1.6              # half-width of an event window, in eclipse durations
MAX_NOISE_BLOCKS = 8            # v2: white-noise scales per star; consecutive sectors share one when there are more sectors than this
TEMPLATE_STEP_DAYS = 2.0 / 1440.0   # v2: spacing of the exact model grid that is integrated over each point's exposure
GP_LNA_BOUNDS = (-12.0, -2.0)   # v2: ln of the red-noise amplitude (normalised flux)
GP_LNRHO_BOUNDS = (float(np.log(0.01)), float(np.log(3.0)))   # v2: ln of the red-noise timescale (days)
L3_PRIOR_SIGMA = 0.10            # half-normal: SPOC/QLP fluxes are already corrected for known neighbours

# Maxted et al. 2020, MNRAS 498, 332, Table 2 / 3 adopted means (TESS sector 2 and 29)
AI_PHE = {"tic": 102069549, "period": 24.5924, "t0_btjd": 2458362.82842 - 2457000.0, "duration": 0.40,
          "truth": {"r1": 0.037686, "r2": 0.061242, "incl": 88.359, "ecosw": -0.065170, "esinw": 0.1758, "e": 0.1875},
          "pass": {"e": 0.01, "esinw": 0.02, "r_frac": 0.05, "incl": 0.5}}


def ellc_lc(t, p, period, t_exp=None, n_int=1, cycle=0.0):
    import ellc
    rsum, k = p["rsum"], p["k"]
    r1 = rsum / (1.0 + k)
    r2 = rsum - r1
    incl = float(np.degrees(np.arccos(p["cosi"])))
    return ellc.lc(t, radius_1=r1, radius_2=r2, sbratio=p["J"], incl=incl, t_zero=p["t0"] + cycle * p.get("dP", 0.0), period=period,
                   f_c=p["fc"], f_s=p["fs"], light_3=p["l3"], ld_1="quad", ldc_1=[p["u1"], U2_FIXED],
                   ld_2="quad", ldc_2=[p["u1b"], U2_FIXED],
                   shape_1="sphere", shape_2="sphere", grid_1="sparse", grid_2="sparse",
                   t_exp=t_exp, n_int=n_int)


def detrend_two_eclipses(t, f, period, t0, duration, sec_phase, sector):
    """Per-sector normalisation and a running median with BOTH eclipses masked."""
    f = np.asarray(f, float)
    out = np.full_like(f, np.nan)
    ph = ((t - t0) / period) % 1.0
    half = 0.75 * duration / period
    mask = (np.minimum(ph, 1 - ph) < half) | (np.abs(ph - sec_phase) < half)
    win = max(6.0 * duration, 0.75)
    for s in np.unique(sector):
        m = sector == s
        fs = f[m] / np.nanmedian(f[m][~mask[m]]) if (~mask[m]).any() else f[m] / np.nanmedian(f[m])
        ser = pd.Series(np.where(mask[m], np.nan, fs), index=pd.to_timedelta(t[m], unit="D"))
        base = ser.rolling(pd.Timedelta(days=win), center=True, min_periods=10).median().interpolate(limit_direction="both").to_numpy()
        out[m] = fs / base
    ok = np.isfinite(out)
    return t[ok], out[ok], sector[ok]


def detrend_local(t, f, period, t0, duration, sec_phase, sector, min_side=5):
    """Each eclipse event (primary and secondary) divided by a quadratic in time fitted to the points
    between 0.6 and 1.6 durations from its centre. Events lacking points on either side are dropped,
    because a one-sided baseline biases the depth. Returns only points within 1.6 durations of an eclipse."""
    keep_t, keep_f, keep_s = [], [], []
    n_cyc = np.round((t - t0) / period)
    for centre_phase in (0.0, sec_phase):
        cyc = np.floor((t - t0) / period - centre_phase + 0.5)
        for c in np.unique(cyc):
            tc = t0 + (c + centre_phase) * period
            m = np.abs(t - tc) < 1.6 * duration
            if m.sum() < 2 * min_side:
                continue
            dtm = t[m] - tc
            ooe = np.abs(dtm) > 0.6 * duration
            if (dtm[ooe] < 0).sum() < min_side or (dtm[ooe] > 0).sum() < min_side:
                continue
            deg = 2 if ooe.sum() >= 4 * min_side else 1
            co = np.polyfit(dtm[ooe], f[m][ooe], deg)
            base = np.polyval(co, dtm)
            keep_t.append(t[m])
            keep_f.append(f[m] / base)
            keep_s.append(sector[m])
    del n_cyc
    if not keep_t:
        return t[:0], f[:0], sector[:0]
    tt, ff, ss = np.concatenate(keep_t), np.concatenate(keep_f), np.concatenate(keep_s)
    o = np.argsort(tt)
    return tt[o], ff[o], ss[o]


CLIP_MAD = 5.0


def clip_against_phase_median(ph, y, dur_phase, sigma):
    """Points more than CLIP_MAD sigma from the median of their phase neighbourhood (width a tenth of the
    eclipse duration) are dropped: cosmic rays and bad cadences, not eclipse structure."""
    if sigma <= 0 or len(ph) < 10:
        return np.ones(len(ph), bool)
    w = max(dur_phase / 10.0, 1e-4)
    idx = np.floor(ph / w).astype(np.int64)
    med = pd.Series(y).groupby(idx).transform("median").to_numpy()
    return np.abs(y - med) <= CLIP_MAD * max(sigma, 1.4826 * np.median(np.abs(y - med)))


def _bin_one(ph, y, duration, period, texp, sec):
    w_fine = max(duration / period / FINE_BINS_PER_DURATION, 0.5 * texp / period)
    win = 1.6 * duration / period
    fine = np.unique(np.concatenate([np.arange(c - win, c + win + w_fine, w_fine) for c in (0.0, sec)]))
    coarse = np.arange(-0.25, 0.75 + COARSE_BIN_PHASE, COARSE_BIN_PHASE)
    in_win = (np.abs(ph) < win) | (np.abs(ph - sec) < win)
    xs, ys, es, ns = [], [], [], []
    for sel, bins in ((in_win, fine), (~in_win, coarse)):
        idx = np.digitize(ph[sel], bins)
        pv, yv = ph[sel], y[sel]
        for b in np.unique(idx):
            mm = idx == b
            n = int(mm.sum())
            if n < 3:
                continue
            yy, pp = yv[mm], pv[mm]
            mad = 1.4826 * np.median(np.abs(yy - np.median(yy)))
            if mad > 0:                                   # one cosmic ray or bad cadence must not move a bin
                ok = np.abs(yy - np.median(yy)) <= CLIP_MAD * mad
                yy, pp = yy[ok], pp[ok]
            n = int(len(yy))
            if n < 3:
                continue
            xs.append(float(pp.mean()))
            ys.append(float(yy.mean()))
            es.append(float(mad / np.sqrt(n)) if mad > 0 else np.nan)
            ns.append(n)
    return np.array(xs), np.array(ys), np.array(es), np.array(ns)


def bin_groups(t, f, sector, period, t0, duration, sec_phase, max_blocks=8):
    """Phase-binned data in groups of (block of sectors, cadence). Each group has its own flux
    normalisation (apertures and contamination change between sectors); groups of the same cadence
    share one noise-scale parameter. Sectors are combined into at most `max_blocks` consecutive blocks
    to keep the model fast. Each group carries the times of one reference cycle (t0 + phase * P)."""
    secs = np.unique(sector)
    dt_sector = {}
    for sc in secs:
        ts = np.sort(t[sector == sc])
        dt_sector[sc] = float(np.median(np.diff(ts))) if len(ts) > 2 else 2.0 / 1440
    cad_key = np.round(np.array([dt_sector[sc] for sc in sector]) * 1440.0).astype(int)   # minutes
    order = {sc: i for i, sc in enumerate(sorted(secs))}
    n_blocks = min(max_blocks, len(secs))
    block = np.array([order[sc] * n_blocks // len(secs) for sc in sector])
    sec = sec_phase if sec_phase < 0.75 else sec_phase - 1.0
    cads = sorted(np.unique(cad_key))
    groups = []
    for key in cads:
        for b in np.unique(block[cad_key == key]):
            m = (cad_key == key) & (block == b)
            ph = (((t[m] - t0) / period) + 0.25) % 1.0 - 0.25    # -0.25 .. 0.75 keeps both eclipses contiguous
            texp = key / 1440.0
            if m.sum() <= MAX_UNBINNED:
                # few points (long cadence, few eclipses): fit them as they are; errors from the scatter
                # just outside the eclipses, rescaled later by the noise parameter
                ooe = (np.abs(ph) > 0.6 * duration / period) & (np.abs(ph - sec) > 0.6 * duration / period)
                yo = f[m][ooe] if ooe.sum() >= 10 else f[m]
                sig = 1.4826 * np.median(np.abs(yo - np.median(yo)))
                xs, ys = ph, f[m]
                keep = clip_against_phase_median(xs, ys, duration / period, sig)
                xs, ys = xs[keep], ys[keep]
                es = np.full(len(xs), sig if sig > 0 else 1e-3)
                ns = np.ones(len(xs), int)
            else:
                xs, ys, es, ns = _bin_one(ph, f[m], duration, period, texp, sec)
                floor = np.nanmedian(es) if np.isfinite(es).any() else 1e-3
                es = np.where(np.isfinite(es) & (es > 0), es, floor)
            if len(xs) < 10:
                continue
            groups.append({"cadence_min": int(key), "noise_idx": cads.index(key),
                           "cycle": float(np.mean(np.round((t[m] - t0) / period))),
                           "sectors": sorted(int(x) for x in np.unique(sector[m])),
                           "t": t0 + xs * period, "y": ys, "e": es, "n": ns,
                           "t_exp": None if key <= 3 else texp, "n_int": 1 if key <= 3 else int(np.ceil(key / 5.0))})
    # renumber noise indices so they are contiguous over the groups actually kept
    used = sorted({g["noise_idx"] for g in groups})
    for g in groups:
        g["noise_idx"] = used.index(g["noise_idx"])
    return groups


# ---------------------------------------------------------------------------------------------------------
# Noise model v2: event-wise data, baselines integrated out, per-sector white noise, Matern-3/2 red noise
# ---------------------------------------------------------------------------------------------------------

def _sector_sigma(events):
    """Point-to-point scatter of the normalised flux, from consecutive pairs of out-of-eclipse points only (eclipse slopes
    would inflate it): 1.4826 * median |difference - median| / sqrt(2). Insensitive to slow trends."""
    d = []
    for ev in events:
        ok = ev["ooe"][1:] & ev["ooe"][:-1]
        d.append(np.diff(ev["y"])[ok])
    d = np.concatenate(d) if d else np.array([])
    if len(d) < 10:
        return 1e-3
    s = 1.4826 * float(np.median(np.abs(d - np.median(d)))) / np.sqrt(2.0)
    return s if s > 0 else 1e-3


def _bin_event_in_time(t, y, width):
    idx = np.floor((t - t[0]) / width).astype(np.int64)
    ts, ys, ns = [], [], []
    for b in np.unique(idx):
        m = idx == b
        ts.append(float(t[m].mean()))
        ys.append(float(y[m].mean()))
        ns.append(int(m.sum()))
    return np.array(ts), np.array(ys), np.array(ns)


def _spike_free(y):
    """Boolean mask of points that are not single-point spikes (cosmic rays, bad cadences).

    A point is compared with the straight line between its two neighbours, which is blind to the steep but smooth ingress and
    egress slopes (a running median lags on a slope and, with a threshold set by the quiet baseline, deletes exactly the
    points that fix the eclipse shape: seen on injected data, where it also biased the scatter estimate low by 20%).
    The threshold is CLIP_MAD times the larger of the global and the local (15-point) robust scatter of that residual."""
    n = len(y)
    if n < 7:
        return np.ones(n, bool)
    r = np.zeros(n)
    r[1:-1] = y[1:-1] - 0.5 * (y[:-2] + y[2:])
    a = np.abs(r[1:-1])
    glob = 1.4826 * float(np.median(a))
    loc = 1.4826 * pd.Series(a).rolling(15, center=True, min_periods=5).median().to_numpy()
    thr = CLIP_MAD * np.maximum(np.where(np.isfinite(loc), loc, glob), max(glob, 1e-6))
    keep = np.ones(n, bool)
    keep[1:-1] = a <= thr
    return keep


def cut_events(t, f, sector, period, t0, duration, sec_phase, min_side=5):
    """Every primary and secondary eclipse event as its own undivided piece: the points within EVENT_WINDOW durations of the
    centre, normalised by the event's own out-of-eclipse median (so the baseline constant is near 1), with the same
    selection rule as detrend_local (events without >= min_side points on each side outside 0.6 durations are dropped,
    because a one-sided baseline biases the depth). Outliers are removed against a 5-point running median.
    Returns a list of dicts with t, y, n (points per binned point), sector, tc, deg, kind."""
    events = []
    for kind, centre_phase in (("primary", 0.0), ("secondary", sec_phase)):
        cyc = np.floor((t - t0) / period - centre_phase + 0.5)
        for c in np.unique(cyc):
            tc = t0 + (c + centre_phase) * period
            m = np.abs(t - tc) < EVENT_WINDOW * duration
            if m.sum() < 2 * min_side:
                continue
            tt, ff, ss = t[m], f[m], sector[m]
            dtm = tt - tc
            ooe = np.abs(dtm) > 0.6 * duration
            if (dtm[ooe] < 0).sum() < min_side or (dtm[ooe] > 0).sum() < min_side:
                continue
            o = np.argsort(tt)
            tt, ff, ss, ooe = tt[o], ff[o], ss[o], ooe[o]
            yy = ff / np.median(ff[ooe])
            keep = _spike_free(yy)
            tt, yy, ss, ooe = tt[keep], yy[keep], ss[keep], ooe[keep]
            if len(tt) < 2 * min_side:
                continue
            events.append({"t": tt, "y": yy, "ooe": ooe, "n": np.ones(len(tt), int), "sector": int(np.bincount(ss.astype(int)).argmax()), "tc": float(tc),
                           "deg": 2 if int(ooe.sum()) >= 4 * min_side else 1, "kind": kind, "cadence_days": float(np.median(np.diff(tt))) if len(tt) > 2 else 0.0014})
    return events


def event_groups(events, duration, gp=True):
    """One group per sector (so one white-noise scale per sector). A group carries its events concatenated (t, y, e), so the
    model is evaluated in one ellc call, plus the per-event slices, polynomial design matrices and time-difference
    matrices. When a sector's cadence is finer than the common bin width (2 * EVENT_WINDOW * duration / EVENT_MAX_POINTS),
    all of its events are binned to that width and the model is integrated over it; otherwise they stay unbinned."""
    secs = sorted({ev["sector"] for ev in events})
    width = 2.0 * EVENT_WINDOW * duration / EVENT_MAX_POINTS
    groups = []
    for gi, sc in enumerate(secs):
        evs = [ev for ev in events if ev["sector"] == sc]
        sigma = _sector_sigma(evs)
        cad = float(np.median([ev["cadence_days"] for ev in evs]))
        binned = cad < 0.9 * width
        texp_days = width if binned else cad
        ts, ys, es, sl, polys, dts, kinds = [], [], [], [], [], [], []
        i0 = 0
        for ev in evs:
            t_, y_, n_ = ev["t"], ev["y"], ev["n"]
            if binned:
                t_, y_, n_ = _bin_event_in_time(t_, y_, width)
            if len(t_) < 6:
                continue
            x = (t_ - ev["tc"]) / (EVENT_WINDOW * duration)
            ts.append(t_); ys.append(y_); es.append(sigma / np.sqrt(n_)); sl.append(slice(i0, i0 + len(t_)))
            polys.append(np.vander(x, ev["deg"] + 1, increasing=True))
            dts.append(np.abs(t_[:, None] - t_[None, :]) if gp else None)
            kinds.append(ev["kind"])
            i0 += len(t_)
        if not ts:
            continue
        groups.append({"cadence_min": int(round(cad * 1440.0)), "noise_idx": 0, "n_white": 0, "gp": bool(gp),
                       "sectors": [int(sc)], "t": np.concatenate(ts), "y": np.concatenate(ys), "e": np.concatenate(es),
                       "events": [{"sl": a_, "V": b_, "dtm": c_, "kind": k_} for a_, b_, c_, k_ in zip(sl, polys, dts, kinds)],
                       "sigma_point": float(sigma), "w": 0.0 if texp_days * 1440.0 <= 3.0 else float(texp_days)})
    n_blocks = min(MAX_NOISE_BLOCKS, len(groups))            # a star seen in 42 sectors must not get 42 noise parameters
    for i, g in enumerate(groups):
        g["noise_idx"] = i * n_blocks // len(groups)
        g["n_white"] = n_blocks
    return groups


def _event_models(p, period_eff, groups):
    """Model flux at every point of every group, as a list of arrays (one per group).

    ellc is evaluated ONCE on a regular grid (TEMPLATE_STEP_DAYS) that covers just the occupied parts of the orbit, and each
    point's value is the exact integral of that piecewise-linear template over the point's own exposure or bin width
    (g["w"] days, 0 = a point sample), found from a cumulative sum. The cost is then set by how much of the orbit is
    covered, not by the number of events, and binned and long-cadence points are integrated properly."""
    t = np.concatenate([g["t"] for g in groups])
    w = np.concatenate([np.full(len(g["t"]), g["w"]) for g in groups])
    ph = (((t - p["t0"]) / period_eff) + 0.25) % 1.0 - 0.25
    step = TEMPLATE_STEP_DAYS / period_eff
    hw = 0.5 * w / period_eff
    lo = np.floor((ph - hw) / step).astype(np.int64)
    hi = np.floor((ph + hw) / step).astype(np.int64) + 1
    span = int((hi - lo).max()) + 1
    cells = lo[:, None] + np.arange(span)[None, :]
    cells = np.unique(cells[cells <= hi[:, None]])
    grid = cells * step
    F = ellc_lc(p["t0"] + grid * period_eff, p, period_eff)
    if not np.all(np.isfinite(F)):
        return None
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (F[1:] + F[:-1]) * step)])    # trapezoid; only differences inside a run are used

    def integral(x):
        k = np.clip(np.searchsorted(cells, np.floor(x / step).astype(np.int64)), 0, len(cells) - 2)
        dx = x - grid[k]
        slope = np.where(cells[k + 1] - cells[k] == 1, (F[np.minimum(k + 1, len(F) - 1)] - F[k]) / step, 0.0)
        return cum[k] + F[k] * dx + 0.5 * slope * dx * dx

    box = w > 0
    m = np.empty(len(t))
    if (~box).any():
        x = ph[~box]
        k = np.clip(np.searchsorted(cells, np.floor(x / step).astype(np.int64)), 0, len(cells) - 2)
        f_ = (x - grid[k]) / step
        m[~box] = F[k] * (1.0 - f_) + F[np.minimum(k + 1, len(F) - 1)] * f_
    if box.any():
        m[box] = (integral(ph[box] + hw[box]) - integral(ph[box] - hw[box])) / (w[box] / period_eff)
    out, i0 = [], 0
    for g in groups:
        out.append(m[i0:i0 + len(g["t"])])
        i0 += len(g["t"])
    return out


def _event_loglike(m, y, e, V, dtm, scale, lna, lnrho):
    """Log-likelihood of one event with its polynomial baseline integrated out (flat prior on the coefficients).

    y = (V c) * m + noise, noise ~ N(0, C), C = diag((scale e)^2) + Matern-3/2(amplitude, rho). With A = diag(m) V,
        ln L = -1/2 [ y^T C^-1 y - b^T M^-1 b + ln|C| + ln|M| + n ln 2 pi ],   M = A^T C^-1 A,  b = A^T C^-1 y.
    The ln|M| term is the Occam factor: it is what lets the baseline uncertainty reach the depth, duration and
    inclination. Returns (log-likelihood, chi-square at the best baseline), or (-inf, inf) if C is not positive definite."""
    from scipy.linalg import cho_factor, cho_solve, solve_triangular
    n = len(y)
    A = m[:, None] * V
    s2 = (e * scale) ** 2
    if dtm is None or lna is None:
        w = 1.0 / s2
        Aw = A * w[:, None]
        M = A.T @ Aw
        b = Aw.T @ y
        yCy = float(np.sum(y * y * w))
        logdetC = float(np.sum(np.log(s2)))
    else:
        a = np.sqrt(3.0) * dtm / np.exp(lnrho)
        C = np.exp(2.0 * lna) * (1.0 + a) * np.exp(-a)
        C[np.diag_indices(n)] += s2
        try:
            L = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            return -np.inf, np.inf
        Ly = solve_triangular(L, y, lower=True)
        LA = solve_triangular(L, A, lower=True)
        M = LA.T @ LA
        b = LA.T @ Ly
        yCy = float(Ly @ Ly)
        logdetC = 2.0 * float(np.sum(np.log(np.diag(L))))
    try:
        cf = cho_factor(M)
    except np.linalg.LinAlgError:
        return -np.inf, np.inf
    chi2 = yCy - float(b @ cho_solve(cf, b))
    logdetM = 2.0 * float(np.sum(np.log(np.diag(cf[0]))))
    return -0.5 * (chi2 + logdetC + logdetM + n * np.log(2.0 * np.pi)), chi2


def _log_like_events(theta, groups, period, t0_ref, return_chi=False):
    p = unpack(theta[:len(PARAMS)], t0_ref)
    nw = groups[0]["n_white"]
    gp = groups[0]["gp"]
    lna = theta[len(PARAMS) + nw] if gp else None
    lnrho = theta[len(PARAMS) + nw + 1] if gp else None
    bad = (-np.inf, np.inf) if return_chi else -np.inf
    try:
        models = _event_models(p, period + p["dP"], groups)
    except Exception:  # noqa: BLE001 - ellc refuses some geometries; treat as impossible
        return bad
    if models is None:
        return bad
    ll, chi = 0.0, 0.0
    for g, m in zip(groups, models):
        scale = float(np.exp(theta[len(PARAMS) + g["noise_idx"]]))
        for ev in g["events"]:
            sl = ev["sl"]
            l1, c1 = _event_loglike(m[sl], g["y"][sl], g["e"][sl], ev["V"], ev["dtm"], scale, lna, lnrho)
            if not np.isfinite(l1):
                return bad
            ll += l1
            chi += c1
    return (ll, chi) if return_chi else ll


def _profiled_residuals(m, g):
    """Per-event residuals with the polynomial baseline solved by weighted least squares (white noise only)."""
    out = []
    for ev in g["events"]:
        sl = ev["sl"]
        A = m[sl][:, None] * ev["V"]
        w = 1.0 / g["e"][sl]
        c, *_ = np.linalg.lstsq(A * w[:, None], g["y"][sl] * w, rcond=None)
        out.append((g["y"][sl] - A @ c) * w)
    return out


def _residuals_events(x, groups, period, t0_ref):
    """Whitened residuals for the least-squares start: white noise only, baselines profiled (solved per event)."""
    p = unpack(x, t0_ref)
    n_all = sum(len(g["y"]) for g in groups) + 3
    if p["fc"] ** 2 + p["fs"] ** 2 >= 0.9 or p["cosi"] >= 1.5 * p["rsum"]:
        return np.full(n_all, 1e3)
    try:
        models = _event_models(p, period + p["dP"], groups)
    except Exception:  # noqa: BLE001
        return np.full(n_all, 1e3)
    if models is None:
        return np.full(n_all, 1e3)
    out = []
    for g, m in zip(groups, models):
        out.extend(_profiled_residuals(m, g))
    out.append(np.array([(p["u1"] - U1_PRIOR[0]) / U1_PRIOR[1], (p["u1b"] - U1_PRIOR[0]) / U1_PRIOR[1], p["l3"] / L3_PRIOR_SIGMA]))
    return np.concatenate(out)


def _white_scales_events(x, groups, period, t0_ref):
    """ln of the per-block error scale that makes the profiled chi-square per point 1 (start values for the sampler)."""
    p = unpack(x, t0_ref)
    models = _event_models(p, period + p["dP"], groups)
    chi = np.zeros(groups[0]["n_white"])
    n = np.zeros(groups[0]["n_white"])
    for g, m in zip(groups, models):
        r = _profiled_residuals(m, g)
        chi[g["noise_idx"]] += float(sum(np.sum(x_ ** 2) for x_ in r))
        n[g["noise_idx"]] += sum(len(x_) - ev["V"].shape[1] for x_, ev in zip(r, g["events"]))
    return [float(np.clip(0.5 * np.log(max(c / max(k, 1), 1e-6)), -2.9, 2.9)) for c, k in zip(chi, n)]


def n_noise(groups):
    return 1 + max(g["noise_idx"] for g in groups)


def unpack(theta, t0_ref):
    p = dict(zip(PARAMS, theta))
    p["t0"] = t0_ref + p["dt0"]
    return p


def log_prior(theta, rsum_max=0.6):
    p = dict(zip(PARAMS, theta[:len(PARAMS)]))
    e = p["fc"] ** 2 + p["fs"] ** 2
    if not (0.003 < p["rsum"] < rsum_max and 0.1 < p["k"] < 10.0 and 0.0 <= p["cosi"] < min(p["rsum"] * 1.5, 0.9)
            and 0.0005 < p["J"] < 20.0 and e < 0.9 and 0.0 <= p["l3"] < 0.95 and 0.0 < p["u1"] < 1.0
            and 0.0 < p["u1b"] < 1.0 and abs(p["dt0"]) < 0.05 and abs(p["dP"]) < 1e-3):
        return -np.inf
    for s in theta[len(PARAMS):]:
        if not -3.0 < s < 3.0:
            return -np.inf
    return -0.5 * (((p["u1"] - U1_PRIOR[0]) / U1_PRIOR[1]) ** 2 + ((p["u1b"] - U1_PRIOR[0]) / U1_PRIOR[1]) ** 2
                   + (p["l3"] / L3_PRIOR_SIGMA) ** 2)


def log_like(theta, groups, period, t0_ref, return_chi=False):
    p = unpack(theta[:len(PARAMS)], t0_ref)
    ll, chi = 0.0, 0.0
    for g in groups:
        lns = theta[len(PARAMS) + g["noise_idx"]]
        try:
            m = ellc_lc(g["t"], p, period, g["t_exp"], g["n_int"], g.get("cycle", 0.0))
        except Exception:  # noqa: BLE001 - ellc refuses some geometries; treat as impossible
            return -np.inf
        if not np.all(np.isfinite(m)):
            return -np.inf
        # free normalisation per group, solved analytically (weighted least squares)
        w = 1.0 / g["e"] ** 2
        norm = float(np.sum(w * g["y"] * m) / np.sum(w * m * m))
        s2 = (g["e"] * np.exp(lns)) ** 2
        r = g["y"] - norm * m
        chi += float(np.sum(r * r / g["e"] ** 2))
        ll += -0.5 * float(np.sum(r * r / s2 + np.log(2 * np.pi * s2)))
    return (ll, chi) if return_chi else ll


def log_prob(theta, groups, period, t0_ref):
    lp = log_prior(theta)
    if not np.isfinite(lp):
        return -np.inf
    ll = log_like(theta, groups, period, t0_ref)
    return lp + ll if np.isfinite(ll) else -np.inf


def log_prior_events(theta, n_white, gp):
    """Same physical prior as v1; per-sector ln noise scales in (-3, 3); ln red-noise amplitude and timescale uniform
    inside GP_LNA_BOUNDS / GP_LNRHO_BOUNDS (i.e. log-uniform amplitude and timescale)."""
    lp = log_prior(theta[:len(PARAMS)])
    if not np.isfinite(lp):
        return -np.inf
    for s_ in theta[len(PARAMS):len(PARAMS) + n_white]:
        if not -3.0 < s_ < 3.0:
            return -np.inf
    if gp:
        lna, lnrho = theta[len(PARAMS) + n_white], theta[len(PARAMS) + n_white + 1]
        if not (GP_LNA_BOUNDS[0] < lna < GP_LNA_BOUNDS[1] and GP_LNRHO_BOUNDS[0] < lnrho < GP_LNRHO_BOUNDS[1]):
            return -np.inf
    return lp


def log_prob_events(theta, groups, period, t0_ref):
    lp = log_prior_events(theta, groups[0]["n_white"], groups[0]["gp"])
    if not np.isfinite(lp):
        return -np.inf
    ll = _log_like_events(theta, groups, period, t0_ref)
    return lp + ll if np.isfinite(ll) else -np.inf


LOWER = np.array([-0.05, 0.003, 0.1, 0.0, 0.0005, -0.95, -0.95, 0.0, 0.0, 0.0, -1e-3])
UPPER = np.array([0.05, 0.6, 10.0, 0.9, 20.0, 0.95, 0.95, 0.95, 1.0, 1.0, 1e-3])


def starts(duration, period, ecosw, depth_ratio):
    rsum0 = float(np.clip(np.pi * duration / period, 0.01, 0.5))
    out = []
    for k in (0.6, 1.0, 1.6):
        for esinw in (-0.15, 0.0, 0.15):
            for b in (0.2, 0.7):
                e = float(np.hypot(ecosw, esinw))
                w = float(np.arctan2(esinw, ecosw if abs(ecosw) > 1e-4 else 1e-4))
                if e < 0.005:
                    e, w = 0.005, 0.0
                out.append([0.0, rsum0, k, b * rsum0, float(np.clip(depth_ratio, 0.01, 5.0)),
                            np.sqrt(e) * np.cos(w), np.sqrt(e) * np.sin(w), 0.02, U1_PRIOR[0], U1_PRIOR[0], 0.0])
    return out


def residuals(x, groups, period, t0_ref):
    p = unpack(x, t0_ref)
    if p["fc"] ** 2 + p["fs"] ** 2 >= 0.9 or p["cosi"] >= 1.5 * p["rsum"]:
        return np.full(sum(len(g["y"]) for g in groups) + 3, 1e3)
    out = []
    for g in groups:
        try:
            m = ellc_lc(g["t"], p, period, g["t_exp"], g["n_int"], g.get("cycle", 0.0))
        except Exception:  # noqa: BLE001
            m = None
        if m is None or not np.all(np.isfinite(m)):
            return np.full(sum(len(gg["y"]) for gg in groups) + 3, 1e3)
        w = 1.0 / g["e"] ** 2
        norm = float(np.sum(w * g["y"] * m) / np.sum(w * m * m))
        out.append((g["y"] - norm * m) / g["e"])
    out.append(np.array([(p["u1"] - U1_PRIOR[0]) / U1_PRIOR[1], (p["u1b"] - U1_PRIOR[0]) / U1_PRIOR[1], p["l3"] / L3_PRIOR_SIGMA]))
    return np.concatenate(out)


def optimise(groups, period, t0_ref, duration, ecosw, depth_ratio, noise="v1", x_init=None):
    """Bounded least squares: short runs from 18 starting points, the best three refined (Nelder-Mead was
    shown to stop in a third-light local minimum on AI Phe); then noise scales set from the residuals."""
    from scipy.optimize import least_squares
    v2 = noise == "v2"
    residuals_fn = _residuals_events if v2 else residuals
    xs = np.array([1e-3, 1e-2, 0.1, 1e-2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.1, 1e-5])
    screened = []
    # v2 is several times dearer per evaluation, so its global search is done with the v1 machinery on folded data and
    # passed in as x_init; here those solutions are only refined under the v2 likelihood
    first = [np.asarray(x, float)[:len(PARAMS)] for x in x_init] if x_init is not None else starts(duration, period, ecosw, depth_ratio)
    # ellc's own numerical noise (about 1e-7 in flux) swamps a finite-difference step of 1.5e-8, scipy's default, and the
    # optimiser then stops far from the minimum (seen on injected data: cost 53000 against 760 at the truth); v1 keeps the default
    lsq_kw = {"diff_step": 1e-4} if v2 else {}
    for s0 in first:                                                  # short runs from every start ...
        x0 = np.clip(np.array(s0), LOWER + 1e-9, UPPER - 1e-9)
        try:
            r = least_squares(residuals_fn, x0, bounds=(LOWER, UPPER), args=(groups, period, t0_ref), x_scale=xs, max_nfev=60, **lsq_kw)
        except Exception:  # noqa: BLE001
            continue
        screened.append(r)
    best = None
    for r0 in sorted(screened, key=lambda r: r.cost)[:3]:              # ... then the best three refined
        try:
            r = least_squares(residuals_fn, r0.x, bounds=(LOWER, UPPER), args=(groups, period, t0_ref), x_scale=xs, max_nfev=400, **lsq_kw)
        except Exception:  # noqa: BLE001
            r = r0
        if best is None or r.cost < best.cost:
            best = r
    if best is None:
        return None
    if v2:
        class R2:
            pass
        out2 = R2()
        lns2 = _white_scales_events(best.x, groups, period, t0_ref)
        sig = float(np.median([g["sigma_point"] for g in groups]))
        extra = [float(np.log(0.3 * sig)), float(np.log(0.1))] if groups[0]["gp"] else []
        out2.x = np.concatenate([best.x, lns2, extra])
        out2.fun = -log_prob_events(out2.x, groups, period, t0_ref)
        return out2
    lns = []
    for i in range(n_noise(groups)):
        chi, n = 0.0, 0
        p = unpack(best.x, t0_ref)
        for g in groups:
            if g["noise_idx"] != i:
                continue
            m = ellc_lc(g["t"], p, period, g["t_exp"], g["n_int"], g.get("cycle", 0.0))
            w = 1.0 / g["e"] ** 2
            norm = float(np.sum(w * g["y"] * m) / np.sum(w * m * m))
            chi += float(np.sum(((g["y"] - norm * m) / g["e"]) ** 2))
            n += len(g["y"])
        lns.append(float(np.clip(0.5 * np.log(max(chi / max(n, 1), 1e-6)), -2.9, 2.9)))

    class R:
        pass
    out = R()
    out.x = np.concatenate([best.x, lns])
    out.fun = -log_prob(out.x, groups, period, t0_ref)
    return out


FIXED_IN_MCMC = ("dt0", "dP")   # timing nuisances: well determined and nearly independent of the shape


_LP = {}


def _lp_global(z):
    """Module-level log-probability so a fork-based process pool can call it (closures cannot be pickled)."""
    th = _LP["base"].copy()
    th[_LP["free"]] = z
    return _LP["fn"](th, _LP["groups"], _LP["period"], _LP["t0"])


def _tau(sampler, n):
    try:
        return float(np.max(sampler.get_autocorr_time(discard=n // 2, quiet=True)))
    except Exception:  # noqa: BLE001
        return None


def sample(x_best, groups, period, t0_ref, steps=1500, walkers=32, seed=7, until_converged=False, max_steps=6000, noise="v1"):
    """emcee with differential-evolution moves over the shape and noise parameters; the eclipse time and
    period correction stay at the least-squares values.

    until_converged: after the first `steps`, keep extending the same chain until the half kept after burn-in
    is at least 20 autocorrelation times long, or max_steps is reached. F26_PROCS > 1 evaluates walkers in a
    process pool (Linux/macOS fork); neither option changes the model or the likelihood."""
    import emcee
    fixed_idx = [PARAMS.index(n) for n in FIXED_IN_MCMC]
    free_idx = [i for i in range(len(x_best)) if i not in fixed_idx]
    base = np.array(x_best, float)
    prob_fn = log_prob_events if noise == "v2" else log_prob

    def lp(z):
        th = base.copy()
        th[free_idx] = z
        return prob_fn(th, groups, period, t0_ref)

    full_scale = np.array([1e-4, 1e-3, 1e-2, 1e-3, 1e-2, 1e-3, 1e-3, 1e-3, 1e-2, 1e-2, 1e-6] + [1e-2] * (len(x_best) - len(PARAMS)))
    scale = full_scale[free_idx]
    rng = np.random.default_rng(seed)
    z0 = base[free_idx]
    walkers = max(walkers, 2 * len(z0) + 2)       # emcee needs at least twice as many walkers as dimensions (v2 has one noise scale per sector)
    p0, tries = [], 0
    while len(p0) < walkers:
        tries += 1
        if tries > 200000:
            raise RuntimeError("could not initialise walkers around the best fit")
        trial = z0 + scale * rng.normal(size=len(z0))
        if np.isfinite(lp(trial)):
            p0.append(trial)
    moves = [(emcee.moves.DEMove(), 0.8), (emcee.moves.DESnookerMove(), 0.2)]
    _LP.update(base=base, free=free_idx, groups=groups, period=period, t0=t0_ref, fn=prob_fn)
    nproc = int(os.environ.get("F26_PROCS", "1") or 1)
    pool = None
    if nproc > 1 and sys.platform != "win32":
        import multiprocessing
        pool = multiprocessing.get_context("fork").Pool(nproc)
    try:
        sampler = emcee.EnsembleSampler(walkers, len(z0), _lp_global, moves=moves, pool=pool)
        sampler.run_mcmc(np.array(p0), steps, progress=False)
        n = steps
        tau = _tau(sampler, n)
        while until_converged and n < max_steps and (tau is None or n / 2 < 20 * tau):
            need = int(40 * tau) if tau else n + 1000
            extra = int(min(max_steps, max(need, n + 500)) - n)
            sampler.run_mcmc(None, extra, progress=False)
            n += extra
            tau = _tau(sampler, n)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    flat = sampler.get_chain(discard=n // 2, thin=5, flat=True)
    chain = np.tile(base, (len(flat), 1))
    chain[:, free_idx] = flat
    return chain, float(np.mean(sampler.acceptance_fraction)), tau, n


def derived(chain):
    rsum, k, cosi, J, fc, fs, l3 = (chain[:, PARAMS.index(n)] for n in ("rsum", "k", "cosi", "J", "fc", "fs", "l3"))
    r1 = rsum / (1 + k)
    r2 = rsum - r1
    e = fc ** 2 + fs ** 2
    w = np.degrees(np.arctan2(fs, fc)) % 360.0
    return {"r1": r1, "r2": r2, "rsum": rsum, "k": k, "incl": np.degrees(np.arccos(cosi)), "J": J, "l3": l3,
            "e": e, "omega_deg": w, "ecosw": e * np.cos(np.radians(w)), "esinw": e * np.sin(np.radians(w)),
            "light_ratio": k ** 2 * J}


def summarise(d):
    out = {}
    for n, v in d.items():
        q = np.percentile(v, [2.5, 16, 50, 84, 97.5])
        out[n] = {"median": float(q[2]), "lo": float(q[2] - q[1]), "hi": float(q[3] - q[2]), "p2.5": float(q[0]), "p97.5": float(q[4])}
    return out


def model_duration(theta, period):
    """Longer of the two total eclipse durations implied by a parameter vector (days)."""
    p = dict(zip(PARAMS, theta[:len(PARAMS)]))
    e = p["fc"] ** 2 + p["fs"] ** 2
    w = np.arctan2(p["fs"], p["fc"])
    si = np.sqrt(max(1.0 - p["cosi"] ** 2, 1e-9))
    out = 0.0
    for sign in (1.0, -1.0):                        # primary, secondary
        rho = (1 - e * e) / (1 + sign * e * np.sin(w))
        b = rho * p["cosi"]
        x = max(p["rsum"] ** 2 - b * b, 0.0)
        arg = min(np.sqrt(x) / (rho * si), 1.0)
        out = max(out, period / np.pi * np.arcsin(arg) * rho ** 2 / np.sqrt(1 - e * e))
    return float(out)


def fit_star(t, f, sector, period, t0, duration, ecosw, depth_ratio, steps=1500, until_converged=False, max_steps=6000, noise=None, gp=True):
    """Fit, then re-detrend with the duration the model implies (a short catalogue duration would
    otherwise let the detrending eat the eclipse wings), and fit again before sampling.

    noise "v1" (default): eclipses divided by their own baseline, folded in phase, white noise per cadence.
    noise "v2": events kept separate, baselines integrated out, white noise per sector plus Matern-3/2 red noise
    (gp=False drops the red-noise term, for tests)."""
    noise = noise or NOISE_DEFAULT
    if noise not in ("v1", "v2"):
        raise ValueError("noise must be 'v1' or 'v2', got %r" % (noise,))
    v2 = noise == "v2"
    sec_phase = (0.5 + 2.0 * ecosw / np.pi) % 1.0
    t1 = time.time()
    best, groups, dur_used = None, None, duration
    x_prev = None
    for _ in range(3):
        if v2:
            events = cut_events(t, f, sector, period, t0, dur_used, sec_phase)
            if len(events) < 4:
                return {"status": "TOO_FEW_ECLIPSES_WITH_BASELINE"}
            groups = event_groups(events, dur_used, gp=gp)
            if not groups or sum(len(g["y"]) for g in groups) < 50:
                return {"status": "NO_DATA"}
        else:
            td, fd, sd = detrend_local(t, f, period, t0, dur_used, sec_phase, sector)
            if len(td) < 50:
                return {"status": "TOO_FEW_ECLIPSES_WITH_BASELINE"}
            groups = bin_groups(td, fd, sd, period, t0, dur_used, sec_phase)
            if not groups:
                return {"status": "NO_DATA"}
        if v2:
            if x_prev is None:                                     # global search on the cheap folded data first
                td, fd, sd = detrend_local(t, f, period, t0, dur_used, sec_phase, sector)
                g1 = bin_groups(td, fd, sd, period, t0, dur_used, sec_phase) if len(td) >= 50 else []
                b1 = optimise(g1, period, t0, dur_used, ecosw, depth_ratio, noise="v1") if g1 else None
                if b1 is None or not np.isfinite(b1.fun):
                    return {"status": "OPTIMISER_FAILED"}
                x_prev = b1.x[:len(PARAMS)]
            best = optimise(groups, period, t0, dur_used, ecosw, depth_ratio, noise="v2", x_init=[x_prev])
            if best is not None:
                x_prev = best.x[:len(PARAMS)]
        else:
            best = optimise(groups, period, t0, dur_used, ecosw, depth_ratio, noise=noise)
        if best is None or not np.isfinite(best.fun):
            return {"status": "OPTIMISER_FAILED"}
        p = dict(zip(PARAMS, best.x[:len(PARAMS)]))
        ecw = (p["fc"] ** 2 + p["fs"] ** 2) * np.cos(np.arctan2(p["fs"], p["fc"]))
        sec_phase = (0.5 + 2.0 * ecw / np.pi) % 1.0
        d_model = model_duration(best.x, period)
        if d_model <= 1.1 * dur_used:
            break
        dur_used = 1.15 * d_model
    chain, acc, tau, steps = sample(best.x, groups, period, t0, steps=steps, until_converged=until_converged, max_steps=max_steps, noise=noise)
    if v2:
        ll, chi = _log_like_events(best.x, groups, period, t0, return_chi=True)
    else:
        ll, chi = log_like(best.x, groups, period, t0, return_chi=True)
    n_bins = int(sum(len(g["y"]) for g in groups))
    summ = summarise(derived(chain))
    n_scale = groups[0]["n_white"] if v2 else len(best.x) - len(PARAMS)
    flags = []
    if summ["rsum"]["median"] > ROCHE_WARN_RSUM:
        flags.append("rsum above %.2f: spherical stars are a poor approximation" % ROCHE_WARN_RSUM)
    # v1: the scales at the least-squares optimum. v2: the posterior medians, because the least-squares start is white-noise
    # only and the red-noise term is meant to absorb what that start cannot
    scales = (np.exp(np.median(chain[:, len(PARAMS):len(PARAMS) + n_scale], axis=0)) if v2
              else np.exp(best.x[len(PARAMS):len(PARAMS) + n_scale]))
    if max(scales) > 5.0:
        flags.append("poor fit: residuals need more than 5 times the measured noise")
    converged = bool(tau is not None and steps / 2 >= 20 * tau)
    if not converged:
        flags.append("chain shorter than 20 autocorrelation times (tau=%s steps): uncertainties are indicative" % ("%.0f" % tau if tau else "n/a"))
    if summ["l3"]["median"] > 0.3:
        flags.append("large third light: inclination and radii are degenerate with it")
    best_p = dict(zip(PARAMS, best.x[:len(PARAMS)]))
    out = {"status": "OK", "noise_model": noise, "period_input_days": float(period), "period_days": float(period + best_p["dP"]),
           "t0_btjd": float(t0 + best_p["dt0"]),
           "duration_input_days": float(duration), "duration_used_days": float(dur_used),
           "n_bins": n_bins, "groups": [{"cadence_min": g["cadence_min"], "n_bins": int(len(g["y"]))} for g in groups],
           "chi2_best": float(chi), "noise_scale": [float(x_) for x_ in scales],
           "acceptance": acc, "autocorr_steps": tau, "steps": steps, "converged": converged, "seconds": round(time.time() - t1, 1),
           "params": summ, "flags": flags,
           "model": {"limb_darkening": "quadratic, u1 fitted per star with prior %.2f+-%.2f, u2=%.2f" % (U1_PRIOR[0], U1_PRIOR[1], U2_FIXED),
                     "detrending": ("quadratic per eclipse event, integrated out of the likelihood (flat prior)" if v2 else "quadratic per eclipse, fitted outside the eclipse"),
                     "outliers": "points beyond %.0f MAD of their phase neighbourhood dropped" % CLIP_MAD,
                     "shapes": "sphere", "period": "pipeline value plus a fitted correction",
                     "third_light": "half-normal prior, width %.2f" % L3_PRIOR_SIGMA}}
    if v2:
        out["model"]["noise"] = ("per-sector white-noise scale%s" % (" plus Matern-3/2 red noise per event" if gp else ""))
        if gp:
            lna = chain[:, len(PARAMS) + n_scale]
            lnrho = chain[:, len(PARAMS) + n_scale + 1]
            out["red_noise"] = {"amplitude_median": float(np.exp(np.median(lna))), "amplitude_p84": float(np.exp(np.percentile(lna, 84))),
                                "timescale_days_median": float(np.exp(np.median(lnrho))), "events": int(sum(len(g["events"]) for g in groups))}
    return out


def load_star(root, tic, cache_dir=None):
    cache = Path(cache_dir) if cache_dir else root / "data" / "processed" / "f13_lc_cache"
    z = np.load(cache / ("TIC%d.npz" % tic))
    t, f, s = z["t"].astype(float), z["f"].astype(float), z["sector"]
    ok = np.isfinite(t) & np.isfinite(f)
    return t[ok], f[ok], s[ok]


def validate(root, steps, cadence_min=2, noise=None):
    import f13_ephemeris as f13
    cache = root / "data" / "processed" / "f13_lc_cache_validation"
    cache.mkdir(parents=True, exist_ok=True)
    lcs = f13.load_or_fetch_lightcurves(AI_PHE["tic"], "SPOC", lambda *_: None, lc_dir=cache)
    t = np.concatenate([np.asarray(lc.time.value, float) for _, lc in lcs])
    f = np.concatenate([np.asarray(lc.flux.value, float) for _, lc in lcs])
    s = np.concatenate([np.full(len(lc), sec) for sec, lc in lcs])
    keep = np.isfinite(t) & np.isfinite(f)          # every sector; eclipses without a two-sided baseline are dropped
    t, f, s = t[keep], f[keep], s[keep]
    if cadence_min > 2:
        # average the 2-minute data into blocks, as a full-frame-image light curve would be
        blk = np.floor((t - t.min()) / (cadence_min / 1440.0)).astype(np.int64)
        df = pd.DataFrame({"b": blk, "t": t, "f": f, "s": s}).groupby("b").agg(t=("t", "mean"), f=("f", "mean"), s=("s", "first"), n=("t", "size"))
        df = df[df["n"] >= 0.8 * cadence_min / 2.0]
        # regular grid times so the cadence detector sees the long cadence
        t, f, s = df["t"].to_numpy(), df["f"].to_numpy(), df["s"].to_numpy()
    res = fit_star(t, f, s, AI_PHE["period"], AI_PHE["t0_btjd"], AI_PHE["duration"],
                   AI_PHE["truth"]["ecosw"], 1.0, steps=steps, noise=noise)
    truth, tol = AI_PHE["truth"], AI_PHE["pass"]
    if res["status"] != "OK":
        return {"star": "AI Phe", "status": res["status"]}
    p = res["params"]
    checks = {
        "e": abs(p["e"]["median"] - truth["e"]) <= tol["e"],
        "esinw": abs(p["esinw"]["median"] - truth["esinw"]) <= tol["esinw"],
        "r1": abs(p["r1"]["median"] / truth["r1"] - 1) <= tol["r_frac"],
        "r2": abs(p["r2"]["median"] / truth["r2"] - 1) <= tol["r_frac"],
        "incl": abs(p["incl"]["median"] - truth["incl"]) <= tol["incl"],
    }
    return {"star": "AI Phe (TIC 102069549)", "reference": "Maxted et al. 2020, MNRAS 498, 332", "noise_model": res.get("noise_model", "v1"),
            "cadence_min": cadence_min, "sectors": sorted(int(x) for x in np.unique(s)), "truth": truth, "tolerance": tol,
            "fit": {k: p[k] for k in ("e", "esinw", "ecosw", "r1", "r2", "incl", "l3", "J")},
            "checks": checks, "passed": bool(all(checks.values())), "run": {k: res[k] for k in ("chi2_best", "acceptance", "autocorr_steps", "seconds", "flags")}}


def targets(root):
    """Stars worth a physical model: eccentric candidates, the period-change candidate, and stars with
    archival velocities that can turn the model into masses (a Gaia SB1 orbit at the eclipse period, or
    an APOGEE orbit with at least three visits)."""
    ecc = json.loads((root / "data" / "processed" / "f22_eccentricity.json").read_text(encoding="utf-8"))["stars"]
    etv_p = root / "data" / "processed" / "f23_etv.json"
    out = {int(t): s for t, s in ecc.items() if s["verdict"] == "ECCENTRIC"}
    if etv_p.exists():
        for t, s in json.loads(etv_p.read_text(encoding="utf-8"))["stars"].items():
            if s["verdict"] == "PERIOD_CHANGE_SMOOTH":
                out.setdefault(int(t), ecc.get(t, {}))
    phys_p = root / "data" / "processed" / "f28_physical.json"
    if phys_p.exists():
        for t, s in json.loads(phys_p.read_text(encoding="utf-8"))["stars"].items():
            go = s.get("gaia_orbit") or {}
            ap = s.get("apogee") or {}
            if (go.get("same_period") and go.get("gaia_k1_kms")) or (ap.get("n", 0) >= 3 and ap.get("k1_kms", 0) > 3 * ap.get("k1_sigma_kms", 1e9)):
                out.setdefault(int(t), ecc.get(t, {}))
    return out


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    steps = int(args[args.index("--steps") + 1]) if "--steps" in args else 1500
    conv = "--converge" in args
    max_steps = int(args[args.index("--max-steps") + 1]) if "--max-steps" in args else 6000
    lc_dir = args[args.index("--lc-dir") + 1] if "--lc-dir" in args else None
    noise = args[args.index("--noise") + 1] if "--noise" in args else None
    if "--validate" in args:
        v = [validate(root, steps, 2, noise), validate(root, steps, 30, noise)]
        (root / "data" / "processed" / ("f26_validation%s.json" % ("_" + noise if noise and noise != "v1" else ""))).write_text(json.dumps(v, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(v, indent=1))
        return
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    sky = {int(r["tic"]): r for r in json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    tg = targets(root)
    if "--tics" in args:
        want = {int(x) for x in args[args.index("--tics") + 1].split(",")}
        tg = {t: s for t, s in tg.items() if t in want}
    out_p = Path(args[args.index("--out") + 1]).resolve() if "--out" in args else root / "data" / "processed" / "f26_ebfit.json"
    res = json.loads(out_p.read_text(encoding="utf-8"))["stars"] if out_p.exists() else {}
    for tic, s in sorted(tg.items()):
        v = vet.loc[tic]
        period, t0, dur = float(sky[tic]["period_days"]), float(v["bls_t0"]), float(v["bls_duration"])
        ecosw = float(s.get("ecosw") or 0.0)
        pd_ = float(v["bls_depth"]) if np.isfinite(v["bls_depth"]) else 0.1
        sd_ = float(s.get("secondary_depth") or 0.3 * pd_)
        try:
            t, f, sec = load_star(root, tic, lc_dir)
            r = fit_star(t, f, sec, period, t0, dur, ecosw, sd_ / max(pd_, 1e-4), steps=steps, until_converged=conv, max_steps=max_steps, noise=noise)
        except Exception as e:  # noqa: BLE001 - visible, never silent
            r = {"status": "ERROR", "error": repr(e)}
        res[str(tic)] = r
        print("TIC %d: %s %s" % (tic, r["status"], "" if r["status"] != "OK" else
              "e=%.3f(+%.3f/-%.3f) i=%.2f r1=%.4f r2=%.4f l3=%.2f %s" % (
                  r["params"]["e"]["median"], r["params"]["e"]["hi"], r["params"]["e"]["lo"], r["params"]["incl"]["median"],
                  r["params"]["r1"]["median"], r["params"]["r2"]["median"], r["params"]["l3"]["median"], "; ".join(r["flags"]))), flush=True)
        out_p.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "stars": res}, indent=1) + "\n",
                         encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
