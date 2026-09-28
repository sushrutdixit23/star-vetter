"""
f12_ground_survey_period.py

Independently confirms each confirmed candidate's TESS-derived orbital
period against real ZTF ground-survey photometry (IRSA's public
light-curve cone-search API, no account needed). This is a genuinely
different line of evidence than the odd/even alias check (same TESS
data) or Gaia RUWE (astrometric, not photometric): a different
instrument, different years, different systematics.

Method, validated for real against TIC 437150434 before writing this:
a Lomb-Scargle periodogram does NOT work here - sparse ground-survey
cadence (a handful of epochs per orbit) almost never samples the
actual eclipse window, so a periodogram built for smooth sinusoidal
signals finds essentially no power at the true period even when the
eclipse is large. The real signal only shows up as individual epochs
landing far below the baseline brightness, clustered at a consistent
phase when folded at the known period - for TIC 437150434, two
independent ZTF epochs landed within 0.003 phase of each other, both
30+ sigma below baseline, which is not something noise does.

Verdict logic per band: fold at the known period, compute
(mag - baseline) / magerr per point, flag points above SIGMA_THRESHOLD.

v1 required only >=2 flagged points within a fixed phase window
(PHASE_CLUSTER_WINDOW). That rule turned out to have essentially no
discriminating power once a band has more than a handful of outliers:
with N outlier points scattered at random phases, the chance that SOME
pair lands within a fixed window purely by coincidence grows fast with
N (Monte Carlo: N=2 -> 9.5%, N=5 -> 69.2%, N=8 -> 97.3%, N=10+ -> ~100%
at a 0.05 window) - so most "confirmations" among high-outlier-count
bands were statistical near-certainties, not evidence.

v1.2 replaces the fixed window with an exact significance test: for N
points on a circle of circumference 1, the probability that the
tightest (cyclically) adjacent gap is <= g by pure chance is the
classical circular-spacings result
  P(min_gap <= g) = 1 - (1 - N*g)^(N-1)   for g <= 1/N
(verified against 200,000-trial Monte Carlo simulation to ~3 decimal
places across N=2,3,5,8,15 and g=0.01,0.03,0.05). CONFIRMED now
requires this p-value to be below SIGNIFICANCE_THRESHOLD, i.e. the
tightest pair of outliers must be tighter than chance would produce
given how many outliers that band actually has. Requiring at least
two outliers (MIN_CLUSTERED_OUTLIERS) still guards against a single
bad point (cosmic ray, blend, instrumental glitch) alone triggering a
confirmation, since a lone point has no gap to test.

v1 tests only the reported period itself, not harmonics - keeping this
shippable; testing 0.5x/2x etc. against ZTF is a natural extension
once real results across all confirmed candidates are in hand.

v1.1: the first full run hit repeated read timeouts on IRSA starting
with the very first target - a target that had just succeeded fine,
standalone, in three separate diagnostic scripts run minutes earlier.
That points to server-side rate-limiting from the burst of back-to-back
requests (diagnostics plus this run), not a broken query. Slowed the
per-request pace (1s -> 3s) and retry backoff (5s -> 8s), and gave
requests more time to complete (60s -> 90s) before calling them a
timeout, rather than assuming a fast, tight polling loop is safe
against a public, unauthenticated archive service.

Cost-safe / resumable: caches to data/processed/f12_ground_survey_period.json,
keyed by TIC as a string. Only CONFIRMED / NOT_CONFIRMED / NO_DATA /
INSUFFICIENT_DATA / TIC_NOT_FOUND count as done; ERROR entries (network
failures) are retried on every run, same pattern as f11_gaia_context.py.

Requires: pip install requests pandas (already installed)

Usage:
  py f12_ground_survey_period.py <project_root> [--force]
"""

import json
import sys
import time
import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astroquery.mast import Catalogs

ZTF_BASE_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
SEARCH_RADIUS_DEG = 3.0 / 3600.0
MIN_POINTS_PER_BAND = 20
SIGMA_THRESHOLD = 5.0
SIGNIFICANCE_THRESHOLD = 0.01
MIN_CLUSTERED_OUTLIERS = 2
MAX_RETRIES = 3
RETRY_DELAY_SEC = 8.0
REQUEST_DELAY_SEC = 3.0
REQUEST_TIMEOUT_SEC = 90
DONE_STATUSES = {"CONFIRMED", "NOT_CONFIRMED", "NO_DATA", "INSUFFICIENT_DATA", "TIC_NOT_FOUND"}


