import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Orbital eccentricity from the position of the secondary eclipse.
#
# In a circular orbit the secondary eclipse sits exactly halfway between primaries
# (phase 0.5). If it is displaced, the orbit is eccentric, and to first order
#       e cos(omega) = (pi / 2) * (phase_secondary - 0.5)
# which is a lower limit on the eccentricity itself (|e cos omega| <= e). This is a
# physical measurement of the system, not a detection statistic, and it needs nothing
# but the light curve.
#
# Two traps are handled explicitly:
#   * The pipeline period may be HALF the true one when the two eclipses look alike.
#     Then the "secondary" hides inside the primary fold. So every star is examined at
#     the pipeline period P and at 2P; at 2P an eccentric orbit shows the second eclipse
#     away from 0.5.
#   * Starspots and pulsations make false dips. A displaced secondary is accepted only if
#     it appears at the same phase in two independent halves of the data (alternating
#     sectors or alternating orbits), each on its own.
#
# What this does NOT show: that the eclipses are on the target rather than a blended
# neighbour (that is the job of the pixel test, ZTF and Gaia), or the eccentricity itself
# (only its projection e cos omega).

N_BINS_PER_DURATION = 4.0
MIN_SECONDARY_SNR = 7.0
MIN_HALF_SNR = 4.0
MIN_OFFSET_PHASE = 0.01           # 1% of the orbit; smaller offsets are within systematic reach
SEARCH = (0.15, 0.85)


def fold_phase(t, period, t0):
    return ((t - t0) / period + 0.5) % 1.0 - 0.5          # -0.5..0.5, primary at 0


def local_baseline(ph, f, centre, half, pad=3.0):
    """Median flux in the two shoulders next to a box, so slow variation does not fake a dip."""
    d = np.abs(((ph - centre + 0.5) % 1.0) - 0.5)
    m = (d > 1.2 * half) & (d < pad * half)
    return np.median(f[m]) if m.sum() >= 10 else np.nan, m.sum()


def scan_secondary(t, f, period, t0, duration, search=SEARCH):
    """Box scan for the deepest dip away from the primary. Returns dict with phase (0..1), depth,
    snr, n_in, or None when the data do not allow it."""
    ph = fold_phase(t, period, t0) % 1.0                    # 0..1 so the scan range is contiguous
    half = 0.5 * duration / period
    if half <= 0 or half > 0.1:
        return None
    step = 2 * half / N_BINS_PER_DURATION
    best = None
    scatter = 1.4826 * np.median(np.abs(f - np.median(f)))
    for c in np.arange(search[0], search[1], step):
        d = np.abs(ph - c)
        inn = d <= half
        if inn.sum() < 10:
            continue
        base, nb = local_baseline(ph, f, c, half)
        if not np.isfinite(base):
            continue
        depth = base - np.median(f[inn])
        local = 1.4826 * np.median(np.abs(f[inn] - np.median(f[inn])))
        noise = max(local, 0.3 * scatter) * np.sqrt(1.0 / inn.sum() + 1.0 / nb) * 1.2533   # error of a median
        snr = depth / noise if noise > 0 else 0.0
        if best is None or snr > best["snr"]:
            best = {"phase": float(c), "depth": float(depth), "snr": float(snr), "n_in": int(inn.sum())}
    if best is None:
        return None
    # refine the centre: depth-weighted centroid of the dip
    d = np.abs(ph - best["phase"])
    m = d <= 1.5 * half
    base, _ = local_baseline(ph, f, best["phase"], half)
    w = np.clip(base - f[m], 0, None)
    if w.sum() > 0:
        best["phase"] = float(np.sum(ph[m] * w) / w.sum())
    return best


def ecosw(phase_secondary):
    return float(0.5 * np.pi * (phase_secondary - 0.5))


def split_halves(t, period, t0, sector=None):
    """Two independent halves: alternating sectors when there are at least two, else alternating orbits."""
    if sector is not None and len(np.unique(sector)) >= 2:
        order = {s: i for i, s in enumerate(np.unique(sector))}
        idx = np.array([order[s] for s in sector])
        return idx % 2 == 0, "alternating sectors"
    cyc = np.floor((t - t0) / period + 0.5).astype(int)
    return cyc % 2 == 0, "alternating orbits"


