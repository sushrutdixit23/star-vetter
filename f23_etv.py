import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import f22_eccentricity as f22

# Eclipse-timing variations over 7 years: TESS sector means plus ZTF seasons.
#
# A constant period gives eclipse times on a straight line. A third body orbiting the
# binary moves it towards and away from us, so the eclipses arrive early and late in turn
# (the light-travel-time effect); mass transfer or angular-momentum loss bends the line into
# a parabola. TESS alone covers a few sectors; ZTF adds an independent telescope, other
# years and a different pipeline, so a drift seen in BOTH is not an artefact of either.
#
# Per ZTF season the eclipse time is fitted with the star's own TESS fold as template
# (free depth scale and baseline, so the different band does not matter). Errors come from
# the chi-square curve, inflated by the reduced chi-square when that exceeds 1.
#
# Verdicts:
#   DRIFT_CONFIRMED   a straight line is rejected (p < 0.001) using TESS and ZTF together AND the
#                     ZTF seasons on their own reject the TESS-only line (they are not where a
#                     constant period from TESS says they should be)
#   DRIFT_TESS_ONLY   TESS rejects a line, ZTF cannot test it
#   CONSTANT          consistent with a constant period
#   NOT_TESTABLE      fewer than three timing groups in total
# Sector-level timing systematics of a few minutes exist (QLP: about 3 minutes), so a
# floor of 2 minutes is added in quadrature to every TESS group and 3 minutes to every ZTF season.

TESS_FLOOR_MIN = 2.0
ZTF_FLOOR_MIN = 3.0
MIN_IN_ECLIPSE = 6


def tess_groups(points, period):
    """Sector-level mean O-C (minutes) from the per-eclipse times, outliers clipped."""
    ep = np.array([p["epoch"] for p in points], float)
    oc = np.array([p["oc_min"] for p in points], float)
    if len(oc) == 0:
        return []
    tt = ep * period
    order = np.argsort(tt)
    tt, oc, ep = tt[order], oc[order], ep[order]
    cl = np.concatenate([[0], np.cumsum(np.diff(tt) > 12.0)])
    out = []
    for c in np.unique(cl):
        m = cl == c
        x = oc[m]
        if len(x) < 3:
            continue
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med)) + 1e-6
        k = np.abs(x - med) < 4 * mad
        if k.sum() < 3:
            continue
        err = x[k].std(ddof=1) / np.sqrt(k.sum())
        out.append({"source": "TESS", "epoch": float(ep[m][k].mean()), "oc_min": float(x[k].mean()),
                    "err_min": float(np.hypot(err, TESS_FLOOR_MIN)), "n": int(k.sum())})
    return out


def _season_fit(ts, fs, period, t0, tp, tf, shifts):
    """Chi-square of template + free scale + free offset for every trial shift (vectorised)."""
    ph = f22.fold_phase(ts, period, t0)[None, :] - shifts[:, None]
    x = np.interp(ph.ravel(), tp, tf, period=1.0).reshape(ph.shape) - 1.0
    n = fs.size
    sx, sy = x.sum(1), fs.sum()
    sxx, sxy = (x * x).sum(1), (x * fs[None, :]).sum(1)
    det = n * sxx - sx * sx
    det = np.where(np.abs(det) < 1e-15, np.nan, det)
    a = (n * sxy - sx * sy) / det
    b = (sy - a * sx) / n
    r = fs[None, :] - (a[:, None] * x + b[:, None])
    chi = (r * r).sum(1)
    return np.where(np.isfinite(chi), chi, np.inf)


