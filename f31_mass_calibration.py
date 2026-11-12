"""Test the mass step of f28_physical.py on eclipsing binaries whose masses and radii are known.

The candidates' Kepler masses came out about 1.4 times the main-sequence expectation (median), and the Physics
page says masses are not recovered. This asks why, using systems where the answer is known:

  1. Radius step. f28 takes Gaia DR3's FLAME radius (which assumes one star) and removes the companion's light:
     R1 = R_Gaia / sqrt(1 + light ratio). Compared here with the published R1.
  2. Mass step. With the PUBLISHED fractional radius r1 (so the light-curve fit is not being tested), the
     Kepler total mass from that R1 is compared with the published total mass. Mass scales as R1 cubed, so a
     few percent in radius becomes ten or more percent in mass.
  3. The main-sequence check f28 applies to candidates (f28.main_sequence_check) is run on the same inputs,
     to see whether it reports "inconsistent" for systems that are in fact fine.

Published values: data/benchmarks/f31_published_properties.json (sources there). Gaia values are fetched once (Gaia archive, or the VizieR copy of
the same catalog when the archive is down) and cached in data/benchmarks/f31_gaia.json.

Usage: python f31_mass_calibration.py <root>    -> data/processed/f31_mass_calibration.json
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

import crossmatch as cx
import f28_physical as f28

TAP = "https://gea.esac.esa.int/tap-server/tap/sync"


def gaia_row_archive(ra, dec, attempts=6):
    """Gaia DR3 row from the ESA archive (TAP)."""
    q = ("SELECT TOP 1 g.source_id, g.phot_g_mean_mag, g.ruwe, g.non_single_star, a.radius_flame, a.radius_flame_lower, "
         "a.radius_flame_upper, a.radius_gspphot, a.teff_gspphot, a.mass_flame FROM gaiadr3.gaia_source AS g LEFT OUTER JOIN "
         "gaiadr3.astrophysical_parameters AS a ON a.source_id = g.source_id WHERE 1 = CONTAINS(POINT('ICRS', g.ra, g.dec), "
         "CIRCLE('ICRS', %.7f, %.7f, 0.0015)) ORDER BY g.phot_g_mean_mag" % (ra, dec))
    for k in range(attempts):
        try:
            r = requests.post(TAP, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": q}, timeout=120)
            if r.ok and r.text.lstrip().startswith("{"):
                d = r.json()
                cols = [c["name"] for c in d["metadata"]]
                return dict(zip(cols, d["data"][0])) if d["data"] else None
        except Exception:  # noqa: BLE001 - retried, then reported
            pass
        time.sleep(10 * (k + 1))
    raise RuntimeError("Gaia archive unavailable")


def gaia_row_vizier(ra, dec, attempts=10):
    """The same Gaia DR3 quantities from VizieR (I/355/gaiadr3 and I/355/paramp, which hold the same catalog), through
    the hardened request path of crossmatch.py: an error reported inside a response raises instead of reading as 'no row'."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    v = cx.vizier_for(cx.MIRROR_SERVER, columns=["**"], row_limit=-1)
    c = SkyCoord(ra * u.deg, dec * u.deg)
    tabs = {}
    for cat in ("I/355/gaiadr3", "I/355/paramp"):
        for k in range(attempts):
            try:
                res = v.query_region(c, radius=5.4 * u.arcsec, catalog=cat, cache=False)
                tabs[cat] = res[0].to_pandas() if len(res) else None
                break
            except Exception:  # noqa: BLE001 - retried, then reported
                time.sleep(2 * (k + 1))
        else:
            raise RuntimeError("VizieR mirror unavailable for " + cat)
    g = tabs["I/355/gaiadr3"]
    if g is None or not len(g):
        return None
    g = g.sort_values("Gmag").iloc[0]
    row = {"source_id": int(g["Source"]), "phot_g_mean_mag": float(g["Gmag"]), "ruwe": float(g["RUWE"]),
           "non_single_star": int(g["NSS"]), "radius_flame": None, "radius_flame_lower": None, "radius_flame_upper": None,
           "radius_gspphot": None, "teff_gspphot": None, "mass_flame": None, "via": "VizieR I/355 (Harvard-CfA mirror)"}
    a = tabs["I/355/paramp"]
    if a is not None and len(a):
        a = a[a["Source"] == g["Source"]]
        if len(a):
            a = a.iloc[0]
            for dst, src in (("radius_flame", "Rad-Flame"), ("radius_flame_lower", "b_Rad-Flame"), ("radius_flame_upper", "B_Rad-Flame"),
                             ("radius_gspphot", "Rad"), ("mass_flame", "Mass-Flame")):
                if src in a and not np.isnan(a[src]):
                    row[dst] = float(a[src])
            if "Teff" in a and not np.isnan(a["Teff"]):
                row["teff_gspphot"] = float(a["Teff"])
    return row


