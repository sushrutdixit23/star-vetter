import sys
import csv
import time
import threading
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Could not import regions")

try:
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Catalogs
except ImportError as exc:
    print("Missing package: " + str(exc))
    print("Install it once with:  py -m pip install astroquery")
    sys.exit(1)

# same 1x/2x/0.5x/3x/1/3x period comparison as the F4 novelty step; this file
# must sit in the same folder as f4_novelty.py
from f4_novelty import best_period_ratio_flag

# Read-only diagnostic: could a NEIGHBOURING star be the real source of each
# candidate's eclipse? TESS pixels are 21 arcsec, so light from stars within
# a few pixels lands in the target's photometric aperture.
#
# The test (standard "dilution feasibility"): if the eclipse were really on
# neighbour n, with intrinsic depth d_n, the depth seen on the target is
#     d_obs = d_n * F_n / F_t      ->     d_n_required = d_obs * F_t / F_n
# with F = 10**(-0.4 * Tmag). A neighbour needing d_n_required > 1 (a >100%
# eclipse) is physically ruled out. Equivalently: a neighbour fainter than
# the target by more than  dm_max = -2.5 log10(d_obs)  cannot do it.
#
# Every simplification here is CONSERVATIVE (favours "blend possible"):
#   - assumes the neighbour's light falls 100% inside the target's aperture,
#     no matter its distance (a real PSF + aperture captures much less);
#   - uses F_t/F_n rather than (F_t+F_n)/F_n, i.e. assumes the pipeline
#     crowding correction removed all other light;
#   - allows eclipse depths right up to 100%.
# So "BLEND_RULED_OUT" is robust; "BLEND_POSSIBLE" over-flags and only means
# the brightness test cannot exclude it - not that a blend is likely.

SEARCH_RADIUS_ARCSEC = 63.0   # 3 TESS pixels
TESS_PIXEL_ARCSEC = 21.0
BAD_DISPOSITIONS = {"ARTIFACT", "DUPLICATE", "SPLIT"}
CACHE_COLUMNS = ["target_TIC", "nbr_TIC", "nbr_Tmag", "sep_arcsec", "nbr_disposition"]

# A remote catalog query can stall forever with no exception at all if the
# server just stops responding - invisible on a machine someone is watching
# (they notice and interrupt), but it hangs an unattended GitHub Actions job
# for its entire time budget. These wrap every such call in a hard
# wall-clock deadline so a stall becomes a normal, logged failure instead of
# blocking the whole run.
CATALOG_TIMEOUT_SEC = 120


def call_with_timeout(fn, args=(), kwargs=None, timeout=60):
    """
    Run fn(*args, **kwargs) with a hard wall-clock deadline. Raises
    TimeoutError if it does not finish in time.

    Uses a plain threading.Thread with daemon=True rather than
    concurrent.futures.ThreadPoolExecutor: ThreadPoolExecutor registers an
    atexit hook that joins every worker thread it ever created before the
    interpreter exits, so a genuinely stuck call would still stall the
    whole script at shutdown even after "timing out". A daemon thread
    carries no such obligation - Python exits without waiting for it.
    """
    kwargs = kwargs or {}
    box = {"value": None, "error": None}

    def runner():
        try:
            box["value"] = fn(*args, **kwargs)
        except Exception as e:
            box["error"] = e

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"call did not finish within {timeout}s")
    if box["error"] is not None:
        raise box["error"]
    return box["value"]


def append_rows(path: Path, rows, write_header):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CACHE_COLUMNS)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CACHE_COLUMNS})
        f.flush()


