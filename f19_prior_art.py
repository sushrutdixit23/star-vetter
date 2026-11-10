import io
import re
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# Prior-art sweep for the survivors, against sources Kostov et al. did NOT filter on.
#
# The earlier "0 of 307 in any catalog" is largely guaranteed by construction:
# Kostov's table2 is what remained after removing every target within 21 arcsec of
# an eclipsing binary in ASAS-SN, ATLAS, Gaia, OGLE, SIMBAD, TESS, VSX, WISE and ZTF.
# That result cannot be read as novelty. What can be checked is material that
# appeared after that filter or that it did not use:
#   * catalogs published after the filter (the 2026 TESS binary and multiple-star
#     papers, fetched from VizieR where they exist);
#   * the TESS Objects of Interest list (a transiting-planet candidate is not a binary);
#   * SIMBAD object types (a star already labelled a rotator or pulsator is a
#     different story from an unlabelled one).
# Every source is reported as CHECKED or NOT_CHECKED with the reason, so a catalog
# that could not be reached is never mistaken for a clean result.

VIZIER = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv"
SIMBAD_TAP = "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync"
MATCH_ARCSEC = 5.0

# (name, VizieR id, what it is). Table ids that VizieR does not hold are reported as such.
VIZIER_SOURCES = [
    ("Kostov+ 2026 eclipsing quadruple candidates (AJ 171, 29)", "J/AJ/171/29", "52 quadruple candidates from the same neural-network pipeline"),
    ("Oddo+ 2026 low-mass M+M TESS binaries (ApJ 996, 82)", "J/ApJ/996/82", "1,292 M-dwarf eclipsing binaries"),
    ("Liu+ 2026 TESS EB classification (ApJS 285, 5)", "J/ApJS/285/5", "20,196 TESS eclipsing binaries classified EA/EB/EW"),
]


def parse_tsv(text):
    """VizieR asu-tsv text -> DataFrame (comment lines, units and dash rows removed), or
    None when the answer is the empty/error stub the mirror sometimes returns."""
    lines = [l for l in text.splitlines()]
    if any("Error=" in l for l in lines):
        return None
    data = [l for l in lines if l and not l.startswith("#")]
    if not data or data[0].startswith("Content-Type"):
        return None
    head = data[0].split("\t")
    rows = [r.split("\t") for r in data[1:] if not re.fullmatch(r"[\s\-\t]+", r) and not r.startswith(("deg", "arcsec", "---"))]
    rows = [r for r in rows if len(r) == len(head)]
    # the second line of a VizieR tsv holds units; drop it if it looks like units
    df = pd.DataFrame(rows, columns=[h.strip() for h in head])
    return df


def fetch_vizier(source, attempts=6, pause=5.0):
    """(DataFrame or None, note). Retries because the mirror intermittently answers empty."""
    note = "no answer"
    for k in range(attempts):
        try:
            r = requests.get(VIZIER, params={"-source": source, "-out.max": "unlimited", "-out.add": "_RAJ,_DEJ"}, timeout=180)
            if "Table or Catalog not found" in r.text:
                return None, "VizieR does not hold %s" % source
            df = parse_tsv(r.text)
            if df is not None and len(df):
                return df, "ok"
            note = "empty or error answer from the mirror"
        except Exception as exc:   # noqa: BLE001
            note = "request failed: %s" % str(exc)[:80]
        time.sleep(pause * (k + 1))
    return None, note


def to_float(s):
    return pd.to_numeric(s, errors="coerce")


