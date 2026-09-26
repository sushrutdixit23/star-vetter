import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Builds the extra data behind the dashboard home page, on top of what
# export_site_data.py already wrote. Read-only against the pipeline: it only
# reads the light-curve CSVs, the vetting CSV, the pixel-check maps, the
# orchestrator logs and the site's own exported candidate JSON.
#
# Writes:
#   site/public/data/detail/TIC{n}.json  per-candidate science panels
#   site/public/data/dashboard.json      sky positions, run history, activity
#
# Everything here is measured from the data, with the method stated next to
# it. Nothing is modelled beyond a binned median (no orbit fit), so there are
# no eccentricity / inclination / "confidence" numbers - those would need a
# full binary-star model this pipeline does not run.

ALIAS_Z = 3.0            # same odd/even gate export_site_data.py uses
CORE_FRAC = 0.35         # in-eclipse = |dt| < 0.35 x duration (same as diag_pixel)
OUT_GAP = 1.0            # out-of-eclipse = more than 1 duration from any eclipse
MAX_RAW = 2500
MAX_ALIAS_RAW = 1200
MAX_ZOOM_RAW = 700


def clean(x, nd=None):
    if x is None:
        return None
    if isinstance(x, (np.floating, np.integer)):
        x = x.item()
    if isinstance(x, float):
        if not np.isfinite(x):
            return None
        if nd is not None:
            return round(x, nd)
    return x


def subsample(n, k, seed=42):
    if n <= k:
        return np.arange(n)
    return np.sort(np.random.default_rng(seed).choice(n, size=k, replace=False))


def phase_of(t, P, t0):
    return ((t - t0 + P / 2) % P) / P - 0.5


def adaptive_edges(P, dur, centers=(0.0, 0.5)):
    """Coarse 1/100-phase bins, refined to duration/6 around each eclipse, so
    a narrow eclipse in a long period is still resolved by the median line."""
    w = dur / P
    coarse = np.linspace(-0.5, 0.5, 101)
    fine = []
    keep = np.ones(len(coarse), bool)
    for c in centers:
        c = ((c + 0.5) % 1.0) - 0.5
        lo, hi = c - 2 * w, c + 2 * w
        step = max(w / 6, 1e-5)
        fine.extend(np.arange(lo, hi + step / 2, step))
        keep &= ~((coarse > lo) & (coarse < hi))
    e = np.concatenate([coarse[keep], np.array(fine)])
    e = np.unique(np.clip(e, -0.5, 0.5))
    return e


def binned_median(phase, flux, edges, min_n=2):
    idx = np.digitize(phase, edges) - 1
    out = []
    for b in range(len(edges) - 1):
        sel = idx == b
        if sel.sum() >= min_n:
            out.append([round(float((edges[b] + edges[b + 1]) / 2), 6), round(float(np.median(flux[sel])), 6)])
    return out


def fold_block(t, f, P, t0, dur, k, seed, second_center=0.5):
    ph = phase_of(t, P, t0)
    edges = adaptive_edges(P, dur, centers=(0.0, second_center))
    binned = binned_median(ph, f, edges)
    pick = subsample(len(ph), k, seed)
    return ph, binned, [[round(float(ph[i]), 5), round(float(f[i]), 6)] for i in pick], pick


def eclipse_depth(t, f, P, t0, dur, center_phase):
    """Depth at a given phase: median of the eclipse core versus the median of
    out-of-eclipse points (more than one duration from both eclipses)."""
    dt = ((t - (t0 + center_phase * P) + P / 2) % P) - P / 2
    dt0 = ((t - t0 + P / 2) % P) - P / 2
    dts = ((t - (t0 + 0.5 * P) + P / 2) % P) - P / 2
    core = np.abs(dt) < CORE_FRAC * dur
    out = (np.abs(dt0) > OUT_GAP * dur) & (np.abs(dts) > OUT_GAP * dur) & (np.abs(dt) > OUT_GAP * dur)
    if core.sum() < 3 or out.sum() < 10:
        return None
    base = np.median(f[out])
    depth = (base - np.median(f[core])) / base
    mad = 1.4826 * np.median(np.abs(f[out] - base))
    err = mad * np.sqrt(np.pi / 2 / core.sum()) / base
    return {"depth": float(depth), "err": float(err), "sigma": float(depth / err) if err > 0 else None,
            "n_core": int(core.sum())}


