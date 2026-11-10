import io
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import f15_neighbours as nb

# Gaia DR3 cross-match of the survivors.
#
# Three things, each independent of the TESS pixels this pipeline processed:
#   1. Identification and astrometric health: which Gaia star is the target, its
#      parallax, RUWE (a high value hints at an unresolved companion or triple).
#   2. Contamination from Gaia itself. The TIC neighbour test (f15) uses the TIC,
#      which is built from Gaia DR2 and lacks DR3 detections; this repeats it with
#      DR3 neighbours (G stands in for Tmag; the two differ by a few tenths of a
#      magnitude, which is small next to the factors of ten that decide viability).
#   3. What Gaia already says about the star: its variability class (vari_summary,
#      vari_classifier_result), whether it is in the DR3 eclipsing-binary table
#      (vari_eclipsing_binary, with a period to compare), whether it has a
#      two-body orbit (nss_two_body_orbit), and its radial-velocity variability
#      fields. Gaia DR4 (2 December 2026) will extend all of these.
#
# Only gaia_source positions are queried per star; the three small tables are
# queried once for all identified source ids.

TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
MATCH_RADIUS_ARCSEC = 6.0       # TIC positions are epoch 2000; Gaia DR3 is epoch 2016
NEIGHBOUR_RADIUS_ARCSEC = 63.0  # same as the TIC neighbour test
NEIGHBOUR_DELTA_MAG = 8.0       # fainter than this cannot supply an eclipse (required depth > 100%)
G_MINUS_T_GUESS = 0.3           # typical G - Tmag for matching only
RUWE_ELEVATED = 1.4
SOURCE_COLUMNS = ("source_id, ra, dec, phot_g_mean_mag, bp_rp, parallax, parallax_error, pmra, pmdec, ruwe, "
                  "astrometric_excess_noise, phot_variable_flag, non_single_star, radial_velocity, "
                  "radial_velocity_error, rv_nb_transits, rv_chisq_pvalue, rv_renormalised_gof")


def tap_csv(adql, attempts=5, pause=6.0):
    last = None
    for k in range(attempts):
        try:
            r = requests.post(TAP_URL, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}, timeout=180)
            if r.status_code == 200 and r.text.strip():
                return pd.read_csv(io.StringIO(r.text))
            last = "HTTP %s %s" % (r.status_code, r.text[:200])
        except Exception as exc:   # noqa: BLE001 - network, retry
            last = exc
        time.sleep(pause * (k + 1))
    raise RuntimeError("Gaia TAP failed: %s" % last)


def cone_query(ra, dec, radius_arcsec, g_max=None):
    where = "1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', %.7f, %.7f, %.8f))" % (ra, dec, radius_arcsec / 3600.0)
    if g_max is not None:
        where += " AND phot_g_mean_mag < %.3f" % g_max
    return "SELECT %s FROM gaiadr3.gaia_source WHERE %s" % (SOURCE_COLUMNS, where)


def separations_arcsec(ra0, dec0, ra, dec):
    cosd = np.cos(np.deg2rad(dec0))
    return np.hypot((np.asarray(ra) - ra0) * cosd, np.asarray(dec) - dec0) * 3600.0


def pick_target(sources, ra, dec, tmag):
    """The Gaia source that is the TIC target: close in position and close in
    brightness (G ~ Tmag + 0.3). Returns (row or None, quality), quality in
    {MATCHED, AMBIGUOUS, NONE}."""
    if sources is None or len(sources) == 0:
        return None, "NONE"
    d = sources.copy()
    d["sep"] = separations_arcsec(ra, dec, d["ra"], d["dec"])
    d = d[d["sep"] <= MATCH_RADIUS_ARCSEC]
    d = d[np.isfinite(d["phot_g_mean_mag"])]
    if len(d) == 0:
        return None, "NONE"
    d["score"] = d["sep"] / MATCH_RADIUS_ARCSEC + np.abs(d["phot_g_mean_mag"] - (tmag + G_MINUS_T_GUESS))
    d = d.sort_values("score")
    best = d.iloc[0]
    quality = "MATCHED"
    if abs(best["phot_g_mean_mag"] - (tmag + G_MINUS_T_GUESS)) > 1.5:
        quality = "AMBIGUOUS"
    elif len(d) > 1 and d.iloc[1]["score"] - best["score"] < 0.3 and abs(d.iloc[1]["phot_g_mean_mag"] - best["phot_g_mean_mag"]) < 1.0:
        quality = "AMBIGUOUS"
    return best, quality


def gaia_neighbours(sources, target_row):
    """Neighbours as the f15 assess_star table: nbr_TIC (the Gaia id), nbr_Tmag (G), sep."""
    d = sources[sources["source_id"] != target_row["source_id"]].copy()
    d["sep_arcsec"] = separations_arcsec(target_row["ra"], target_row["dec"], d["ra"], d["dec"])
    d = d[(d["sep_arcsec"] > 0.05) & (d["sep_arcsec"] <= NEIGHBOUR_RADIUS_ARCSEC) & np.isfinite(d["phot_g_mean_mag"])]
    return pd.DataFrame({"nbr_TIC": d["source_id"].astype("int64"), "nbr_Tmag": d["phot_g_mean_mag"].astype(float),
                         "sep_arcsec": d["sep_arcsec"].astype(float)})