def ztf_season_times(t, f, period, t0, template_phase, template_flux, half_width, n_boot=60, seed=5, min_dchi=25.0):
    """One eclipse time per ZTF observing season, relative to (period, t0), in minutes.
    The error is the bootstrap scatter of the fitted shift (points resampled within the season),
    which captures sparse sampling and red noise better than a chi-square curve. A season is used
    only if the eclipse is detected in it (chi-square drop of at least min_dchi against no eclipse)."""
    out = []
    if t is None:
        return out
    rng = np.random.default_rng(seed)
    season = np.floor((t - 2458000.5 - 120.0) / 365.25).astype(int)      # seasons split in the summer gap
    tp = np.asarray(template_phase)
    tf = np.asarray(template_flux)
    shifts = np.linspace(-4 * half_width, 4 * half_width, 161)
    for s in np.unique(season):
        m = season == s
        ts, fs = t[m], f[m]
        if len(ts) < 30:
            continue
        chi = _season_fit(ts, fs, period, t0, tp, tf, shifts)
        i = int(np.argmin(chi))
        if i in (0, len(shifts) - 1):
            continue
        ph0 = f22.fold_phase(ts, period, t0) - shifts[i]
        n_in = int((np.abs(ph0) < half_width).sum())
        flat = ((fs - fs.mean()) ** 2).sum()
        s2 = chi[i] / max(len(ts) - 3, 1)
        if n_in < MIN_IN_ECLIPSE or (flat - chi[i]) / s2 < min_dchi:
            continue
        boots = []
        for _ in range(n_boot):
            k = rng.integers(0, len(ts), len(ts))
            cb = _season_fit(ts[k], fs[k], period, t0, tp, tf, shifts)
            boots.append(shifts[int(np.argmin(cb))])
        err = max(float(np.std(boots)), shifts[1] - shifts[0])
        epoch = float(np.round((np.median(ts) - t0) / period))
        out.append({"source": "ZTF", "season": int(2018 + s), "epoch": epoch,
                    "oc_min": float((shifts[i] * period + (epoch * period - epoch * period)) * 1440.0),
                    "err_min": float(np.hypot(err * period * 1440.0, ZTF_FLOOR_MIN)), "n": int(len(ts)), "n_in_eclipse": n_in})
    return out


def tess_sector_times(t, f, sector, period, t0, template_phase, template_flux, half_width, n_boot=40, seed=7):
    """One eclipse time per TESS sector, with exactly the same template fit as the ZTF seasons,
    so the two instruments share one zero point (the template's own centre)."""
    out = []
    rng = np.random.default_rng(seed)
    tp, tf = np.asarray(template_phase), np.asarray(template_flux)
    shifts = np.linspace(-4 * half_width, 4 * half_width, 161)
    for s in np.unique(sector):
        m = sector == s
        ts, fs = t[m], f[m]
        if len(ts) < 200:
            continue
        chi = _season_fit(ts, fs, period, t0, tp, tf, shifts)
        i = int(np.argmin(chi))
        if i in (0, len(shifts) - 1):
            continue
        ph0 = f22.fold_phase(ts, period, t0) - shifts[i]
        if (np.abs(ph0) < half_width).sum() < 3 * MIN_IN_ECLIPSE:
            continue
        boots = []
        for _ in range(n_boot):
            k = rng.integers(0, len(ts), len(ts))
            boots.append(shifts[int(np.argmin(_season_fit(ts[k], fs[k], period, t0, tp, tf, shifts)))])
        err = max(float(np.std(boots)), shifts[1] - shifts[0])
        epoch = float(np.round((np.median(ts) - t0) / period))
        out.append({"source": "TESS", "sector": int(s), "epoch": epoch, "oc_min": float(shifts[i] * period * 1440.0),
                    "err_min": float(np.hypot(err * period * 1440.0, TESS_FLOOR_MIN)), "n": int(len(ts))})
    return out


def fit_poly(E, y, s, deg):
    A = np.vstack([E ** k for k in range(deg + 1)]).T
    w = 1.0 / s
    co, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
    r = y - A @ co
    return co, float(((r / s) ** 2).sum()), r


def chi2_sf(x, k):
    from scipy.stats import chi2
    return float(chi2.sf(x, k))


