"""
f11_gaia_context.py

Adds real Gaia DR3 astrophysical context to every confirmed candidate on
the site. Right now a candidate's page shows numbers about the detection
(period, depth, SNR) but nothing about the star itself. This adds real
characterization: how far away it is (parallax -> distance), how bright
it actually is (absolute magnitude, not just apparent), its color
(BP-RP), and RUWE - a measure of how well Gaia's own single-star
astrometric model fits the source. An elevated RUWE (> 1.4, the standard
Lindegren et al. 2018/2021 threshold) is itself independent evidence a
star is an unresolved binary, from a completely different method than
the light curve - a genuinely strong cross-check, not decoration.

v2: the Gaia archive is unstable right now (its own banner says so - in
preparation for DR4) and returns transient Error 200 / Error 500
responses under load. v1 cached these as permanent failures, so a
resumed run would never retry them. Fixed: only OK / TIC_NOT_FOUND /
NO_GAIA_MATCH count as "done"; ERROR entries are retried on every run.
Also added retry-with-backoff per query and a small delay between
requests to go easier on an archive that is already flagging itself as
fragile.

v3: distance_pc was computed from parallax whenever parallax > 0, with
no check on measurement quality. A low-S/N parallax (common alongside a
poor, high-RUWE astrometric fit) can be a tiny positive number and
invert into a wildly implausible distance - the real run against all 88
confirmed candidates produced one at 1.3 million pc, which is not a
real distance for a TESS-observed star. Fixed: distance_pc and abs_g_mag
are now only computed when parallax_snr (parallax / parallax_error) is
at least PARALLAX_SNR_THRESHOLD (5.0, the standard threshold for when a
naive 1/parallax inversion is trustworthy - Bailer-Jones/Luri et al.).
Below that, distance_pc is None with a note explaining why, and a new
distance_reliable flag records the decision explicitly. parallax_snr is
now stored whenever it can be computed at all (not just when parallax is
positive), since a low or negative-parallax high-SNR case is itself
useful diagnostic information. Also added --recompute, which reapplies
this logic to an existing cache's already-fetched raw Gaia fields with
no network calls at all - use it after a logic fix like this one instead
of re-querying an archive that is already under load.

Cost-safe / resumable: caches to data/processed/f11_gaia_context.json,
keyed by TIC as a string. Delete the cache file, or pass --force, to
re-run everything including already-successful entries (hits the network
again). Pass --recompute to reapply current derived-field logic to the
existing cache with no network calls.

Requires: pip install astroquery (already installed - used by f2c/f4f/etc)

Usage:
  py f11_gaia_context.py <project_root> [--force] [--recompute]
"""

import json
import math
import sys
import time
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia
from astroquery.mast import Catalogs

SEARCH_RADIUS_ARCSEC = 5.0
RUWE_THRESHOLD = 1.4
PARALLAX_SNR_THRESHOLD = 5.0
MAX_RETRIES = 3
RETRY_DELAY_SEC = 4.0
REQUEST_DELAY_SEC = 1.0
DONE_STATUSES = {"OK", "TIC_NOT_FOUND", "NO_GAIA_MATCH"}


def get_tic_coords(tic):
    result = Catalogs.query_criteria(catalog="Tic", ID=str(tic)).to_pandas()
    if len(result) == 0:
        return None
    row = result.iloc[0]
    return float(row["ra"]), float(row["dec"]), float(row["Tmag"])


def query_gaia_once(ra, dec, radius_arcsec):
    coord = SkyCoord(ra=ra * u.degree, dec=dec * u.degree, frame="icrs")
    radius = u.Quantity(radius_arcsec, u.arcsec)
    job = Gaia.cone_search_async(coord, radius=radius)
    results = job.get_results()
    if len(results) == 0:
        return None
    results.sort("dist")
    return results[0]


def query_gaia_with_retry(ra, dec, radius_arcsec):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return query_gaia_once(ra, dec, radius_arcsec)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                print(f"(attempt {attempt}/{MAX_RETRIES} failed, retrying in {RETRY_DELAY_SEC:.0f}s) ", end="", flush=True)
                time.sleep(RETRY_DELAY_SEC)
    raise last_exc


