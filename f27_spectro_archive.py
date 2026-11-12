"""Archival spectroscopy for the survivors (no telescope needed).

Collects, for every survivor, whatever spectroscopic information public surveys already hold:

  Gaia DR3 (ESA TAP)   radial_velocity, rv_amplitude_robust (peak-to-peak of the epoch RVs), number of
                       RV transits, chi-square p-value, vbroad, template Teff; FLAME radius and mass;
                       any two-body orbit in nss_two_body_orbit (SB1, SB2, EclipsingSpectro ...).
  APOGEE DR17          allStar summary and per-visit radial velocities (III/286).
  GALAH DR4            per-star and per-spectrum radial velocities (J/other/PASA/42.51).
  GALAH DR3            per-star values (J/MNRAS/506/150).
  LAMOST DR11          low- and medium-resolution catalogues, one row per spectrum (V/162).
  RAVE DR6             (III/283).

Survey queries are cone searches of 3 arcsec around the TIC position on the CfA VizieR mirror; every
returned row is kept as it came back in data/processed/f27_cache/TIC<n>.json, so later steps never
depend on the network and nothing is dropped silently. Rows from different surveys are not merged
here; f28 decides what each row is worth.

Usage:  python f27_spectro_archive.py <root> [--only TIC,TIC]
Writes: data/processed/f27_cache/TIC<n>.json and data/processed/f27_spectro_archive.json (summary).
"""

import io
import sys
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

VIZIER = "https://vizier.cfa.harvard.edu/viz-bin/votable"
TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
RADIUS_ARCSEC = 3.0
SURVEYS = {
    "apogee_dr17": "III/286",
    "galah_dr4": "J/other/PASA/42.51",
    "galah_dr3": "J/MNRAS/506/150",
    "lamost_dr11": "V/162",
    "rave_dr6": "III/283",
}
GAIA_SOURCE_COLS = ("source_id, ra, dec, phot_g_mean_mag, grvs_mag, radial_velocity, radial_velocity_error, "
                    "rv_nb_transits, rv_method_used, rv_chisq_pvalue, rv_renormalised_gof, rv_amplitude_robust, "
                    "rv_template_teff, vbroad, vbroad_error, teff_gspphot, logg_gspphot, non_single_star")
GAIA_AP_COLS = "source_id, teff_gspspec, logg_gspspec, radius_flame, radius_flame_lower, radius_flame_upper, mass_flame, mass_flame_lower, mass_flame_upper, lum_flame"
GAIA_NSS_COLS = ("source_id, nss_solution_type, period, period_error, eccentricity, eccentricity_error, arg_periastron, "
                 "semi_amplitude_primary, semi_amplitude_primary_error, semi_amplitude_secondary, semi_amplitude_secondary_error, "
                 "center_of_mass_velocity, mass_ratio, t_periastron, goodness_of_fit")


def _get(url, attempts=4, pause=5.0, timeout=90):
    last = None
    for k in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "star-vetter-archive/1.0"})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:  # noqa: BLE001 - retried, then raised
            last = e
            time.sleep(pause * (k + 1))
    raise last


def _clean(v):
    if isinstance(v, (bytes, np.bytes_)):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if v is np.ma.masked:
        return None
    return v


def vizier_cone(source, ra, dec, radius=RADIUS_ARCSEC):
    """{table_id: [row dicts]} for every table of the catalogue that has a row within `radius`."""
    from astropy.io.votable import parse
    q = {"-source": source, "-c": "%.6f %+.6f" % (ra, dec), "-c.rs": "%g" % radius, "-out.all": "", "-out.max": "200"}
    raw = _get(VIZIER + "?" + urllib.parse.urlencode(q))
    out = {}
    for t in parse(io.BytesIO(raw)).iter_tables():
        arr = t.array
        if not len(arr):
            continue
        rows = []
        for r in arr:
            rows.append({n: _clean(r[n]) for n in arr.dtype.names})
        out[t.ID or t.name] = rows
    return out