def assess_contamination(d_obs, g_target, offset, diff_snr, nbrs):
    """The f15 test at its headline floor with Gaia neighbours."""
    r = nb.assess_star(d_obs, g_target, offset, diff_snr, nbrs, nb.HEADLINE_FLOOR_ARCSEC)
    r["status"] = nb.classify(r)
    r["n_neighbours"] = int(len(nbrs))
    return r


def rv_variability(row):
    """Gaia DR3 radial-velocity fields as a simple, honest summary. Variability statistics
    exist only for bright stars (G_RVS <= 12); a faint star has none and this says so."""
    rv, n = row.get("radial_velocity"), row.get("rv_nb_transits")
    if rv is None or not np.isfinite(rv):
        return {"has_rv": False, "variable": None, "note": "no Gaia RV"}
    p = row.get("rv_chisq_pvalue")
    if p is None or not np.isfinite(p):
        return {"has_rv": True, "variable": None, "rv": float(rv), "n_transits": None if n is None else int(n),
                "note": "RV from combined spectra only; no variability statistic at this brightness"}
    return {"has_rv": True, "variable": bool(p < 0.01), "rv": float(rv), "rv_chisq_pvalue": float(p),
            "n_transits": None if n is None else int(n), "note": "chi-square p<0.01 means the epoch RVs scatter more than their errors"}


def table_rows(table, ids, cols, batch=150):
    """Rows of a small Gaia table for a list of source ids, in batches."""
    out = []
    ids = sorted({int(i) for i in ids})
    for k in range(0, len(ids), batch):
        chunk = ids[k:k + batch]
        q = "SELECT %s FROM gaiadr3.%s WHERE source_id IN (%s)" % (cols, table, ",".join(str(i) for i in chunk))
        try:
            out.append(tap_csv(q))
        except RuntimeError:
            raise
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def period_relation(p_tess, p_gaia, tol=0.02):
    """How a Gaia period relates to the TESS one: 'same', 'half', 'double', or 'unrelated'."""
    if not (p_tess and p_gaia and p_tess > 0 and p_gaia > 0):
        return None
    r = p_gaia / p_tess
    for name, x in (("same", 1.0), ("half", 0.5), ("double", 2.0)):
        if abs(r / x - 1.0) < tol:
            return name
    return "unrelated"


# ---------------------------------------------------------------- driver

