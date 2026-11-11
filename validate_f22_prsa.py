"""Independent check of f22_eccentricity.py against published secondary-eclipse phases.

Prsa et al. 2022 (VizieR J/ApJS/258/16) fitted a primary and a secondary eclipse phase for
4,584 TESS eclipsing binaries with other code. This script asks two questions of the
eccentricity measurement, using only those other people's numbers as the answer key:

  1. Position: where f22 finds the secondary, how far is it from the published phase?
  2. Verdict:  among systems the catalog puts at phase 0.5 (circular) how many does f22 call
               ECCENTRIC (false positives), and among systems the catalog puts clearly away from
               0.5 how many does it recover (recall)?

The published period, epoch and primary width start the measurement (f22 needs them, as it
needs the pipeline's values for survivors); the published secondary phase is never used until
grading. Light curves are the 2-minute TESS curves via f13's cached loader.

Usage:  python validate_f22_prsa.py <root> [--n 30] [--seed 5] [--max-minutes 45]
Writes: data/processed/f22_validation_prsa.csv and prints a summary (also saved as
        data/processed/f22_validation_prsa_summary.json).
"""

import io
import sys
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

import f13_ephemeris as f13
import f22_eccentricity as f22

URL = ("https://vizier.cfa.harvard.edu/viz-bin/votable?-source=J/ApJS/258/16/tess-ebs"
       "&-out=TIC,Tmag,BJD0,Per,Morph,Wp-pf,Dp-pf,Phip-pf,Ws-pf,Ds-pf,Phis-pf&-out.max=10000")
CIRCULAR_TOL = 0.004          # published secondary this close to phase 0.5 counts as circular
ECCENTRIC_MIN = 0.03          # ... this far counts as clearly eccentric (|e cos w| of about 0.047)
AGREE_TOL = 0.01              # phase agreement counted as a match