def query_neighbours(ra, dec, target_tic, retries=2, delay=3):
    coord = SkyCoord(ra * u.deg, dec * u.deg)
    last = None
    for attempt in range(retries + 1):
        try:
            r = call_with_timeout(
                Catalogs.query_region, args=(coord,),
                kwargs={"radius": SEARCH_RADIUS_ARCSEC * u.arcsec, "catalog": "TIC"},
                timeout=CATALOG_TIMEOUT_SEC,
            )
            rows = []
            for rec in r:
                nid = int(rec["ID"])
                if nid == target_tic:
                    continue
                disp = rec["disposition"]
                disp = "" if disp is None or np.ma.is_masked(disp) else str(disp)
                tm = rec["Tmag"]
                tm = np.nan if tm is None or np.ma.is_masked(tm) else float(tm)
                rows.append({"target_TIC": target_tic, "nbr_TIC": nid, "nbr_Tmag": tm,
                             "sep_arcsec": float(rec["dstArcSec"]), "nbr_disposition": disp})
            if not rows:
                # marker row so an empty field is still recorded as "queried"
                rows.append({"target_TIC": target_tic, "nbr_TIC": -1, "nbr_Tmag": np.nan,
                             "sep_arcsec": np.nan, "nbr_disposition": "NONE"})
            return rows, None
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(delay)
    return None, last