def other_dips(t, f, period, t0, duration, sec_phase):
    """Deepest dip away from BOTH the primary and the claimed secondary. A third dip means the
    pipeline period is a multiple of the true one and the 'secondary' is only one of several."""
    ph = fold_phase(t, period, t0) % 1.0
    half = 0.5 * duration / period
    step = 2 * half / N_BINS_PER_DURATION
    scatter = 1.4826 * np.median(np.abs(f - np.median(f)))
    best = None
    for c in np.arange(0.03, 0.97, step):
        if min(c, 1.0 - c) < 3 * half or abs(c - sec_phase) < 3 * half:
            continue
        inn = np.abs(ph - c) <= half
        if inn.sum() < 10:
            continue
        base, nb = local_baseline(ph, f, c, half)
        if not np.isfinite(base):
            continue
        local = 1.4826 * np.median(np.abs(f[inn] - np.median(f[inn])))
        noise = max(local, 0.3 * scatter) * np.sqrt(1.0 / inn.sum() + 1.0 / nb) * 1.2533
        snr = (base - np.median(f[inn])) / noise if noise > 0 else 0.0
        if best is None or snr > best["snr"]:
            best = {"phase": float(c), "depth": float(base - np.median(f[inn])), "snr": float(snr)}
    return best


def fast_periodicity(t, f, period, t0, duration, sec_phase, sec_depth):
    """Periodic signal much shorter than the orbit, measured with both eclipses masked. A star that
    pulsates or rotates 3 or more times per 'orbit' folds into fake dips at arbitrary phases."""
    from astropy.timeseries import LombScargle
    ph = fold_phase(t, period, t0) % 1.0
    half = 0.5 * duration / period
    keep = (np.minimum(ph, 1.0 - ph) > 2 * half) & (np.abs(ph - sec_phase) > 2 * half)
    if keep.sum() < 200:
        return None
    tt, ff = t[keep], f[keep]
    if len(tt) > 20000:
        sel = np.linspace(0, len(tt) - 1, 20000).astype(int)
        tt, ff = tt[sel], ff[sel]
    ls = LombScargle(tt, ff)
    freq, power = ls.autopower(minimum_frequency=2.5 / period, maximum_frequency=24.0, samples_per_peak=5)
    if len(freq) == 0:
        return None
    k = int(np.argmax(power))
    amp = float(np.sqrt(power[k]) * np.std(ff) * np.sqrt(2.0))
    return {"period_days": float(1.0 / freq[k]), "amplitude": amp, "fap": float(ls.false_alarm_probability(power[k])),
            "amplitude_over_secondary_depth": float(amp / sec_depth) if sec_depth > 0 else None}