def crossmatch(table, targets, arcsec=MATCH_ARCSEC):
    """Targets (tic, ra, dec) against a table by TIC when it has a TIC column, else by position.
    Returns {tic: row dict}."""
    out = {}
    cols = {c.lower(): c for c in table.columns}
    tic_col = next((cols[c] for c in cols if c in ("tic", "ticid", "tic_id", "tic id")), None)
    if tic_col is not None:
        t = pd.to_numeric(table[tic_col], errors="coerce")
        idx = {int(v): i for i, v in zip(table.index, t) if np.isfinite(v)}
        for tic in targets["tic"]:
            if int(tic) in idx:
                out[int(tic)] = table.loc[idx[int(tic)]].to_dict()
        return out
    ra_c, dec_c = cols.get("_raj2000") or cols.get("_raj"), cols.get("_dej2000") or cols.get("_dej")
    if ra_c is None or dec_c is None:
        return out
    tra, tdec = to_float(table[ra_c]).to_numpy(), to_float(table[dec_c]).to_numpy()
    ok = np.isfinite(tra) & np.isfinite(tdec)
    for _, r in targets.iterrows():
        cosd = np.cos(np.deg2rad(r["dec"]))
        sep = np.where(ok, np.hypot((tra - r["ra"]) * cosd, tdec - r["dec"]) * 3600.0, np.inf)
        i = int(np.argmin(sep)) if len(sep) else -1
        if i >= 0 and sep[i] <= arcsec:
            row = table.iloc[i].to_dict()
            row["_sep_arcsec"] = float(sep[i])
            out[int(r["tic"])] = row
    return out