def per_epoch(t, f, P, t0, dur, min_sigma=5.0):
    """Depth of every individual predicted eclipse that the data covers:
    median of its core against the median of its own local baseline (1-3
    durations either side). An eclipse is 'seen' at >= min_sigma. This is
    how a period that only fits some of the eclipses gets caught.

    The point-count floor below scales to this star's own cadence. A fixed
    "5 core points" is easy for a multi-hour eclipse at 30-minute cadence,
    but is close to unreachable for a ~3-hour eclipse at that same cadence
    no matter how clean the data is -- the window just does not contain 5
    samples. The floor is instead 60% of the most points a perfectly-timed
    window of that width could ever hold at this star's own cadence, still
    clamped to [3, 5] for the core and [6, 10] for the baseline so a "seen"
    epoch is never based on too few points to trust, and a well-sampled
    star keeps exactly the original 5/10 requirement."""
    diffs = np.diff(np.sort(t))
    fine = diffs[diffs < 0.05]
    if fine.size:
        cadence = float(np.median(fine))
    elif diffs.size:
        cadence = float(np.median(diffs))
    else:
        cadence = np.nan
    if np.isfinite(cadence) and cadence > 0:
        min_core = int(np.clip(round(0.6 * (2 * CORE_FRAC * dur) / cadence), 3, 5))
        min_local = int(np.clip(round(0.6 * (4 * dur) / cadence), 6, 10))
    else:
        min_core, min_local = 5, 10
    E_all = np.round((t - t0) / P).astype(int)
    rows = []
    for E in np.unique(E_all):
        tc = t0 + E * P
        dt = t - tc
        core = np.abs(dt) < CORE_FRAC * dur
        local = (np.abs(dt) > 1.0 * dur) & (np.abs(dt) < 3.0 * dur)
        if core.sum() < min_core or local.sum() < min_local:
            continue
        base = np.median(f[local])
        d = (base - np.median(f[core])) / base
        mad = 1.4826 * np.median(np.abs(f[local] - base))
        err = mad * np.sqrt(np.pi / 2 / core.sum()) / base if mad > 0 else np.nan
        sig = d / err if err and np.isfinite(err) and err > 0 else np.nan
        rows.append({"epoch": int(E), "t_mid": round(float(tc), 5), "depth": clean(float(d), 6),
                     "err": clean(float(err), 6), "sigma": clean(float(sig), 2),
                     "seen": bool(np.isfinite(sig) and sig >= min_sigma)})
    return rows


def pooled_from_epochs(rows):
    seen = [r for r in rows if r["seen"]]
    if not seen:
        return None
    d = np.array([r["depth"] for r in seen])
    e = np.array([r["err"] for r in seen])
    err = float(np.median(e) / np.sqrt(len(d)))
    if len(d) >= 3:
        err = max(err, float(np.std(d, ddof=1) / np.sqrt(len(d))))
    dep = float(np.median(d))
    return {"depth": dep, "err": err, "sigma": dep / err if err > 0 else None, "n_core": len(seen)}


def secondary_search(t, f, P, t0, dur):
    """Look for the deepest dip anywhere away from the primary (an eccentric
    orbit puts the secondary away from phase 0.5). Because many phases are
    tried, 'detected' needs 5 sigma rather than 3."""
    w = dur / P
    dt0 = ((t - t0 + P / 2) % P) - P / 2
    out_base = np.abs(dt0) > 1.0 * dur
    best = None
    for ph in np.arange(0.0, 1.0, max(w / 3, 0.002)):
        c = ((ph + 0.5) % 1.0) - 0.5
        if abs(c) < 2 * w:
            continue
        dt = ((t - (t0 + c * P) + P / 2) % P) - P / 2
        core = np.abs(dt) < CORE_FRAC * dur
        if core.sum() < 5:
            continue
        ref = out_base & (np.abs(dt) > 1.0 * dur)
        base = np.median(f[ref])
        dep = (base - np.median(f[core])) / base
        mad = 1.4826 * np.median(np.abs(f[ref] - base))
        err = mad * np.sqrt(np.pi / 2 / core.sum()) / base
        if err > 0 and (best is None or dep / err > best["sigma"]):
            best = {"depth": float(dep), "err": float(err), "sigma": float(dep / err),
                    "n_core": int(core.sum()), "phase": round(float(ph), 4)}
    if best is None:
        return None
    best["detected"] = bool(best["sigma"] >= 5.0)
    return best


