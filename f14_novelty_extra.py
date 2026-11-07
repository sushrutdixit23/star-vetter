"""f14 - extra novelty cross-match against six time-domain variable catalogs.

f4f already checks VSX, Gaia, ASAS-SN, the TESS EB catalog and the TOI list.
This stage adds six more catalogs that f4f does not use, because "not in VSX"
is a weak statement for a star that ZTF or ATLAS has already flagged as periodic:

    ZTF periodic variables (Chen+ 2020)   CRTS periodic variables (Drake+ 2014)
    WISE periodic variables (Chen+ 2018)  ATLAS variables (Heinze+ 2018)
    ASAS-3 variables (Pojmanski 2002)     KELT variables (Oelkers+ 2018)

For each candidate it asks each catalog one question: is there a source within
the TESS-pixel scale of the target, and does its period match ours (at ratio
1, 1/2 or 2, because Lomb-Scargle surveys often report half the orbital period
of an eclipsing binary)?

Design rules (same as upstream.py / f4f):

* FAIL CLOSED. A query that errored, timed out or returned something we cannot
  read is recorded as QUERY_FAILED, never as "no match". VizieR answers a
  malformed request with an error document that has NO table, so "no table" is
  an error here, not "zero rows". Zero rows is accepted only when the response
  contains a table carrying every column we need.
* Footprints are respected. A catalog that does not cover the star's sky
  position cannot say anything about it, so the outcome is NOT_COVERED, not
  "clear". Footprints are approximate declination cuts (see FOOTPRINT notes).
* Exit code 3 (upstream down) if a catalog stops answering or too many
  individual queries fail, and nothing final is written, same as f4f.

Host: the CDS Strasbourg VizieR was unreachable on 2026-11-06, so queries go to
the Harvard-CfA VizieR mirror (vizier.cfa.harvard.edu), same catalogs.

Usage:  python f14_novelty_extra.py <root> [--only TIC,TIC] [--limit N]
            [--tiers CLEAN,THIN MARGIN] [--refresh] [--self-test] [--host URL]
Output: data/processed/f14_extra_catalogs.csv   (one row per star x catalog)
        data/processed/f14_novelty_extra.csv    (one row per star: verdict)
Cache:  data/processed/f14_cache/<catalog>.json  (successful queries only)

Limits worth stating when quoting results: a clear result means "not listed in
these six catalogs", which is weaker than "not variable" (the surveys are
magnitude- and cadence-limited), the ZTF/CRTS/ASAS footprints are approximate,
and catalog positions are not proper-motion corrected (5 arcsec is generous
for all but the highest-proper-motion stars).
"""

import argparse
import io
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

from upstream import EXIT_UPSTREAM_DOWN, FailureBreaker

DEFAULT_HOST = "https://vizier.cfa.harvard.edu"
USER_AGENT = "star-vetter-novelty/1.0"
PERIOD_TOLERANCE = 0.01          # |P_cat / (k * P) - 1| < 1 percent
PERIOD_RATIOS = (1.0, 0.5, 2.0)  # catalog period = k * our period
MAX_UNRESOLVED_FRACTION = 0.02
BREAKER_LIMIT = 5
RETRIES = 2
RETRY_DELAY_SEC = 5
TIMEOUT_SEC = 60


def _ztf_cover(ra, dec):
    return dec > -28.0


def _crts_cover(ra, dec):
    return -70.0 < dec < 65.0


def _asas_cover(ra, dec):
    return dec < 25.0


def _all_sky(ra, dec):
    return True


def _unknown(ra, dec):
    return None      # KELT strips: we do not assert coverage either way


