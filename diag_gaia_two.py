import sys
import time
from datetime import datetime, timezone

from astroquery.mast import Catalogs
from astroquery.gaia import Gaia
from astropy.coordinates import SkyCoord
import astropy.units as u

RADIUS_ARCSEC = 5.0

def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

def resolve_tic(tic):
    result = Catalogs.query_criteria(catalog="Tic", ID=str(tic)).to_pandas()
    if len(result) == 0:
        return None
    row = result.iloc[0]
    return float(row["ra"]), float(row["dec"]), float(row["Tmag"])

def try_cone_search(tic, ra, dec):
    coord = SkyCoord(ra=ra * u.degree, dec=dec * u.degree, frame="icrs")
    radius = u.Quantity(RADIUS_ARCSEC, u.arcsec)
    t0 = now()
    try:
        job = Gaia.cone_search_async(coord, radius=radius)
        results = job.get_results()
        t1 = now()
        print("[%s -> %s] TIC %s cone_search_async: OK, %d row(s)" % (t0, t1, tic, len(results)))
        return True
    except Exception as exc:
        t1 = now()
        print("[%s -> %s] TIC %s cone_search_async: FAILED: %s: %s" % (t0, t1, tic, type(exc).__name__, exc))
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: py diag_gaia_two.py <known_good_tic> <problem_tic> [rounds]")
        sys.exit(1)

    good_tic = sys.argv[1]
    bad_tic = sys.argv[2]
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    print("Resolving coordinates via MAST for both targets...")
    good_coords = resolve_tic(good_tic)
    bad_coords = resolve_tic(bad_tic)

    if good_coords is None:
        print("TIC %s not found in MAST TIC catalog." % good_tic)
        sys.exit(1)
    if bad_coords is None:
        print("TIC %s not found in MAST TIC catalog." % bad_tic)
        sys.exit(1)

    print("TIC %s (known-good): RA=%s Dec=%s Tmag=%s" % (good_tic, good_coords[0], good_coords[1], good_coords[2]))
    print("TIC %s (problem):    RA=%s Dec=%s Tmag=%s" % (bad_tic, bad_coords[0], bad_coords[1], bad_coords[2]))
    print("")
    print("Interleaving %d round(s) of cone_search_async, alternating targets..." % rounds)
    print("")

    good_ok = 0
    good_fail = 0
    bad_ok = 0
    bad_fail = 0

    for i in range(1, rounds + 1):
        print("--- Round %d ---" % i)
        if try_cone_search(good_tic, good_coords[0], good_coords[1]):
            good_ok += 1
        else:
            good_fail += 1
        time.sleep(1.0)

        if try_cone_search(bad_tic, bad_coords[0], bad_coords[1]):
            bad_ok += 1
        else:
            bad_fail += 1
        time.sleep(1.0)
        print("")

    print("=== Summary ===")
    print("TIC %s (known-good): %d OK, %d FAILED" % (good_tic, good_ok, good_fail))
    print("TIC %s (problem):    %d OK, %d FAILED" % (bad_tic, bad_ok, bad_fail))
    print("")
    if good_fail == 0 and bad_fail == rounds:
        print("Interpretation: known-good target succeeded every time while the problem target")
        print("failed every time, interleaved in the same run. This points to something specific")
        print("to TIC %s (its Gaia entry or sky position), not general archive instability." % bad_tic)
    elif good_fail > 0 and bad_fail > 0:
        print("Interpretation: both targets failed at least once during this run. This points to")
        print("general archive/session instability rather than something specific to TIC %s." % bad_tic)
    elif good_fail == 0 and bad_fail == 0:
        print("Interpretation: both targets succeeded this time. TIC %s's earlier failures may have" % bad_tic)
        print("been transient after all - rerun a few more times to build confidence.")
    else:
        print("Interpretation: mixed result, no clean pattern. Rerun with more rounds if unclear.")

if __name__ == "__main__":
    main()