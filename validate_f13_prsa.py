"""Independent check of f13_ephemeris.py against published ephemerides.

Prsa et al. 2022 (VizieR J/ApJS/258/16) list a period and an epoch of primary
eclipse (BJD0, in BTJD) for 4,584 TESS eclipsing binaries, fitted by other
people with other code. This script asks whether f13 recovers them.

For each selected known EB it deliberately DEGRADES the starting ephemeris the
way a coarse BLS search would (period wrong by ~2e-4 relative, epoch wrong by up
to +/-0.4 eclipse durations), runs the real f13 chain from the raw TESS light
curves, and compares the fitted period and eclipse time with the published
values. The published numbers are never used in the measurement, only to start a
perturbed search and to grade it afterwards.

By default only TESS sectors 1-26 are used, because that is the data Prsa et al.
fitted. Using later sectors as well (--all-sectors) measures something different:
real eclipse-timing drift between that era and years later, which a linear
ephemeris cannot follow and which f13's hold-out is designed to flag.

Reported per star:
  d_epoch_min   fitted minus published time of the same eclipse, minutes
  z_period      (P_fit - P_published) / sqrt(sigma_fit^2 + sigma_published^2)
  swapped       fitted eclipse sits half a period from the published primary
                (primary/secondary naming differs; not an error in timing)
Pass criteria for the whole sample are printed at the end: median |d_epoch| and
the spread of z_period (about 1 if the quoted errors are honest).

Usage:  python validate_f13_prsa.py <root> [--n 24] [--seed 11] [--max-minutes 60]
            [--all-sectors]
Writes: data/processed/f13_validation_prsa.csv   (f13_validation_prsa_allsectors.csv
        with --all-sectors)
"""

import io
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

import f13_ephemeris as f13

PRSA_URL = ("https://vizier.cfa.harvard.edu/viz-bin/votable?-source=J/ApJS/258/16/tess-ebs"
            "&-out=TIC,RAJ2000,DEJ2000,Tmag,BJD0,e_BJD0,Per,e_Per,Morph,Wp-pf,Dp-pf&-out.max=10000")