# per_cols: every period column the catalog offers. class_col: its variability
# type (may be None). id_col: source name. tic_col: catalog carries TIC IDs, so
# a TIC equal to ours is an exact match whatever the separation.
# r_same / r_near: "same star" and "nearby" radii in arcsec. ASAS-3 has ~15
# arcsec pixels and positions to match, so it gets wider radii.
CATALOGS = [
    {"key": "ztf", "name": "ZTF periodic variables", "source": "J/ApJS/249/18/table2",
     "per_cols": ["Per", "Per-g", "Per-r"], "class_col": "Type", "id_col": "ID",
     "tic_col": None, "r_same": 5.0, "r_near": 21.0, "covered": _ztf_cover},
    {"key": "crts", "name": "CRTS periodic variables", "source": "J/ApJS/213/9/table3",
     "per_cols": ["Per"], "class_col": "Cl", "id_col": "CRTS",
     "tic_col": None, "r_same": 5.0, "r_near": 21.0, "covered": _crts_cover},
    {"key": "wise", "name": "WISE periodic variables", "source": "J/ApJS/237/28/table2",
     "per_cols": ["Per"], "class_col": "Type", "id_col": "WISE",
     "tic_col": None, "r_same": 5.0, "r_near": 21.0, "covered": _all_sky},
    {"key": "atlas", "name": "ATLAS variables", "source": "J/AJ/156/241/table4",
     "per_cols": ["ls-Pday", "fp-period", "fp-lngfitper"], "class_col": "Class",
     "id_col": "ATOID", "tic_col": None, "r_same": 5.0, "r_near": 21.0,
     "covered": _all_sky},
    {"key": "asas", "name": "ASAS-3 variables", "source": "II/264/asas3",
     "per_cols": ["Per"], "class_col": "Class", "id_col": "ASAS",
     "tic_col": None, "r_same": 15.0, "r_near": 30.0, "covered": _asas_cover},
    {"key": "kelt", "name": "KELT variables", "source": "J/AJ/155/39/Variables",
     "per_cols": ["Per-LS"], "class_col": None, "id_col": "_2MASS",
     "tic_col": "TIC", "r_same": 5.0, "r_near": 21.0, "covered": _unknown},
]
CATALOG_BY_KEY = {c["key"]: c for c in CATALOGS}


class CatalogError(RuntimeError):
    """The catalog answered, but not with a usable result (error document,
    missing table, missing columns). Treated exactly like a failed query."""


# ---------------------------------------------------------------- fetch/parse

def build_url(host, source, ra=None, dec=None, radius_arcsec=None, max_rows=None):
    q = [("-source", source), ("-out", "*")]
    if ra is None:
        q.append(("-out.add", "_RAJ,_DEJ"))        # no cone, so no separation column
    else:
        q.append(("-out.add", "_r,_RAJ,_DEJ"))
        q.append(("-c", f"{ra:.6f}{dec:+.6f}"))   # explicit sign: "215.5-84.4"
        q.append(("-c.rs", f"{radius_arcsec:g}"))
        q.append(("-c.u", "arcsec"))
    if max_rows is not None:
        q.append(("-out.max", str(max_rows)))
    return host.rstrip("/") + "/viz-bin/votable?" + urllib.parse.urlencode(q, safe="/,")