def main():
    if len(sys.argv) != 2:
        print("Usage: py diag_blend.py <project_root>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    nov = pd.read_csv(proc / "f4f_novelty_results.csv")
    nov["TIC"] = nov["TIC"].astype(int)

    print("=" * 72)
    print(f"BLEND DIAGNOSTIC: {len(nov)} trustworthy detections "
          f"({int((nov['verdict'] == 'NOVEL').sum())} NOVEL; the rest act as a control group)")
    print("=" * 72)

    print(f"\nFetching target brightness + TIC contamination ratio for {len(nov)} stars...")
    try:
        tinfo = call_with_timeout(Catalogs.query_criteria, kwargs={"catalog": "Tic", "ID": nov["TIC"].tolist()},
                                   timeout=CATALOG_TIMEOUT_SEC)
    except TimeoutError:
        print(f"\nMAST TIC catalog did not respond within {CATALOG_TIMEOUT_SEC}s.")
        print("Check your connection (and firewall/proxy settings if any) and try again.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nCould not reach the MAST TIC catalog: {exc}")
        print("This needs outbound internet access to mast.stsci.edu. Check your connection and try again.")
        sys.exit(1)
    tinfo = tinfo[["ID", "ra", "dec", "Tmag", "contratio"]].to_pandas()
    tinfo = tinfo.rename(columns={"ID": "TIC", "Tmag": "target_Tmag"})
    tinfo["TIC"] = tinfo["TIC"].astype(int)
    df = nov.merge(tinfo, on="TIC", how="inner")

    cache_path = proc / "diag_blend_neighbours.csv"
    done = set()
    if cache_path.exists():
        done = set(pd.read_csv(cache_path)["target_TIC"].astype(int))
        print(f"Found neighbour cache with {len(done)} star(s) already queried - reusing them.")
    write_header = not cache_path.exists()

    todo = df[~df["TIC"].isin(done)]
    print(f"Querying TIC neighbours within {SEARCH_RADIUS_ARCSEC:.0f} arcsec "
          f"({SEARCH_RADIUS_ARCSEC / TESS_PIXEL_ARCSEC:.0f} TESS pixels) for {len(todo)} star(s)...")
    failed = []
    for i, (_, r) in enumerate(todo.iterrows()):
        rows, err = query_neighbours(r["ra"], r["dec"], int(r["TIC"]))
        if rows is None:
            failed.append(int(r["TIC"]))
            print(f"  WARNING: TIC {int(r['TIC'])} neighbour query failed: {repr(err)[:200]}")
            continue
        append_rows(cache_path, rows, write_header)
        write_header = False
        if (i + 1) % 20 == 0:
            print(f"  ... {i + 1}/{len(todo)} queried (safe to stop; re-run resumes)")
        time.sleep(0.05)

    nb = pd.read_csv(cache_path)
    nb = nb[nb["target_TIC"].isin(df["TIC"])]
    nb = nb[(nb["nbr_TIC"] != -1) & (~nb["nbr_disposition"].fillna("").isin(BAD_DISPOSITIONS))]
    nb = nb.merge(df[["TIC", "target_Tmag", "bls_depth"]], left_on="target_TIC", right_on="TIC")

    n_nan_tmag = int(nb["nbr_Tmag"].isna().sum())
    nb = nb[nb["nbr_Tmag"].notna()].copy()
    # required intrinsic eclipse depth on the neighbour (see header)
    nb["flux_ratio_t_over_n"] = 10 ** (-0.4 * (nb["target_Tmag"] - nb["nbr_Tmag"]))
    nb["required_depth"] = nb["bls_depth"] * nb["flux_ratio_t_over_n"]
    nb["capable"] = nb["required_depth"] <= 1.0

    # known EBs / TOIs among the neighbours (local catalogs cached by f4e, no
    # network). A capable neighbour that is a KNOWN periodic variable whose
    # period matches ours (1x, 2x, 0.5x, 3x, 1/3x) is the strongest, most
    # specific contamination signal available without pixel-level data.
    known = []
    for fname, label, pcol in [("cat_tess_ebs_prsa2022.csv", "TESS_EB", "tess_eb_period"),
                               ("cat_toi_exofop.csv", "TOI", "toi_period")]:
        p = proc / fname
        if p.exists():
            k = pd.read_csv(p, usecols=["TIC", pcol]).rename(columns={pcol: "known_period"})
            k["label"] = label
            known.append(k)
    known = pd.concat(known, ignore_index=True) if known else pd.DataFrame(
        columns=["TIC", "known_period", "label"])
    known["TIC"] = known["TIC"].astype(int)
    nb["nbr_known_as"] = nb["nbr_TIC"].map(known.drop_duplicates("TIC").set_index("TIC")["label"]).fillna("")
    kn_nb = nb[nb["capable"]].merge(known, left_on="nbr_TIC", right_on="TIC", suffixes=("", "_k"))
    kn_nb = kn_nb.merge(df[["TIC", "bls_period"]], left_on="target_TIC", right_on="TIC",
                        suffixes=("", "_t"))
    kn_nb["period_check"] = [best_period_ratio_flag(bp, kp) for bp, kp in
                             zip(kn_nb["bls_period"], pd.to_numeric(kn_nb["known_period"], errors="coerce"))]
    period_matched = kn_nb[kn_nb["period_check"].str.startswith("agrees")]
    matched_targets = set(period_matched["target_TIC"].astype(int))

    per = []
    for _, r in df.iterrows():
        tic = int(r["TIC"])
        s = nb[nb["target_TIC"] == tic]
        cap = s[s["capable"]]
        best = cap.sort_values("required_depth").iloc[0] if len(cap) else None
        if tic in failed:
            status = "QUERY_FAILED"
        elif tic in matched_targets:
            status = "LIKELY_CONTAMINATION"
        elif len(cap) == 0:
            status = "BLEND_RULED_OUT"
        else:
            status = "BLEND_POSSIBLE"
        per.append({
            "TIC": tic, "verdict": r["verdict"], "bls_depth": r["bls_depth"],
            "bls_snr": r["bls_snr"], "n_eclipses_observed": r.get("n_eclipses_observed", np.nan),
            "target_Tmag": r["target_Tmag"], "tic_contratio": r["contratio"],
            "dm_max": -2.5 * np.log10(r["bls_depth"]) if r["bls_depth"] > 0 else np.nan,
            "n_neighbours": len(s), "n_capable_neighbours": len(cap),
            "blend_status": status,
            "best_nbr_TIC": int(best["nbr_TIC"]) if best is not None else None,
            "best_nbr_dTmag": float(best["nbr_Tmag"] - r["target_Tmag"]) if best is not None else None,
            "best_nbr_sep_arcsec": float(best["sep_arcsec"]) if best is not None else None,
            "best_nbr_required_depth": float(best["required_depth"]) if best is not None else None,
            "capable_nbr_known_as": ";".join(sorted(set(cap["nbr_known_as"]) - {""})),
        })
    res = pd.DataFrame(per)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    print(f"\n({n_nan_tmag} neighbour rows had no Tmag in the TIC and were skipped; "
          f"artifact/duplicate TIC entries excluded.)")

    print("\n--- 1. Blend status by verdict ---")
    print(pd.crosstab(res["verdict"], res["blend_status"], margins=True).to_string())

    n = res[res["verdict"] == "NOVEL"]
    print("\n--- 2. NOVEL: blend status vs. eclipse depth (deep eclipses are hard to fake) ---")
    dbin = pd.cut(n["bls_depth"], [0, 0.01, 0.05, 0.2, 1.0],
                  labels=["<1%", "1-5%", "5-20%", ">20%"])
    print(pd.crosstab(dbin, n["blend_status"], margins=True).to_string())

    print("\n--- 3. NOVEL: TIC contamination ratio (flux from neighbours / target flux, "
          "in the SPOC aperture model) ---")
    print(n["tic_contratio"].describe().to_string())
    print(f"  NOVEL stars with contratio > 0.5 (neighbours add >50% extra light): "
          f"{int((n['tic_contratio'] > 0.5).sum())}")

    print("\n--- 4. NOVEL with BLEND_POSSIBLE: the most capable neighbour for each ---")
    bp = n[n["blend_status"] == "BLEND_POSSIBLE"].sort_values("bls_snr", ascending=False)
    if len(bp):
        print(bp[["TIC", "bls_depth", "bls_snr", "target_Tmag", "tic_contratio",
                  "n_capable_neighbours", "best_nbr_TIC", "best_nbr_dTmag",
                  "best_nbr_sep_arcsec", "best_nbr_required_depth", "capable_nbr_known_as"]]
              .to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    else:
        print("None.")

    print("\n--- 5. Capable neighbours that are THEMSELVES a known TESS EB or TOI, with period check ---")
    if len(kn_nb):
        show = kn_nb.merge(res[["TIC", "verdict"]], left_on="target_TIC", right_on="TIC", suffixes=("", "_r"))
        print(show[["target_TIC", "verdict", "bls_period", "nbr_TIC", "label", "known_period",
                    "sep_arcsec", "period_check"]].to_string(index=False, float_format=lambda x: f"{x:.6f}"))
        print(f"  -> {len(matched_targets)} star(s) whose period matches a known variable neighbour: "
              f"LIKELY_CONTAMINATION")
    else:
        print("None.")

    print("\n--- 6. Top 15 NOVEL by SNR with blend status ---")
    print(n.sort_values("bls_snr", ascending=False).head(15)[
        ["TIC", "bls_depth", "bls_snr", "n_eclipses_observed", "dm_max", "n_neighbours",
         "n_capable_neighbours", "blend_status"]].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    n_ok = int((n["blend_status"] == "BLEND_RULED_OUT").sum())
    n_cont = int((n["blend_status"] == "LIKELY_CONTAMINATION").sum())
    print(f"\n*** NOVEL with a blend ruled out by brightness alone: {n_ok} / {len(n)} ***")
    print(f"*** NOVEL whose period matches a known variable neighbour (likely contamination): "
          f"{n_cont} / {len(n)} ***")
    ctrl = res[res["verdict"] != "NOVEL"]
    print(f"    (control group, already-catalogued stars: {int((ctrl['blend_status'] == 'BLEND_POSSIBLE').sum())}"
          f" / {len(ctrl)} also flagged BLEND_POSSIBLE - the brightness test alone does not discriminate)")
    if failed:
        print(f"  {len(failed)} star(s) had failed neighbour queries - re-run to retry them.")

    out = proc / "diag_blend_results.csv"
    res.to_csv(out, index=False)
    print(f"\nPer-star results written to: {out}")
    print(f"Neighbour cache: {cache_path}")


if __name__ == "__main__":
    main()