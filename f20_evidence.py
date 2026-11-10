import re
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import f18_gaia_dr3 as gaia

# One evidence dossier per survivor, built only from files the other modules write.
#
# The tiers say what has actually been shown, in terms a referee would accept:
#
#   INDEPENDENTLY_SUPPORTED  at least one line of evidence that does not use the TESS
#                            pixels this pipeline processed AND nothing against it:
#                              * ZTF: eclipses recovered at the TESS period by another
#                                telescope (f17), or
#                              * Gaia DR3: a spectroscopic-binary (SB1) orbit whose period
#                                equals the TESS period or half/double it (f18) - radial
#                                velocities, a different physical measurement.
#   TESS_ONLY_CLEAN          no independent line yet, but no caveat either: the cleanest tier
#                            of the TESS vetting, no viable neighbour in the TIC or in Gaia.
#   TESS_ONLY_CAVEATS        no independent line, with one or more caveats (period alias,
#                            thin margin, a viable neighbour, ...). Candidate only.
#   DISFAVOURED              evidence against: ZTF could have seen the eclipse and did not,
#                            or the star is a TESS planet candidate.
#
# Separately, NOVELTY says what is already known about the star, which is a different
# question from whether it is real:
#   KNOWN_ECLIPSING     listed or labelled as an eclipsing binary elsewhere
#   KNOWN_BINARY        known as a (spectroscopic or astrometric) binary but not as eclipsing
#   KNOWN_VARIABLE      listed as a variable, possibly at another period
#   NO_PRIOR_FOUND      nothing found in the sources checked (which are not exhaustive)

EB_NAME = re.compile(r"(^|[^A-Za-z])EB($|[^A-Za-z])|-EB-")


def gaia_period_support(gaia_star, p_tess):
    """Does a Gaia SB1 / orbital solution carry the TESS period (or half/double)?
    Returns (relation, solution_type) or (None, None). Astrometric 'Orbital' solutions
    with periods of hundreds of days are not period support for an eclipsing pair."""
    nss = (gaia_star or {}).get("gaia_nss")
    if not nss or not nss.get("period_days"):
        return None, None
    rel = gaia.period_relation(p_tess, float(nss["period_days"]))
    if rel in ("same", "half", "double"):
        return rel, nss.get("solution_type")
    return None, nss.get("solution_type")


def novelty_label(novelty, prior, gaia_star, p_tess):
    """(label, reasons) from the catalog novelty verdict, the post-2025 sweep, SIMBAD and Gaia."""
    reasons = []
    verdict = (novelty or {}).get("verdict")
    simbad = (prior or {}).get("simbad") or {}
    name = simbad.get("main_id", "")
    otype = simbad.get("otype", "")
    rel, sol = gaia_period_support(gaia_star, p_tess)
    if verdict == "ALREADY_KNOWN":
        reasons.append("catalog match at this period")
    if simbad.get("group") == "eclipsing_binary" or EB_NAME.search(name or ""):
        reasons.append("SIMBAD: %s (%s)" % (name, otype))
    if (prior or {}).get("in_new_catalogs"):
        reasons.append("listed in " + ", ".join(c["id"] for c in prior["in_new_catalogs"]))
    if reasons:
        return "KNOWN_ECLIPSING", reasons
    if rel:
        reasons.append("Gaia DR3 %s orbit, period %s the TESS period" % (sol, {"same": "equals", "half": "is half", "double": "is double"}[rel]))
    if otype in ("SB*", "**", "SB?", "**?"):
        reasons.append("SIMBAD: %s (%s)" % (name, otype))
    if reasons:
        return "KNOWN_BINARY", reasons
    if verdict in ("KNOWN_VARIABLE_PERIOD_DIFFERS", "NEARBY_VARIABLE") or simbad.get("group") == "other_variable_or_peculiar":
        why = verdict if verdict in ("KNOWN_VARIABLE_PERIOD_DIFFERS", "NEARBY_VARIABLE") else "SIMBAD: %s (%s)" % (name, otype)
        return "KNOWN_VARIABLE", [why]
    return "NO_PRIOR_FOUND", []


def contamination_flags(neigh, gaia_star):
    """Statuses of the two neighbour tests (TIC-based f15, Gaia-based f18)."""
    a = (neigh or {}).get("status")
    b = ((gaia_star or {}).get("contamination") or {}).get("status")
    return a, b