def fetch_bytes(url, timeout=TIMEOUT_SEC):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _cell(value):
    """Masked/NaN -> None; bytes -> str; numpy scalars -> python."""
    if value is np.ma.masked:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def parse_response(raw, cat, need_sep=True):
    """Parse a VizieR VOTable into a list of source dicts.

    Raises CatalogError unless the response is a well-formed result: a table
    must be present, no Error element, and every column we rely on must exist
    (an empty table still lists its columns, so zero rows is only believed when
    the schema is right)."""
    from astropy.io.votable import parse_single_table

    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    if 'name="Error"' in text or 'QUERY_STATUS" value="ERROR' in text:
        msg = text.split('name="Error"')[1][:200] if 'name="Error"' in text else "QUERY_STATUS=ERROR"
        raise CatalogError("VizieR returned an error: " + " ".join(msg.split())[:160])
    if "<TABLE" not in text:
        raise CatalogError("response has no table")
    try:
        table = parse_single_table(io.BytesIO(raw if isinstance(raw, bytes) else raw.encode())).to_table()
    except Exception as exc:  # noqa: BLE001
        raise CatalogError(f"could not parse VOTable: {exc!r}"[:200])

    needed = (["_r"] if need_sep else []) + list(cat["per_cols"]) + [cat["id_col"]]
    needed += [c for c in (cat["class_col"], cat["tic_col"]) if c]
    missing = [c for c in needed if c not in table.colnames]
    if missing:
        raise CatalogError(f"{cat['key']}: columns missing from response: {missing}")

    rows = []
    for rec in table:
        periods = []
        for col in cat["per_cols"]:
            v = _cell(rec[col])
            if v is not None and float(v) > 0:
                periods.append(float(v))
        sep = _cell(rec["_r"]) if "_r" in table.colnames else None
        cls = _cell(rec[cat["class_col"]]) if cat["class_col"] else None
        tic = _cell(rec[cat["tic_col"]]) if cat["tic_col"] else None
        rows.append({
            "sep_arcsec": float(sep) if sep is not None else None,
            "periods": periods,
            "cls": "" if cls is None else str(cls).strip(),
            "source_id": str(_cell(rec[cat["id_col"]]) or "").strip(),
            "tic": int(tic) if tic not in (None, "") else None,
            "ra": _cell(rec["_RAJ2000"]) if "_RAJ2000" in table.colnames else None,
            "dec": _cell(rec["_DEJ2000"]) if "_DEJ2000" in table.colnames else None,
        })
    return rows


def query_catalog(cat, ra, dec, host=DEFAULT_HOST, fetch=fetch_bytes,
                  retries=RETRIES, delay=RETRY_DELAY_SEC, timeout=TIMEOUT_SEC):
    """One cone search. Returns the parsed rows (possibly an empty list, which
    is a verified 'nothing there'). Raises CatalogError or the transport error
    after `retries` further attempts."""
    url = build_url(host, cat["source"], ra, dec, cat["r_near"])
    last = None
    for attempt in range(retries + 1):
        try:
            return parse_response(fetch(url, timeout), cat)
        except Exception as exc:  # noqa: BLE001 - transport and parse errors alike
            last = exc
            if attempt < retries:
                time.sleep(delay)
    raise last


# ------------------------------------------------------------------- matching

def period_match(cat_periods, our_periods, tol=PERIOD_TOLERANCE):
    """Best (ratio, relative_error) over all catalog and our periods, or None.
    ratio k means catalog period ~ k * ours (k = 0.5, 1 or 2)."""
    best = None
    for pc in cat_periods:
        for po in our_periods:
            if not (po and po > 0):
                continue
            for k in PERIOD_RATIOS:
                err = abs(pc / (k * po) - 1.0)
                if err < tol and (best is None or err < best[1]):
                    best = (k, err)
    return best


