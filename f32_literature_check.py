"""f32_literature_check.py - what has been published about each trusted-eccentric star?

WHY THIS EXISTS
The catalog cross-matches (f14, f19) answer "is this star in a list of eclipsing binaries?". They cannot answer
"has anyone published an orbit for it?". Kostov et al. 2025 removed every target within 21 arcsec of a known
eclipsing binary, so a catalog miss is built in and is not evidence of novelty. This script asks SIMBAD, which holds
the literature references that curators attach to each object, for every star whose light-curve eccentricity passes
the trust rule (export_findings.e_reliable), and records exactly what came back.

WHAT IT DOES NOT DO
SIMBAD is not complete: a paper that lists a star only in a table of thousands may be missing. ADS full-text search
would be the stronger check, but its API needs a personal token and the sandbox cannot use the web interface. The
manual web-search part (data/processed/f32_web_search.json) is therefore a second, separate record, written by hand
and labelled as such. A result of "not found" from either means "not found in what was searched", never "novel".

CONTRACT (same fail-closed rule as upstream.py and crossmatch.py)
A query that cannot be completed after retries makes that star UNCHECKED. UNCHECKED is never reported as "no
reference found". The script exits 3 if any star is UNCHECKED, 0 otherwise.

USAGE
    python f32_literature_check.py [repo_dir]
Writes data/processed/f32_literature.json and docs/literature_check.md.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SIMBAD_TAP = "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync"
CONE_ARCSEC = 6.0
# A paper that lists this many SIMBAD objects or more is a survey or a catalog, not a study of this star.
SURVEY_NOBJECT = 200
BINARY_WORDS = re.compile(r"eclips|binar|orbit|eccentr|apsid|radial.velocit|spectroscop|SB[12]|double.lined|tidal", re.I)
EXIT_UNCHECKED = 3


class QueryFailed(RuntimeError):
    """A SIMBAD query could not be completed; the star must be reported UNCHECKED."""


def tap(adql, attempts=6, timeout=60, session=None):
    """Run one ADQL query and return the rows. Raises QueryFailed if no complete answer arrives."""
    s = session or requests
    last = "no attempt made"
    for k in range(attempts):
        try:
            r = s.post(SIMBAD_TAP, data={"request": "doQuery", "lang": "adql", "format": "json", "query": adql}, timeout=timeout)
            if r.status_code != 200:
                last = "HTTP %d" % r.status_code
            else:
                j = r.json()
                if "data" not in j or "metadata" not in j:
                    last = "answer without data/metadata: " + str(j)[:100]
                else:
                    return j["data"]
        except (requests.RequestException, ValueError) as exc:
            last = "%s: %s" % (type(exc).__name__, str(exc)[:100])
        time.sleep(min(2.0 ** k, 20.0))
    raise QueryFailed("SIMBAD query failed after %d attempts (%s): %s" % (attempts, last, adql[:120]))


def sql_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def classify_reference(title, nobject):
    """'survey' = a paper listing many objects; 'study' = few objects; 'mid' = in between."""
    n = int(nobject or 0)
    kind = "survey" if n >= SURVEY_NOBJECT else ("study" if n <= 20 else "mid")
    return kind, bool(BINARY_WORDS.search(title or ""))


def find_objects(star, session=None):
    """SIMBAD objects for one star: by identifier (TIC, Gaia DR3) and by position. Returns a list of dicts."""
    found = {}
    idents = ["TIC %d" % star["tic"]]
    if star.get("gaia_id"):
        idents.append("Gaia DR3 %s" % star["gaia_id"])
    rows = tap("SELECT b.oid, b.main_id, b.otype, b.nbref, b.ra, b.dec, i.id FROM basic AS b JOIN ident AS i ON i.oidref = b.oid WHERE i.id IN (%s)"
               % ", ".join(sql_quote(x) for x in idents), session=session)
    for oid, main_id, otype, nbref, ra, dec, ident in rows:
        d = found.setdefault(int(oid), {"oid": int(oid), "main_id": main_id, "otype": otype, "nbref": int(nbref or 0), "ra": ra, "dec": dec, "via": []})
        d["via"].append("identifier " + ident)
    rows = tap("SELECT oid, main_id, otype, nbref, ra, dec, DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', %.7f, %.7f)) * 3600 AS sep "
               "FROM basic WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', %.7f, %.7f, %.7f)) = 1"
               % (star["ra"], star["dec"], star["ra"], star["dec"], CONE_ARCSEC / 3600.0), session=session)
    for oid, main_id, otype, nbref, ra, dec, sep in rows:
        d = found.setdefault(int(oid), {"oid": int(oid), "main_id": main_id, "otype": otype, "nbref": int(nbref or 0), "ra": ra, "dec": dec, "via": []})
        d["via"].append("position within %.0f arcsec" % CONE_ARCSEC)
        d["sep_arcsec"] = round(float(sep), 2)
    for d in found.values():
        if "sep_arcsec" not in d:
            d["sep_arcsec"] = None
    return sorted(found.values(), key=lambda d: (d["sep_arcsec"] is None, d["sep_arcsec"] or 0.0))


def references_of(oid, session=None):
    # SIMBAD's ADQL rejects ORDER BY on the "year" column (HTTP 400), so the sort is done here.
    rows = tap("SELECT r.bibcode, r.\"year\", r.journal, r.title, r.nbobject, r.doi FROM ref AS r JOIN has_ref AS h ON h.oidbibref = r.oidbib "
               "WHERE h.oidref = %d" % int(oid), session=session)
    out = []
    for bibcode, year, journal, title, nobject, doi in sorted(rows, key=lambda x: (-(x[1] or 0), x[0])):
        kind, binary_words = classify_reference(title, nobject)
        out.append({"bibcode": bibcode, "year": year, "journal": journal, "title": title, "nbobject": nobject, "kind": kind,
                    "mentions_binary_topics": binary_words, "doi": doi})
    return out


def verdict_for(objects):
    """Plain verdict from a COMPLETE SIMBAD answer."""
    if not objects:
        return "NOT_IN_SIMBAD"
    refs = [r for o in objects for r in o["references"]]
    if not refs:
        return "IN_SIMBAD_NO_REFERENCES"
    if all(r["kind"] == "survey" for r in refs):
        return "IN_SIMBAD_SURVEY_PAPERS_ONLY"
    return "IN_SIMBAD_WITH_STUDIES"


def check_star(star, session=None):
    rec = {k: star[k] for k in ("tic", "gaia_id", "ra", "dec", "tmag", "period_days", "e", "omega_deg")}
    try:
        objects = find_objects(star, session=session)
        for o in objects:
            o["references"] = references_of(o["oid"], session=session)
    except QueryFailed as exc:
        rec.update({"status": "UNCHECKED", "reason": str(exc), "objects": [], "verdict": "UNCHECKED"})
        return rec
    rec.update({"status": "CHECKED", "objects": objects, "verdict": verdict_for(objects)})
    return rec


def trusted_eccentric_stars(repo):
    """The stars whose light-curve e passes the trust rule and is clearly above zero, with their catalog data."""
    ecc = json.loads((repo / "site/public/data/eccentric.json").read_text(encoding="utf-8"))
    stars = []
    for row in ecc["physical"]["fits"]:
        if row.get("status") != "OK" or not row.get("e_reliable"):
            continue
        if row["e"]["median"] < 0.02:
            continue
        cat = json.loads((repo / ("site/public/data/detail/TIC%d.json" % row["tic"])).read_text(encoding="utf-8"))["catalog"]
        stars.append({"tic": row["tic"], "gaia_id": cat.get("gaia_id"), "ra": cat["ra"], "dec": cat["dec"], "tmag": cat.get("tmag"),
                      "period_days": row["period_days"], "e": row["e"]["median"], "omega_deg": row["omega_deg"]["median"]})
    return sorted(stars, key=lambda s: s["period_days"])


def site_labels(repo):
    """The novelty label and evidence tier the site already shows, so this report and the site cannot disagree silently."""
    ecc = json.loads((repo / "site/public/data/eccentric.json").read_text(encoding="utf-8"))
    return {c["tic"]: (c.get("novelty"), c.get("evidence_tier")) for c in ecc["candidates"]}


def write_markdown(path, records, generated, labels=None, web=None):
    labels = labels or {}
    lines = ["# Literature check on the trusted-eccentric stars", "",
             "Generated by `f32_literature_check.py` on %s. Three sources, in decreasing strength: SIMBAD references (script, Harvard mirror), the catalog "
             "cross-matches already on the site (f14, f16, f19), and a manual web search. ADS full-text search has NOT been done (it needs a login); the queries "
             "for it are at the end." % generated, "",
             "This is not a novelty claim. A result of \"nothing found\" means nothing was found in what was searched. SIMBAD is incomplete, and a paper "
             "that lists a star only inside a large table can be missing from it.", "",
             "| TIC | P (d) | e | Tmag | SIMBAD | Site label | Studies in SIMBAD |", "|---|---|---|---|---|---|---|"]
    for r in records:
        nov, tier = labels.get(r["tic"], (None, None))
        objs = "; ".join("%s (%s)" % (o["main_id"], o["otype"]) for o in r["objects"])
        studies = [x for o in r["objects"] for x in o["references"] if x["kind"] != "survey"]
        lines.append("| %d | %.4f | %.3f | %s | %s%s | %s | %d |" % (
            r["tic"], r["period_days"], r["e"], "%.1f" % r["tmag"] if r.get("tmag") else "n/a", r["verdict"], " - " + objs if objs else "",
            nov or "n/a", len(studies)))
    lines += ["", "## What each source says", ""]
    for r in records:
        nov, tier = labels.get(r["tic"], (None, None))
        lines.append("### TIC %d" % r["tic"])
        lines.append("")
        if r["status"] != "CHECKED":
            lines += ["- SIMBAD: UNCHECKED. " + r["reason"], ""]
            continue
        if not r["objects"]:
            lines.append("- SIMBAD: no object by TIC, by Gaia DR3 number, or within %.0f arcsec." % CONE_ARCSEC)
        for o in r["objects"]:
            lines.append("- SIMBAD: %s, type %s, %d references; matched by %s%s." % (
                o["main_id"], o["otype"], o["nbref"], " and ".join(o["via"]), "" if o["sep_arcsec"] is None else "; %.2f arcsec from the TIC position" % o["sep_arcsec"]))
            for x in o["references"]:
                lines.append("  - %s %s, %s: %s (%s paper, %s objects)" % (x["year"], x["bibcode"], x["journal"], x["title"], x["kind"], x["nbobject"]))
        if nov:
            lines.append("- Site label: %s (evidence tier %s). See `docs/novelty_findings.md` for the catalog cross-match behind it." % (nov, tier))
        w = (web or {}).get("stars", {}).get(str(r["tic"]))
        if w:
            lines.append("- Web search (manual, weak): %s." % w["outcome"])
        lines.append("")
    if web:
        lines += ["## About the web search", "", web["how_to_read"], "",
                  "Calibration: for TIC 370553309 the web search did not find the Gaia DR3 SB1 orbit that SIMBAD records, so a web search that finds nothing "
                  "says very little.", ""]
    lines += ["## ADS full-text queries still to run", "",
              "ADS full-text search needs a login, which the sandbox does not have. Paste each line into the search box at https://ui.adsabs.harvard.edu/ "
              "and write the number of hits, and the bibcodes if any, in the last column. Gaia numbers usually appear without the words \"Gaia DR3\" in tables, "
              "so the number is searched on its own.", "",
              "| TIC | Query | Hits (fill in) |", "|---|---|---|"]
    for r in records:
        q = 'full:"TIC %d" OR full:"%s"' % (r["tic"], r["gaia_id"]) if r.get("gaia_id") else 'full:"TIC %d"' % r["tic"]
        lines.append("| %d | `%s` | |" % (r["tic"], q))
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# Positive control: a star that SIMBAD certainly holds, with many studies (Maxted et al. 2020 analysed it from TESS).
# If the machinery cannot find it by TIC and by position alone, "not in SIMBAD" for the real stars means nothing.
CONTROL = {"tic": 102069549, "gaia_id": None, "ra": 17.39246835629, "dec": -46.2655754776, "tmag": 8.0, "period_days": 24.59, "e": 0.1875, "omega_deg": 0.0}


def run_control(session=None):
    """Return (ok, text). The control must be found by TIC and by position alone, and have specific studies."""
    by_tic = check_star(CONTROL, session=session)
    by_pos = check_star(dict(CONTROL, tic=999999999), session=session)
    ok = (by_tic["status"] == "CHECKED" and by_pos["status"] == "CHECKED" and by_tic["verdict"] == "IN_SIMBAD_WITH_STUDIES"
          and by_pos["verdict"] == "IN_SIMBAD_WITH_STUDIES" and any("AI Phe" in o["main_id"] for o in by_pos["objects"]))
    return ok, "control AI Phe: by TIC %s, by position only %s" % (by_tic["verdict"], by_pos["verdict"])


def main(argv):
    repo = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parent
    stars = trusted_eccentric_stars(repo)
    print("%d trusted-eccentric stars" % len(stars))
    session = requests.Session()
    ok, text = run_control(session)
    print(text)
    if not ok:
        print("The positive control failed, so no result from this run can be trusted. Nothing was written.")
        return EXIT_UNCHECKED
    records = []
    for s in stars:
        rec = check_star(s, session=session)
        records.append(rec)
        print("TIC %-10d %-30s %s" % (rec["tic"], rec["verdict"], "; ".join("%s [%s] %d refs" % (o["main_id"], o["otype"], len(o["references"])) for o in rec["objects"])))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"generated_at": generated, "source": "SIMBAD TAP, " + SIMBAD_TAP, "cone_arcsec": CONE_ARCSEC, "survey_nobjects": SURVEY_NOBJECT, "control": text,
           "n_unchecked": sum(r["status"] != "CHECKED" for r in records), "stars": records}
    (repo / "data/processed/f32_literature.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    wp = repo / "data/processed/f32_web_search.json"
    web = json.loads(wp.read_text(encoding="utf-8")) if wp.exists() else None
    write_markdown(repo / "docs/literature_check.md", records, generated, labels=site_labels(repo), web=web)
    return EXIT_UNCHECKED if out["n_unchecked"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