def gaia_row(ra, dec):
    """Gaia archive first; if it is down (it was, 2026-11-12), the VizieR copy of the same catalog."""
    try:
        return gaia_row_archive(ra, dec, attempts=2)
    except RuntimeError:
        return gaia_row_vizier(ra, dec)


def main():
    root = Path(sys.argv[1]).resolve()
    props = json.loads((root / "data" / "benchmarks" / "f31_published_properties.json").read_text(encoding="utf-8"))
    cache_p = root / "data" / "benchmarks" / "f31_gaia.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    rows = []
    for s in props["systems"]:
        if s["name"] not in cache:
            try:
                cache[s["name"]] = gaia_row(s["ra"], s["dec"])
                cache_p.write_text(json.dumps(cache, indent=1) + "\n", encoding="utf-8", newline="\n")
            except RuntimeError:
                rows.append({"name": s["name"], "status": "GAIA_ARCHIVE_UNAVAILABLE"})
                continue
        g = cache[s["name"]] or {}
        row = {"name": s["name"], "gaia_source_id": g.get("source_id"), "ruwe": g.get("ruwe"), "non_single_star": g.get("non_single_star"),
               "published": {k: s[k] for k in ("r1", "R1", "R2", "M1", "M2", "light_ratio", "period")}}
        R = g.get("radius_flame")
        if R is None:
            row["status"] = "NO_GAIA_RADIUS"
            rows.append(row)
            continue
        R1 = R / np.sqrt(1.0 + s["light_ratio"])
        a = R1 / s["r1"]
        mt = f28.total_mass(a, s["period"])
        m_pub = s["M1"] + s["M2"]
        ms = f28.main_sequence_check(mt, float(R1), s["light_ratio"], g.get("mass_flame"))
        ms_true = f28.main_sequence_check(m_pub, float(s["R1"]), s["light_ratio"], g.get("mass_flame"))
        row.update({"status": "OK", "gaia_radius_flame": R, "gaia_mass_flame": g.get("mass_flame"),
                    "R1_from_gaia": float(R1), "R1_ratio": float(R1 / s["R1"]),
                    "kepler_mass_from_gaia": float(mt), "published_total_mass": m_pub, "mass_ratio": float(mt / m_pub),
                    "ms_check_on_gaia_inputs": ms, "ms_check_on_true_mass_and_radius": ms_true})
        rows.append(row)
    ok = [r for r in rows if r["status"] == "OK"]
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "what": "f28's Gaia-radius mass method applied to eclipsing binaries with published masses and radii",
           "rows": rows,
           "summary": {"n": len(ok),
                       "median_R1_ratio": float(np.median([r["R1_ratio"] for r in ok])) if ok else None,
                       "median_mass_ratio": float(np.median([r["mass_ratio"] for r in ok])) if ok else None,
                       "ms_ratio_on_gaia_inputs": [r["ms_check_on_gaia_inputs"].get("ms_ratio") for r in ok],
                       "ms_ratio_on_true_values": [r["ms_check_on_true_mass_and_radius"].get("ms_ratio") for r in ok]}}
    (root / "data" / "processed" / "f31_mass_calibration.json").write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["summary"], indent=1, default=float))


if __name__ == "__main__":
    main()