def safe_float(val):
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def compute_derived_fields(parallax, parallax_err, g_mag, ruwe):
    derived = {}

    parallax_snr = None
    if parallax is not None and parallax_err is not None and parallax_err > 0:
        parallax_snr = round(parallax / parallax_err, 2)
        derived["parallax_snr"] = parallax_snr

    distance_reliable = (
        parallax is not None and parallax > 0
        and parallax_snr is not None and parallax_snr >= PARALLAX_SNR_THRESHOLD
    )
    derived["distance_reliable"] = distance_reliable

    if distance_reliable:
        distance_pc = 1000.0 / parallax
        derived["distance_pc"] = round(distance_pc, 2)
        if g_mag is not None:
            derived["abs_g_mag"] = round(g_mag - 5 * math.log10(distance_pc) + 5, 3)
    else:
        derived["distance_pc"] = None
        if parallax is None:
            derived["note"] = "parallax missing - distance unreliable"
        elif parallax <= 0:
            derived["note"] = "parallax non-positive - distance unreliable"
        else:
            derived["note"] = (
                f"parallax SNR too low ({parallax_snr}) - noisy astrometric solution, "
                "distance unreliable"
            )

    if ruwe is not None:
        derived["elevated_ruwe"] = ruwe > RUWE_THRESHOLD

    return derived


def recompute_from_cache(cache):
    n = 0
    for entry in cache.values():
        if entry.get("status") != "OK":
            continue
        parallax = entry.get("parallax_mas")
        parallax_err = entry.get("parallax_error_mas")
        g_mag = entry.get("phot_g_mean_mag")
        ruwe = entry.get("ruwe")
        for key in ("distance_pc", "abs_g_mag", "parallax_snr", "distance_reliable", "elevated_ruwe", "note"):
            entry.pop(key, None)
        entry.update(compute_derived_fields(parallax, parallax_err, g_mag, ruwe))
        n += 1
    return n


