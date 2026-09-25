import sys
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

MATCH_RADIUS_ARCSEC = 5.0
EB_TOKENS = {"EA", "EB", "EW", "E"}
ELL_TOKENS = {"ELL"}
EP_TOKENS = {"EP"}

GAIA_ECL_CLASS = "ECL"
GAIA_ELL_CLASS = "ELL"
GAIA_EP_CLASS = "EP"


def type_tokens(type_str):
    if type_str is None:
        return set()
    s = str(type_str).strip().upper()
    if s == "" or s.lower() == "nan":
        return set()
    s = s.replace(":", "").replace("?", "")
    for sep in ["/", "+", "|", ","]:
        s = s.replace(sep, " ")
    return set(s.split())


def classify_tokens(tokens):
    is_eb = bool(tokens & EB_TOKENS)
    is_ell = bool(tokens & ELL_TOKENS)
    is_ep = bool(tokens & EP_TOKENS)
    is_known = len(tokens) > 0
    return is_eb, is_ell, is_ep, is_known


def best_period_ratio_flag(our_period, catalog_period, tol=0.01):
    if catalog_period is None or not np.isfinite(catalog_period) or catalog_period <= 0:
        return "no_catalog_period"
    if our_period is None or not np.isfinite(our_period) or our_period <= 0:
        return "no_bls_period"
    ratio = our_period / catalog_period
    for label, target in [("1x", 1.0), ("2x", 2.0), ("0.5x", 0.5), ("3x", 3.0), ("1/3x", 1.0 / 3.0)]:
        if abs(ratio - target) / target < tol:
            return f"agrees_{label}"
    return f"disagrees(ratio={ratio:.4f})"