def evaluate(cat, rows, ra, dec, our_periods, our_tic=None):
    """Turn raw catalog rows into one outcome for this star and catalog.

    status is one of: NOT_COVERED (outside the footprint, rows ignored),
    SAME_STAR_PERIOD_MATCH, SAME_STAR_OTHER_PERIOD, SAME_STAR_NO_PERIOD,
    NEARBY_PERIOD_MATCH, NEARBY_OTHER, NO_MATCH (verified empty; `covered` says
    whether the catalog is known to cover the position: True, or None when
    unknown). QUERY_FAILED is assigned by the caller, never here."""
    covered = cat["covered"](ra, dec)
    out = {"catalog": cat["key"], "covered": covered, "n_rows": len(rows),
           "nearest_sep_arcsec": None, "nearest_class": "", "nearest_period_d": None,
           "match_ratio": None, "match_rel_err": None, "source_id": ""}
    if covered is False:
        out["status"] = "NOT_COVERED"
        return out
    if not rows:
        out["status"] = "NO_MATCH"
        return out

    def is_same(r):
        if cat["tic_col"] and our_tic is not None and r["tic"] == our_tic:
            return True
        return r["sep_arcsec"] is not None and r["sep_arcsec"] <= cat["r_same"]

    rows = sorted(rows, key=lambda r: (not is_same(r),
                                       r["sep_arcsec"] if r["sep_arcsec"] is not None else 1e9))
    same = [r for r in rows if is_same(r)]
    pool = same if same else rows
    # the best period match among the pool of interest
    chosen, match = None, None
    for r in pool:
        m = period_match(r["periods"], our_periods)
        if m and (match is None or m[1] < match[1]):
            chosen, match = r, m
    head = chosen or pool[0]
    out.update({"nearest_sep_arcsec": head["sep_arcsec"], "nearest_class": head["cls"],
                "nearest_period_d": head["periods"][0] if head["periods"] else None,
                "source_id": head["source_id"]})
    if match:
        out["match_ratio"], out["match_rel_err"] = match
    if same:
        out["status"] = ("SAME_STAR_PERIOD_MATCH" if match else
                         "SAME_STAR_OTHER_PERIOD" if any(r["periods"] for r in same)
                         else "SAME_STAR_NO_PERIOD")
    else:
        out["status"] = "NEARBY_PERIOD_MATCH" if match else "NEARBY_OTHER"
    return out


VERDICT_ORDER = ["ALREADY_KNOWN", "KNOWN_VARIABLE_PERIOD_DIFFERS",
                 "NEARBY_PERIOD_MATCH", "NEARBY_VARIABLE", "INCOMPLETE",
                 "NO_MATCH", "NO_MATCH_WEAK", "NOT_COVERED"]


def star_verdict(outcomes):
    """Combine the per-catalog outcomes. A real positive always counts, even if
    another catalog failed. 'NO_MATCH' needs every covered catalog verified
    and at least one catalog that actually covers the star."""
    st = {o["catalog"]: o["status"] for o in outcomes}
    vals = set(st.values())
    if "SAME_STAR_PERIOD_MATCH" in vals:
        return "ALREADY_KNOWN"
    if vals & {"SAME_STAR_OTHER_PERIOD", "SAME_STAR_NO_PERIOD"}:
        return "KNOWN_VARIABLE_PERIOD_DIFFERS"
    if "NEARBY_PERIOD_MATCH" in vals:
        return "NEARBY_PERIOD_MATCH"
    if "NEARBY_OTHER" in vals:
        return "NEARBY_VARIABLE"
    if "QUERY_FAILED" in vals:
        return "INCOMPLETE"
    if any(o["status"] == "NO_MATCH" and o["covered"] is True for o in outcomes):
        return "NO_MATCH"
    if "NO_MATCH" in vals:          # only catalogs with unknown coverage
        return "NO_MATCH_WEAK"
    return "NOT_COVERED"


# ------------------------------------------------------------------ self-test

def self_test(host=DEFAULT_HOST, fetch=fetch_bytes, log=print):
    """Positive control for every catalog, using only the catalog itself.
    1. Fetch its first row (no cone): proves the table exists and that every
       column we rely on is present.
    2. Cone-search at that row's own position: must return that row at a
       separation of about zero. Proves coordinates, units and the cone syntax.
    Returns (ok, problems). Transport failures raise; schema/logic problems are
    returned so the caller can tell 'service down' (exit 3) from 'we are wrong'."""
    problems = []
    for cat in CATALOGS:
        raw = fetch(build_url(host, cat["source"], max_rows=1), TIMEOUT_SEC)
        try:
            first = parse_response(raw, cat, need_sep=False)
        except CatalogError as exc:
            problems.append(f"{cat['key']}: first-row query unusable: {exc}")
            continue
        if not first or first[0]["ra"] is None:
            problems.append(f"{cat['key']}: first-row query returned no position")
            continue
        ra, dec = first[0]["ra"], first[0]["dec"]
        try:
            rows = parse_response(fetch(build_url(host, cat["source"], ra, dec, 3.0), TIMEOUT_SEC), cat)
        except CatalogError as exc:
            problems.append(f"{cat['key']}: control cone search unusable: {exc}")
            continue
        near = [r for r in rows if r["sep_arcsec"] is not None and r["sep_arcsec"] < 2.0]
        if not near:
            problems.append(f"{cat['key']}: control cone search at a known source's own "
                            f"position returned no source (got {len(rows)} rows)")
            continue
        log(f"  self-test {cat['key']:6s} ok (control source {near[0]['source_id'] or '?'}, "
            f"{len(rows)} row(s) within 3 arcsec)")
    return (not problems), problems


