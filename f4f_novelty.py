import sys
import csv
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Could not import regions")

try:
    from astropy.table import Table
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from astroquery.mast import Catalogs
    from astroquery.vizier import Vizier
    from astroquery.xmatch import XMatch
except ImportError as exc:
    print("Missing package: " + str(exc))
    print("This script needs astroquery (astropy comes with it as a dependency).")
    print("Install it once with:  py -m pip install astroquery")
    sys.exit(1)

# Reuses the classification logic UNCHANGED from f4_novelty.py - this file
# must sit in the same folder as f4_novelty.py. No science changes: same
# catalogs (VSX, ASAS-SN, Gaia DR3 veb + classifier), same match radius,
# same verdict rules.
from f4_novelty import (
    type_tokens, classify_tokens, best_period_ratio_flag,
    MATCH_RADIUS_ARCSEC, GAIA_ECL_CLASS, GAIA_ELL_CLASS, GAIA_EP_CLASS,
)

# f4f = f4e pointed at f3i's vetting output (adds the median-depth gate,
# gap #8), plus one new verdict: CONTAMINATED - a star whose period matches a
# KNOWN variable neighbour bright enough to cause the dip (from
# diag_blend.py's diag_blend_results.csv, if present; e.g. TIC 158329671, at
# exactly half the period of TESS EB TIC 158329676 40 arcsec away). Such a
# star's signal is real but almost certainly not its own.
#
# (f4e notes follow.) f4e = f4d plus two TESS-specific catalogs, matched by exact TIC ID:
#   - Prsa et al. 2022 TESS eclipsing-binary catalog (VizieR J/ApJS/258/16,
#     4,584 EBs from 2-min cadence sectors 1-26). A match = KNOWN_EB.
#   - The TESS Objects of Interest list (ExoFOP), i.e. signals the TESS
#     team already flagged. TESS Disposition 'EB' = the TOI was later
#     identified as an eclipsing binary -> KNOWN_EB. Any other TOI match ->
#     new verdict KNOWN_TOI (the signal is already catalogued, so it is not
#     novel), and a planet-like disposition sets exoplanet_conflict.
# VSX / ASAS-SN / Gaia matching is unchanged. Both new catalogs are cached
# to data/processed/ after the first download; if a later download fails,
# the cached copy is used (with a warning showing its date), so a network
# hiccup never silently turns a known star into a NOVEL one.
ASASSN_CACHE_COLUMNS = ["TIC", "asassn_queried_ok", "asassn_match", "asassn_name",
                         "asassn_type", "asassn_period", "asassn_error"]


