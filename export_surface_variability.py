"""Look for starspot and flare evidence in each candidate's full light curves.

Reads the cached full light curves (data/processed/f13_lc_cache/TIC*.npz, one
row per cadence: t, f, e, sector) and writes site/public/data/surface_variability.json.
The plate draws spots or flares ONLY where this file flags them.

Every star gets an explicit status for each test:
  detected      the evidence passed its gates
  none          the test could run and found nothing above the gates
  not_tested    the data could not support the test (too few sectors or
                points, eclipses could not be aligned, cadence too slow for
                flares). "not_tested" is never shown as "no spots/flares".

SPOTS (two independent tests, both on out-of-eclipse data per sector):
  A  rotation signal that is not the orbit: after removing each sector's
     orbital harmonics and a linear trend, the strongest Lomb-Scargle peak
     (0.3-10 d; orbital harmonics and the 13.7-day TESS orbit systematics
     excluded) must reach SNR >= SPOT_SNR in at least two orbit segments
     (each TESS sector is split at its mid-sector gap) at periods
     agreeing within SPOT_PERIOD_TOL, with amplitude >= SPOT_MIN_AMP.
  B  orbit-locked modulation that changes: the first two orbital harmonics
     are fitted per sector; if they differ between sectors by more than
     their (red-noise inflated) errors allow (chi2 p < SPOT_P) and by at
     least SPOT_MIN_CHANGE, something on the stars is evolving. A tide or
     reflection effect does not change from sector to sector.
FLARES (cadence <= FLARE_MAX_CADENCE_MIN only): detrend with a running median
  outside eclipses; a flare candidate is >= 3 consecutive points above
  3 sigma with a peak of at least 4 sigma. The same detector run on the
  NEGATIVE residuals counts false alarms (eclipses are masked, so real dips
  are not expected); a star is flagged only with >= FLARE_MIN flares and a
  false-alarm count of at most a fifth of them.

LIMITS (copied into the output): a flare may come from a neighbouring star in
the aperture; the data cannot say which of the two stars is spotted or
flaring; spot size is a rough estimate.

Usage:  python export_surface_variability.py <root>
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

SPOT_SNR = 8.0
SPOT_PERIOD_TOL = 0.05
SPOT_MIN_AMP = 0.002
SPOT_P = 1e-4
SPOT_MIN_CHANGE = 0.003
SPOT_PMIN_D, SPOT_PMAX_D = 0.3, 10.0
TESS_ORBIT_D = 13.7
MIN_CYCLES = 2.5
MIN_OOT_POINTS = 150
FLARE_MAX_CADENCE_MIN = 4.0
FLARE_MIN = 3
FLARE_SIGMA = 3.0
FLARE_PEAK_SIGMA = 4.0
FLARE_NCONSEC = 3
FLARE_FALSE_RATIO = 0.2
TREND_HOURS = 6.0


def _circ(d):
    return np.abs((d + 0.5) % 1.0 - 0.5)


def eclipse_mask(t, P, t0, dur, sec_phase=0.5):
    """True where a point is inside a primary or secondary eclipse window
    (1.0 x the eclipse duration, centred on each)."""
    ph = ((t - t0) / P) % 1.0
    half = dur / P  # window half-width = one duration (generous)
    return (_circ(ph) < half) | (_circ(ph - sec_phase) < half)


def align_sector(t, f, P, t0, dur):
    """Move t0 onto this sector's primary eclipse (the ephemeris may have
    drifted over years). Box-smoothed fold, minimum phase. Returns the new t0
    or None if the dip is not significant."""
    nb = 200
    ph = ((t - t0) / P) % 1.0
    idx = np.minimum((ph * nb).astype(int), nb - 1)
    cnt = np.bincount(idx, minlength=nb)
    sm = np.bincount(idx, weights=f, minlength=nb)
    if (cnt == 0).any():
        return None
    prof = sm / cnt
    w = max(3, int(round(dur / P * nb)))
    kern = np.ones(w) / w
    ext = np.concatenate([prof[-w:], prof, prof[:w]])
    box = np.convolve(ext, kern, mode="same")[w:-w]
    k = int(np.argmin(box))
    out = float(np.median(prof))
    depth = out - box[k]
    noise = 1.4826 * np.median(np.abs(prof - out)) or 1e-9
    if depth < 5 * noise / math.sqrt(w) * 1.0 or depth < 3 * noise:
        return None
    centre = (k + 0.5) / nb
    shift = centre if centre < 0.5 else centre - 1.0
    return t0 + shift * P


def _design(t, P, t0, tm):
    phi = 2 * math.pi * (t - t0) / P
    return np.column_stack([np.ones_like(t), (t - tm), np.cos(phi), np.sin(phi), np.cos(2 * phi), np.sin(2 * phi)])


def _beta(res, cad_per_bin):
    """Red-noise inflation: ratio of the scatter of K-point means to the
    white-noise expectation, averaged over a few K, floored at 1."""
    out = []
    for k in (cad_per_bin // 2 or 1, cad_per_bin, cad_per_bin * 2):
        k = max(2, int(k))
        n = len(res) // k
        if n < 6:
            continue
        b = res[: n * k].reshape(n, k).mean(1)
        out.append(b.std() / (res.std() / math.sqrt(k) + 1e-12))
    return max(1.0, float(np.mean(out))) if out else 1.0


def sector_harmonics(t, f, P, t0, dur, sec_phase):
    """Per-segment fit of orbital harmonics + linear trend on out-of-eclipse
    points. Returns dict or None."""
    oot = ~eclipse_mask(t, P, t0, dur, sec_phase)
    if oot.sum() < MIN_OOT_POINTS:
        return None
    tt, ff = t[oot], f[oot]
    if (tt.max() - tt.min()) / P < MIN_CYCLES:
        return None
    med = float(np.median(ff)) or 1.0
    ff = ff / med
    tm = float(tt.mean())
    X = _design(tt, P, t0, tm)
    beta, *_ = np.linalg.lstsq(X, ff, rcond=None)
    res = ff - X @ beta
    s = 1.4826 * np.median(np.abs(res - np.median(res))) or float(res.std())
    good = np.abs(res) < 4 * s
    if good.sum() < MIN_OOT_POINTS:
        return None
    X, ff, tt = X[good], ff[good], tt[good]
    beta, *_ = np.linalg.lstsq(X, ff, rcond=None)
    res = ff - X @ beta
    cad = float(np.median(np.diff(tt))) or 0.01
    kbin = int(max(5, 0.1 * P / cad))
    infl = _beta(res, kbin)
    sig = float(res.std())
    cov = (sig * infl) ** 2 * np.linalg.inv(X.T @ X)
    return {
        "h": beta[2:6] / beta[0], "cov": cov[2:6, 2:6] / beta[0] ** 2, "t": tt, "res": res,
        "sigma": sig, "beta": infl, "n": int(len(ff)), "cad": cad, "kbin": kbin,
    }


def spot_B(per_sector):
    """Do the orbital harmonics change between sectors? Returns dict."""
    if len(per_sector) < 2:
        return {"status": "not_tested", "reason": "fewer than two usable orbit segments"}
    H = np.array([p["h"] for p in per_sector])
    W = [np.linalg.inv(p["cov"]) for p in per_sector]
    Wsum = sum(W)
    mean = np.linalg.solve(Wsum, sum(w @ h for w, h in zip(W, H)))
    chi2 = float(sum((h - mean) @ w @ (h - mean) for w, h in zip(W, H)))
    dof = 4 * (len(per_sector) - 1)
    from scipy.stats import chi2 as chi2d
    p = float(chi2d.sf(chi2, dof))
    change = float(max(np.hypot(*(h[:2] - mean[:2])) + np.hypot(*(h[2:] - mean[2:])) for h in H))
    det = p < SPOT_P and change >= SPOT_MIN_CHANGE
    return {"status": "detected" if det else "none", "chi2": round(chi2, 1), "dof": dof, "p": p, "change": round(change, 5), "n_segments": len(per_sector)}


def _excluded_period(pd, P):
    for k in (1, 2, 3, 4):
        if abs(pd - P / k) < 0.10 * P / k or abs(pd - P * k) < 0.10 * P * k:
            return True
    for k in (1, 2, 3, 4):
        if abs(pd - TESS_ORBIT_D / k) < 0.05 * TESS_ORBIT_D / k:
            return True
    return False


def sector_rotation_peak(ps, P):
    """Strongest non-orbital periodic signal in one sector's residuals."""
    from astropy.timeseries import LombScargle
    t, y = ps["t"], ps["res"]
    if len(t) > 4000:  # bin to ~15 min: spot signals are slow
        step = int(len(t) // 4000) + 1
        n = len(t) // step
        t = t[: n * step].reshape(n, step).mean(1)
        y = y[: n * step].reshape(n, step).mean(1)
    span = t.max() - t.min()
    pmax = min(SPOT_PMAX_D, span / 2.0)
    if pmax <= SPOT_PMIN_D * 1.5:
        return None
    freq = np.linspace(1 / pmax, 1 / SPOT_PMIN_D, 4000)
    power = LombScargle(t, y - y.mean()).power(freq, normalization="psd")
    order = np.argsort(power)[::-1]
    for i in order[:400]:
        pd = 1.0 / freq[i]
        if _excluded_period(pd, P):
            continue
        w = 2 * math.pi * freq[i]
        A = np.column_stack([np.cos(w * t), np.sin(w * t)])
        c, *_ = np.linalg.lstsq(A, y - y.mean(), rcond=None)
        amp = float(math.hypot(*c))
        # noise AFTER removing the candidate signal, so the signal does not
        # inflate its own red-noise estimate
        y2 = y - y.mean() - A @ c
        step_b = max(2, int(ps["kbin"] // max(1, len(ps["t"]) // len(t))))
        err = float(y2.std()) * _beta(y2, step_b) * math.sqrt(2.0 / max(1, len(t)))
        return {"period": float(pd), "amp": amp, "snr": amp / err if err > 0 else 0.0}
    return None


def spot_A(per_sector, P):
    peaks = [pk for pk in (sector_rotation_peak(ps, P) for ps in per_sector) if pk]
    strong = [pk for pk in peaks if pk["snr"] >= SPOT_SNR and pk["amp"] >= SPOT_MIN_AMP]
    if len(per_sector) < 2:
        return {"status": "not_tested", "reason": "fewer than two usable orbit segments"}
    if len(strong) >= 2:
        med = float(np.median([pk["period"] for pk in strong]))
        agree = [pk for pk in strong if abs(pk["period"] - med) < SPOT_PERIOD_TOL * med]
        if len(agree) >= 2:
            return {
                "status": "detected", "period_days": round(float(np.median([pk["period"] for pk in agree])), 4),
                "amplitude": round(float(np.median([pk["amp"] for pk in agree])), 5),
                "n_segments": len(agree), "n_tested": len(per_sector),
            }
    return {"status": "none", "n_tested": len(per_sector)}


def find_flares(t, f, mask, cad_min, sign=1):
    """Run the flare detector on f (eclipse points masked). sign=-1 runs it
    on the inverted residuals (false-alarm count)."""
    from scipy.ndimage import median_filter
    keep = ~mask & np.isfinite(f)
    if keep.sum() < 300:
        return [], 0.0
    tt, ff = t[keep], f[keep]
    cad = cad_min / 1440.0
    win = int(max(5, TREND_HOURS / 24.0 / cad)) | 1
    out, exposure = [], 0.0
    # split at gaps > 0.5 d
    cuts = np.where(np.diff(tt) > 0.5)[0] + 1
    for seg_t, seg_f in zip(np.split(tt, cuts), np.split(ff, cuts)):
        if len(seg_t) < 3 * win:
            continue
        exposure += float(seg_t[-1] - seg_t[0])
        trend = median_filter(seg_f, size=win, mode="nearest")
        r = (seg_f - trend) * sign
        s = 1.4826 * np.median(np.abs(r - np.median(r))) or float(r.std())
        if s <= 0:
            continue
        z = r / s
        above = z > FLARE_SIGMA
        i = 0
        n = len(z)
        while i < n:
            if above[i]:
                j = i
                while j + 1 < n and above[j + 1] and seg_t[j + 1] - seg_t[j] < 2.5 * cad:
                    j += 1
                if j - i + 1 >= FLARE_NCONSEC and z[i : j + 1].max() >= FLARE_PEAK_SIGMA:
                    k = i + int(np.argmax(z[i : j + 1]))
                    base = float(trend[k]) or 1.0
                    out.append({"t": float(seg_t[k]), "amp": float(r[k] / base), "dur_min": float((seg_t[j] - seg_t[i]) * 1440 + cad_min), "sigma": float(z[k])})
                i = j + 1
            else:
                i += 1
    return out, exposure


def flare_summary(t, f, mask, cad_min):
    if cad_min > FLARE_MAX_CADENCE_MIN:
        return {"status": "not_tested", "reason": f"cadence {cad_min:.0f} min is too slow to resolve flares"}
    pos, exp_d = find_flares(t, f, mask, cad_min, +1)
    neg, _ = find_flares(t, f, mask, cad_min, -1)
    if exp_d <= 0:
        return {"status": "not_tested", "reason": "no usable continuous segments"}
    ok = len(pos) >= FLARE_MIN and len(neg) <= FLARE_FALSE_RATIO * len(pos)
    rec = {
        "status": "detected" if ok else "none",
        "n_candidates": len(pos), "n_false_alarms": len(neg), "exposure_days": round(exp_d, 2),
        "cadence_min": round(cad_min, 2),
    }
    if ok:
        rec["rate_per_day"] = round(len(pos) / exp_d, 4)
        big = max(pos, key=lambda x: x["amp"])
        keep = ~mask & (np.abs(t - big["t"]) < 0.125)
        snip = [[round(float((tt - big["t"]) * 24), 3), round(float(ff / np.median(f[keep])), 5)] for tt, ff in zip(t[keep], f[keep])]
        rec["biggest"] = {"t_btjd": round(big["t"], 4), "amp": round(big["amp"], 5), "dur_min": round(big["dur_min"], 1), "snippet": snip[:260]}
    return rec


def split_segments(ts, min_gap=0.5):
    """Split one sector's (sorted) times at its mid-sector gap, i.e. into the
    two ~13-day TESS orbits. Returns a list of index slices."""
    if len(ts) < 400:
        return [slice(0, len(ts))]
    span = ts[-1] - ts[0]
    gaps = np.diff(ts)
    mid = (ts[:-1] - ts[0]) / span
    cand = np.where((mid > 0.3) & (mid < 0.7) & (gaps > min_gap))[0]
    if len(cand) == 0:
        return [slice(0, len(ts))]
    k = int(cand[np.argmax(gaps[cand])]) + 1
    return [slice(0, k), slice(k, len(ts))]


def analyse_star(t, f, sector, P, t0, dur, sec_phase=0.5):
    out = {"spots_A": None, "spots_B": None, "flares": None, "segments_used": 0}
    per, mask_all = [], np.zeros(len(t), bool)
    cads = []
    for s in np.unique(sector):
        m = sector == s
        idx = np.where(m)[0]
        if len(idx) < 200:
            continue
        o = np.argsort(t[idx])
        idx = idx[o]
        cads.append(float(np.median(np.diff(t[idx]))) * 1440)
        med = np.median(f[idx]) or 1.0
        for sl in split_segments(t[idx]):
            gi = idx[sl]
            ts, fs = t[gi], f[gi] / med
            if len(ts) < 200:
                continue
            t0s = align_sector(ts, fs, P, t0, dur)
            if t0s is None:
                continue
            mask_all[gi] = eclipse_mask(ts, P, t0s, dur, sec_phase)
            ps = sector_harmonics(ts, fs, P, t0s, dur, sec_phase)
            if ps:
                per.append(ps)
    out["segments_used"] = len(per)
    out["spots_B"] = spot_B(per)
    out["spots_A"] = spot_A(per, P) if per else {"status": "not_tested", "reason": "no usable sector"}
    cad = min(cads) if cads else 99.0
    if cad <= FLARE_MAX_CADENCE_MIN:
        fin = np.isfinite(f)
        # per-sector normalise before the flare search
        fn = f.astype(float).copy()
        for s in np.unique(sector):
            m = sector == s
            fn[m] = fn[m] / (np.nanmedian(fn[m]) or 1.0)
        order = np.argsort(t)
        out["flares"] = flare_summary(t[order], fn[order], (mask_all | ~fin)[order], cad)
    else:
        out["flares"] = {"status": "not_tested", "reason": f"cadence {cad:.0f} min is too slow to resolve flares"}
    return out


def main(root):
    root = Path(root)
    lc_dir = root / "data/processed/f13_lc_cache"
    stars = {}
    for f in sorted((root / "site/public/data/detail").glob("TIC*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        tic = d["tic"]
        npz = lc_dir / f"TIC{tic}.npz"
        P, t0, dur = d.get("period_true_days"), d.get("t0_btjd"), d.get("duration_days")
        if not npz.exists() or not P or not dur:
            stars[str(tic)] = {"tested": False, "reason": "no full light curve in the cache"}
            continue
        z = np.load(npz)
        sec = d.get("secondary") or {}
        sp = sec.get("phase") if sec.get("detected") else 0.5
        rec = analyse_star(z["t"].astype(float), z["f"].astype(float), z["sector"], float(P), float(t0), float(dur), float(sp))
        rec["tested"] = True
        rec["teff_k"] = (d.get("catalog") or {}).get("teff_k")
        stars[str(tic)] = rec
    counts = {"stars": len(stars)}
    for key in ("spots_A", "spots_B", "flares"):
        for st in ("detected", "none", "not_tested"):
            counts[f"{key}_{st}"] = sum(1 for v in stars.values() if v.get(key) and v[key]["status"] == st)
    counts["no_cache"] = sum(1 for v in stars.values() if not v.get("tested"))
    # Negative control: stars hotter than the Kraft break (~6500 K) have no
    # outer convection zone, so spot-like changes there are not spots. A test
    # that fires about as often on them as on cool stars cannot be trusted.
    control = {}
    for name, sel in (("cool_lt_6500", lambda t: t is not None and t < 6500), ("hot_ge_6500", lambda t: t is not None and t >= 6500)):
        rows = [v for v in stars.values() if v.get("tested") and v["spots_B"]["status"] != "not_tested" and sel(v.get("teff_k"))]
        control[name] = {"tested": len(rows), "flagged": sum(v["spots_B"]["status"] == "detected" for v in rows)}
    doc = {
        "method": __doc__.split("Usage:")[0].strip(),
        "thresholds": {"spot_snr": SPOT_SNR, "spot_p": SPOT_P, "flare_sigma": FLARE_SIGMA, "flare_min": FLARE_MIN, "flare_false_ratio": FLARE_FALSE_RATIO},
        "counts": counts,
        "spots_B_control": control,
        "limits": [
            "A flare may come from a neighbouring star in the same pixels.",
            "The data cannot say which of the two stars is spotted or flaring.",
            "Test B (changing orbit-locked modulation) fires on stars too hot to have spots about as often as on cool stars (see spots_B_control), so it is reported but NOT used to draw spots.",
        ],
        "stars": stars,
    }
    path = root / "site/public/data/surface_variability.json"
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