def periodicity_check(t, f, P_true):
    """Independent cross-check with a Lomb-Scargle periodogram. A detached
    eclipsing binary has narrow dips and LOW sinusoid power; if the light
    curve is instead dominated by a smooth sinusoid, the box search can lock
    onto a multiple of that period, and the 'eclipses' are not eclipses."""
    try:
        from astropy.timeseries import LombScargle
    except ImportError:
        return None
    base = float(t.max() - t.min())
    if base <= 0:
        return None
    freq, power = LombScargle(t, f).autopower(minimum_frequency=2.0 / base,
                                              maximum_frequency=1 / 0.05, samples_per_peak=10)
    i = int(np.argmax(power))
    p_ls = float(1 / freq[i])
    pw = float(power[i])
    ratio = P_true / p_ls
    k = int(round(ratio))
    # strong sinusoid whose period is NOT the adopted period (or half of it)
    flag = pw >= 0.2 and not (k in (1, 2) and abs(ratio - k) < 0.02 * k)
    out = {"ls_period_days": round(p_ls, 6), "ls_power": round(pw, 3), "ratio": round(ratio, 3), "flag": bool(flag)}
    if flag:
        out["text"] = (f"The light curve is dominated by a smooth sinusoid with period {p_ls:.5f} d "
                       f"(Lomb-Scargle power {pw:.2f}); the adopted {P_true:.5f} d is {ratio:.2f} x that. "
                       f"The true period is more likely {p_ls:.5f} d (pulsation or spots) or "
                       f"{2 * p_ls:.5f} d (contact binary), and the 'eclipses' may not be eclipses.")
    return out


def zoom(t, f, P, tc, dur, seed):
    dt = ((t - tc + P / 2) % P) - P / 2
    sel = np.abs(dt) < 3 * dur
    x, y = dt[sel] * 24.0, f[sel]                 # hours from eclipse centre
    if len(x) == 0:
        return None
    step = dur * 24.0 / 10
    edges = np.arange(-3 * dur * 24.0, 3 * dur * 24.0 + step, step)
    bins = binned_median(x, y, edges)
    pick = subsample(len(x), MAX_ZOOM_RAW, seed)
    return {"raw": [[round(float(x[i]), 4), round(float(y[i]), 6)] for i in pick],
            "binned": [[round(a, 4), b] for a, b in bins],
            "half_width_h": round(3 * dur * 24.0, 4)}