def gaia_query(cols, table, ids):
    q = "SELECT %s FROM %s WHERE source_id IN (%s)" % (cols, table, ",".join(str(int(i)) for i in ids))
    raw = _get(TAP + "?" + urllib.parse.urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": q}))
    # source ids are 19-digit integers: read them as text first, never through a float
    df = pd.read_csv(io.BytesIO(raw), dtype={"source_id": str})
    df["source_id"] = df["source_id"].map(int)
    return df


def gaia_block(ids):
    """{source_id: {"source": {...}, "ap": {...} or None, "nss": [...]}} in chunks of 200."""
    ids = [int(i) for i in ids if i]
    out = {i: {"source": None, "ap": None, "nss": []} for i in ids}
    for k in range(0, len(ids), 200):
        chunk = ids[k:k + 200]
        for name, cols, table in (("source", GAIA_SOURCE_COLS, "gaiadr3.gaia_source"),
                                  ("ap", GAIA_AP_COLS, "gaiadr3.astrophysical_parameters"),
                                  ("nss", GAIA_NSS_COLS, "gaiadr3.nss_two_body_orbit")):
            df = gaia_query(cols, table, chunk)
            for r in df.to_dict("records"):          # iterrows would turn the 19-digit id into a float
                rec = {c: _clean(r[c]) for c in df.columns}
                sid = int(r["source_id"])
                if name == "nss":
                    out[sid]["nss"].append(rec)
                else:
                    out[sid][name] = rec
    return out


def summarise_star(rec):
    s = {"surveys_with_rows": sorted(k for k, v in rec["surveys"].items() if v), "n_rows": {}}
    for k, v in rec["surveys"].items():
        s["n_rows"][k] = sum(len(rows) for rows in (v or {}).values()) if isinstance(v, dict) else 0
    g = rec.get("gaia") or {}
    src = g.get("source") or {}
    s["gaia_rv_amplitude_kms"] = src.get("rv_amplitude_robust")
    s["gaia_rv_transits"] = src.get("rv_nb_transits")
    s["gaia_nss_types"] = [n.get("nss_solution_type") for n in g.get("nss") or []]
    return s


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    only = None
    if "--only" in args:
        only = {int(x) for x in args[args.index("--only") + 1].split(",")}
    proc = root / "data" / "processed"
    cache = proc / "f27_cache"
    cache.mkdir(parents=True, exist_ok=True)
    sky = json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]
    gaia_dr3 = json.loads((root / "site" / "public" / "data" / "gaia_dr3.json").read_text(encoding="utf-8"))["stars"]
    stars = [r for r in sky if only is None or int(r["tic"]) in only]
    sid_of = {int(r["tic"]): (gaia_dr3.get(str(int(r["tic"]))) or {}).get("source_id") for r in stars}

    print("Gaia DR3: %d source ids" % sum(1 for v in sid_of.values() if v), flush=True)
    gaia = gaia_block([v for v in sid_of.values() if v])

    summary = {}
    for i, r in enumerate(stars):
        tic = int(r["tic"])
        path = cache / ("TIC%d.json" % tic)
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
        else:
            rec = {"tic": tic, "ra": r["ra"], "dec": r["dec"], "radius_arcsec": RADIUS_ARCSEC, "surveys": {}}
            for name, src in SURVEYS.items():
                try:
                    rec["surveys"][name] = vizier_cone(src, float(r["ra"]), float(r["dec"]))
                except Exception as e:  # noqa: BLE001 - recorded, never silent
                    rec["surveys"][name] = {"_error": repr(e)}
        sid = sid_of.get(tic)
        rec["gaia_source_id"] = sid
        rec["gaia"] = gaia.get(int(sid)) if sid else None
        path.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8", newline="\n")
        summary[str(tic)] = summarise_star(rec)
        print("%d/%d TIC %d: %s" % (i + 1, len(stars), tic, ", ".join("%s=%d" % (k, n) for k, n in summary[str(tic)]["n_rows"].items() if n) or "none"), flush=True)

    tot = {name: sum(1 for s in summary.values() if s["n_rows"].get(name)) for name in SURVEYS}
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "n_stars": len(summary),
           "stars_with_rows_per_survey": tot,
           "gaia_with_rv_amplitude": sum(1 for s in summary.values() if s["gaia_rv_amplitude_kms"] is not None),
           "gaia_with_nss_orbit": sum(1 for s in summary.values() if s["gaia_nss_types"]),
           "stars": summary}
    (proc / "f27_spectro_archive.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in out.items() if k != "stars"}, indent=1))


if __name__ == "__main__":
    main()