def simbad_types(targets, attempts=4):
    """SIMBAD main object type for each target within MATCH_ARCSEC (ADQL cone, one query per
    batch of positions through a UPLOAD-free OR chain)."""
    out, note = {}, "ok"
    rows = list(targets.itertuples(index=False))
    for k in range(0, len(rows), 25):
        chunk = rows[k:k + 25]
        conds = " OR ".join("1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', %.6f, %.6f, %.6f))" % (r.ra, r.dec, MATCH_ARCSEC / 3600.0) for r in chunk)
        q = "SELECT main_id, ra, dec, otype, otype_txt FROM basic WHERE " + conds
        df = None
        for a in range(attempts):
            try:
                resp = requests.post(SIMBAD_TAP, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": q}, timeout=120)
                if resp.status_code == 200:
                    df = pd.read_csv(io.StringIO(resp.text))
                    break
                note = "HTTP %s" % resp.status_code
            except Exception as exc:   # noqa: BLE001
                note = "request failed: %s" % str(exc)[:80]
            time.sleep(4 * (a + 1))
        if df is None:
            return None, note
        for r in chunk:
            cosd = np.cos(np.deg2rad(r.dec))
            if len(df):
                sep = np.hypot((df["ra"] - r.ra) * cosd, df["dec"] - r.dec) * 3600.0
                j = int(sep.idxmin())
                if sep[j] <= MATCH_ARCSEC:
                    out[int(r.tic)] = {"main_id": str(df.loc[j, "main_id"]), "otype": str(df.loc[j, "otype"]), "otype_txt": str(df.loc[j, "otype_txt"]), "sep_arcsec": float(sep[j])}
    return out, note


EB_TYPES = {"EB*", "EB*Algol", "EB*beta", "EB*WUMa", "**", "Al*", "bL*", "WU*"}
OTHER_VARIABLE_PREFIXES = ("V*", "Pu*", "RR*", "Ce*", "Mi*", "RV*", "Er*", "Ro*", "BY*", "Fl*", "Or*", "TT*", "dS*", "gD*", "rotV", "LP*", "SX*", "Ir*", "Psr", "Pl", "Pl?", "Tr", "TrS", "BD*", "WD*", "HB*", "No*", "CV*", "XB", "HXB", "LXB")


def classify_simbad(otype):
    """Group a SIMBAD otype: eclipsing binary / other variable / planet or transit / plain star / other."""
    o = (otype or "").strip()
    if o in ("Pl", "Pl?", "Tr", "TrS", "PlanetaryNebula"):
        return "planet_or_transit"
    if o in EB_TYPES or o.startswith("EB"):
        return "eclipsing_binary"
    if o in ("*", "*iC", "*iN", "**?", "Em*", "Ma*", "bC*", "s*b", "Be*", "HB*"):
        return "plain_star"
    if o.endswith("*") or o.endswith("*?") or o.startswith(OTHER_VARIABLE_PREFIXES):
        return "other_variable_or_peculiar"
    return "other"


def toi_matches(toi, targets):
    """Candidates whose TIC is on the ExoFOP TOI list, with the TFOPWG disposition."""
    cols = {c.lower(): c for c in toi.columns}
    tic_c = cols.get("tic id") or cols.get("tic")
    disp_c = cols.get("tfopwg disposition") or cols.get("disposition")
    if tic_c is None:
        return {}
    d = toi.set_index(pd.to_numeric(toi[tic_c], errors="coerce"))
    out = {}
    for tic in targets["tic"]:
        if int(tic) in d.index:
            row = d.loc[[int(tic)]].iloc[0]
            out[int(tic)] = {"toi": str(row.get(cols.get("toi"), "")), "disposition": str(row.get(disp_c, "")) if disp_c else ""}
    return out


def build(targets, root):
    sources = []
    matches = {int(t): [] for t in targets["tic"]}
    for name, vid, what in VIZIER_SOURCES:
        df, note = fetch_vizier(vid)
        if df is None:
            sources.append({"name": name, "id": vid, "what": what, "status": "NOT_CHECKED", "reason": note})
            continue
        m = crossmatch(df, targets)
        sources.append({"name": name, "id": vid, "what": what, "status": "CHECKED", "rows": int(len(df)), "matches": int(len(m))})
        for tic, row in m.items():
            matches[tic].append({"source": name, "id": vid})
    toi_path = root / "data" / "processed" / "cat_toi_exofop.csv"
    if toi_path.exists():
        tm = toi_matches(pd.read_csv(toi_path), targets)
        sources.append({"name": "ExoFOP TOI list", "id": "cat_toi_exofop.csv", "what": "TESS Objects of Interest", "status": "CHECKED",
                        "rows": int(len(pd.read_csv(toi_path))), "matches": int(len(tm))})
    else:
        tm = {}
        sources.append({"name": "ExoFOP TOI list", "id": "cat_toi_exofop.csv", "what": "TESS Objects of Interest", "status": "NOT_CHECKED", "reason": "file missing"})
    simbad, snote = simbad_types(targets)
    if simbad is None:
        sources.append({"name": "SIMBAD object types", "id": "simbad", "what": "SIMBAD main object type", "status": "NOT_CHECKED", "reason": snote})
        simbad = {}
    else:
        sources.append({"name": "SIMBAD object types", "id": "simbad", "what": "SIMBAD main object type", "status": "CHECKED", "matches": int(len(simbad))})
    stars = {}
    for tic in matches:
        s = simbad.get(tic)
        stars[str(tic)] = {"in_new_catalogs": matches[tic], "toi": tm.get(tic),
                           "simbad": None if not s else dict(s, group=classify_simbad(s["otype"]))}
    groups = {}
    for v in stars.values():
        if v["simbad"]:
            g = v["simbad"]["group"]
            groups[g] = groups.get(g, 0) + 1
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": sources,
            "summary": {"stars": len(stars), "in_any_new_catalog": sum(bool(v["in_new_catalogs"]) for v in stars.values()),
                        "on_toi_list": sum(bool(v["toi"]) for v in stars.values()),
                        "simbad_identified": sum(bool(v["simbad"]) for v in stars.values()), "simbad_groups": groups},
            "note": "Kostov et al. removed every target within 21 arcsec of a known eclipsing binary before publishing table2, so no match in VSX, ASAS-SN, ATLAS, Gaia or ZTF binary lists is expected and is not evidence of novelty. This sweep covers material that filter did not use.",
            "stars": stars}


def main():
    if len(sys.argv) < 2:
        print("Usage: py f19_prior_art.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    dash = pd.DataFrame(json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"])
    rep = build(dash[["tic", "ra", "dec"]], root)
    path = root / "site" / "public" / "data" / "prior_art.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    for s in rep["sources"]:
        print("%-62s %-11s %s" % (s["name"][:62], s["status"], s.get("matches", s.get("reason", ""))))
    print(rep["summary"])
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