def eclipse_timings(t, f, ferr, P, t0, dur, allowed=None):
    """O-C: each observed primary eclipse is timed by sliding the star's own
    mean eclipse profile (template) across it and minimising chi-square, with
    a free flux offset. A straight line T = T0 + P*E is then fitted and the
    residuals are the O-C values."""
    dt_all = ((t - t0 + P / 2) % P) - P / 2
    win = np.abs(dt_all) < 2 * dur
    if win.sum() < 20:
        return {"points": [], "n": 0, "note": "too few in-eclipse points to build a template"}
    step = dur / 12
    edges = np.arange(-2 * dur, 2 * dur + step, step)
    tb = binned_median(dt_all[win], f[win], edges, min_n=3)
    if len(tb) < 10:
        return {"points": [], "n": 0, "note": "too few in-eclipse points to build a template"}
    tx = np.array([b[0] for b in tb])
    ty = np.array([b[1] for b in tb])

    out = np.abs(dt_all) > 1.5 * dur
    scatter = 1.4826 * np.median(np.abs(f[out] - np.median(f[out]))) if out.sum() > 10 else np.nan
    epochs = np.round((t - t0) / P).astype(int)
    shifts = np.linspace(-0.5 * dur, 0.5 * dur, 201)
    pts = []
    for E in np.unique(epochs):
        if allowed is not None and int(E) not in allowed:
            continue
        tc = t0 + E * P
        dt = t - tc
        sel = np.abs(dt) < 2 * dur
        if sel.sum() < 10:
            continue
        d = dt[sel]
        if (np.abs(d) < 0.5 * dur).sum() < 5:
            continue
        if ((d > -dur) & (d < -0.2 * dur)).sum() < 2 or ((d > 0.2 * dur) & (d < dur)).sum() < 2:
            continue
        y = f[sel]
        s = ferr[sel] if ferr is not None else np.full(sel.sum(), scatter)
        s = np.where(np.isfinite(s) & (s > 0), s, scatter)
        if not np.all(np.isfinite(s)):
            continue
        w = 1 / s ** 2
        chi = []
        for sh in shifts:
            m = np.interp(d - sh, tx, ty, left=np.nan, right=np.nan)
            ok = np.isfinite(m)
            if ok.sum() < 8:
                chi.append(np.inf)
                continue
            r = y[ok] - m[ok]
            off = np.sum(w[ok] * r) / np.sum(w[ok])
            chi.append(np.sum(w[ok] * (r - off) ** 2))
        chi = np.array(chi)
        k = int(np.argmin(chi))
        if not np.isfinite(chi[k]) or k == 0 or k == len(shifts) - 1:
            continue
        # parabola through the minimum and its neighbours
        x3, y3 = shifts[k - 1:k + 2], chi[k - 1:k + 2]
        a, b, c = np.polyfit(x3, y3, 2)
        if a <= 0:
            continue
        best = -b / (2 * a)
        err = 1 / np.sqrt(a)                       # delta chi2 = 1
        dof = max(int(sel.sum()) - 2, 1)
        red = chi[k] / dof
        if red > 1:
            err *= np.sqrt(red)                    # inflate if the fit is poor
        pts.append((int(E), float(tc + best), float(err), int(sel.sum())))

    res = {"points": [], "n": len(pts)}
    if len(pts) < 3:
        res["note"] = (f"only {len(pts)} fully-covered eclipse(s) in the data - "
                       f"at least 3 are needed to test the period for timing changes")
        res["points"] = [{"epoch": e, "oc_min": None, "err_min": round(er * 1440, 3)} for e, _, er, _ in pts]
        return res
    E = np.array([p[0] for p in pts], float)
    T = np.array([p[1] for p in pts])
    S = np.array([p[2] for p in pts])
    W = 1 / S ** 2
    A = np.vstack([np.ones_like(E), E]).T
    cov = np.linalg.inv(A.T @ (A * W[:, None]))
    beta = cov @ (A.T @ (W * T))
    oc = T - A @ beta
    chi2 = float(np.sum(W * oc ** 2))
    dof = len(pts) - 2
    res.update({
        "points": [{"epoch": int(e), "oc_min": round(float(o) * 1440, 3), "err_min": round(float(s) * 1440, 3)}
                   for e, o, s in zip(E, oc, S)],
        "period_fit_days": float(beta[1]),
        "period_fit_err_days": float(np.sqrt(cov[1, 1])),
        "rms_min": round(float(np.sqrt(np.mean(oc ** 2))) * 1440, 3),
        "chi2_red": round(chi2 / dof, 3) if dof > 0 else None,
        "dof": dof,
    })
    return res


def parse_log(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"orchestrator_(\d{8})_(\d{6})", path.name)
    run_id = f"{m.group(1)}-{m.group(2)}" if m else path.stem

    def grab(pat, cast=str):
        mm = re.search(pat, txt)
        return cast(mm.group(1)) if mm else None

    started = grab(r"Started:\s+(\S+)")
    finished = grab(r"Finished:\s+(\S+)")
    runtime_min = None
    if started and finished:
        try:
            runtime_min = round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() / 60, 1)
        except ValueError:
            pass
    complete = "ORCHESTRATOR RUN COMPLETE" in txt
    stopped = "Stopping" in txt
    return {
        "id": run_id,
        "log_file": path.name,
        "started": started,
        "finished": finished,
        "runtime_min": runtime_min,
        "status": "Completed" if complete else ("Stopped" if stopped else "Incomplete"),
        "targets_drawn": grab(r"Drew (\d+) new", int),
        "fetched": grab(r"(\d+)/\d+ of this batch fetched", int),
        "confirmed_total": grab(r"Wrote dossiers for (\d+) confirmed", int),
        "stage_failures": len(re.findall(r"FAILED \(exit code", txt)),
        "retries": len(re.findall(r"\(attempt [2-9]/", txt)),
    }


