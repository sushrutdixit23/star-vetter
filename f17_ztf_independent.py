import io
import sys
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astropy.timeseries import BoxLeastSquares

# Independent photometric check of the TESS survivors against ZTF.
#
# Why this exists. Every earlier check used TESS pixels that this pipeline
# processed, so none of them is independent in a referee's sense. ZTF is another
# telescope, another pipeline, other years, and a point-spread function about ten
# times narrower than a TESS pixel, so it also tests WHICH star is eclipsing.
#
# Why not fold at the TESS ephemeris. The pipeline's BLS period is good to about
# 1e-3 (fractional) and its T0 sits in the TESS years, so extrapolating to a ZTF
# baseline of years smears the eclipse completely. Instead each star gets a LOCAL
# box-least-squares scan on the ZTF data, in a narrow period window around the
# TESS period, with the TESS duration. That scan can find the eclipse at a
# slightly refined period and any phase.
#
# Calibration, per star and from the star's own data:
#   * control periods: the same local scan at many unrelated periods (not near a
#     harmonic of the TESS period). The p-value is the fraction of control scans
#     whose best signal-to-noise is at least as large. This includes the
#     look-elsewhere effect of scanning and the star's own red noise.
#   * power: a box eclipse of the TESS depth is injected into the star's own ZTF
#     data at random phase and a random refined period inside the scan window, and
#     the scan is repeated. Power is the fraction of injections that exceed the
#     99th percentile of the control scans. A star is only "testable" when power is
#     high, so "not seen" is evidence against the candidate only where ZTF could
#     have seen it.
#
# Outcomes: CONFIRMED, NOT_SEEN (testable, not confirmed), INCONCLUSIVE (not
# testable, not confirmed), NO_DATA.

IRSA_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
SEARCH_RADIUS_ARCSEC = 3.0
SAME_STAR_ARCSEC = 0.75          # ZTF objects within this of the nearest one are the same star
BAD_CATFLAGS_MASK = 32768        # IRSA's recommended mask for clean photometry
MAX_MAGERR = 0.2
MIN_POINTS = 40
SCAN_HALF_WIDTH = 2.0e-3         # fractional period window searched around the TESS period
DURATION_FACTORS = (0.7, 1.0)    # box durations tried, as fractions of the TESS duration
N_CONTROLS = 300
N_INJECTIONS = 24
CONTROL_QUANTILE = 0.99
POWER_TESTABLE = 0.5
P_CONFIRM = 0.01
MIN_EVENTS = 2                   # distinct eclipse epochs with points in the box
DEPTH_RATIO_RANGE = (0.3, 3.0)   # ZTF vs TESS depth, loose: colour and crowding differ
HARMONIC_EXCLUSION = 0.02        # control periods stay this far (fractional) from n*P/m
SEED = 20261110


def wilson(k, n, z=1.959964):
    if n <= 0:
        return {"k": int(k), "n": int(n), "rate": None, "lo": None, "hi": None}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"k": int(k), "n": int(n), "rate": float(p), "lo": float(max(0.0, c - h)), "hi": float(min(1.0, c + h))}


def rng_for(tic, salt=0):
    return np.random.default_rng([SEED, int(tic), int(salt)])


# ---------------------------------------------------------------- data

def select_same_star(df, ra, dec):
    """Keep the ZTF objects that are the target: those within SAME_STAR_ARCSEC of the
    object nearest to the target position (field overlaps give several objects for
    one star; a neighbour inside the cone is a different star and is dropped)."""
    if df is None or len(df) == 0:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    pos = df.groupby("oid")[["ra", "dec"]].median()
    cosd = np.cos(np.deg2rad(dec))
    sep = np.hypot((pos["ra"] - ra) * cosd, pos["dec"] - dec) * 3600.0
    best = sep.idxmin()
    d_best = np.hypot((pos["ra"] - pos.loc[best, "ra"]) * cosd, pos["dec"] - pos.loc[best, "dec"]) * 3600.0
    keep = d_best[d_best <= SAME_STAR_ARCSEC].index
    return df[df["oid"].isin(keep)]


