import sys

from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia
from astroquery.mast import Catalogs

tic = sys.argv[1] if len(sys.argv) > 1 else "119459681"

print(f"Resolving TIC {tic} coordinates via MAST...")
result = Catalogs.query_criteria(catalog="Tic", ID=str(tic)).to_pandas()
row = result.iloc[0]
ra, dec, tmag = float(row["ra"]), float(row["dec"]), float(row["Tmag"])
print(f"RA={ra} Dec={dec} Tmag={tmag}")

coord = SkyCoord(ra=ra * u.degree, dec=dec * u.degree, frame="icrs")

print("\n--- Attempt 1: cone_search_async (what f11 uses) ---")
try:
    job = Gaia.cone_search_async(coord, radius=u.Quantity(5.0, u.arcsec))
    res = job.get_results()
    print(f"OK: {len(res)} result(s)")
    if len(res):
        print(res[["source_id", "dist", "parallax", "ruwe"]])
except Exception as exc:
    print(f"FAILED: {type(exc).__name__}: {exc}")

print("\n--- Attempt 2: plain ADQL query via launch_job_async ---")
try:
    query = f"""
    SELECT source_id, ra, dec, parallax, parallax_error, phot_g_mean_mag, bp_rp, ruwe,
           DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra}, {dec})) AS sep_deg
    FROM gaiadr3.gaia_source
    WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, 0.0013889))
    ORDER BY sep_deg ASC
    """
    job2 = Gaia.launch_job_async(query)
    res2 = job2.get_results()
    print(f"OK: {len(res2)} result(s)")
    if len(res2):
        print(res2)
except Exception as exc:
    print(f"FAILED: {type(exc).__name__}: {exc}")