def assess(groups):
    if len(groups) < 3:
        return {"verdict": "NOT_TESTABLE", "groups": groups}
    E = np.array([g["epoch"] for g in groups])
    y = np.array([g["oc_min"] for g in groups])
    s = np.array([g["err_min"] for g in groups])
    co1, c1, r1 = fit_poly(E, y, s, 1)
    p_line = chi2_sf(c1, len(E) - 2)
    res = {"groups": groups, "n_groups": len(groups), "chi2_line": c1, "dof_line": len(E) - 2, "p_line": p_line,
           "residual_range_min": float(np.ptp(r1))}
    if len(E) >= 4:
        co2, c2, _ = fit_poly(E, y, s, 2)
        res.update({"chi2_quad": c2, "dof_quad": len(E) - 3, "p_quad": chi2_sf(c2, len(E) - 3), "quad_coeff_min_per_cycle2": float(co2[2])})
    ist = np.array([g["source"] == "TESS" for g in groups])
    izt = ~ist
    res["n_tess"], res["n_ztf"] = int(ist.sum()), int(izt.sum())
    tess_rejects = None
    if ist.sum() >= 3:
        _, ct, _ = fit_poly(E[ist], y[ist], s[ist], 1)
        tess_rejects = chi2_sf(ct, int(ist.sum()) - 2) < 1e-3
    # do the ZTF seasons fall where the TESS-only straight line puts them?
    ztf_rejects = None
    if ist.sum() >= 2 and izt.sum() >= 2:
        A = np.vstack([np.ones(ist.sum()), E[ist]]).T
        w = 1.0 / s[ist]
        co, *_ = np.linalg.lstsq(A * w[:, None], y[ist] * w, rcond=None)
        cov = np.linalg.inv((A * w[:, None]).T @ (A * w[:, None]))
        Az = np.vstack([np.ones(izt.sum()), E[izt]]).T
        pred = Az @ co
        V = np.diag(s[izt] ** 2) + Az @ cov @ Az.T
        d = y[izt] - pred
        cz = float(d @ np.linalg.solve(V, d))
        res.update({"chi2_ztf_vs_tess_line": cz, "p_ztf_vs_tess_line": chi2_sf(cz, int(izt.sum()))})
        ztf_rejects = res["p_ztf_vs_tess_line"] < 1e-3
    res["tess_rejects_line"], res["ztf_rejects_tess_line"] = tess_rejects, ztf_rejects
    if p_line < 1e-3 and ztf_rejects:
        res["verdict"] = "DRIFT_CONFIRMED"
    elif p_line < 1e-3 and ztf_rejects is None:
        res["verdict"] = "DRIFT_TESS_ONLY"
    elif p_line < 1e-3:
        res["verdict"] = "DRIFT_UNCONFIRMED"
    else:
        res["verdict"] = "CONSTANT"
    return res


def tess_arrays(root, tic, P, t0, duration):
    lc = root / "data" / "processed" / "f13_lc_cache" / ("TIC%d.npz" % tic)
    if not lc.exists():
        return None
    z = np.load(lc)
    tt, ff, ss = z["t"].astype(float), z["f"].astype(float), z["sector"]
    ok = np.isfinite(tt) & np.isfinite(ff)
    td, fd, sd = f22.detrend(tt[ok], ff[ok], P, t0 - 2457000.0, duration, ss[ok])
    return td + 2457000.0, fd, sd