def to_relative_flux(df):
    """Pool all clean points of the target into one normalised flux series.
    Each (object, filter) series is divided by its own median, so filter offsets and
    field overlaps do not matter. Returns time (HJD - 2400000.5), flux, flux error."""
    d = df[(df["catflags"] == 0) & (df["magerr"] > 0) & (df["magerr"] <= MAX_MAGERR) & np.isfinite(df["mag"])]
    t, f, e = [], [], []
    for _, g in d.groupby(["oid", "filtercode"]):
        if len(g) < 10:
            continue
        flux = 10.0 ** (-0.4 * (g["mag"].to_numpy(float) - np.median(g["mag"])))
        err = flux * g["magerr"].to_numpy(float) * np.log(10.0) / 2.5
        t.append(g["mjd"].to_numpy(float))
        f.append(flux)
        e.append(err)
    if not t:
        return np.array([]), np.array([]), np.array([])
    t, f, e = np.concatenate(t), np.concatenate(f), np.concatenate(e)
    # drop only implausibly BRIGHT outliers; faint outliers may be the eclipse
    s = 1.4826 * np.median(np.abs(f - np.median(f)))
    ok = f < 1.0 + max(5 * s, 0.05)
    order = np.argsort(t[ok])
    return t[ok][order], f[ok][order], e[ok][order]


# ---------------------------------------------------------------- statistics

def period_window(p0, duration, span, half_width=SCAN_HALF_WIDTH):
    """Period grid around p0 fine enough that the eclipse cannot drift by more than a
    fifth of its duration across the whole ZTF baseline."""
    step = max(duration * p0 / (5.0 * max(span, 1.0)), 1e-9)   # absolute period step (days)
    n = int(np.clip(2 * half_width * p0 / step, 20, 4000))
    return np.linspace(p0 * (1 - half_width), p0 * (1 + half_width), n)


def local_scan(t, f, e, p0, duration):
    """Best box depth signal-to-noise in a narrow period window around p0.
    Returns dict(snr, depth, depth_err, period, t0, n_events)."""
    span = float(t.max() - t.min())
    periods = period_window(p0, duration, span)
    bls = BoxLeastSquares(t, f, dy=e)
    durs = np.array([x * duration for x in DURATION_FACTORS])
    r = bls.power(periods, durs, objective="snr")
    i = int(np.nanargmax(r.depth_snr))
    P, T0, D = float(r.period[i]), float(r.transit_time[i]), float(r.duration[i])
    ph = ((t - T0 + 0.5 * P) % P) - 0.5 * P
    inbox = np.abs(ph) <= 0.5 * D
    epochs = np.unique(np.round((t[inbox] - T0) / P).astype(int)) if inbox.any() else np.array([])
    return {"snr": float(r.depth_snr[i]), "depth": float(r.depth[i]), "depth_err": float(r.depth_err[i]),
            "period": P, "t0": T0, "duration": D, "n_in": int(inbox.sum()), "n_events": int(len(epochs))}


def control_periods(p0, n, rng, span, lo=0.3, hi=3.0):
    """Unrelated trial periods: log-uniform ratios to p0 that stay clear of every
    simple harmonic n/m of p0 (m, n up to 4) and keep at least 3 cycles in the span."""
    harmonics = np.array([a / b for a in range(1, 5) for b in range(1, 5)])
    out = []
    tries = 0
    while len(out) < n and tries < 50 * n:
        tries += 1
        r = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        if np.min(np.abs(r / harmonics - 1.0)) < HARMONIC_EXCLUSION:
            continue
        if p0 * r * 3 > span or p0 * r < 0.2:
            continue
        out.append(p0 * r)
    return np.array(out)


def inject_box(t, f, p, t0, duration, depth):
    ph = ((t - t0 + 0.5 * p) % p) - 0.5 * p
    g = f.copy()
    g[np.abs(ph) <= 0.5 * duration] *= (1.0 - depth)
    return g


def assess(t, f, e, p0, duration, depth_tess, tic, n_controls=N_CONTROLS, n_injections=N_INJECTIONS):
    """Full per-star test. Returns a dict of results and the verdict."""
    span = float(t.max() - t.min())
    obs = local_scan(t, f, e, p0, duration)
    rng = rng_for(tic, 1)
    ctrl_p = control_periods(p0, n_controls, rng, span)
    ctrl = np.array([local_scan(t, f, e, p, duration)["snr"] for p in ctrl_p])
    p_value = float((1 + np.sum(ctrl >= obs["snr"])) / (1 + len(ctrl))) if len(ctrl) else None
    thr = float(np.quantile(ctrl, CONTROL_QUANTILE)) if len(ctrl) >= 20 else None
    # power: inject the TESS-depth eclipse at a random refined period and phase
    rng_i = rng_for(tic, 2)
    hits = 0
    for _ in range(n_injections):
        p = p0 * (1 + rng_i.uniform(-0.7, 0.7) * SCAN_HALF_WIDTH)
        t0 = float(t.min() + rng_i.uniform(0, p))
        g = inject_box(t, f, p, t0, duration, depth_tess)
        if thr is not None and local_scan(t, g, e, p0, duration)["snr"] >= thr:
            hits += 1
    power = hits / max(n_injections, 1)
    ratio = obs["depth"] / depth_tess if depth_tess > 0 else None
    ratio_err = obs["depth_err"] / depth_tess if depth_tess > 0 else None
    return {"obs": obs, "p_value": p_value, "control_snr_q99": thr, "n_controls": int(len(ctrl)),
            "power": float(power), "depth_ratio": ratio, "depth_ratio_err": ratio_err, "span_days": span}