# --------------------------------------------------------------------- driver

def load_candidates(root, tiers=None, only=None, limit=None):
    idx = json.load(open(os.path.join(root, "site", "public", "data", "index.json"),
                         encoding="utf-8"))
    rows = []
    for c in idx["candidates"]:
        if tiers and c.get("tier") not in tiers:
            continue
        if only and int(c["tic"]) not in only:
            continue
        path = os.path.join(root, "site", "public", "data", "detail", f"TIC{c['tic']}.json")
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        cat = d.get("catalog") or {}
        if cat.get("ra") is None or cat.get("dec") is None:
            continue
        periods = sorted({round(float(p), 8) for p in
                          (d.get("period_true_days"), d.get("period_bls_days")) if p})
        rows.append({"tic": int(c["tic"]), "tier": c.get("tier", ""), "ra": float(cat["ra"]),
                     "dec": float(cat["dec"]), "periods": periods})
    rows.sort(key=lambda r: r["tic"])
    return rows[:limit] if limit else rows


def _cache_key(star, cat):
    return f"{star['ra']:.5f},{star['dec']:+.5f},{cat['r_near']:g},{cat['source']}"


def run_catalog(cat, stars, cache_path, host, refresh, results, log):
    """Worker: query one catalog for every star, resuming from its cache.
    Fills results[tic] = (rows | None, error | None). Stops early if the
    catalog keeps failing (breaker)."""
    cache = {}
    if os.path.exists(cache_path) and not refresh:
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    breaker = FailureBreaker(BREAKER_LIMIT)
    done = 0
    for star in stars:
        key = str(star["tic"])
        hit = cache.get(key)
        if hit and hit.get("key") == _cache_key(star, cat):
            results[(cat["key"], star["tic"])] = (hit["rows"], None)
            continue
        try:
            rows = query_catalog(cat, star["ra"], star["dec"], host=host)
        except Exception as exc:  # noqa: BLE001
            results[(cat["key"], star["tic"])] = (None, str(exc)[:160])
            if breaker.record(False):
                log(f"  [{cat['key']}] {BREAKER_LIMIT} failures in a row, giving up on this catalog")
                results[(cat["key"], "TRIPPED")] = (None, "breaker tripped")
                break
            continue
        breaker.record(True)
        cache[key] = {"key": _cache_key(star, cat), "rows": rows}
        results[(cat["key"], star["tic"])] = (rows, None)
        done += 1
        if done % 25 == 0:
            _save_json(cache_path, cache)
            log(f"  [{cat['key']}] {done} new queries")
    _save_json(cache_path, cache)


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def build_tables(stars, results):
    """Per-star x catalog and per-star tables from the raw results."""
    import pandas as pd

    per_cat, per_star = [], []
    for star in stars:
        outs = []
        for cat in CATALOGS:
            rows, err = results.get((cat["key"], star["tic"]), (None, "not queried"))
            if rows is None:
                o = {"catalog": cat["key"], "covered": cat["covered"](star["ra"], star["dec"]),
                     "status": "QUERY_FAILED", "n_rows": 0, "nearest_sep_arcsec": None,
                     "nearest_class": "", "nearest_period_d": None, "match_ratio": None,
                     "match_rel_err": None, "source_id": "", "error": err}
                if o["covered"] is False:      # outside footprint: a failure is moot
                    o["status"] = "NOT_COVERED"
            else:
                o = evaluate(cat, rows, star["ra"], star["dec"], star["periods"], star["tic"])
                o["error"] = ""
            o["tic"] = star["tic"]
            outs.append(o)
            per_cat.append(o)
        v = star_verdict(outs)
        pick = lambda *s: ",".join(o["catalog"] for o in outs if o["status"] in s)  # noqa: E731
        per_star.append({
            "tic": star["tic"], "tier": star["tier"], "verdict": v,
            "matched_catalogs": pick("SAME_STAR_PERIOD_MATCH"),
            "known_other_period": pick("SAME_STAR_OTHER_PERIOD", "SAME_STAR_NO_PERIOD"),
            "nearby_catalogs": pick("NEARBY_PERIOD_MATCH", "NEARBY_OTHER"),
            "failed_catalogs": pick("QUERY_FAILED"),
            "clear_catalogs": ",".join(o["catalog"] for o in outs
                                       if o["status"] == "NO_MATCH" and o["covered"] is True),
            "not_covered": pick("NOT_COVERED"),
        })
    cols = ["tic", "catalog", "status", "covered", "n_rows", "nearest_sep_arcsec", "nearest_class",
            "nearest_period_d", "match_ratio", "match_rel_err", "source_id", "error"]
    return pd.DataFrame(per_cat)[cols], pd.DataFrame(per_star)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tiers", default="")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--host", default=DEFAULT_HOST)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)

    print(f"Self-test against {a.host} ...", flush=True)
    try:
        ok, problems = self_test(a.host)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::VizieR mirror unreachable: {exc!r}"[:300], flush=True)
        return EXIT_UPSTREAM_DOWN
    if not ok:
        for p in problems:
            print("::error::self-test failed: " + p, flush=True)
        return 1
    if a.self_test:
        print("Self-test passed.")
        return 0

    only = {int(x) for x in a.only.split(",") if x.strip()} or None
    tiers = {x.strip() for x in a.tiers.split(",") if x.strip()} or None
    stars = load_candidates(root, tiers, only, a.limit or None)
    print(f"{len(stars)} candidate(s) x {len(CATALOGS)} catalogs", flush=True)

    results = {}
    cache_dir = os.path.join(root, "data", "processed", "f14_cache")
    threads = [threading.Thread(target=run_catalog, daemon=True, args=(
        cat, stars, os.path.join(cache_dir, cat["key"] + ".json"), a.host, a.refresh,
        results, lambda m: print(m, flush=True))) for cat in CATALOGS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tripped = sorted(k[0] for k in results if k[1] == "TRIPPED")
    if tripped:
        print(f"::error::catalog(s) stopped answering: {tripped}. Nothing written; "
              f"rerun resumes from cache.", flush=True)
        return EXIT_UPSTREAM_DOWN
    failed = sum(1 for (k, t), (rows, err) in results.items() if rows is None)
    total = len(stars) * len(CATALOGS)
    if total and failed / total > MAX_UNRESOLVED_FRACTION:
        print(f"::error::{failed}/{total} queries failed (> {MAX_UNRESOLVED_FRACTION:.0%}). "
              f"Nothing written; rerun resumes from cache.", flush=True)
        return EXIT_UPSTREAM_DOWN

    per_cat, per_star = build_tables(stars, results)
    out_dir = os.path.join(root, "data", "processed")
    per_cat.to_csv(os.path.join(out_dir, "f14_extra_catalogs.csv"), index=False,
                   encoding="utf-8", lineterminator="\n")
    per_star.to_csv(os.path.join(out_dir, "f14_novelty_extra.csv"), index=False,
                    encoding="utf-8", lineterminator="\n")
    print("\nVerdicts:")
    print(per_star["verdict"].value_counts().to_string())
    print(f"({failed} individual quer{'y' if failed == 1 else 'ies'} unresolved, "
          f"recorded as QUERY_FAILED)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