def calibrate(root, n_rep=3, seed=11):
    """False-drift rate of the whole procedure on synthetic constant-period stars: each star's own
    ZTF times, its own TESS template, its ZTF residuals shuffled within each season, and its TESS
    group errors. Returns the fraction flagged as a drift (should be about 0.1% at p < 0.001)."""
    d = root / "site" / "public" / "data"
    sky = {int(r["tic"]): r for r in json.loads((d / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    rng = np.random.default_rng(seed)
    flagged, total, per = 0, 0, []
    for tic in sorted(sky):
        dp = d / "detail" / ("TIC%d.json" % tic)
        zp = root / "data" / "ztf_raw" / ("TIC%d.csv" % tic)
        if not dp.exists() or not zp.exists() or tic not in vet.index:
            continue
        det = json.loads(dp.read_text(encoding="utf-8"))
        if not det.get("fold", {}).get("binned"):
            continue
        tm = det.get("timing") or {}
        P = float(tm.get("period_fit_days") or sky[tic]["period_days"])
        t0 = float(vet.loc[tic, "bls_t0"]) + 2457000.0
        tz, fz = f22.load_ztf(zp)
        if tz is None:
            continue
        b = np.array(det["fold"]["binned"], float)
        half = 0.75 * float(vet.loc[tic, "bls_duration"]) / P
        real = ztf_season_times(tz, fz, P, t0, b[:, 0], b[:, 1], half, n_boot=20)
        if len(real) < 2:
            continue
        # synthetic: template at the constant ephemeris, real depth scale, shuffled residuals
        mod = np.interp(f22.fold_phase(tz, P, t0), b[:, 0], b[:, 1], period=1.0) - 1.0
        A = np.vstack([mod, np.ones_like(mod)]).T
        co, *_ = np.linalg.lstsq(A, fz, rcond=None)
        res = fz - A @ co
        ta = tess_arrays(root, tic, P, t0, float(vet.loc[tic, "bls_duration"]))
        if ta is None:
            continue
        tt_, ft_, st_ = ta
        modt = np.interp(f22.fold_phase(tt_, P, t0), b[:, 0], b[:, 1], period=1.0) - 1.0
        At = np.vstack([modt, np.ones_like(modt)]).T
        cot, *_ = np.linalg.lstsq(At, ft_, rcond=None)
        rest = ft_ - At @ cot
        for _ in range(n_rep):
            season = np.floor((tz - 2458000.5 - 120.0) / 365.25).astype(int)
            rs = res.copy()
            for s_ in np.unique(season):
                m = season == s_
                rs[m] = rng.permutation(res[m])
            fsyn = A @ co + rs
            rt = rest.copy()
            for s_ in np.unique(st_):
                m = st_ == s_
                rt[m] = rng.permutation(rest[m])
            g = tess_sector_times(tt_, At @ cot + rt, st_, P, t0, b[:, 0], b[:, 1], half, n_boot=20)
            g += ztf_season_times(tz, fsyn, P, t0, b[:, 0], b[:, 1], half, n_boot=20)
            a = assess(sorted(g, key=lambda x: x["epoch"]))
            total += 1
            hit = a["verdict"] in ("DRIFT_CONFIRMED", "DRIFT_TESS_ONLY", "DRIFT_UNCONFIRMED")
            flagged += hit
            per.append((tic, hit))
    return {"trials": total, "flagged": flagged, "rate": flagged / total if total else None,
            "stars_flagged": sorted({t for t, h in per if h})}


def run(root, tics=None):
    d = root / "site" / "public" / "data"
    sky = {int(r["tic"]): r for r in json.loads((d / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    stars = {}
    for tic in sorted(sky):
        if tics and tic not in tics:
            continue
        dp = d / "detail" / ("TIC%d.json" % tic)
        if not dp.exists() or tic not in vet.index:
            continue
        det = json.loads(dp.read_text(encoding="utf-8"))
        tm = det.get("timing") or {}
        P = float(tm.get("period_fit_days") or sky[tic]["period_days"])     # per-eclipse timing fit is the most precise period
        t0 = float(vet.loc[tic, "bls_t0"]) + 2457000.0
        groups = []
        b = np.array(det["fold"]["binned"], float) if det.get("fold", {}).get("binned") else None
        half = 0.75 * float(vet.loc[tic, "bls_duration"]) / P
        ta = tess_arrays(root, tic, P, t0, float(vet.loc[tic, "bls_duration"])) if b is not None else None
        if ta is not None:
            groups = tess_sector_times(ta[0], ta[1], ta[2], P, t0, b[:, 0], b[:, 1], half)
        zp = root / "data" / "ztf_raw" / ("TIC%d.csv" % tic)
        if zp.exists() and b is not None:
            tz, fz = f22.load_ztf(zp)
            # template epoch = TESS t0 at epoch 0 (oc relative to the same linear ephemeris as TESS points)
            groups += ztf_season_times(tz, fz, P, t0, b[:, 0], b[:, 1], half)
        groups.sort(key=lambda g: g["epoch"])
        stars[str(tic)] = assess(groups)
        stars[str(tic)]["period_days"] = P
    counts = {}
    for s in stars.values():
        counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "counts": counts,
            "floors_min": {"tess": TESS_FLOOR_MIN, "ztf": ZTF_FLOOR_MIN}, "stars": stars}


def main():
    root = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 2 and sys.argv[2] == "--calibrate":
        print(json.dumps(calibrate(root), indent=1))
        return
    rep = run(root)
    p = root / "data" / "processed" / "f23_etv.json"
    p.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rep["counts"]))
    print("Written: %s" % p)


if __name__ == "__main__":
    main()