def query_asassn_with_retry(v, coord, tic, retries=2, delay=3):
    """Query ASAS-SN (II/366/catv2021) for one star, retrying transient
    failures before giving up. Returns a dict matching ASASSN_CACHE_COLUMNS
    (minus TIC, added by the caller)."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = v.query_region(coord, radius=MATCH_RADIUS_ARCSEC * u.arcsec,
                                catalog="II/366/catv2021")
            if len(r) > 0 and len(r[0]) > 0:
                best = r[0][np.argmin(r[0]["_r"])] if "_r" in r[0].colnames else r[0][0]
                name = best["ASASSN-V"] if "ASASSN-V" in r[0].colnames else None
                atype = best["Type"] if "Type" in r[0].colnames else None
                aper = best["Per"] if "Per" in r[0].colnames else None
                return {"asassn_queried_ok": True, "asassn_match": True,
                        "asassn_name": name, "asassn_type": atype,
                        "asassn_period": aper, "asassn_error": ""}
            return {"asassn_queried_ok": True, "asassn_match": False,
                     "asassn_name": None, "asassn_type": None,
                     "asassn_period": None, "asassn_error": ""}
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(delay)
    return {"asassn_queried_ok": False, "asassn_match": False,
            "asassn_name": None, "asassn_type": None,
            "asassn_period": None, "asassn_error": str(last_err)[:200]}


def append_asassn_row(cache_path: Path, row: dict, write_header: bool):
    with open(cache_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ASASSN_CACHE_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in ASASSN_CACHE_COLUMNS})
        f.flush()


TOI_URL = "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv"
TOI_PLANET_LIKE_TFOPWG = {"PC", "CP", "KP", "APC"}
TOI_NEA_URL = ("https://exoplanetarchive.ipac.caltech.edu/TAP/sync?"
               "query=select+tid,toi,tfopwg_disp,pl_orbper+from+toi&format=csv")
TOI_MANUAL_FILE = "toi_manual_download.csv"
TOI_PLANET_LIKE_TESS = {"PC", "CP", "KP"}


def _cached_fetch(label, cache_path, fetch_fn):
    """Fetch a catalog fresh; on failure fall back to the cached copy.
    Returns a DataFrame, or None if neither works."""
    try:
        df = fetch_fn()
        df.to_csv(cache_path, index=False)
        print(f"  {label}: downloaded {len(df)} rows (cached to {cache_path.name})")
        return df
    except Exception as exc:
        if cache_path.exists():
            age = time.strftime("%Y-%m-%d", time.localtime(cache_path.stat().st_mtime))
            df = pd.read_csv(cache_path)
            print(f"  {label}: download failed ({str(exc)[:80]}) - using cached copy from {age} "
                  f"({len(df)} rows)")
            return df
        print(f"  {label}: download failed ({str(exc)[:80]}) and no cached copy exists - "
              f"this catalog is SKIPPED for this run. Re-run when online.")
        return None


def load_tess_eb(processed_dir: Path):
    def fetch():
        v = Vizier(row_limit=-1, columns=["TIC", "Per", "Morph"])
        t = v.get_catalogs("J/ApJS/258/16/tess-ebs")[0].to_pandas()
        t["TIC"] = t["TIC"].astype(int)
        return t.rename(columns={"Per": "tess_eb_period", "Morph": "tess_eb_morph"})
    return _cached_fetch("TESS EB catalog (Prsa+ 2022)", processed_dir / "cat_tess_ebs_prsa2022.csv", fetch)


def load_toi(processed_dir: Path):
    # toi-loader v2: three sources tried in order, full errors printed.
    #  1. ExoFOP (primary, has both TESS and TFOPWG dispositions)
    #  2. NASA Exoplanet Archive mirror of the same TOI table (same TOIs; has
    #     TFOPWG disposition but no 'TESS Disposition' column)
    #  3. a copy the user saved from a browser (browsers get through some
    #     network/antivirus/certificate setups that scripts cannot)
    # then the previous cached copy, then give up loudly.
    import io
    import requests
    cache_path = processed_dir / "cat_toi_exofop.csv"
    manual_path = processed_dir / TOI_MANUAL_FILE
    exofop_cols = ["TIC ID", "TOI", "TESS Disposition", "TFOPWG Disposition", "Period (days)"]

    def from_exofop_frame(t):
        t = t[exofop_cols].rename(columns={
            "TIC ID": "TIC", "TOI": "toi", "TESS Disposition": "toi_tess_disp",
            "TFOPWG Disposition": "toi_tfopwg_disp", "Period (days)": "toi_period"})
        t["TIC"] = t["TIC"].astype(int)
        return t

    errors = []
    t, src = None, None
    try:
        r = requests.get(TOI_URL, timeout=120)
        r.raise_for_status()
        t, src = from_exofop_frame(pd.read_csv(io.StringIO(r.text))), "ExoFOP"
    except Exception as exc:
        errors.append(("ExoFOP", exc))

    if t is None:
        try:
            r = requests.get(TOI_NEA_URL, timeout=120)
            r.raise_for_status()
            n = pd.read_csv(io.StringIO(r.text))
            t = pd.DataFrame({"TIC": n["tid"].astype(int), "toi": n["toi"],
                              "toi_tess_disp": np.nan, "toi_tfopwg_disp": n["tfopwg_disp"],
                              "toi_period": n["pl_orbper"]})
            src = ("NASA Exoplanet Archive mirror (no 'TESS Disposition' column, so a TOI "
                   "the TESS team re-labelled EB counts as KNOWN_TOI rather than KNOWN_EB)")
        except Exception as exc:
            errors.append(("NASA Exoplanet Archive", exc))

    if t is None and manual_path.exists():
        try:
            t, src = from_exofop_frame(pd.read_csv(manual_path)), f"browser download ({manual_path.name})"
        except Exception as exc:
            errors.append((f"browser download {manual_path.name}", exc))

    for name, exc in errors:
        print(f"  TOI source failed - {name}: {repr(exc)[:600]}")

    if t is not None:
        t.to_csv(cache_path, index=False)
        print(f"  TESS TOI list: loaded {len(t)} rows from {src} (cached to {cache_path.name})")
        return t

    if cache_path.exists():
        age = time.strftime("%Y-%m-%d", time.localtime(cache_path.stat().st_mtime))
        t = pd.read_csv(cache_path)
        print(f"  TESS TOI list: all sources failed - using cached copy from {age} ({len(t)} rows)")
        return t

    print("  TESS TOI list: all sources failed and no cached copy exists - SKIPPED this run.")
    print("  To fix without any network debugging: open this link in your browser,")
    print(f"      {TOI_URL}")
    print(f"  save the file as  {manual_path}")
    print("  and re-run this script.")
    return None


def best_toi_row(rows, our_period):
    """A star can host several TOIs (multi-planet systems) - pick the one
    whose period is closest to ours (in log space, so aliases rank fairly)."""
    if len(rows) == 1:
        return rows.iloc[0]
    p = pd.to_numeric(rows["toi_period"], errors="coerce")
    score = np.abs(np.log(p / our_period)).fillna(np.inf)
    return rows.iloc[int(np.argmin(score.values))]


def main():
    if len(sys.argv) != 2:
        print("Usage: py f4f_novelty.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    vet_path = project_root / "data" / "processed" / "f3i_vetting_results.csv"
    out_path = project_root / "data" / "processed" / "f4f_novelty_results.csv"
    asassn_cache_path = project_root / "data" / "processed" / "f4b_asassn_cache.csv"

    vet = pd.read_csv(vet_path)
    trustworthy = vet[(vet["status"] == "OK") & (vet["depth_flagged_implausible"] == False)].copy()
    trustworthy["TIC"] = trustworthy["TIC"].astype(int)

    print("=" * 70)
    print(f"F4f NOVELTY CROSS-MATCH: {len(trustworthy)} trustworthy detections to check")
    print("=" * 70)

    if len(trustworthy) == 0:
        print("\nNo trustworthy detections found in f3i_vetting_results.csv. Nothing to cross-match.")
        sys.exit(1)

    # --- Step 1: coordinates ---
    tic_ids = trustworthy["TIC"].tolist()
    print(f"\nQuerying MAST TIC catalog for {len(tic_ids)} stars' coordinates...")
    try:
        tic_info = Catalogs.query_criteria(catalog="Tic", ID=tic_ids)
    except Exception as exc:
        print(f"\nCould not reach the MAST TIC catalog: {exc}")
        print("This needs outbound internet access to mast.stsci.edu. Check your connection and try again.")
        sys.exit(1)
    tic_info = tic_info[["ID", "ra", "dec", "Tmag"]].to_pandas()
    tic_info = tic_info.rename(columns={"ID": "TIC"})
    tic_info["TIC"] = tic_info["TIC"].astype(int)

    missing = set(tic_ids) - set(tic_info["TIC"])
    if missing:
        print(f"WARNING: {len(missing)} TIC(s) not found in the TIC catalog, skipped: {sorted(missing)}")

    merged = trustworthy.merge(tic_info, on="TIC", how="inner")
    print(f"Resolved coordinates for {len(merged)} / {len(trustworthy)} stars.")

    # --- Step 2: batch cross-match against VSX and the two Gaia tables ---
    cat1 = Table.from_pandas(merged[["TIC", "ra", "dec"]])
    xmatch_catalogs = {
        "vsx": "vizier:B/vsx/vsx",
        "gaia_veb": "vizier:I/358/veb",
        "gaia_class": "vizier:I/358/vclassre",
    }
    xmatch_results = {}
    for key, cat2 in xmatch_catalogs.items():
        print(f"\nCross-matching against {cat2} (radius={MATCH_RADIUS_ARCSEC} arcsec)...")
        try:
            xm = XMatch.query(cat1=cat1, cat2=cat2, max_distance=MATCH_RADIUS_ARCSEC * u.arcsec,
                               colRA1="ra", colDec1="dec")
            xm_df = xm.to_pandas()
            if len(xm_df) > 0:
                xm_df = xm_df.sort_values("angDist").drop_duplicates(subset="TIC", keep="first")
            xmatch_results[key] = xm_df
            print(f"  {len(xm_df)} / {len(merged)} stars matched.")
        except Exception as exc:
            print(f"  FAILED ({exc}). Treating as zero matches for this catalog and continuing.")
            xmatch_results[key] = pd.DataFrame()

    # --- Step 3: ASAS-SN, per star, cached + resumable + retried ---
    print(f"\nCross-matching against ASAS-SN (II/366/catv2021) star by star (cached, resumable)...")
    asassn_cache = {}
    if asassn_cache_path.exists():
        prior = pd.read_csv(asassn_cache_path)
        for _, r in prior.iterrows():
            asassn_cache[int(r["TIC"])] = r.to_dict()
        n_ok = sum(1 for r in asassn_cache.values() if r.get("asassn_queried_ok") in (True, "True"))
        print(f"  Found existing cache with {len(asassn_cache)} star(s) already queried "
              f"({n_ok} succeeded) - successes are reused, failures are retried.")

    write_header = not asassn_cache_path.exists()
    v = Vizier(columns=["*"], row_limit=-1)
    # a retried star gets a NEW row appended to the cache; on the next load the
    # later row wins (rows are read in file order), so the cache stays valid
    def needs_query(tic):
        c = asassn_cache.get(tic)
        return c is None or c.get("asassn_queried_ok") not in (True, "True")
    todo = [row for _, row in merged.iterrows() if needs_query(int(row["TIC"]))]
    print(f"  {len(todo)} star(s) to query this run (new, or failed last time).")

    n_done_this_run = 0
    start_time = time.time()
    for row in todo:
        tic = int(row["TIC"])
        coord = SkyCoord(ra=row["ra"] * u.deg, dec=row["dec"] * u.deg, frame="icrs")
        res = query_asassn_with_retry(v, coord, tic)
        res["TIC"] = tic
        append_asassn_row(asassn_cache_path, res, write_header)
        write_header = False
        asassn_cache[tic] = res
        n_done_this_run += 1
        if not res["asassn_queried_ok"]:
            print(f"    WARNING: TIC {tic} ASAS-SN query failed after retries: {res['asassn_error']}")
        if n_done_this_run % 50 == 0 and n_done_this_run < len(todo):
            elapsed = time.time() - start_time
            rate = elapsed / n_done_this_run
            eta = rate * (len(todo) - n_done_this_run)
            print(f"    ... {n_done_this_run}/{len(todo)} queried this run, "
                  f"{elapsed/60:.1f} min elapsed, ~{eta/60:.0f} min remaining "
                  f"(safe to stop anytime - resume by re-running this script)")
        time.sleep(0.05)  # be polite to the CDS server

    # count only the stars in THIS run's trustworthy list (the shared cache also
    # holds stars that earlier F3 versions passed and this one does not)
    this_run = [asassn_cache.get(int(t), {}) for t in merged["TIC"]]
    n_query_failures = sum(1 for r in this_run if r.get("asassn_queried_ok") not in (True, "True"))
    n_matches = sum(1 for r in this_run if r.get("asassn_match") in (True, "True"))
    print(f"  {n_matches} / {len(merged)} stars matched. "
          f"({n_query_failures} star(s) never resolved after retries, treated as no-match)")

    # --- Step 3b: TESS-specific catalogs, exact TIC match ---
    print(f"\nLoading TESS-specific catalogs (matched by exact TIC ID)...")
    processed_dir = project_root / "data" / "processed"
    tess_eb = load_tess_eb(processed_dir)
    toi = load_toi(processed_dir)
    tess_eb_by_tic = {} if tess_eb is None else {int(r["TIC"]): r for _, r in tess_eb.iterrows()}
    toi_by_tic = {} if toi is None else {int(k): g for k, g in toi.groupby("TIC")}
    if tess_eb is not None:
        print(f"  {sum(1 for t in merged['TIC'] if int(t) in tess_eb_by_tic)} / {len(merged)} "
              f"stars in the TESS EB catalog.")
    if toi is not None:
        print(f"  {sum(1 for t in merged['TIC'] if int(t) in toi_by_tic)} / {len(merged)} "
              f"stars are TOIs.")
    catalogs_skipped = [n for n, c in [("TESS EB", tess_eb), ("TOI", toi)] if c is None]

    blend_path = processed_dir / "diag_blend_results.csv"
    contaminated = set()
    if blend_path.exists():
        b = pd.read_csv(blend_path)
        contaminated = set(b.loc[b["blend_status"] == "LIKELY_CONTAMINATION", "TIC"].astype(int))
        print(f"  Blend check (diag_blend_results.csv): {len(contaminated)} star(s) match a known "
              f"variable neighbour's period.")
    else:
        print("  NOTE: diag_blend_results.csv not found - CONTAMINATED verdicts not applied "
              "(run diag_blend.py to enable).")

    # --- Step 4: assemble the per-star verdict ---
    vsx = xmatch_results.get("vsx", pd.DataFrame())
    gveb = xmatch_results.get("gaia_veb", pd.DataFrame())
    gcls = xmatch_results.get("gaia_class", pd.DataFrame())

    out_rows = []
    for _, row in merged.iterrows():
        tic = int(row["TIC"])
        our_period = row["bls_period"]

        vsx_row = vsx[vsx["TIC"] == tic] if len(vsx) else pd.DataFrame()
        gveb_row = gveb[gveb["TIC"] == tic] if len(gveb) else pd.DataFrame()
        gcls_row = gcls[gcls["TIC"] == tic] if len(gcls) else pd.DataFrame()
        asn = asassn_cache.get(tic, {})

        vsx_type = vsx_row["Type"].iloc[0] if len(vsx_row) else None
        vsx_period = vsx_row["Period"].iloc[0] if len(vsx_row) and "Period" in vsx_row else None
        vsx_name = vsx_row["Name"].iloc[0] if len(vsx_row) else None

        asn_match = asn.get("asassn_match") in (True, "True")
        asn_type = asn.get("asassn_type") if asn_match else None
        asn_period = asn.get("asassn_period") if asn_match else None
        asn_name = asn.get("asassn_name") if asn_match else None
        # pandas re-reads NaN-like blanks from the cache CSV as float nan -
        # normalize those back to a clean None/empty rather than "nan" text
        if pd.isna(asn_type):
            asn_type = None
        if pd.isna(asn_period):
            asn_period = None

        gaia_class = gcls_row["Class"].iloc[0] if len(gcls_row) else None
        gaia_class_score = gcls_row["ClassSc"].iloc[0] if len(gcls_row) else None

        has_gaia_veb = len(gveb_row) > 0
        gaia_veb_period = None
        if has_gaia_veb and "Freq" in gveb_row and pd.notna(gveb_row["Freq"].iloc[0]) and gveb_row["Freq"].iloc[0] != 0:
            gaia_veb_period = 1.0 / gveb_row["Freq"].iloc[0]

        vsx_eb, vsx_ell, vsx_ep, vsx_known = classify_tokens(type_tokens(vsx_type))
        asn_eb, asn_ell, asn_ep, asn_known = classify_tokens(type_tokens(asn_type))
        gaia_eb = gaia_class == GAIA_ECL_CLASS
        gaia_ell = gaia_class == GAIA_ELL_CLASS
        gaia_ep = gaia_class == GAIA_EP_CLASS
        gaia_known = pd.notna(gaia_class) if gaia_class is not None else False

        teb = tess_eb_by_tic.get(tic)
        tess_eb_match = teb is not None
        tess_eb_period = teb["tess_eb_period"] if tess_eb_match else None
        tess_eb_morph = teb["tess_eb_morph"] if tess_eb_match else None

        toi_rows = toi_by_tic.get(tic)
        toi_match = toi_rows is not None
        if toi_match:
            tr = best_toi_row(toi_rows, our_period)
            toi_id, toi_tess_disp = tr["toi"], tr["toi_tess_disp"]
            toi_tfopwg_disp, toi_period = tr["toi_tfopwg_disp"], tr["toi_period"]
        else:
            toi_id = toi_tess_disp = toi_tfopwg_disp = toi_period = None
        toi_is_eb = toi_match and toi_tess_disp == "EB"
        toi_planet_like = toi_match and (toi_tfopwg_disp in TOI_PLANET_LIKE_TFOPWG or
                                         (pd.isna(toi_tfopwg_disp) and toi_tess_disp in TOI_PLANET_LIKE_TESS))

        known_as_eb = has_gaia_veb or vsx_eb or asn_eb or gaia_eb or tess_eb_match or toi_is_eb
        known_ellipsoidal = (not known_as_eb) and (vsx_ell or asn_ell or gaia_ell)
        exoplanet_conflict = vsx_ep or asn_ep or gaia_ep or toi_planet_like
        any_known = vsx_known or asn_known or gaia_known or has_gaia_veb

        if known_as_eb:
            verdict = "KNOWN_EB"
        elif known_ellipsoidal:
            verdict = "KNOWN_ELLIPSOIDAL"
        elif toi_match:
            verdict = "KNOWN_TOI"
        elif any_known:
            verdict = "KNOWN_OTHER_TYPE"
        else:
            verdict = "NOVEL"
        if verdict == "NOVEL" and tic in contaminated:
            verdict = "CONTAMINATED"

        # VizieR marks a masked/missing numeric cell as the literal string
        # '--' (astropy's standard display form for a masked value). That
        # string survives the ASAS-SN cache's CSV round trip - pd.notna('--')
        # is True (it's a real, non-null string), so the old check let it
        # through and float('--') crashed the whole run partway through
        # the very last, cheapest step, after every slow network call had
        # already completed. Catching the conversion failure per-candidate
        # (rather than trusting pd.notna alone) makes this robust against
        # '--' and any other non-numeric placeholder a catalog might use,
        # from any of the three sources, not just the one that broke first.
        period_source, catalog_period = None, None
        # TESS-derived periods first: same instrument, most directly comparable
        for src, per in [("tess_eb", tess_eb_period), ("toi", toi_period), ("vsx", vsx_period),
                         ("gaia_veb", gaia_veb_period), ("asassn", asn_period)]:
            if per is None or pd.isna(per):
                continue
            try:
                candidate_period = float(per)
            except (ValueError, TypeError):
                continue
            period_source, catalog_period = src, candidate_period
            break
        period_check = best_period_ratio_flag(our_period, catalog_period) if catalog_period else "no_catalog_period"

        out_rows.append({
            "TIC": tic,
            "bls_period": our_period,
            "bls_depth": row["bls_depth"],
            "bls_snr": row["bls_snr"],
            "n_eclipses_observed": row["n_eclipses_observed"],
            "gap_edge_suspect": bool(row["gap_edge_suspect"]) if pd.notna(row["gap_edge_suspect"]) else False,
            "verdict": verdict,
            "exoplanet_conflict": bool(exoplanet_conflict),
            "vsx_match": len(vsx_row) > 0,
            "vsx_name": vsx_name,
            "vsx_type": vsx_type,
            "vsx_period": vsx_period,
            "asassn_match": asn_match,
            "asassn_queried_ok": asn.get("asassn_queried_ok") in (True, "True"),
            "asassn_name": asn_name,
            "asassn_type": asn_type,
            "asassn_period": asn_period,
            "gaia_veb_match": has_gaia_veb,
            "gaia_veb_period": gaia_veb_period,
            "gaia_class_match": pd.notna(gaia_class) if gaia_class is not None else False,
            "gaia_class": gaia_class,
            "gaia_class_score": gaia_class_score,
            "tess_eb_match": tess_eb_match,
            "tess_eb_period": tess_eb_period,
            "tess_eb_morph": tess_eb_morph,
            "toi_match": toi_match,
            "toi": toi_id,
            "toi_tess_disp": toi_tess_disp,
            "toi_tfopwg_disp": toi_tfopwg_disp,
            "toi_period": toi_period,
            "period_check_source": period_source,
            "period_check": period_check,
        })

    result = pd.DataFrame(out_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)

    # --- Step 5: report ---
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    n = len(result)
    n_known_eb = int((result["verdict"] == "KNOWN_EB").sum())
    n_ell = int((result["verdict"] == "KNOWN_ELLIPSOIDAL").sum())
    n_other = int((result["verdict"] == "KNOWN_OTHER_TYPE").sum())
    n_toi = int((result["verdict"] == "KNOWN_TOI").sum())
    n_cont = int((result["verdict"] == "CONTAMINATED").sum())
    n_novel = int((result["verdict"] == "NOVEL").sum())
    n_conflict = int(result["exoplanet_conflict"].sum())
    n_unresolved = int((~result["asassn_queried_ok"]).sum())
    n_novel_caution = int(((result["verdict"] == "NOVEL") & result["gap_edge_suspect"]).sum())

    print("\n" + "=" * 70)
    print("F4f NOVELTY CROSS-MATCH SUMMARY")
    print("=" * 70)
    print(f"{n} trustworthy detections checked against VSX, ASAS-SN, Gaia DR3 (veb + classifier), "
          f"the TESS EB catalog and the TOI list")
    if catalogs_skipped:
        print(f"  ** WARNING: catalog(s) SKIPPED this run (no download, no cache): "
              f"{', '.join(catalogs_skipped)} - NOVEL counts below are an upper bound **")
    print(f"  KNOWN_EB (confirmed elsewhere as eclipsing/ellipsoidal-orbit binary): {n_known_eb}")
    print(f"  KNOWN_ELLIPSOIDAL (catalogued as ellipsoidal, not formally eclipsing): {n_ell}")
    print(f"  KNOWN_TOI (already a TESS Object of Interest):                       {n_toi}")
    print(f"  KNOWN_OTHER_TYPE (catalogued, but as a different kind of variable):   {n_other}")
    print(f"  CONTAMINATED (period matches a known variable neighbour):            {n_cont}")
    print(f"  NOVEL (no match in any of the 5 catalogs):                           {n_novel}")
    print(f"    of which carry the gap-edge CAUTION flag:                          {n_novel_caution}")
    if n_conflict:
        print(f"  ** EXOPLANET_CONFLICT: {n_conflict} star(s) an independent pipeline calls a planet host, not a binary **")
    if n_unresolved:
        print(f"  NOTE: {n_unresolved} star(s) never got a working ASAS-SN answer after retries - "
              f"treated as no-match there. Re-run this script later - failed stars are "
              f"retried automatically.")

    if n_conflict:
        print("\n--- EXOPLANET CONFLICTS (check these first) ---")
        print(result[result["exoplanet_conflict"]][
            ["TIC", "bls_period", "bls_depth", "bls_snr", "vsx_type", "gaia_class"]
        ].to_string(index=False))

    if n_toi:
        print(f"\n--- KNOWN_TOI ({n_toi}): signal already flagged by the TESS team ---")
        print(result[result["verdict"] == "KNOWN_TOI"][
            ["TIC", "bls_period", "bls_depth", "toi", "toi_tess_disp", "toi_tfopwg_disp",
             "toi_period", "period_check"]
        ].to_string(index=False))

    if n_cont:
        print(f"\n--- CONTAMINATED ({n_cont}): real signal, but from a known variable neighbour ---")
        print(result[result["verdict"] == "CONTAMINATED"][
            ["TIC", "bls_period", "bls_depth", "bls_snr"]].to_string(index=False))

    if n_other:
        print(f"\n--- KNOWN_OTHER_TYPE ({n_other}): catalogued as something else - worth a second look ---")
        print(result[result["verdict"] == "KNOWN_OTHER_TYPE"][
            ["TIC", "bls_period", "bls_snr", "vsx_type", "asassn_type", "gaia_class"]
        ].to_string(index=False))

    known_with_period = result[(result["verdict"].isin(["KNOWN_EB", "KNOWN_ELLIPSOIDAL"])) &
                                (result["period_check"] != "no_catalog_period")]
    if len(known_with_period):
        print(f"\n--- Independent period cross-check for the {len(known_with_period)} known binaries with a catalog period ---")
        print(known_with_period[["TIC", "bls_period", "period_check_source", "period_check"]].to_string(index=False))

    novel = result[result["verdict"] == "NOVEL"].sort_values("bls_snr", ascending=False)
    if len(novel):
        print(f"\n--- Top NOVEL candidates by SNR (strongest, cleanest first) ---")
        print(novel[["TIC", "bls_period", "bls_depth", "bls_snr", "n_eclipses_observed",
                     "gap_edge_suspect"]].head(15).to_string(index=False))
        if n_novel_caution:
            print(f"\n--- NOVEL with gap-edge CAUTION flag ({n_novel_caution}): check the folded plot first ---")
            print(novel[novel["gap_edge_suspect"]][["TIC", "bls_period", "bls_depth", "bls_snr",
                  "n_eclipses_observed"]].to_string(index=False))

    print("\nNOTE ON 'NOVEL': this means 'not found in VSX / ASAS-SN / Gaia DR3 / TESS EB catalog /")
    print("TOI list' only.")
    print("These catalogs are incomplete, especially for fainter or crowded fields,")
    print("so a NOVEL verdict is evidence of an uncatalogued star, not proof of a genuinely")
    print("new astrophysical discovery. Trust it in proportion to the star's own F3 quality")
    print("(SNR, n_in_transit, clean folded light curve) - a high-SNR novel detection is a")
    print("much stronger candidate than a marginal one that merely wasn't caught elsewhere.")

    print(f"\nFull results written to: {out_path}")


if __name__ == "__main__":
    main()