def activity(path, keep=14):
    ev = []
    stage = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"STAGE: (.+?)\s+\(attempt (\d+)/(\d+)\)", s)
        if m:
            stage = m.group(1)
            continue
        m = re.match(r"-> (.+) finished OK in ([\d.]+) min", s)
        if m:
            ev.append({"kind": "ok", "stage": m.group(1), "text": f"finished OK in {m.group(2)} min"})
            continue
        m = re.match(r"-> (.+) FAILED \(exit code (\-?\d+)\) after ([\d.]+) min", s)
        if m:
            ev.append({"kind": "fail", "stage": m.group(1),
                       "text": f"failed (exit code {m.group(2)}) after {m.group(3)} min - retried"})
            continue
        if s.startswith("[ORCHESTRATOR] Decision:"):
            ev.append({"kind": "decision", "stage": stage or "", "text": s.split("Decision:", 1)[1].strip()})
    return ev[-keep:]


def main():
    if len(sys.argv) != 2:
        print("Usage: py export_dashboard.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    lc_dir = root / "data" / "lightcurves"
    pix_dir = root / "data" / "pixel_check"
    log_dir = root / "data" / "logs"
    site_data = root / "site" / "public" / "data"
    cand_dir = site_data / "candidates"
    detail_dir = site_data / "detail"
    detail_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    tics = [int(c["tic"]) for c in index["candidates"]]
    vet = pd.read_csv(proc / "f3i_vetting_results.csv").set_index("TIC")
    print(f"Dashboard export for {len(tics)} candidate(s)")

    # ---- TIC catalog: sky position, Gaia G, distance, Teff, radius ----
    cat = {}
    try:
        from astroquery.mast import Catalogs
        t = Catalogs.query_criteria(catalog="Tic", ID=tics)
        cols = [c for c in ["ID", "ra", "dec", "Tmag", "GAIAmag", "d", "e_d", "Teff", "rad", "GAIA"] if c in t.colnames]
        df = t[cols].to_pandas()
        for _, r in df.iterrows():
            cat[int(r["ID"])] = {
                "ra": clean(r.get("ra"), 5), "dec": clean(r.get("dec"), 5),
                "tmag": clean(r.get("Tmag"), 3), "gaia_g": clean(r.get("GAIAmag"), 3),
                "dist_pc": clean(r.get("d"), 1), "dist_err_pc": clean(r.get("e_d"), 1),
                "teff_k": clean(r.get("Teff"), 0), "radius_rsun": clean(r.get("rad"), 3),
                "gaia_id": str(r["GAIA"]) if "GAIA" in r and pd.notna(r["GAIA"]) else None,
            }
        print(f"  TIC catalog: {len(cat)} row(s)")
    except Exception as exc:
        print(f"  WARNING: TIC catalog query failed ({repr(exc)[:120]}) - sky map and distances left blank")

    sky = []
    for tic in tics:
        cj = json.loads((cand_dir / f"TIC{tic}.json").read_text(encoding="utf-8"))
        eph = cj["ephemeris"]
        v = vet.loc[tic]
        info = cat.get(tic, {})

        # data/lightcurves/ is regenerated fresh by each pipeline run and is
        # not committed to git (see .gitignore) - only stars fetched THIS run
        # have their raw light curve on disk. index.json is cumulative across
        # every run, so most candidates here were exported earlier and their
        # light curve is long gone from this fresh checkout. f5_dossier.py
        # already skips this case the same way; this mirrors that fix.
        lc_path = lc_dir / f"TIC{tic}.csv"
        detail_path = detail_dir / f"TIC{tic}.json"
        if not lc_path.exists():
            if detail_path.exists():
                existing = json.loads(detail_path.read_text(encoding="utf-8"))
                sky.append({"tic": tic, "tier": cj["tier"], "ra": info.get("ra"), "dec": info.get("dec"),
                            "period_days": existing["period_true_days"], "bls_snr": eph["bls_snr"]})
                print(f"  TIC {tic}: light curve not present this run - reusing existing detail export")
            else:
                print(f"  WARNING: TIC {tic} has no light curve and no prior detail export - skipped "
                      f"(its dashboard page will 404 until this star is re-fetched)")
            continue

        lc = pd.read_csv(lc_path)
        good = np.isfinite(lc["time"].values) & np.isfinite(lc["flux"].values)
        t = lc["time"].values[good]
        f = lc["flux"].values[good]
        ferr = lc["flux_err"].values[good] if "flux_err" in lc.columns else None

        P_bls = float(eph["period_days"])
        dur = float(eph["duration_days"])
        t0 = float(eph["t0_btjd"])
        aliased = bool(eph["aliased"])
        P_true = 2 * P_bls if aliased else P_bls

        # which eclipse is the primary at the true period? (for an alias, the
        # deeper of the two BLS eclipses)
        if aliased:
            a0 = eclipse_depth(t, f, P_true, t0, dur, 0.0)
            a1 = eclipse_depth(t, f, P_true, t0, dur, 0.5)
            if a0 and a1 and a1["depth"] > a0["depth"]:
                t0 = t0 + P_bls

        # primary: every covered eclipse measured on its own
        epochs = per_epoch(t, f, P_true, t0, dur)
        n_cov = len(epochs)
        n_seen = sum(1 for r in epochs if r["seen"])
        a = pooled_from_epochs(epochs)
        # an epoch is "absent" only if it is significantly SHALLOWER than the
        # typical eclipse (under half its depth, and > 5 sigma below it) - not
        # merely too noisy to see
        for r in epochs:
            r["absent"] = bool(a is not None and r["err"] and r["depth"] is not None
                               and r["depth"] < 0.5 * a["depth"]
                               and (a["depth"] - r["depth"]) > 5 * r["err"])
        missing = [r for r in epochs if r["absent"]]

        per = periodicity_check(t, f, P_true)
        checks = []
        if missing:
            checks.append(f"No eclipse at {len(missing)} of {n_cov} covered epochs where the "
                          f"{P_true:.5f} d period predicts one (each under half the typical depth, "
                          f"> 5 sigma below it). The period is probably wrong - the dips seen may be "
                          f"separate eclipses of a longer-period system.")
        if per and per.get("flag"):
            checks.append(per["text"])

        # fall back to the whole-light-curve fold depth (already computed by
        # the vetting step) when no single predicted eclipse could be measured
        # on its own -- this happens for real when the eclipse duration is
        # close to or below one cadence step, so a per-epoch core window can
        # never hold enough points, no matter how good the data is. This is
        # a real, already-computed number, not a fabricated one.
        if a is None:
            rd, rs = v.get("robust_depth"), v.get("robust_sigma")
            if rd is not None and np.isfinite(rd):
                a = {"depth": float(rd),
                     "err": float(rd) / float(rs) if rs is not None and np.isfinite(rs) and rs > 0 else None,
                     "sigma": float(rs) if rs is not None and np.isfinite(rs) else None,
                     "n_core": None, "whole_curve": True}
                diffs_wc = np.diff(np.sort(t))
                fine_wc = diffs_wc[diffs_wc < 0.05]
                cad_wc = float(np.median(fine_wc)) if fine_wc.size else float(np.median(diffs_wc))
                if n_cov == 0:
                    checks.append(f"Eclipse duration ({dur * 24:.2f} h) is too short relative to this light "
                                  f"curve's ~{cad_wc * 1440:.0f}-minute cadence for any single predicted eclipse "
                                  f"to hold enough points to measure on its own. The primary depth below is the "
                                  f"whole-light-curve fold measurement from the vetting step, not a per-epoch one.")
                else:
                    checks.append(f"None of the {n_cov} covered predicted eclipses reached 5 sigma on its own. "
                                  f"The primary depth below is the whole-light-curve fold measurement from the "
                                  f"vetting step, not a per-epoch one.")

        # secondary: searched for, not assumed at phase 0.5
        b = secondary_search(t, f, P_true, t0, dur)
        secondary = {k: (clean(x, 6) if isinstance(x, float) else x) for k, x in b.items()} if b else None
        sec_phase = b["phase"] if b and b["detected"] else 0.5

        # folds: main (true period, with residuals from the binned median),
        # and the alias pair (BLS period vs double it)
        ph, binned, raw, pick = fold_block(t, f, P_true, t0, dur, MAX_RAW, 1, sec_phase)
        bx = np.array([p[0] for p in binned])
        by = np.array([p[1] for p in binned])
        model = np.interp(ph[pick], bx, by)
        resid = [[r[0], round(float(r[1] - m), 6)] for r, m in zip(raw, model)]
        resid_rms = float(np.std([r[1] for r in resid])) if resid else None

        _, b1, r1, _ = fold_block(t, f, P_bls, float(eph["t0_btjd"]), dur, MAX_ALIAS_RAW, 2)
        _, b2, r2, _ = fold_block(t, f, 2 * P_bls, float(eph["t0_btjd"]), dur, MAX_ALIAS_RAW, 3)

        oc = eclipse_timings(t, f, ferr, P_true, t0, dur, allowed={r['epoch'] for r in epochs if r['seen']})

        maps = None
        mp = pix_dir / f"TIC{tic}_pixel.json"
        if mp.exists():
            maps = json.loads(mp.read_text(encoding="utf-8"))

        detail = {
            "tic": tic,
            "period_true_days": P_true,
            "period_bls_days": P_bls,
            "aliased": aliased,
            "t0_btjd": t0,
            "duration_days": dur,
            "baseline_days": round(float(t.max() - t.min()), 2),
            "n_points": int(len(t)),
            "odd_even_z": clean(v.get("odd_even_z"), 3),
            "depth_odd": clean(v.get("depth_odd"), 6),
            "depth_even": clean(v.get("depth_even"), 6),
            "primary": {k: clean(x, 6) for k, x in a.items()} if a else None,
            "periodicity": per,
            "checks": checks,
            "epochs": {"covered": n_cov, "seen": n_seen, "absent": len(missing), "rows": epochs},
            "secondary": secondary,
            "catalog": info,
            "fold": {"binned": binned, "raw": raw, "resid": resid,
                     "resid_rms": clean(resid_rms, 6), "second_phase": sec_phase},
            "alias": {"bls": {"binned": b1, "raw": r1}, "double": {"binned": b2, "raw": r2}},
            "zoom": {"primary": zoom(t, f, P_true, t0, dur, 4),
                     "secondary": zoom(t, f, P_true, t0 + sec_phase * P_true, dur, 5)},
            "timing": oc,
            "pixel_maps": maps,
        }
        (detail_dir / f"TIC{tic}.json").write_text(json.dumps(detail, separators=(",", ":")),
                                                   encoding="utf-8", newline="\n")
        sky.append({"tic": tic, "tier": cj["tier"], "ra": info.get("ra"), "dec": info.get("dec"),
                    "period_days": P_true, "bls_snr": eph["bls_snr"]})
        print(f"  TIC {tic}: P={P_true:.5f} d, primary "
              f"{(a['depth'] * 100 if a else float('nan')):.3f}% (seen in {n_seen}/{n_cov} covered eclipses), "
              f"secondary {(b['sigma'] if b else float('nan')):.1f} sigma at phase "
              f"{(b['phase'] if b else float('nan')):.3f}, {oc['n']} timed, pixel maps {'yes' if maps else 'no'}")
        for c in checks:
            print("    CHECK: " + c)

    logs = sorted(log_dir.glob("orchestrator_*.log")) if log_dir.exists() else []
    runs = [parse_log(p) for p in logs]
    runs.sort(key=lambda r: r["id"], reverse=True)
    dash = {
        "sky": sky,
        "runs": runs,
        "activity": activity(logs[-1]) if logs else [],
        "activity_log": logs[-1].name if logs else None,
    }
    (site_data / "dashboard.json").write_text(json.dumps(dash, separators=(",", ":")),
                                              encoding="utf-8", newline="\n")
    print(f"  {len(runs)} run(s) parsed from logs, {len(dash['activity'])} activity event(s)")
    print(f"Wrote {detail_dir} and {site_data / 'dashboard.json'}")


if __name__ == "__main__":
    main()
