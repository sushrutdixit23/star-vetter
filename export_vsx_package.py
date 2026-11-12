import sys
import json
import math
from pathlib import Path

import pandas as pd

# Submission package for the AAVSO Variable Star Index (VSX), built only from files the
# pipeline already wrote. Nothing here is sent anywhere.
#
# VSX does not accept TESS-only evidence for a new variable. So the package contains only
# survivors with independent photometry (ZTF) behind them, and it is split by how safe the
# entry is, so a first submission cannot contain a star with an unresolved caveat:
#
#   wave1     independently supported by ZTF, no prior record found, and NO caveat of any kind
#   wave2     the same, but with at least one caveat (period alias, RUWE, neighbour, odd/even).
#             Hold these until the caveat is resolved; most need a physical look first.
#   existing  independently supported but already listed somewhere as a variable (possibly at
#             another period): look up the existing VSX entry first; these are corrections or
#             confirmations, not new entries.
#
# Every row carries its caveats and the evidence, so the person submitting can see why.

OUT_DIR = Path("docs") / "vsx"
COLUMNS = ["tic", "gaia_dr3_source_id", "ra_deg", "dec_deg", "g_mag", "vsx_type", "period_days", "period_source",
           "epoch_bjd_tdb", "amplitude_mag_tess", "ztf_p_value", "ztf_epochs", "ztf_span_days", "tess_odd_even_z",
           "secondary_z_ztf", "ruwe", "wave", "caveats", "evidence", "novelty_reasons"]


def amplitude_mag(depth):
    """Fractional flux depth -> magnitude amplitude (TESS band)."""
    if depth is None or not (0.0 < depth < 1.0):
        return None
    return -2.5 * math.log10(1.0 - depth)


def best_period(tess, ztf_refined, tol=2e-3):
    """The ZTF-refined period (baseline of years) when it agrees with TESS to within tol, else TESS."""
    if ztf_refined and abs(ztf_refined - tess) / tess <= tol:
        return float(ztf_refined), "ZTF refined (baseline of years), agrees with TESS"
    return float(tess), "TESS BLS"


def wave_of(star):
    """wave1 / wave2 / existing / None for one evidence entry."""
    if star["evidence_tier"] != "INDEPENDENTLY_SUPPORTED" or star["ztf_status"] != "CONFIRMED":
        return None
    if star["novelty"] == "NO_PRIOR_FOUND":
        return "wave1" if not star["caveats"] else "wave2"
    if star["novelty"] == "KNOWN_VARIABLE":
        return "existing"
    return None          # known eclipsing or known binary: already catalogued, nothing to submit