def verdict(res):
    """CONFIRMED / NOT_SEEN / INCONCLUSIVE from an assess() result."""
    if res is None:
        return "NO_DATA"
    o, p = res["obs"], res["p_value"]
    ratio, err = res["depth_ratio"], res["depth_ratio_err"]
    consistent = ratio is not None and (ratio + 2 * err) >= DEPTH_RATIO_RANGE[0] and (ratio - 2 * err) <= DEPTH_RATIO_RANGE[1]
    if p is not None and p <= P_CONFIRM and o["n_events"] >= MIN_EVENTS and o["snr"] > 0 and consistent:
        return "CONFIRMED"
    if res["power"] >= POWER_TESTABLE:
        return "NOT_SEEN"
    return "INCONCLUSIVE"


def odd_even(t, f, e, period, t0, duration):
    """Depth of odd and even eclipses at this period: z of their difference. A period that
    is half the true one shows a significant difference."""
    ph = ((t - t0 + 0.5 * period) % period) - 0.5 * period
    inb = np.abs(ph) <= 0.4 * duration
    cyc = np.round((t - t0) / period).astype(int)
    outb = (np.abs(ph) > 1.0 * duration) & (np.abs(ph) < 3.0 * duration)
    base = np.median(f[outb]) if outb.sum() >= 5 else np.median(f)
    out = {}
    for name, sel in (("odd", inb & (cyc % 2 != 0)), ("even", inb & (cyc % 2 == 0))):
        n = int(sel.sum())
        if n >= 3:
            w = 1.0 / np.maximum(e[sel], 1e-9) ** 2
            out[name] = (float(base - np.average(f[sel], weights=w)), float(1.0 / np.sqrt(w.sum())), n)
        else:
            out[name] = None
    if out["odd"] and out["even"]:
        z = (out["odd"][0] - out["even"][0]) / np.hypot(out["odd"][1], out["even"][1])
        return {"odd": out["odd"][0], "even": out["even"][0], "n_odd": out["odd"][2], "n_even": out["even"][2], "z": float(z)}
    return None


def secondary(t, f, e, period, t0, duration):
    """Depth at phase 0.5 relative to nearby out-of-eclipse flux, and its significance."""
    ph = ((t - t0) / period) % 1.0
    half = 0.4 * duration / period
    sec = np.abs(ph - 0.5) <= half
    out = (np.abs(ph - 0.5) > 2 * half) & (np.abs(ph - 0.5) < 6 * half)
    if sec.sum() < 3 or out.sum() < 5:
        return None
    w = 1.0 / np.maximum(e[sec], 1e-9) ** 2
    d = float(np.median(f[out]) - np.average(f[sec], weights=w))
    err = float(1.0 / np.sqrt(w.sum()))
    return {"depth": d, "z": d / err, "n": int(sec.sum())}


# ---------------------------------------------------------------- download

def fetch_ztf(ra, dec, cache_dir, tic, attempts=4, pause=4.0):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / ("TIC%d.csv" % tic)
    if path.exists():
        txt = path.read_text(encoding="utf-8")
        return pd.read_csv(io.StringIO(txt)) if txt.strip() else pd.DataFrame()
    last = None
    for k in range(attempts):
        try:
            r = requests.get(IRSA_URL, params={"POS": "CIRCLE %.6f %.6f %.6f" % (ra, dec, SEARCH_RADIUS_ARCSEC / 3600.0),
                                              "FORMAT": "CSV", "BAD_CATFLAGS_MASK": BAD_CATFLAGS_MASK}, timeout=150)
            r.raise_for_status()
            path.write_text(r.text, encoding="utf-8", newline="\n")
            return pd.read_csv(io.StringIO(r.text)) if r.text.strip() else pd.DataFrame()
        except Exception as exc:   # noqa: BLE001 - network, retry
            last = exc
            time.sleep(pause * (k + 1))
    raise RuntimeError("IRSA ZTF request failed for TIC %d: %s" % (tic, last))