def print_summary(tics, cache):
    ok = [v for v in cache.values() if v.get("status") == "OK"]
    with_distance = [v for v in ok if v.get("distance_pc") is not None]
    low_snr_excluded = [v for v in ok if v.get("distance_reliable") is False and v.get("parallax_snr") is not None]
    missing_parallax = [v for v in ok if v.get("distance_reliable") is False and v.get("parallax_snr") is None]
    elevated = [v for v in ok if v.get("elevated_ruwe")]
    no_match = [v for v in cache.values() if v.get("status") == "NO_GAIA_MATCH"]
    still_failed = [v for v in cache.values() if v.get("status") == "ERROR"]

    print("\n" + "=" * 72)
    print("F11 GAIA DR3 CONTEXT SUMMARY")
    print("=" * 72)
    print(f"Total candidates: {len(tics)}")
    print(f"Matched to a Gaia DR3 source: {len(ok)}")
    print(f"No Gaia match within {SEARCH_RADIUS_ARCSEC} arcsec: {len(no_match)}")
    print(f"Still failing after retries (will retry next run): {len(still_failed)}")
    print(f"Reliable distance (parallax SNR >= {PARALLAX_SNR_THRESHOLD}): {len(with_distance)}")
    if with_distance:
        dists = sorted(v["distance_pc"] for v in with_distance)
        print(f"  Distance range: {dists[0]:.1f} to {dists[-1]:.1f} pc (median {dists[len(dists)//2]:.1f} pc)")
    print(f"Excluded for low parallax SNR (noisy astrometric fit): {len(low_snr_excluded)}")
    print(f"Excluded for missing/non-positive parallax: {len(missing_parallax)}")
    print(f"Elevated RUWE (>{RUWE_THRESHOLD}, independent binarity evidence): {len(elevated)}")


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    recompute = "--recompute" in argv
    positional = [a for a in argv if a not in ("--force", "--recompute")]
    if len(positional) != 1:
        print("Usage: py f11_gaia_context.py <project_root> [--force] [--recompute]")
        sys.exit(1)
    root = Path(positional[0]).resolve()
    site_data = root / "site" / "public" / "data"
    cache_path = root / "data" / "processed" / "f11_gaia_context.json"
    site_out_path = site_data / "gaia_context.json"

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    candidates = index.get("candidates", [])
    tics = [int(c["tic"]) for c in candidates]
    print(f"Loaded {len(tics)} confirmed candidates from {site_data / 'index.json'}")

    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    if recompute:
        if not cache:
            print("No existing cache to recompute from. Run without --recompute first.")
            sys.exit(1)
        n = recompute_from_cache(cache)
        print(f"Recomputed derived fields for {n} OK entry(ies) from already-cached raw Gaia data (no network calls).")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        site_data.mkdir(parents=True, exist_ok=True)
        site_out_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        print(f"Wrote {cache_path}")
        print(f"Wrote {site_out_path}")
        print_summary(tics, cache)
        return

    if cache:
        n_done = sum(1 for v in cache.values() if v.get("status") in DONE_STATUSES)
        n_retry = sum(1 for v in cache.values() if v.get("status") not in DONE_STATUSES)
        print(f"Found existing cache: {n_done} resolved, {n_retry} will be retried (transient failures).")

    def is_done(tic):
        entry = cache.get(str(tic))
        return entry is not None and entry.get("status") in DONE_STATUSES

    todo = [t for t in tics if force or not is_done(t)]
    print(f"{len(todo)} target(s) to query this run.\n")

    for i, tic in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] TIC {tic} ... ", end="", flush=True)
        try:
            coords = get_tic_coords(tic)
            if coords is None:
                cache[str(tic)] = {"status": "TIC_NOT_FOUND"}
                print("TIC not found in TIC catalog")
                continue
            ra, dec, tmag = coords
            src = query_gaia_with_retry(ra, dec, SEARCH_RADIUS_ARCSEC)
            if src is None:
                cache[str(tic)] = {"status": "NO_GAIA_MATCH", "ra": ra, "dec": dec}
                print(f"no Gaia source within {SEARCH_RADIUS_ARCSEC} arcsec")
                continue

            parallax = safe_float(src["parallax"])
            parallax_err = safe_float(src["parallax_error"])
            g_mag = safe_float(src["phot_g_mean_mag"])
            bp_rp = safe_float(src["bp_rp"])
            ruwe = safe_float(src["ruwe"])
            sep_arcsec = float(src["dist"]) * 3600.0

            entry = {
                "status": "OK",
                "gaia_source_id": int(src["source_id"]),
                "separation_arcsec": round(sep_arcsec, 3),
                "parallax_mas": parallax,
                "parallax_error_mas": parallax_err,
                "phot_g_mean_mag": g_mag,
                "bp_rp": bp_rp,
                "ruwe": ruwe,
            }
            entry.update(compute_derived_fields(parallax, parallax_err, g_mag, ruwe))

            cache[str(tic)] = entry
            dist_str = f"{entry['distance_pc']} pc" if entry.get("distance_pc") is not None else "distance n/a"
            if ruwe is not None:
                ruwe_str = f"RUWE={ruwe:.2f}" + (" (ELEVATED)" if entry.get("elevated_ruwe") else "")
            else:
                ruwe_str = "RUWE n/a"
            print(f"matched, sep {sep_arcsec:.2f}arcsec, {dist_str}, {ruwe_str}")

        except Exception as exc:
            cache[str(tic)] = {"status": "ERROR", "error": str(exc)[:300]}
            print(f"FAILED after {MAX_RETRIES} attempts: {exc}")

        time.sleep(REQUEST_DELAY_SEC)

        if i % 10 == 0:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    site_data.mkdir(parents=True, exist_ok=True)
    site_out_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    print_summary(tics, cache)
    print(f"\nWrote {cache_path}")
    print(f"Wrote {site_out_path}")
    print("\nNOTE for the UI side: gaia_context.json is a new data file, keyed")
    print("by TIC as a string. Not wired into any candidate page yet - that's")
    print("a UI change, out of scope here.")


if __name__ == "__main__":
    main()