def assess(t, f, period, t0, duration, sector=None):
    """Secondary-eclipse position at the pipeline period. (A scan at twice the period is NOT done
    here: at 2P the other primary always sits at phase 0.5 and would be mistaken for a secondary.
    The half-period case is handled from the eclipse times instead, see alternation().)"""
    out = {"verdict": "NO_SECONDARY", "ecosw": None}
    full = scan_secondary(t, f, period, t0, duration)
    if full is None:
        out["verdict"] = "NOT_TESTABLE"
        return out
    a, how = split_halves(t, period, t0, sector)
    h1 = scan_secondary(t[a], f[a], period, t0, duration) if a.sum() > 200 else None
    h2 = scan_secondary(t[~a], f[~a], period, t0, duration) if (~a).sum() > 200 else None
    out.update({"secondary": full, "half_a": h1, "half_b": h2, "halves": how})
    if full["snr"] < MIN_SECONDARY_SNR:
        return out
    tol = max(1.5 * duration / period, 0.01)
    if h1 is None or h2 is None or min(h1["snr"], h2["snr"]) < MIN_HALF_SNR or \
            abs(h1["phase"] - full["phase"]) > tol or abs(h2["phase"] - full["phase"]) > tol:
        out["verdict"] = "SECONDARY_NOT_REPRODUCED"
        return out
    if abs(h1["phase"] - h2["phase"]) > 0.5 * duration / period:
        out["verdict"] = "SECONDARY_NOT_REPRODUCED"
        return out
    sig = float(max(abs(h1["phase"] - h2["phase"]) / 2.0, 0.25 * duration / period / max(full["snr"], 1.0)))
    off = full["phase"] - 0.5
    out.update({"secondary_phase": full["phase"], "secondary_phase_sigma": sig, "secondary_depth": full["depth"],
                "secondary_snr": full["snr"], "ecosw": ecosw(full["phase"]), "ecosw_sigma": float(0.5 * np.pi * sig)})
    out["verdict"] = "ECCENTRIC" if abs(off) >= max(MIN_OFFSET_PHASE, 3 * sig) else "CIRCULAR_WITHIN_ERRORS"
    if out["verdict"] == "ECCENTRIC":
        extra = other_dips(t, f, period, t0, duration, full["phase"])
        fast = fast_periodicity(t, f, period, t0, duration, full["phase"], full["depth"])
        out["other_dip"], out["fast_signal"] = extra, fast
        if extra is not None and extra["snr"] >= MIN_SECONDARY_SNR and extra["depth"] >= 0.3 * full["depth"]:
            out["verdict"] = "PERIOD_MULTIPLE_SUSPECTED"
        elif fast is not None and fast["fap"] < 1e-3 and (fast["amplitude_over_secondary_depth"] or 0) >= 0.5:
            out["verdict"] = "FAST_VARIABLE"
    return out


def alternation(points, period, min_each=3):
    """Half-period case. If the true period is Q = 2P and the orbit is eccentric, the pipeline folds
    the primary and the secondary together, and the two alternate in time: odd and even eclipses
    have O-C offsets that differ by Q * delta, where the secondary sits at phase 0.5 + delta of Q.
    Returns delta, e cos(omega) and a robust significance from the eclipse times, or None."""
    ep = np.array([p["epoch"] for p in points], int)
    oc = np.array([p["oc_min"] for p in points], float)
    if len(oc) < 2 * min_each:
        return None
    ev, od = oc[ep % 2 == 0], oc[ep % 2 == 1]
    if len(ev) < min_each or len(od) < min_each:
        return None

    def loc(x):
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        return med, max(mad, 0.05) * 1.2533 / np.sqrt(len(x))

    m1, e1 = loc(ev)
    m2, e2 = loc(od)
    d_min = m1 - m2
    sig = float(np.hypot(e1, e2))
    q = 2.0 * period
    delta = d_min / 1440.0 / q
    return {"odd_even_time_offset_min": float(d_min), "offset_sigma_min": sig, "z": float(d_min / sig),
            "true_period_days": q, "delta_phase": float(delta), "ecosw": ecosw(0.5 + abs(delta)),
            "ecosw_sigma": float(0.5 * np.pi * sig / 1440.0 / q), "n_even": int(len(ev)), "n_odd": int(len(od))}


def detrend(t, f, period, t0, duration, sector):
    """Per-sector normalisation plus a running median that is long compared with the eclipse and
    is computed with the primary eclipse masked. Keeps eclipses, removes slow trends."""
    f = np.asarray(f, float).copy()
    out = np.full_like(f, np.nan)
    ph = np.abs(fold_phase(t, period, t0))
    inecl = ph < 0.75 * duration / period
    win_days = max(6.0 * duration, 0.75)
    for s in np.unique(sector):
        m = sector == s
        ts, fs = t[m], f[m] / np.nanmedian(f[m])
        ser = pd.Series(np.where(inecl[m], np.nan, fs), index=pd.to_timedelta(ts, unit="D"))
        base = ser.rolling(pd.Timedelta(days=win_days), center=True, min_periods=10).median().interpolate(limit_direction="both").to_numpy()
        out[m] = fs / base
    ok = np.isfinite(out)
    return t[ok], out[ok], sector[ok]