def main():
    project_root = Path(sys.argv[1]).resolve()
    vet_path = project_root / "data" / "processed" / "f3e_vetting_results.csv"
    out_path = project_root / "data" / "processed" / "f4_novelty_results.csv"

    vet = pd.read_csv(vet_path)
    trustworthy = vet[(vet["status"] == "OK") & (vet["depth_flagged_implausible"] == False)].copy()
    trustworthy["TIC"] = trustworthy["TIC"].astype(int)

    print("=" * 70)
    print(f"F4 NOVELTY CROSS-MATCH: {len(trustworthy)} trustworthy detections to check")
    print("=" * 70)

    if len(trustworthy) == 0:
        print("\nNo trustworthy detections found in f3e_vetting_results.csv (status==OK and")
        print("depth_flagged_implausible==False). Nothing to cross-match. Stopping.")
        sys.exit(1)

    tic_ids = trustworthy["TIC"].tolist()
    print(f"\nQuerying MAST TIC catalog for {len(tic_ids)} stars' coordinates...")
    try:
        tic_info = Catalogs.query_criteria(catalog="Tic", ID=tic_ids)
    except Exception as exc:
        print(f"\nCould not reach the MAST TIC catalog: {exc}")
        print("This needs outbound internet access to mast.stsci.edu. Check your")
        print("connection (and firewall/proxy settings if any) and try again.")
        sys.exit(1)
    tic_info = tic_info[["ID", "ra", "dec", "Tmag"]].to_pandas()
    tic_info = tic_info.rename(columns={"ID": "TIC"})
    tic_info["TIC"] = tic_info["TIC"].astype(int)

    missing = set(tic_ids) - set(tic_info["TIC"])
    if missing:
        print(f"WARNING: {len(missing)} TIC(s) not found in the TIC catalog, skipped: {sorted(missing)}")

    merged = trustworthy.merge(tic_info, on="TIC", how="inner")
    print(f"Resolved coordinates for {len(merged)} / {len(trustworthy)} stars.")

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

    print(f"\nCross-matching against ASAS-SN (II/366/catv2021) star by star...")
    v = Vizier(columns=["*"], row_limit=-1)
    asassn_rows = []
    asassn_failures = []
    for _, row in merged.iterrows():
        tic = int(row["TIC"])
        try:
            coord = SkyCoord(ra=row["ra"] * u.deg, dec=row["dec"] * u.deg, frame="icrs")
            r = v.query_region(coord, radius=MATCH_RADIUS_ARCSEC * u.arcsec,
                                catalog="II/366/catv2021")
            if len(r) > 0 and len(r[0]) > 0:
                best = r[0][np.argmin(r[0]["_r"])] if "_r" in r[0].colnames else r[0][0]
                d = {c: best[c] for c in r[0].colnames}
                d["TIC"] = tic
                asassn_rows.append(d)
        except Exception as exc:
            asassn_failures.append((tic, str(exc)))
        time.sleep(0.05)
    asassn_df = pd.DataFrame(asassn_rows)
    print(f"  {len(asassn_df)} / {len(merged)} stars matched.")
    if asassn_failures:
        print(f"  WARNING: {len(asassn_failures)} query failure(s), treated as no-match:")
        for tic, msg in asassn_failures[:5]:
            print(f"    TIC {tic}: {msg}")
        if len(asassn_failures) > 5:
            print(f"    ... and {len(asassn_failures) - 5} more")

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
        asn_row = asassn_df[asassn_df["TIC"] == tic] if len(asassn_df) else pd.DataFrame()

        vsx_type = vsx_row["Type"].iloc[0] if len(vsx_row) else None
        vsx_period = vsx_row["Period"].iloc[0] if len(vsx_row) and "Period" in vsx_row else None
        vsx_name = vsx_row["Name"].iloc[0] if len(vsx_row) else None

        asn_type = asn_row["Type"].iloc[0] if len(asn_row) else None
        asn_period = asn_row["Per"].iloc[0] if len(asn_row) and "Per" in asn_row else None
        asn_name = asn_row["ASASSN-V"].iloc[0] if len(asn_row) else None

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

        known_as_eb = has_gaia_veb or vsx_eb or asn_eb or gaia_eb
        known_ellipsoidal = (not known_as_eb) and (vsx_ell or asn_ell or gaia_ell)
        exoplanet_conflict = vsx_ep or asn_ep or gaia_ep
        any_known = vsx_known or asn_known or gaia_known or has_gaia_veb

        if known_as_eb:
            verdict = "KNOWN_EB"
        elif known_ellipsoidal:
            verdict = "KNOWN_ELLIPSOIDAL"
        elif any_known:
            verdict = "KNOWN_OTHER_TYPE"
        else:
            verdict = "NOVEL"

        period_source, catalog_period = None, None
        for src, per in [("vsx", vsx_period), ("gaia_veb", gaia_veb_period), ("asassn", asn_period)]:
            if per is not None and pd.notna(per):
                period_source, catalog_period = src, float(per)
                break
        period_check = best_period_ratio_flag(our_period, catalog_period) if catalog_period else "no_catalog_period"

        out_rows.append({
            "TIC": tic,
            "bls_period": our_period,
            "bls_depth": row["bls_depth"],
            "bls_snr": row["bls_snr"],
            "verdict": verdict,
            "exoplanet_conflict": bool(exoplanet_conflict),
            "vsx_match": len(vsx_row) > 0,
            "vsx_name": vsx_name,
            "vsx_type": vsx_type,
            "vsx_period": vsx_period,
            "asassn_match": len(asn_row) > 0,
            "asassn_name": asn_name,
            "asassn_type": asn_type,
            "asassn_period": asn_period,
            "gaia_veb_match": has_gaia_veb,
            "gaia_veb_period": gaia_veb_period,
            "gaia_class_match": pd.notna(gaia_class) if gaia_class is not None else False,
            "gaia_class": gaia_class,
            "gaia_class_score": gaia_class_score,
            "period_check_source": period_source,
            "period_check": period_check,
        })

    result = pd.DataFrame(out_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    n = len(result)
    n_known_eb = int((result["verdict"] == "KNOWN_EB").sum())
    n_ell = int((result["verdict"] == "KNOWN_ELLIPSOIDAL").sum())
    n_other = int((result["verdict"] == "KNOWN_OTHER_TYPE").sum())
    n_novel = int((result["verdict"] == "NOVEL").sum())
    n_conflict = int(result["exoplanet_conflict"].sum())

    print("\n" + "=" * 70)
    print("F4 NOVELTY CROSS-MATCH SUMMARY")
    print("=" * 70)
    print(f"{n} trustworthy detections checked against VSX, ASAS-SN, Gaia DR3 (veb + classifier)")
    print(f"  KNOWN_EB (confirmed elsewhere as eclipsing/ellipsoidal-orbit binary): {n_known_eb}")
    print(f"  KNOWN_ELLIPSOIDAL (catalogued as ellipsoidal, not formally eclipsing): {n_ell}")
    print(f"  KNOWN_OTHER_TYPE (catalogued, but as a different kind of variable):   {n_other}")
    print(f"  NOVEL (no match in any of the 3 catalogs):                           {n_novel}")
    if n_conflict:
        print(f"  ** EXOPLANET_CONFLICT: {n_conflict} star(s) an independent pipeline calls a planet host, not a binary **")

    if n_conflict:
        print("\n--- EXOPLANET CONFLICTS (check these first) ---")
        print(result[result["exoplanet_conflict"]][
            ["TIC", "bls_period", "bls_depth", "bls_snr", "vsx_type", "gaia_class"]
        ].to_string(index=False))

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
        print(novel[["TIC", "bls_period", "bls_depth", "bls_snr"]].head(15).to_string(index=False))

    print("\nNOTE ON 'NOVEL': this means 'not found in VSX / ASAS-SN / Gaia DR3' only.")
    print("These three catalogs are incomplete, especially for fainter or crowded fields,")
    print("so a NOVEL verdict is evidence of an uncatalogued star, not proof of a genuinely")
    print("new astrophysical discovery. Trust it in proportion to the star's own F3 quality")
    print("(SNR, n_in_transit, clean folded light curve) - a high-SNR novel detection is a")
    print("much stronger candidate than a marginal one that merely wasn't caught elsewhere.")

    print(f"\nFull results written to: {out_path}")


if __name__ == "__main__":
    main()