def build(inputs, pixel, root):
    """inputs: DataFrame (tic, ra, dec, Tmag, bls_period, bls_depth, tier) -> report dict."""
    cache = root / "data" / "processed" / "f18_cache"
    cache.mkdir(parents=True, exist_ok=True)

    def one(row):
        tic = int(row["tic"])
        path = cache / ("TIC%d.csv" % tic)
        if path.exists():
            return tic, pd.read_csv(path)
        g_max = float(row["Tmag"]) + G_MINUS_T_GUESS + NEIGHBOUR_DELTA_MAG
        df = tap_csv(cone_query(float(row["ra"]), float(row["dec"]), NEIGHBOUR_RADIUS_ARCSEC, g_max))
        df.to_csv(path, index=False, lineterminator="\n")
        return tic, df

    rows = [r for _, r in inputs.iterrows()]
    with ThreadPoolExecutor(max_workers=4) as ex:
        sources = dict(ex.map(one, rows))

    stars, target_ids = {}, {}
    for row in rows:
        tic = int(row["tic"])
        tgt, quality = pick_target(sources[tic], float(row["ra"]), float(row["dec"]), float(row["Tmag"]))
        if tgt is None:
            stars[str(tic)] = {"match": "NONE"}
            continue
        target_ids[tic] = int(tgt["source_id"])
        p = pixel.get(tic)
        nbrs = gaia_neighbours(sources[tic], tgt)
        contamination = None
        if p is not None:
            contamination = assess_contamination(float(row["bls_depth"]), float(tgt["phot_g_mean_mag"]),
                                                 float(p["centroid_offset_arcsec"]), float(p["diff_peak_snr"]), nbrs)
        stars[str(tic)] = {
            "match": quality, "source_id": int(tgt["source_id"]), "g_mag": float(tgt["phot_g_mean_mag"]),
            "bp_rp": None if not np.isfinite(tgt["bp_rp"]) else float(tgt["bp_rp"]),
            "parallax_mas": None if not np.isfinite(tgt["parallax"]) else float(tgt["parallax"]),
            "parallax_over_error": None if not np.isfinite(tgt["parallax"]) else float(tgt["parallax"] / tgt["parallax_error"]),
            "ruwe": None if not np.isfinite(tgt["ruwe"]) else float(tgt["ruwe"]),
            "ruwe_elevated": bool(np.isfinite(tgt["ruwe"]) and tgt["ruwe"] > RUWE_ELEVATED),
            "phot_variable_flag": str(tgt["phot_variable_flag"]),
            "non_single_star": int(tgt["non_single_star"]),
            "rv": rv_variability(tgt),
            "contamination": contamination,
            "closest_gaia_neighbour": None if len(nbrs) == 0 else {
                "sep_arcsec": float(nbrs["sep_arcsec"].min()),
                "delta_g": float(nbrs.loc[nbrs["sep_arcsec"].idxmin(), "nbr_Tmag"] - tgt["phot_g_mean_mag"])},
        }

    ids = list(target_ids.values())
    tables = {}
    for name, cols in (("vari_summary", "source_id, num_selected_g_fov, in_vari_classification_result, in_vari_eclipsing_binary"),
                       ("vari_eclipsing_binary", "source_id, frequency, model_type, reference_time"),
                       ("vari_classifier_result", "source_id, best_class_name, best_class_score"),
                       ("nss_two_body_orbit", "source_id, nss_solution_type, period, period_error")):
        tables[name] = table_rows(name, ids, cols)
    by_id = {}
    for name, df in tables.items():
        for _, r in df.iterrows():
            by_id.setdefault(int(r["source_id"]), {})[name] = r.to_dict()
    for tic_s, s in stars.items():
        sid = s.get("source_id")
        if sid is None:
            continue
        rec = by_id.get(sid, {})
        s["gaia_variability"] = rec.get("vari_classifier_result", {}).get("best_class_name")
        eb = rec.get("vari_eclipsing_binary")
        if eb and np.isfinite(eb.get("frequency", np.nan)) and eb["frequency"] > 0:
            p_g = 1.0 / float(eb["frequency"])
            s["gaia_eb"] = {"period_days": p_g, "relation": period_relation(float(inputs[inputs["tic"] == int(tic_s)]["bls_period"].iloc[0]), p_g)}
        else:
            s["gaia_eb"] = None
        nss = rec.get("nss_two_body_orbit")
        s["gaia_nss"] = None if not nss else {"solution_type": str(nss.get("nss_solution_type")), "period_days": None if not np.isfinite(nss.get("period", np.nan)) else float(nss["period"])}

    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "data_release": "Gaia DR3",
            "method": {"match": "nearest Gaia DR3 source within %.0f arcsec scored by separation and |G - (Tmag + %.1f)|" % (MATCH_RADIUS_ARCSEC, G_MINUS_T_GUESS),
                       "contamination": "f15 neighbour test (Gaussian PSF, 6 arcsec centroid floor) with Gaia DR3 neighbours within 63 arcsec; G stands in for Tmag",
                       "dr4": "Gaia DR4 is due 2 December 2026; rerun after release"},
            "stars": stars}


def summarise(rep, tic_status_f15=None):
    s = rep["stars"]
    matched = [v for v in s.values() if v.get("match") in ("MATCHED", "AMBIGUOUS")]
    cnt = {}
    for v in matched:
        c = v.get("contamination")
        if c:
            cnt[c["status"]] = cnt.get(c["status"], 0) + 1
    return {"stars": len(s), "matched": sum(v.get("match") == "MATCHED" for v in s.values()),
            "ambiguous": sum(v.get("match") == "AMBIGUOUS" for v in s.values()),
            "none": sum(v.get("match") == "NONE" for v in s.values()),
            "ruwe_elevated": sum(bool(v.get("ruwe_elevated")) for v in matched),
            "contamination_status_gaia": cnt,
            "in_gaia_eb_table": sum(bool(v.get("gaia_eb")) for v in matched),
            "gaia_eb_period_relation": _count([v["gaia_eb"]["relation"] for v in matched if v.get("gaia_eb")]),
            "in_gaia_nss_orbit": sum(bool(v.get("gaia_nss")) for v in matched),
            "with_gaia_rv": sum(bool(v.get("rv", {}).get("has_rv")) for v in matched),
            "rv_variable": sum(v.get("rv", {}).get("variable") is True for v in matched),
            "gaia_variability_classes": _count([v.get("gaia_variability") for v in matched if v.get("gaia_variability")])}


def _count(items):
    out = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: py f18_gaia_dr3.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    dash = pd.DataFrame(json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"])
    man = pd.read_csv(root / "data" / "processed" / "f2c_manifest.csv")[["TIC", "Tmag"]]
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv")[["TIC", "bls_period", "bls_depth"]]
    inputs = dash.merge(man, left_on="tic", right_on="TIC").merge(vet, on="TIC")
    pix = pd.read_csv(root / "data" / "processed" / "diag_pixel_results_v2.csv")
    pix = pix[pix["role"] == "candidate"].drop_duplicates("TIC").set_index("TIC")
    pixel = {int(t): r for t, r in pix.iterrows()}
    rep = build(inputs, pixel, root)
    rep["summary"] = summarise(rep)
    path = root / "site" / "public" / "data" / "gaia_dr3.json"
    path.write_text(json.dumps(rep, indent=1, default=lambda x: None if x is None else float(x)) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rep["summary"], indent=1))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