def run(root, tics=None):
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    sky = {int(r["tic"]): r for r in json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    cache = root / "data" / "processed" / "f13_lc_cache"
    detail = root / "site" / "public" / "data" / "detail"
    stars = {}
    for tic in sorted(sky):
        if tics and tic not in tics:
            continue
        dp = detail / ("TIC%d.json" % tic)
        alt = None
        pfit = None
        if dp.exists():
            tm = json.loads(dp.read_text(encoding="utf-8")).get("timing") or {}
            pfit = tm.get("period_fit_days")
            alt = alternation(tm.get("points") or [], float(sky[tic]["period_days"]))
        p = cache / ("TIC%d.npz" % tic)
        if not p.exists() or tic not in vet.index:
            stars[str(tic)] = {"verdict": "NO_LIGHT_CURVE", "alternation": alt}
            continue
        z = np.load(p)
        v = vet.loc[tic]
        t, f, sec = z["t"].astype(float), z["f"].astype(float), z["sector"]
        ok = np.isfinite(t) & np.isfinite(f)
        t, f, sec = t[ok], f[ok], sec[ok]
        period, t0, dur = float(sky[tic]["period_days"]), float(v["bls_t0"]), float(v["bls_duration"])
        try:
            td, fd, sd = detrend(t, f, period, t0, dur, sec)
            res = assess(td, fd, period, t0, dur, sd)
        except Exception as e:  # noqa: BLE001 - one bad star must not stop the run, and must be visible
            res = {"verdict": "ERROR", "error": repr(e)}
        res["alternation"] = alt
        if res.get("verdict") == "ECCENTRIC":
            zp = root / "data" / "ztf_raw" / ("TIC%d.csv" % tic)
            res["ztf"], res["ztf_coverage"] = None, "no_file"
            if zp.exists():
                tz, fz = load_ztf(zp)
                res["ztf_coverage"] = "insufficient_points"
                try:
                    res["ztf"] = ztf_secondary(tz, fz, float(pfit or period), t0 + 2457000.0, dur, res["secondary_phase"])
                    if res["ztf"] is not None:
                        res["ztf_coverage"] = "measured"
                except Exception as e:  # noqa: BLE001 - visible, never silent
                    res["ztf"], res["ztf_coverage"] = {"error": repr(e)}, "error"
        res["n_points"] = int(len(t))
        res["n_sectors"] = int(len(np.unique(sec)))
        stars[str(tic)] = res
    counts = {}
    for s in stars.values():
        counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "counts": counts,
            "method": "Box scan for the secondary eclipse at the pipeline period (the half-period case is read from odd/even eclipse times); e cos(omega) = (pi/2)(phase - 0.5); "
                      "accepted only when two independent halves of the data each show the dip at the same phase; ECCENTRIC stars are re-measured in ZTF with calibrated random-phase controls.",
            "stars": stars}