def get_tic_coords(tic):
    result = Catalogs.query_criteria(catalog="Tic", ID=str(tic)).to_pandas()
    if len(result) == 0:
        return None
    row = result.iloc[0]
    return float(row["ra"]), float(row["dec"]), float(row["Tmag"])


def fetch_ztf_once(ra, dec):
    params = {"POS": f"CIRCLE {ra} {dec} {SEARCH_RADIUS_DEG}", "FORMAT": "CSV"}
    resp = requests.get(ZTF_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    if not resp.text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(resp.text))


def fetch_ztf_with_retry(ra, dec):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_ztf_once(ra, dec)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                print(f"(attempt {attempt}/{MAX_RETRIES} failed, retrying in {RETRY_DELAY_SEC:.0f}s) ", end="", flush=True)
                time.sleep(RETRY_DELAY_SEC)
    raise last_exc


def analyze_band(mjd, mag, magerr, period):
    baseline_mag = float(np.median(mag))
    typical_err = float(np.median(magerr))
    phase = (mjd % period) / period
    sigma = (mag - baseline_mag) / np.where(magerr > 0, magerr, np.nan)

    outlier_mask = sigma >= SIGMA_THRESHOLD
    outlier_idx = np.where(outlier_mask)[0]
    n = int(len(outlier_idx))

    band_result = {
        "n_points": int(len(mag)),
        "baseline_mag": round(baseline_mag, 4),
        "typical_err": round(typical_err, 4),
        "n_outliers": n,
        "p_value": None,
        "verdict": "NOT_CONFIRMED",
        "clustered_points": [],
    }

    if n < MIN_CLUSTERED_OUTLIERS:
        return band_result

    outlier_phases = phase[outlier_idx]
    order = np.argsort(outlier_phases)
    sorted_idx = outlier_idx[order]
    sorted_phases = outlier_phases[order]

    # Gaps between cyclically-adjacent outliers (sorted-neighbor gaps, plus
    # the wraparound gap from the last point back to the first). The
    # smallest of these is the "tightest cluster" statistic.
    gaps = np.diff(sorted_phases)
    wrap_gap = 1.0 - sorted_phases[-1] + sorted_phases[0]
    all_gaps = np.concatenate([gaps, [wrap_gap]])
    g_min = float(all_gaps.min())
    gap_pos = int(all_gaps.argmin())

    # P(min circular gap among n points on a unit circle is <= g_min),
    # i.e. the chance a set of n randomly-phased outliers would produce a
    # pair at least this tight purely by coincidence. Exact for g_min <=
    # 1/n; g_min > 1/n cannot happen when there is any real gap this small
    # relative to n, but the max(0, ...) guards the edge case numerically.
    p_value = 1.0 - max(0.0, 1.0 - n * g_min) ** (n - 1)
    band_result["p_value"] = round(p_value, 6)

    if p_value < SIGNIFICANCE_THRESHOLD:
        band_result["verdict"] = "CONFIRMED"
        i, j = gap_pos, (gap_pos + 1) % n
        pair_idx = sorted(set([int(sorted_idx[i]), int(sorted_idx[j])]))
        band_result["clustered_points"] = [
            {
                "phase": round(float(phase[k]), 4),
                "mag": round(float(mag[k]), 4),
                "sigma": round(float(sigma[k]), 1),
            }
            for k in pair_idx
        ]

    return band_result


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    positional = [a for a in argv if a != "--force"]
    if len(positional) != 1:
        print("Usage: py f12_ground_survey_period.py <project_root> [--force]")
        sys.exit(1)
    root = Path(positional[0]).resolve()
    site_data = root / "site" / "public" / "data"
    cache_path = root / "data" / "processed" / "f12_ground_survey_period.json"
    site_out_path = site_data / "ground_survey_period.json"

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    candidates = index.get("candidates", [])
    print(f"Loaded {len(candidates)} confirmed candidates from {site_data / 'index.json'}")

    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        n_done = sum(1 for v in cache.values() if v.get("status") in DONE_STATUSES)
        n_retry = sum(1 for v in cache.values() if v.get("status") not in DONE_STATUSES)
        print(f"Found existing cache: {n_done} resolved, {n_retry} will be retried (transient failures).")

    def is_done(tic):
        entry = cache.get(str(tic))
        return entry is not None and entry.get("status") in DONE_STATUSES

    todo = [c for c in candidates if force or not is_done(c["tic"])]
    print(f"{len(todo)} target(s) to query this run.\n")

    for i, cand in enumerate(todo, 1):
        tic = cand["tic"]
        period = float(cand["period_days"])
        print(f"[{i}/{len(todo)}] TIC {tic} (period={period:.6f}d) ... ", end="", flush=True)
        try:
            coords = get_tic_coords(tic)
            if coords is None:
                cache[str(tic)] = {"status": "TIC_NOT_FOUND"}
                print("TIC not found in TIC catalog")
                continue
            ra, dec, tmag = coords

            df = fetch_ztf_with_retry(ra, dec)
            if len(df) == 0:
                cache[str(tic)] = {"status": "NO_DATA", "ra": ra, "dec": dec}
                print("no ZTF data at this position")
                continue

            df = df[df["catflags"] == 0].copy()

            bands = {}
            any_tested = False
            any_confirmed = False
            for band, group in df.groupby("filtercode"):
                if len(group) < MIN_POINTS_PER_BAND:
                    continue
                any_tested = True
                mjd = group["mjd"].to_numpy()
                mag = group["mag"].to_numpy()
                magerr = group["magerr"].to_numpy()
                band_result = analyze_band(mjd, mag, magerr, period)
                bands[band] = band_result
                if band_result["verdict"] == "CONFIRMED":
                    any_confirmed = True

            if not any_tested:
                cache[str(tic)] = {
                    "status": "INSUFFICIENT_DATA",
                    "ra": ra, "dec": dec,
                    "n_points_total": int(len(df)),
                }
                print(f"only {len(df)} good points total, none reach {MIN_POINTS_PER_BAND}/band")
                continue

            overall = "CONFIRMED" if any_confirmed else "NOT_CONFIRMED"
            cache[str(tic)] = {
                "status": overall,
                "period_days_tested": period,
                "ra": ra, "dec": dec,
                "bands": bands,
            }
            band_summary = ", ".join(f"{b}:{r['n_points']}pt/{r['verdict']}" for b, r in bands.items())
            print(f"{overall} ({band_summary})")

        except Exception as exc:
            cache[str(tic)] = {"status": "ERROR", "error": str(exc)[:300]}
            print(f"FAILED after {MAX_RETRIES} attempts: {exc}")

        finally:
            # Runs after every target - including the "continue" branches above
            # (TIC_NOT_FOUND / NO_DATA / INSUFFICIENT_DATA) - so a long run of
            # cheap no-data results can never sit unflushed if this process is
            # interrupted before reaching a CONFIRMED/NOT_CONFIRMED/ERROR result.
            time.sleep(REQUEST_DELAY_SEC)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    site_data.mkdir(parents=True, exist_ok=True)
    site_out_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    confirmed = [v for v in cache.values() if v.get("status") == "CONFIRMED"]
    not_confirmed = [v for v in cache.values() if v.get("status") == "NOT_CONFIRMED"]
    no_data = [v for v in cache.values() if v.get("status") == "NO_DATA"]
    insufficient = [v for v in cache.values() if v.get("status") == "INSUFFICIENT_DATA"]
    not_found = [v for v in cache.values() if v.get("status") == "TIC_NOT_FOUND"]
    still_failed = [v for v in cache.values() if v.get("status") == "ERROR"]

    print("\n" + "=" * 72)
    print("F12 GROUND-SURVEY PERIOD CONFIRMATION SUMMARY")
    print("=" * 72)
    print(f"Total candidates: {len(candidates)}")
    print(f"Independently CONFIRMED via ZTF phase-fold: {len(confirmed)}")
    print(f"Tested but not confirmed (no clustered outliers found): {len(not_confirmed)}")
    print(f"No ZTF data at this position (likely too far south): {len(no_data)}")
    print(f"Insufficient good points to test (<{MIN_POINTS_PER_BAND}/band): {len(insufficient)}")
    print(f"TIC not found in MAST: {len(not_found)}")
    print(f"Still failing after retries (will retry next run): {len(still_failed)}")
    print(f"\nWrote {cache_path}")
    print(f"Wrote {site_out_path}")
    print("\nNOTE for the UI side: ground_survey_period.json is new data, keyed")
    print("by TIC as a string. Not wired into any candidate page yet - that's")
    print("a UI change, out of scope here.")


if __name__ == "__main__":
    main()