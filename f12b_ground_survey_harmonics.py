"""
f12b_ground_survey_harmonics.py

The natural extension f12_ground_survey_period.py's own docstring flagged:
v1 tested only the reported period itself. This tests each candidate's
ZTF light curve folded at 0.5x and 2x that period too, reusing the exact
fetch/analysis method already validated in f12 (same analyze_band logic,
same 5-sigma / clustered-outlier criteria) - only run against the 37
candidates f12 already found usable ZTF coverage for, since there is
nothing to test where f12 got NO_DATA or INSUFFICIENT_DATA.

Motivation beyond curiosity: f12 folds every candidate at cand["period_days"]
- the raw BLS period from index.json - even for the 14 candidates the
pipeline's own odd/even check already flagged as period-aliased (primary
and secondary eclipses differ in depth, so the true period is twice the
search period; see ephemeris.aliased / corrected_period_days in each
candidate's detail JSON). For those 14, testing 2x here is not a curiosity
run - it is testing the period the pipeline actually believes is correct,
which f12 never did. For the other, non-aliased candidates, an unexpected
confirmation at 0.5x or 2x instead of 1x would be a real anomaly: it would
mean ZTF's independent data disagrees with what the TESS-side odd/even
check concluded, worth a second look either way.

Folding at exactly half the true period always tends to stack primary and
secondary eclipses onto the same reduced phase, regardless of their
individual depths - which is exactly the mechanism that produces this kind
of alias in a BLS search in the first place. So a CONFIRMED verdict at 1x
for an aliased candidate does not by itself say whether the true period is
1x or 2x; it only says something eclipses there. Testing 2x directly is
what actually checks the corrected period.

Cost-safe / resumable: reuses ra/dec already cached by f12 (no repeat MAST
lookups), caches to data/processed/f12b_ground_survey_harmonics.json keyed
by TIC, and checkpoints after every target via a finally block - not every
10th, and not skipped by any early-exit branch - a lesson learned running
f12 itself, where checkpointing only every 10 targets (and skipping it
entirely on cheap no-data results) meant a long run of cheap results right
up against a time budget could be silently lost and redone.

Requires: pip install requests pandas (already installed)

Usage:
  py f12b_ground_survey_harmonics.py <project_root> [--force]
"""