def main():
    if len(sys.argv) < 2:
        print("Usage: py f22_eccentricity.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    rep = run(root)
    path = root / "data" / "processed" / "f22_eccentricity.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rep["counts"]))
    print("Written: %s" % path)




def load_ztf(path):
    """ZTF light curve as (hjd, relative flux), each filter normalised on its own median; clean points only."""
    d = pd.read_csv(path)
    if d.empty or "mag" not in d.columns:
        return None, None
    d["mag"] = pd.to_numeric(d["mag"], errors="coerce")
    d["hjd"] = pd.to_numeric(d["hjd"], errors="coerce")
    d["catflags"] = pd.to_numeric(d["catflags"], errors="coerce")
    d = d[(d["catflags"] == 0) & np.isfinite(d["mag"]) & np.isfinite(d["hjd"])]
    t, f = [], []
    for _, g in d.groupby("filtercode"):
        if len(g) < 20:
            continue
        fl = 10 ** (-0.4 * (g["mag"].to_numpy(float) - np.median(g["mag"])))
        t.append(g["hjd"].to_numpy(float))
        f.append(fl)
    if not t:
        return None, None
    return np.concatenate(t), np.concatenate(f)


def refine_period_primary(t_hjd, f, period, t0_bjd, duration, n_grid=401):
    """Re-fit the period from the PRIMARY eclipse in ZTF only (the secondary is never used, so the
    later secondary test stays independent). Searches the range over which the TESS period could
    have drifted by 0.1 in phase across the ZTF baseline; the best period maximises the in-eclipse
    dip of the folded primary."""
    n_cyc = max((t_hjd.max() - t0_bjd) / period, 1.0)
    dp = 0.1 * period / n_cyc
    half = 0.5 * duration / period
    best = (period, -np.inf)
    for P in np.linspace(period - dp, period + dp, n_grid):
        ph = fold_phase(t_hjd, P, t0_bjd)
        for c in np.linspace(-0.08, 0.08, 33):
            m = np.abs(((ph - c + 0.5) % 1.0) - 0.5) <= half
            if m.sum() < 5:
                continue
            base = np.median(f[~m])
            val = (base - np.median(f[m])) * np.sqrt(m.sum())
            if val > best[1]:
                best = (float(P), float(val))
    return best[0]


def ztf_secondary(t_hjd, f, period, t0_bjd, duration, tess_phase, n_controls=200, seed=3, refine=True):
    """Independent check of a TESS secondary-eclipse phase in ZTF photometry.

    The ZTF primary is located first (so an imprecise epoch cannot shift the result), then the
    secondary is measured RELATIVE to it. The detection is calibrated against boxes placed at
    random phases away from both eclipses, the same idea as the control periods of f17.
    Returns dict or None."""
    if t_hjd is None or len(t_hjd) < 50:
        return None
    if refine:
        period = refine_period_primary(t_hjd, f, period, t0_bjd, duration)
    ph = fold_phase(t_hjd, period, t0_bjd)
    half = 0.5 * duration / period
    # locate the primary within +-0.05 of the expected phase
    best = None
    for c in np.linspace(-0.05, 0.05, 101):
        m = np.abs(((ph - c + 0.5) % 1.0) - 0.5) <= half
        if m.sum() < 3:
            continue
        v = np.median(f[m])
        if best is None or v < best[1]:
            best = (c, v, int(m.sum()))
    if best is None:
        return None
    t0z = t0_bjd + best[0] * period
    sec = scan_secondary(t_hjd, f, period, t0z, duration)
    if sec is None:
        return None
    # chance: the same statistic for boxes at random phases away from both eclipses
    rng = np.random.default_rng(seed)
    ph2 = fold_phase(t_hjd, period, t0z) % 1.0
    scatter = 1.4826 * np.median(np.abs(f - np.median(f)))
    ctrl = []
    for c in rng.uniform(0.1, 0.9, n_controls * 3):
        if abs(c - tess_phase) < 4 * half:
            continue
        inn = np.abs(ph2 - c) <= half
        if inn.sum() < 3:
            continue
        base, nb = local_baseline(ph2, f, c, half)
        if not np.isfinite(base):
            continue
        local = 1.4826 * np.median(np.abs(f[inn] - np.median(f[inn])))
        noise = max(local, 0.3 * scatter) * np.sqrt(1.0 / inn.sum() + 1.0 / nb) * 1.2533
        ctrl.append((base - np.median(f[inn])) / noise if noise > 0 else 0.0)
        if len(ctrl) >= n_controls:
            break
    # the statistic AT the TESS phase, measured directly (not the scan maximum)
    inn = np.abs(ph2 - tess_phase) <= half
    at = None
    if inn.sum() >= 3:
        base, nb = local_baseline(ph2, f, tess_phase, half)
        local = 1.4826 * np.median(np.abs(f[inn] - np.median(f[inn])))
        noise = max(local, 0.3 * scatter) * np.sqrt(1.0 / inn.sum() + 1.0 / nb) * 1.2533
        at = float((base - np.median(f[inn])) / noise) if noise > 0 and np.isfinite(base) else None
    p = None if at is None or not ctrl else float((1 + np.sum(np.array(ctrl) >= at)) / (1 + len(ctrl)))
    agree = abs(sec["phase"] - tess_phase) <= max(1.5 * duration / period, 0.01)
    return {"period_used_days": float(period), "n_points": int(len(f)), "primary_shift_phase": float(best[0]), "scan_phase": sec["phase"], "scan_snr": sec["snr"],
            "snr_at_tess_phase": at, "n_in_at_tess_phase": int(inn.sum()), "p_value": p,
            "scan_agrees_with_tess": bool(agree),
            "confirmed": bool(p is not None and p <= 0.01 and agree)}


if __name__ == "__main__":
    main()