def assess_star(row):
    """row: dict with tier, p_tess, ztf, gaia, neigh, prior, novelty, toi.
    Returns the dossier entry."""
    ztf = row.get("ztf") or {}
    z = ztf.get("status")
    rel, sol = gaia_period_support(row.get("gaia"), row["p_tess"])
    lines, against, caveats = [], [], []
    if z == "CONFIRMED":
        lines.append("ZTF recovers the eclipses (p=%.3g, power %.2f)" % (ztf.get("p_value") or 0, ztf.get("power") or 0))
    if rel:
        lines.append("Gaia DR3 %s orbit at the TESS period (%s)" % (sol, rel))
    if z == "NOT_SEEN":
        against.append("ZTF could have seen the eclipse (power %.2f) and did not" % (ztf.get("power") or 0))
    if (row.get("prior") or {}).get("toi") or row.get("toi"):
        against.append("on the TESS Objects of Interest list")
    tier = row.get("tier")
    if tier and tier != "CLEAN":
        caveats.append("TESS vetting tier %s" % tier.lower())
    ta, gb = contamination_flags(row.get("neigh"), row.get("gaia"))
    for src, st in (("TIC", ta), ("Gaia", gb)):
        if st == "UNSEPARABLE_NEIGHBOUR":
            caveats.append("a bright-enough neighbour is too close to separate in TESS pixels (%s)" % src)
        elif st == "VIABLE_NEIGHBOUR_AT_OFFSET":
            caveats.append("a bright-enough neighbour sits at the measured offset (%s)" % src)
    if (row.get("gaia") or {}).get("ruwe_elevated"):
        caveats.append("Gaia RUWE above 1.4 (possible unresolved companion)")
    if (row.get("gaia") or {}).get("match") == "AMBIGUOUS":
        caveats.append("Gaia source identification ambiguous")
    od = ztf.get("odd_even_at_2P")
    if z == "CONFIRMED" and od and abs(od.get("z", 0)) > 3:
        caveats.append("ZTF odd/even eclipse depths differ (z=%.1f): the true period may be twice the one tested" % od["z"])
    if against:
        tier_out = "DISFAVOURED"
    elif lines:
        tier_out = "INDEPENDENTLY_SUPPORTED"
    elif not caveats:
        tier_out = "TESS_ONLY_CLEAN"
    else:
        tier_out = "TESS_ONLY_CAVEATS"
    nov, why = novelty_label(row.get("novelty"), row.get("prior"), row.get("gaia"), row["p_tess"])
    return {"evidence_tier": tier_out, "independent_lines": lines, "against": against, "caveats": caveats,
            "novelty": nov, "novelty_reasons": why, "ztf_status": z or "NOT_RUN",
            "gaia_period_relation": rel}


def summarise(stars):
    tiers, nov, cross = {}, {}, {}
    for s in stars.values():
        tiers[s["evidence_tier"]] = tiers.get(s["evidence_tier"], 0) + 1
        nov[s["novelty"]] = nov.get(s["novelty"], 0) + 1
        k = "%s|%s" % (s["evidence_tier"], s["novelty"])
        cross[k] = cross.get(k, 0) + 1
    ztf = {}
    for s in stars.values():
        ztf[s["ztf_status"]] = ztf.get(s["ztf_status"], 0) + 1
    return {"stars": len(stars), "by_evidence_tier": tiers, "by_novelty": nov, "tier_by_novelty": cross, "by_ztf_status": ztf}


def build(root):
    data = root / "site" / "public" / "data"
    dash = pd.DataFrame(json.loads((data / "dashboard.json").read_text(encoding="utf-8"))["sky"])
    gaia_d = json.loads((data / "gaia_dr3.json").read_text(encoding="utf-8"))["stars"]
    prior = json.loads((data / "prior_art.json").read_text(encoding="utf-8"))["stars"]
    neigh = json.loads((data / "neighbours.json").read_text(encoding="utf-8"))["stars"]
    nov = json.loads((data / "novelty_extra.json").read_text(encoding="utf-8"))["stars"]
    ztf = {}
    for p in (root / "data" / "processed" / "f17_ztf").glob("TIC*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        ztf[str(d["tic"])] = d
    stars = {}
    for _, r in dash.iterrows():
        t = str(int(r["tic"]))
        stars[t] = assess_star({"tier": r["tier"], "p_tess": float(r["period_days"]), "ztf": ztf.get(t), "gaia": gaia_d.get(t),
                                "neigh": neigh.get(t), "prior": prior.get(t), "novelty": nov.get(t), "toi": None})
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": summarise(stars),
            "definitions": {
                "INDEPENDENTLY_SUPPORTED": "At least one line of evidence that does not use TESS pixels processed by this pipeline (ZTF recovery, or a Gaia DR3 spectroscopic-binary period equal to the TESS period or half/double it), and nothing against it.",
                "TESS_ONLY_CLEAN": "No independent line yet; cleanest TESS tier and no viable neighbour in the TIC or in Gaia.",
                "TESS_ONLY_CAVEATS": "No independent line yet, with at least one caveat. Candidate only.",
                "DISFAVOURED": "Evidence against: ZTF could have seen the eclipse and did not, or a TESS planet candidate.",
                "KNOWN_ECLIPSING": "Listed or labelled as an eclipsing binary elsewhere.",
                "KNOWN_BINARY": "Known as a spectroscopic or astrometric binary but not as eclipsing.",
                "KNOWN_VARIABLE": "Listed as a variable, possibly at another period.",
                "NO_PRIOR_FOUND": "Nothing found in the sources checked, which are not exhaustive."},
            "stars": stars}


def main():
    if len(sys.argv) < 2:
        print("Usage: py f20_evidence.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    rep = build(root)
    path = root / "site" / "public" / "data" / "evidence.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rep["summary"], indent=1))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