def load_catalog():
    from astropy.io.votable import parse_single_table
    req = urllib.request.Request(URL, headers={"User-Agent": "star-vetter-validation/1.0"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    df = parse_single_table(io.BytesIO(raw)).to_table().to_pandas()
    df["TIC"] = df["TIC"].astype(np.int64)
    df["sec_phase"] = (df["Phis-pf"] - df["Phip-pf"]) % 1.0
    df["off"] = (df["sec_phase"] - 0.5).abs()
    return df


def pick(df, n, seed):
    """Half circular, half clearly eccentric, all with a measurable secondary and a deep primary."""
    ok = df[(df["Morph"] < 0.5) & df["Per"].between(1.5, 25.0) & df["Tmag"].between(9.0, 13.5)
            & df["Dp-pf"].between(0.03, 0.6) & (df["Ds-pf"] > 0.01) & df["Wp-pf"].between(0.01, 0.15)
            & df["Ws-pf"].between(0.01, 0.15)].dropna(subset=["sec_phase", "BJD0", "Per", "Wp-pf"])
    circ = ok[ok["off"] <= CIRCULAR_TOL]
    ecc = ok[ok["off"] >= ECCENTRIC_MIN]
    k = n // 2
    a = circ.sample(min(k, len(circ)), random_state=seed)
    b = ecc.sample(min(n - k, len(ecc)), random_state=seed)
    return pd.concat([a.assign(truth="CIRCULAR"), b.assign(truth="ECCENTRIC")]).reset_index(drop=True)


def measure(tic, P, t0, dur, cache, all_sectors=False):
    lcs = f13.load_or_fetch_lightcurves(tic, "SPOC", lambda *_: None, lc_dir=cache)
    if not lcs:
        return {"verdict": "NO_LIGHT_CURVE"}
    t = np.concatenate([np.asarray(lc.time.value, float) for _, lc in lcs])
    f = np.concatenate([np.asarray(lc.flux.value, float) for _, lc in lcs])
    s = np.concatenate([np.full(len(lc), sec) for sec, lc in lcs])
    ok = np.isfinite(t) & np.isfinite(f)
    if not all_sectors:                       # the sectors the catalog was fitted on (no apsidal drift)
        ok &= s <= 26
        if len(np.unique(s[ok])) < 2:
            return {"verdict": "TOO_FEW_SECTORS_IN_RANGE"}
    td, fd, sd = f22.detrend(t[ok], f[ok], P, t0, dur, s[ok])
    return f22.assess(td, fd, P, t0, dur, sd)


def summarise(res):
    got = res[res["verdict"].isin(["ECCENTRIC", "CIRCULAR_WITHIN_ERRORS"])]
    d = (got["mine"] - got["sec_phase"]).abs()
    d = np.minimum(d, 1.0 - d)
    circ = res[res["truth"] == "CIRCULAR"]
    ecc = res[res["truth"] == "ECCENTRIC"]
    out = {
        "n_tested": int(len(res)),
        "n_with_measurement": int(len(got)),
        "median_abs_phase_error": float(np.median(d)) if len(d) else None,
        "fraction_within_%.3f" % AGREE_TOL: float((d <= AGREE_TOL).mean()) if len(d) else None,
        "circular_truth": int(len(circ)),
        "false_positive_eccentric": int((circ["verdict"] == "ECCENTRIC").sum()),
        "eccentric_truth": int(len(ecc)),
        "recovered_eccentric": int((ecc["verdict"] == "ECCENTRIC").sum()),
        "eccentric_truth_verdicts": ecc["verdict"].value_counts().to_dict(),
        "circular_truth_verdicts": circ["verdict"].value_counts().to_dict(),
    }
    if len(circ):
        out["false_positive_rate"] = out["false_positive_eccentric"] / len(circ)
    if len(ecc):
        out["recall_eccentric"] = out["recovered_eccentric"] / len(ecc)
    return out


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    n = int(args[args.index("--n") + 1]) if "--n" in args else 30
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 5
    budget = 60.0 * (float(args[args.index("--max-minutes") + 1]) if "--max-minutes" in args else 45.0)
    cache = root / "data" / "processed" / "f13_lc_cache_prsa"
    all_sectors = "--all-sectors" in args
    cat = pick(load_catalog(), 4 * n, seed)
    cat = pd.concat([cat[cat.truth == "CIRCULAR"].reset_index(drop=True), cat[cat.truth == "ECCENTRIC"].reset_index(drop=True)]
                    ).sort_index(kind="stable").reset_index(drop=True)
    print("Selected %d catalog systems (%d circular, %d eccentric by the published phase)" % (
        len(cat), (cat.truth == "CIRCULAR").sum(), (cat.truth == "ECCENTRIC").sum()), flush=True)
    t_start = time.time()
    rows = []
    for _, r in cat.iterrows():
        measured = sum(1 for x in rows if x["verdict"] != "TOO_FEW_SECTORS_IN_RANGE")
        if measured >= n:
            break
        if time.time() - t_start > budget:
            print("Time budget reached, stopping.", flush=True)
            break
        tic = int(r["TIC"])
        P, dur = float(r["Per"]), float(r["Wp-pf"]) * float(r["Per"])
        t0 = float(r["BJD0"])
        try:
            res = measure(tic, P, t0, dur, cache, all_sectors)
        except Exception as e:  # noqa: BLE001 - recorded, never silent
            res = {"verdict": "ERROR", "error": repr(e)}
        mine = res.get("secondary_phase")
        rows.append({"TIC": tic, "truth": r["truth"], "period_days": P, "sec_phase": float(r["sec_phase"]),
                     "mine": mine if mine is not None else np.nan, "verdict": res["verdict"],
                     "ecosw_mine": res.get("ecosw") if res.get("ecosw") is not None else np.nan,
                     "ecosw_published": float(np.pi / 2 * (r["sec_phase"] - 0.5))})
        print("TIC %d truth=%s published=%.4f mine=%s verdict=%s" % (
            tic, r["truth"], r["sec_phase"], "%.4f" % mine if mine is not None else "-", res["verdict"]), flush=True)
    df = pd.DataFrame(rows)
    df = df[df["verdict"] != "TOO_FEW_SECTORS_IN_RANGE"].reset_index(drop=True)
    out = root / "data" / "processed"
    df.to_csv(out / "f22_validation_prsa.csv", index=False, encoding="utf-8", lineterminator="\n")
    summ = summarise(df)
    (out / "f22_validation_prsa_summary.json").write_text(json.dumps(summ, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