def build(root):
    d = root / "site" / "public" / "data"
    ev = json.loads((d / "evidence.json").read_text(encoding="utf-8"))["stars"]
    ztf = json.loads((d / "ztf_independent.json").read_text(encoding="utf-8"))["stars"]
    gaia = json.loads((d / "gaia_dr3.json").read_text(encoding="utf-8"))["stars"]
    sky = {str(r["tic"]): r for r in json.loads((d / "dashboard.json").read_text(encoding="utf-8"))["sky"]}
    vet = pd.read_csv(root / "data" / "processed" / "f3i_vetting_results.csv").set_index("TIC")
    rows = []
    for tic, s in ev.items():
        w = wave_of(s)
        if w is None or tic not in sky or int(tic) not in vet.index:
            continue
        z, g, v, k = ztf.get(tic, {}), gaia.get(tic) or {}, vet.loc[int(tic)], sky[tic]
        period, src = best_period(float(k["period_days"]), z.get("refined_period"))
        rows.append({
            "tic": int(tic), "gaia_dr3_source_id": g.get("source_id"), "ra_deg": round(float(k["ra"]), 6), "dec_deg": round(float(k["dec"]), 6),
            "g_mag": None if g.get("g_mag") is None else round(float(g["g_mag"]), 3),
            "vsx_type": "E", "period_days": round(period, 6), "period_source": src,
            "epoch_bjd_tdb": round(float(v["bls_t0"]) + 2457000.0, 4),
            "amplitude_mag_tess": None if amplitude_mag(float(v["bls_depth"])) is None else round(amplitude_mag(float(v["bls_depth"])), 3),
            "ztf_p_value": z.get("p_value"), "ztf_epochs": z.get("epochs"), "ztf_span_days": None if z.get("span_days") is None else round(z["span_days"]),
            "tess_odd_even_z": None if pd.isna(v.get("odd_even_z")) else round(float(v["odd_even_z"]), 2),
            "secondary_z_ztf": None if z.get("secondary_z") is None else round(z["secondary_z"], 1),
            "ruwe": g.get("ruwe"), "wave": w, "caveats": "; ".join(s["caveats"]), "evidence": "; ".join(s["independent_lines"]),
            "novelty_reasons": "; ".join(s["novelty_reasons"]),
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.sort_values(["wave", "ztf_p_value"]).reset_index(drop=True)


README = """# VSX submission package

Built by `export_vsx_package.py` from the pipeline's own files. Nothing here has been sent to VSX.

## What is in it

| File | Rows | What it is | Safe to submit? |
|---|---|---|---|
| vsx_wave1.csv | {n1} | ZTF-confirmed, no prior record found, no caveat of any kind | Yes, after the RNAAS note is public (cite its DOI) |
| vsx_wave2_caveats.csv | {n2} | Same, but each has at least one caveat (period alias, RUWE above 1.4, neighbour, odd/even) | Not yet: resolve the caveat first |
| vsx_check_existing.csv | {n3} | ZTF-confirmed but already listed as a variable somewhere, possibly at another period | No new entry: look up the existing VSX record, then submit a period correction if it differs |

Stars already known as eclipsing binaries or as spectroscopic binaries are left out: they are catalogued.

## How VSX works (check the current form, it changes)

1. You need a free AAVSO account. Submissions go through the "Submit new variable star" form on VSX
   (aavso.org/vsx), one star at a time, or a bulk spreadsheet through the VSX team for larger lists.
2. For each star VSX asks for coordinates, type, period, epoch, amplitude, and a reference.
   Type `E` means eclipsing, unclassified. Do not guess EA/EB/EW without a light-curve model.
3. The reference should be the RNAAS note's DOI (after it is published) and the Zenodo record
   doi:10.5281/zenodo.24115848 for the frozen predictions. Do not submit before the note is public.
4. Epochs here are BJD_TDB; VSX asks for HJD. The two differ by under 10 minutes, so say BJD_TDB in the remarks.
5. VSX moderators may reject a star on TESS-only evidence. The ZTF evidence is the reason these rows are here.
   Quote the ZTF p-value, number of epochs and baseline from the CSV.

## Do not submit

- Any star from wave 2 or `existing` as a new entry.
- Any star for which you have not looked at the ZTF folded light curve yourself.
- Any star the VSX search by coordinates (3 arcsec) already returns, even under another name.
  Run that search for every wave-1 star first; the pipeline checked SIMBAD and VizieR but not VSX's
  own live database, which is the authority.

`ztf_p_value` of 0.0033 is the floor of the test (no control period out of 300 matched the signal), not a measured value.
Quote it as "p < 0.01".

Period columns: `period_days` is the ZTF-refined period when it agrees with TESS to 0.2 percent
(a baseline of years pins the period far better than 27 days of TESS), otherwise the TESS period.
"""


def write(root, df):
    out = root / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    names = {"wave1": "vsx_wave1.csv", "wave2": "vsx_wave2_caveats.csv", "existing": "vsx_check_existing.csv"}
    counts = {}
    for w, name in names.items():
        sub = df[df["wave"] == w]
        counts[w] = len(sub)
        sub.to_csv(out / name, index=False, encoding="utf-8", lineterminator="\n")
    (out / "README.md").write_text(README.format(n1=counts["wave1"], n2=counts["wave2"], n3=counts["existing"]), encoding="utf-8", newline="\n")
    return counts


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_vsx_package.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    df = build(root)
    counts = write(root, df)
    print("wave1 %d, wave2 %d, existing %d" % (counts["wave1"], counts["wave2"], counts["existing"]))
    print("Written under %s" % (root / OUT_DIR))


if __name__ == "__main__":
    main()