import json
import sys
import time
import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

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
HARMONICS = [0.5, 2.0]  # 1x already covered by f12_ground_survey_period.py


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
    # Uses the same exact chance-corrected significance test as
    # f12_ground_survey_period.py (see that module's docstring for the
    # derivation/Monte Carlo verification): P(min circular gap among n
    # randomly-phased outliers <= g) = 1 - (1 - n*g)^(n-1). Because this
    # test is a property of the observed outliers' own phase gaps - not a
    # fixed window compared against - it needs no separate window-scaling
    # treatment for the 0.5x/2x periods tested here; the same function
    # used at 1x is directly correct at every multiplier.
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

    gaps = np.diff(sorted_phases)
    wrap_gap = 1.0 - sorted_phases[-1] + sorted_phases[0]
    all_gaps = np.concatenate([gaps, [wrap_gap]])
    g_min = float(all_gaps.min())
    gap_pos = int(all_gaps.argmin())

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
        print("Usage: py f12b_ground_survey_harmonics.py <project_root> [--force]")
        sys.exit(1)
    root = Path(positional[0]).resolve()
    site_data = root / "site" / "public" / "data"
    f12_cache_path = root / "data" / "processed" / "f12_ground_survey_period.json"
    cache_path = root / "data" / "processed" / "f12b_ground_survey_harmonics.json"
    site_out_path = site_data / "ground_survey_harmonics.json"

    if not f12_cache_path.exists():
        print(f"{f12_cache_path} not found - run f12_ground_survey_period.py first.")
        sys.exit(1)
    f12_cache = json.loads(f12_cache_path.read_text(encoding="utf-8"))

    usable = {tic: v for tic, v in f12_cache.items() if v.get("status") in ("CONFIRMED", "NOT_CONFIRMED")}
    print(f"{len(usable)} candidate(s) with usable ZTF coverage from f12's cache.")

    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def is_done(tic):
        entry = cache.get(tic)
        if entry is None or entry.get("status") == "ERROR":
            return False
        return set(entry.get("harmonics", {}).keys()) >= {str(h) for h in HARMONICS}

    todo = [tic for tic in usable if force or not is_done(tic)]
    print(f"{len(todo)} target(s) to query this run.\n")

    for i, tic in enumerate(todo, 1):
        f12_entry = usable[tic]
        base_period = float(f12_entry["period_days_tested"])
        ra = f12_entry["ra"]
        dec = f12_entry["dec"]

        detail_path = site_data / "candidates" / f"TIC{tic}.json"
        aliased = None
        corrected_period_days = None
        if detail_path.exists():
            eph = json.loads(detail_path.read_text(encoding="utf-8")).get("ephemeris", {})
            aliased = eph.get("aliased")
            corrected_period_days = eph.get("corrected_period_days")

        print(f"[{i}/{len(todo)}] TIC {tic} (base={base_period:.6f}d, aliased={aliased}) ... ", end="", flush=True)
        try:
            df = fetch_ztf_with_retry(ra, dec)
            df = df[df["catflags"] == 0].copy()

            harmonics_out = {}
            summary_bits = []
            for mult in HARMONICS:
                period = base_period * mult
                bands = {}
                any_confirmed = False
                for band, group in df.groupby("filtercode"):
                    if len(group) < MIN_POINTS_PER_BAND:
                        continue
                    mjd = group["mjd"].to_numpy()
                    mag = group["mag"].to_numpy()
                    magerr = group["magerr"].to_numpy()
                    band_result = analyze_band(mjd, mag, magerr, period)
                    bands[band] = band_result
                    if band_result["verdict"] == "CONFIRMED":
                        any_confirmed = True
                harmonics_out[str(mult)] = {
                    "period_days_tested": period,
                    "any_confirmed": any_confirmed,
                    "bands": bands,
                }
                summary_bits.append(f"{mult}x:{'CONFIRMED' if any_confirmed else 'not confirmed'}")

            cache[tic] = {
                "status": "DONE",
                "base_period_days": base_period,
                "base_confirmed": f12_entry["status"] == "CONFIRMED",
                "aliased_tess_side": aliased,
                "corrected_period_days": corrected_period_days,
                "harmonics": harmonics_out,
            }
            print(", ".join(summary_bits))

        except Exception as exc:
            cache[tic] = {"status": "ERROR", "error": str(exc)[:300]}
            print(f"FAILED after {MAX_RETRIES} attempts: {exc}")

        finally:
            time.sleep(REQUEST_DELAY_SEC)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    site_data.mkdir(parents=True, exist_ok=True)
    site_out_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    done = [v for v in cache.values() if v.get("status") == "DONE"]
    errored = [v for v in cache.values() if v.get("status") == "ERROR"]

    done_items = [(tic, v) for tic, v in cache.items() if v.get("status") == "DONE"]
    aliased_confirmed_at_2x = [
        (t, v) for t, v in done_items
        if v.get("aliased_tess_side") and v["harmonics"].get("2.0", {}).get("any_confirmed")
    ]
    aliased_not_confirmed_at_2x = [
        (t, v) for t, v in done_items
        if v.get("aliased_tess_side") and not v["harmonics"].get("2.0", {}).get("any_confirmed")
    ]
    unexpected_harmonic = [
        (t, v) for t, v in done_items
        if not v.get("aliased_tess_side")
        and (v["harmonics"].get("0.5", {}).get("any_confirmed") or v["harmonics"].get("2.0", {}).get("any_confirmed"))
    ]

    print("\n" + "=" * 72)
    print("F12B GROUND-SURVEY HARMONIC CHECK SUMMARY")
    print("=" * 72)
    print(f"Candidates checked: {len(done)} (of {len(usable)} with usable ZTF coverage)")
    print(f"Still failing after retries: {len(errored)}")
    print()
    print(f"TESS-side aliased candidates (true period believed = 2x tested): {sum(1 for v in done if v.get('aliased_tess_side'))}")
    print(f"  -> ZTF also confirms at the corrected (2x) period: {len(aliased_confirmed_at_2x)}")
    print(f"  -> ZTF does NOT confirm at the corrected (2x) period: {len(aliased_not_confirmed_at_2x)}")
    print()
    print(f"Non-aliased candidates showing an UNEXPECTED confirmation at 0.5x or 2x: {len(unexpected_harmonic)}")
    if unexpected_harmonic:
        for t, v in unexpected_harmonic:
            print(f"  TIC {t} base_period={v['base_period_days']:.5f}d: "
                  f"0.5x={'CONFIRMED' if v['harmonics'].get('0.5',{}).get('any_confirmed') else 'no'}, "
                  f"2x={'CONFIRMED' if v['harmonics'].get('2.0',{}).get('any_confirmed') else 'no'}")
    if aliased_not_confirmed_at_2x:
        print("\nAliased candidates where ZTF does NOT confirm the corrected period:")
        for t, v in aliased_not_confirmed_at_2x:
            print(f"  TIC {t} tested_period(1x)={v['base_period_days']:.5f}d corrected(2x)={v.get('corrected_period_days')}")
    print(f"\nWrote {cache_path}")
    print(f"Wrote {site_out_path}")


if __name__ == "__main__":
    main()