# ---------------------------------------------------------------- driver

def star_inputs(root):
    dash = pd.DataFrame(json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"])
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv")
    vet = vet[["TIC", "bls_period", "bls_t0", "bls_duration", "bls_depth", "n_eclipses_observed"]]
    m = dash.merge(vet, left_on="tic", right_on="TIC", how="left")
    return m.rename(columns={"period_days": "adopted_period"})


def analyse_star(row, raw):
    """One star: from raw IRSA rows to a result dict."""
    df = select_same_star(raw, float(row["ra"]), float(row["dec"]))
    t, f, e = to_relative_flux(df) if len(df) else (np.array([]), np.array([]), np.array([]))
    base = {"tic": int(row["tic"]), "tier": row["tier"], "n_points": int(len(t)),
            "tess_period": float(row["bls_period"]), "adopted_period": float(row["adopted_period"]),
            "tess_depth": float(row["bls_depth"]), "tess_duration": float(row["bls_duration"])}
    if len(t) < MIN_POINTS or (t.max() - t.min()) < 30:
        base["status"] = "NO_DATA"
        return base
    res = assess(t, f, e, float(row["bls_period"]), float(row["bls_duration"]), float(row["bls_depth"]), int(row["tic"]))
    base.update(res)
    base["status"] = verdict(res)
    o = res["obs"]
    base["ztf_span_days"] = res["span_days"]
    base["epochs_with_points"] = o["n_events"]
    # alias and secondary evidence at the refined ephemeris
    base["secondary"] = secondary(t, f, e, o["period"], o["t0"], o["duration"])
    base["odd_even_at_2P"] = odd_even(t, f, e, 2.0 * o["period"], o["t0"], o["duration"])
    return base


def summarise(stars):
    n = len(stars)
    cnt = {}
    for s in stars:
        cnt[s["status"]] = cnt.get(s["status"], 0) + 1
    testable = [s for s in stars if s["status"] in ("CONFIRMED", "NOT_SEEN")]
    conf = [s for s in testable if s["status"] == "CONFIRMED"]
    by_tier = {}
    for s in stars:
        b = by_tier.setdefault(s["tier"], {"n": 0, "CONFIRMED": 0, "NOT_SEEN": 0, "INCONCLUSIVE": 0, "NO_DATA": 0})
        b["n"] += 1
        b[s["status"]] += 1
    return {"stars": n, "by_status": cnt, "by_tier": by_tier,
            "testable": len(testable), "confirmed_among_testable": wilson(len(conf), len(testable)),
            "confirmed_among_with_data": wilson(cnt.get("CONFIRMED", 0), n - cnt.get("NO_DATA", 0))}


def main():
    argv = sys.argv[1:]
    if not argv:
        print("Usage: py f17_ztf_independent.py <project_root> [--limit N] [--shard i/n] [--reverse]")
        sys.exit(1)
    root = Path(argv[0]).resolve()
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    shard, nshard = (0, 1)
    if "--shard" in argv:
        a, b = argv[argv.index("--shard") + 1].split("/")
        shard, nshard = int(a), int(b)
    cache = root / "data" / "ztf_raw"
    out_dir = root / "data" / "processed" / "f17_ztf"
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = star_inputs(root).sort_values("tic").reset_index(drop=True)
    if limit:
        inputs = inputs.head(limit)
    inputs = inputs.iloc[shard::nshard]
    if "--reverse" in argv:
        inputs = inputs.iloc[::-1]       # work from the other end; finished stars are skipped
    for k, (_, row) in enumerate(inputs.iterrows(), 1):
        tic = int(row["tic"])
        out = out_dir / ("TIC%d.json" % tic)
        if out.exists():
            continue
        t0 = time.time()
        try:
            raw = fetch_ztf(float(row["ra"]), float(row["dec"]), cache, tic)
            res = analyse_star(row, raw)
        except Exception as exc:   # noqa: BLE001
            print("[%d/%d] TIC %d FAILED: %s" % (k, len(inputs), tic, exc), flush=True)
            continue
        out.write_text(json.dumps(res, default=lambda x: None if x is None else float(x)), encoding="utf-8", newline="\n")
        print("[%d/%d] TIC %d %s n=%d  %.0fs" % (k, len(inputs), tic, res["status"], res["n_points"], time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
