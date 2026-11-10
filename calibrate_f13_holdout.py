"""How often does f13's hold-out reject a binary whose clock is known to be fine?

The hold-out test (f13_ephemeris.leave_one_sector_out / rolling_origin) is a
statistical test with a stated false-alarm rate. This script measures that rate
on real stars, using published binaries (Prsa et al. 2022, VizieR J/ApJS/258/16)
as the sample: clean, detached, well-timed systems observed in TESS sectors
1-26. Each is measured by the real f13 chain from the raw light curves, starting
at the published ephemeris, and the hold-out is run on the result.

A failure here is NOT automatically a false alarm: some real binaries have
genuine timing variations. So the figures are an upper bound on the false-alarm
rate, and every failing star is listed with its timing scatter for inspection.

Procedure used to set f13_ephemeris.R_FLOOR_DAYS: tune on one seed, then report
on a different seed. Stars listed in --exclude are skipped, so the two samples
are disjoint.

Usage:  python calibrate_f13_holdout.py <root> [--seed 23] [--n 25] [--floor-min 1.0]
            [--exclude data/processed/f13_validation_prsa.csv] [--max-minutes 40]
Writes: data/processed/f13_holdout_calibration_seed<seed>.csv
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import f13_ephemeris as f13
import validate_f13_prsa as v

MAX_SECTOR = 26


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    root = Path(argv[0]).resolve()
    seed, n, budget = 23, 25, 40.0
    floor_min = f13.R_FLOOR_DAYS * 1440.0
    exclude = None
    for i, a in enumerate(argv):
        if a == "--seed":
            seed = int(argv[i + 1])
        elif a == "--n":
            n = int(argv[i + 1])
        elif a == "--floor-min":
            floor_min = float(argv[i + 1])
        elif a == "--exclude":
            exclude = Path(argv[i + 1])
        elif a == "--max-minutes":
            budget = float(argv[i + 1])
    f13.R_FLOOR_DAYS = floor_min / 1440.0
    proc = root / "data" / "processed"
    lc_dir = proc / "f13_lc_cache"
    skip = set()
    if exclude is not None and exclude.exists():
        skip = set(pd.read_csv(exclude)["tic"].astype(int))

    orig = f13.load_or_fetch_lightcurves
    f13.load_or_fetch_lightcurves = lambda *a, **k: [(s, lc) for s, lc in orig(*a, **k) if s <= MAX_SECTOR]
    pool = v.select(v.load_prsa(), n * 4, seed)
    t_start = time.time()
    rows = []
    for _, pr in pool.iterrows():
        if len(rows) >= n or (time.time() - t_start) / 60 > budget:
            break
        tic = int(pr["TIC"])
        if tic in skip:
            continue
        try:
            if not 3 <= v.sectors_available(tic, MAX_SECTOR) <= 8:
                continue
            lcs = f13.load_or_fetch_lightcurves(tic, "SPOC", lambda *a: None, lc_dir)
            dur = float(pr["Wp-pf"] * pr["Per"])
            t_mid = float(np.median(np.asarray(lcs[0][1].time.value, float)))
            mid = pr["BJD0"] + pr["Per"] * round((t_mid - pr["BJD0"]) / pr["Per"])
            meas = f13.measure_star(tic, "SPOC", float(pr["Per"]), float(mid), dur, lambda *a: None, lc_dir)
        except Exception as exc:  # noqa: BLE001 - one bad star must not stop the run
            print(f"TIC {tic}: skipped ({str(exc)[:60]})")
            continue
        if meas.get("status") != "OK" or len(meas["eclipses"]) < 4:
            continue
        ecl = meas["eclipses"]
        keep = f13.clip_outliers(np.array([x["E"] for x in ecl], float), np.array([x["T"] for x in ecl]),
                                 np.array([x["sigma"] for x in ecl]), np.array([x["sector"] for x in ecl]))
        ecl = [x for x, k in zip(ecl, keep) if k]
        fit = f13.fit_line([x["E"] for x in ecl], [x["T"] for x in ecl], [x["sigma"] for x in ecl],
                           [x["sector"] for x in ecl])
        ho = f13.leave_one_sector_out(ecl) + f13.rolling_origin(ecl)
        if fit is None or not ho:
            continue
        worst = max(ho, key=lambda r: r["z_equiv"])
        rows.append({"tic": tic, "status": f13.holdout_status(ho), "n_sectors": len({x["sector"] for x in ecl}),
                     "n_eclipses": len(ecl), "timing_rms_min": fit["rms"] * 1440.0,
                     "worst_kind": worst["kind"], "worst_z": worst["z_equiv"],
                     "worst_pred_sigma_min": worst["pred_sigma_min_mean"]})
        print(f"TIC {tic}: {rows[-1]['status']}  rms {rows[-1]['timing_rms_min']:.2f} min  "
              f"worst z {rows[-1]['worst_z']:.2f} ({len(rows)}/{n})", flush=True)

    df = pd.DataFrame(rows)
    out = proc / f"f13_holdout_calibration_seed{seed}.csv"
    df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
    if df.empty:
        print("No star could be tested.")
        return 1
    nf = int((df["status"] == "FAIL").sum())
    print("\n" + "=" * 66)
    print(f"HOLD-OUT CALIBRATION: {len(df)} published binaries, sectors 1-{MAX_SECTOR}, "
          f"shared-offset floor {floor_min:g} min")
    print("=" * 66)
    print(f"  passed {len(df) - nf}, failed {nf}  ({nf / len(df):.0%} failed; design rate is about 1%)")
    for _, r in df[df["status"] == "FAIL"].iterrows():
        print(f"  failed: TIC {int(r['tic'])}, timing scatter {r['timing_rms_min']:.2f} min, "
              f"{r['worst_kind']} z = {r['worst_z']:.1f}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