def load_prsa():
    from astropy.io.votable import parse_single_table
    req = urllib.request.Request(PRSA_URL, headers={"User-Agent": "star-vetter-validation/1.0"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    df = parse_single_table(io.BytesIO(raw)).to_table().to_pandas()
    df["TIC"] = df["TIC"].astype(np.int64)
    return df


def select(df, n, seed):
    """Clean, detached, well-timed systems with obvious primary eclipses."""
    ok = df[(df["Morph"] < 0.5) & df["Per"].between(1.0, 12.0) & df["Tmag"].between(9.0, 13.0)
            & df["Dp-pf"].between(0.05, 0.6) & df["Wp-pf"].between(0.02, 0.2)
            & (df["e_BJD0"] < 0.002) & (df["e_Per"] < 1e-5)]
    return ok.sample(frac=1.0, random_state=seed).reset_index(drop=True)


PRSA_MAX_SECTOR = 26      # the data window of the published ephemerides


def sectors_available(tic, max_sector=None):
    import lightkurve as lk
    from upstream import call_with_timeout
    sr = call_with_timeout(lk.search_lightcurve, args=(f"TIC {tic}",),
                           kwargs={"author": "SPOC", "exptime": 120}, timeout=90)
    if len(sr) == 0:
        return 0
    seq = {int(s) for s in sr.table["sequence_number"]}
    return len({s for s in seq if max_sector is None or s <= max_sector})


def compare(fit_row, pr):
    """fit_row: f13 analyse_star row; pr: published row. Returns dict."""
    P, sP = fit_row["period_days"], fit_row["period_sigma_days"]
    T0 = fit_row["t0_btjd"]
    k = round((T0 - pr["BJD0"]) / pr["Per"])
    d = T0 - (pr["BJD0"] + k * pr["Per"])           # days, in (-P/2, P/2]
    half = pr["Per"] / 2
    swapped = abs(abs(d) - half) < 0.1 * half
    if swapped:                                      # compare to the secondary instead
        d = d - np.sign(d) * half
    sig_epoch = np.hypot(fit_row["t0_sigma_min"] / 1440.0, pr["e_BJD0"] + abs(k) * pr["e_Per"])
    return {"d_epoch_min": d * 1440.0, "sigma_epoch_min": sig_epoch * 1440.0, "swapped": bool(swapped),
            "z_period": (P - pr["Per"]) / np.hypot(sP, pr["e_Per"]),
            "d_period_s": (P - pr["Per"]) * 86400.0}


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    root = Path(argv[0]).resolve()
    n, seed, budget = 24, 11, 60.0
    max_sector = PRSA_MAX_SECTOR if "--all-sectors" not in argv else None
    for i, a in enumerate(argv):
        if a == "--n":
            n = int(argv[i + 1])
        elif a == "--seed":
            seed = int(argv[i + 1])
        elif a == "--max-minutes":
            budget = float(argv[i + 1])
    proc = root / "data" / "processed"
    lc_dir = proc / "f13_lc_cache"
    rng = np.random.default_rng(seed)
    t_start = time.time()
    orig_loader = f13.load_or_fetch_lightcurves
    if max_sector is not None:
        f13.load_or_fetch_lightcurves = lambda *a, **k: [
            (s, lc) for s, lc in orig_loader(*a, **k) if s <= max_sector]
    pool = select(load_prsa(), n, seed)
    print(f"{len(pool)} candidates pass the selection; testing up to {n} with 3-8 sectors of 2-min data")

    rows = []
    for _, pr in pool.iterrows():
        if len(rows) >= n or (time.time() - t_start) / 60 > budget:
            break
        tic = int(pr["TIC"])
        try:
            ns = sectors_available(tic, max_sector)
        except Exception as exc:  # noqa: BLE001
            print(f"TIC {tic}: sector search failed ({str(exc)[:60]})")
            continue
        if not 3 <= ns <= 8:
            continue
        dur = float(pr["Wp-pf"] * pr["Per"])
        P0 = float(pr["Per"] * (1.0 + rng.normal(0.0, 2e-4)))
        # A real BLS epoch lies inside the data it searched. Put ours in a randomly
        # chosen observed sector, then degrade it by up to +/-0.4 durations.
        lcs = f13.load_or_fetch_lightcurves(tic, "SPOC", print, lc_dir)
        pick = lcs[int(rng.integers(len(lcs)))][1]
        t_mid = float(np.median(np.asarray(pick.time.value, float)))
        mid = pr["BJD0"] + pr["Per"] * round((t_mid - pr["BJD0"]) / pr["Per"])
        t00 = float(mid + rng.uniform(-0.4, 0.4) * dur)
        try:
            meas = f13.measure_star(tic, "SPOC", P0, t00, dur, print, lc_dir)
            if meas.get("status") != "OK":
                print(f"TIC {tic}: {meas.get('status')}")
                continue
            row, _, _ = f13.analyse_star(tic, meas, float(pr["RAJ2000"]), float(pr["DEJ2000"]), P0)
        except Exception as exc:  # noqa: BLE001
            print(f"TIC {tic}: error {str(exc)[:80]}")
            continue
        if row.get("status") != "OK":
            print(f"TIC {tic}: {row.get('status')}")
            continue
        cmp_ = compare(row, pr)
        rows.append({"tic": tic, "tmag": pr["Tmag"], "period_published": pr["Per"],
                     "start_period_error_s": (P0 - pr["Per"]) * 86400.0,
                     "start_epoch_error_min": (t00 - (mid)) * 1440.0,
                     "n_sectors": row["n_sectors_measured"], "n_eclipses": row["n_eclipses"],
                     "timing_rms_min": row["timing_rms_min"], "holdout": row["holdout_status"], **cmp_})
        r = rows[-1]
        print(f"TIC {tic}: d_epoch {r['d_epoch_min']:+6.2f} min (sigma {r['sigma_epoch_min']:.2f}), "
              f"z_period {r['z_period']:+5.2f}, {r['n_eclipses']} eclipses/{r['n_sectors']} sectors"
              f"{' [swapped primary]' if r['swapped'] else ''}  ({len(rows)}/{n})", flush=True)

    df = pd.DataFrame(rows)
    name = "f13_validation_prsa.csv" if max_sector is not None else "f13_validation_prsa_allsectors.csv"
    df.to_csv(proc / name, index=False, encoding="utf-8", lineterminator="\n")
    if df.empty:
        print("No star could be validated.")
        return 1
    z = df["z_period"].to_numpy()
    mad_sigma = 1.4826 * float(np.median(np.abs(z - np.median(z))))
    print("\n" + "=" * 70)
    scope = f"sectors 1-{max_sector} only" if max_sector else "ALL sectors (includes real timing drift)"
    print(f"VALIDATION vs Prsa+2022 ({len(df)} known EBs; {scope}; starting ephemeris degraded on purpose)")
    print("=" * 70)
    print(f"  epoch:  median |d| = {df['d_epoch_min'].abs().median():.2f} min, "
          f"max |d| = {df['d_epoch_min'].abs().max():.2f} min, "
          f"within 3 sigma: {(df['d_epoch_min'].abs() < 3 * df['sigma_epoch_min']).mean():.0%}")
    print(f"  period: median z = {np.median(z):+.2f}, robust spread of z = {mad_sigma:.2f} "
          f"(1.0 would mean honest errors), |z|<3 for {(np.abs(z) < 3).mean():.0%}")
    print(f"  primary/secondary swapped in {int(df['swapped'].sum())} of {len(df)}")
    print(f"  hold-out: {df['holdout'].value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
