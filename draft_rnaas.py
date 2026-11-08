import re
import sys
import json
from pathlib import Path

# Draft of a Research Note of the AAS, generated from the pipeline's own JSON
# files so that every number in the text can be traced to a file and cannot
# drift from the site. RNAAS limits: 1,500 words, one table OR one figure, an
# abstract, references. The AAS requires an AI-usage disclosure on submission.
#
# Fields the author must complete before submitting are marked [[...]]; the
# draft refuses to claim a DOI it does not have.

WORD_LIMIT = 1500
DATA = Path("site") / "public" / "data"


def _load(root, name):
    return json.loads((root / DATA / name).read_text(encoding="utf-8"))


def pc(x, d=1):
    return "%.*f%%" % (d, 100.0 * x)


def pci(m, d=1):
    """median/lo/hi dict -> '2.22% (95% interval 1.98 to 2.48%)'."""
    return "%.*f%% (95%% interval %.*f to %.*f%%)" % (d, 100 * m["median"], d, 100 * m["lo"], d, 100 * m["hi"])


def kn(r):
    return "%d of %d" % (r["k"], r["n"])


def bjd(btjd):
    return "%.4f" % (btjd + 2457000.0)


def table_rows(pred):
    stars = sorted(pred["stars"], key=lambda s: s["predictions"][0]["t_btjd"] if s["predictions"] else 1e9)
    rows = []
    for s in stars:
        e = s["ephemeris"]
        pr = s["predictions"]
        sectors = sorted({p["sector"] for p in pr})
        rows.append({
            "tic": s["tic"], "tmag": s["tmag"], "grade": s["grade"].capitalize(),
            "period": e["period_days"], "period_sigma": e["period_sigma_days"],
            "t0": e["t0_btjd"] + 2457000.0, "n": len(pr),
            "sectors": ", ".join(str(x) for x in sectors),
            "first": pr[0]["t_btjd"] + 2457000.0, "sigma_first": pr[0]["sigma_min"],
            "best_sigma": s["best_sigma_min"],
        })
    return rows


def render(audit, rec, alias, nb, pred, novelty, xm):
    a, r, al = audit, rec, alias
    ot = a["rates"]["on_target_per_usable"]
    ps = a["rates"]["passed_gates_per_usable"]
    f = {x["key"]: x["count"] for x in a["funnel"]}
    ro = r["recall_overall"]
    fa = r["false_alarm_shuffle"]
    by_depth = {c["bin"]: c for c in r["recall_by_depth"]}
    head = str(nb["method"]["headline_floor_arcsec"]).rstrip("0").rstrip(".")
    nbs = nb["summary_by_floor"][str(int(nb["method"]["headline_floor_arcsec"]))]
    rows = table_rows(pred)
    c = pred["counts"]
    v = pred["validation"]
    h = pred["holdout_calibration"]
    n_ecl = sum(x["n"] for x in rows)
    deep = by_depth.get(">10%")

    L = []
    L.append("# An audit of the unvetted TESS Ten Thousand eclipsing-binary list, with pre-registered eclipse times for TESS Year 9")
    L.append("")
    L.append("Sushrut Dixit [[ORCID and affiliation, e.g. Independent researcher, Lucknow, India]]")
    L.append("")
    L.append("## Abstract")
    L.append("")
    L.append(
        "Kostov et al. (2025) published about 873,000 eclipsing-binary detections from TESS full-frame images without "
        "vetting them. I ran an independent pipeline on a random sample of %s of those stars. %s had a usable light curve; "
        "%s were confirmed on-target in difference images, %s of usable stars. These are entries of the published list that survived "
        "an independent check, not new detections. Injecting artificial binaries into real light curves shows the pipeline "
        "recovers about %s of those it could reach, so the rate is a lower bound. I also give pre-registered mid-eclipse times, "
        "with uncertainties and an outcome rule, for %d primary eclipses of %d stars in TESS Year 9." % (
            format(f["sampled"], ","), format(f["usable"], ","), format(f["on_target"], ","), pci(ot, 2),
            pc(ro["detected"]["rate"], 0), n_ecl, len(rows)))
    L.append("")
    L.append("## 1. Purpose")
    L.append("")
    L.append(
        "Kostov et al. (2025) describe the bulk of their list as unvetted and unvalidated neural-network detections. A "
        "random-sample audit gives one estimate of what an independent check recovers, and a frozen list of timing "
        "predictions gives a test that no later analysis can adjust.")
    L.append("")
    L.append("## 2. Sample and audit")
    L.append("")
    L.append(
        "Stars were drawn at random, stratified by TESS magnitude into fifths of the list (seeded, %s stars, %s of the list), "
        "and population figures are re-weighted by each fifth's share. Light curves from SPOC, QLP or GSFC-ELEANOR-LITE were "
        "flattened and searched with box least squares, then passed through gates on eclipse count, in-eclipse points, "
        "signal-to-noise, depth consistency and photometric quality (Lightkurve Collaboration 2018; Astropy Collaboration 2022). "
        "Stars with no catalog match were then checked in TESS difference images for whether the dimming lies on the target." % (
            format(f["sampled"], ","), pc(a["frame"]["sampled_fraction"], 1)))
    L.append("")
    L.append(
        "Of %s sampled stars, %s (%s) had a usable light curve. Of those, %s%% passed the statistical gates and %s "
        "were confirmed on-target: %s. The rate falls from %s for the brightest fifth (Tmag up to %.2f) to %s for the faintest (Tmag above %.2f)." % (
            format(f["sampled"], ","), format(f["usable"], ","), pc(a["rates"]["usable_per_sampled"]["median"], 0),
            "%.1f" % (100 * ps["median"]), format(f["on_target"], ","), pci(ot, 2),
            pc(a["strata"][0]["on_target_per_usable"]["rate"], 1), a["frame"]["strata_inner_edges"][0],
            pc(a["strata"][-1]["on_target_per_usable"]["rate"], 1), a["frame"]["strata_inner_edges"][-1]))
    L.append("")
    L.append("## 3. How much the pipeline misses")
    L.append("")
    L.append(
        "To measure recall I injected %d artificial binaries (trapezoid eclipses, circular orbits, period 0.65 to 39.8 d, primary "
        "depth 0.2 to 50%%) into real light curves of %d sampled stars whose unmodified light curves fail the gates, and ran "
        "the unchanged gates. Of the %d injections the search range could reach, %s (%s) passed with a period correct or half or "
        "double the true one. Recall rises with depth, from %s for depths under 0.5%% to %s above 10%%%s. The "
        "gate most often responsible for misses was the requirement of at least three usable eclipses. Copies of the real light "
        "curves cut into one-day chunks and shuffled passed the gates in %s cases (%s), a measure of false alarms from noise." % (
            r["counts"]["injections"], r["counts"]["stars"], ro["n"], kn(ro["detected"]), pc(ro["detected"]["rate"], 0),
            pc(by_depth["<0.5%"]["detected"]["rate"], 0), pc(deep["detected"]["rate"], 0) if deep else "n/a",
            "" if not deep else " (%s)" % kn(deep["detected"]), kn(fa), pc(fa["rate"], 1)))
    L.append("")
    L.append(
        "Injections were made after flattening, so recall for real eclipses is probably lower. Recall depends on the injected "
        "mix of periods and depths and is meant to be compared across bins, not quoted as one number.")
    L.append("")
    L.append(
        "Neighbour contamination was assessed with TESS Input Catalog neighbours within 63 arcsec. A neighbour counts if it is "
        "bright enough, after allowing for the fraction of its light in the aperture, and consistent with the measured "
        "centroid to within an assumed %s arcsec. For %d of %d stars no neighbour qualifies; for %d a qualifying neighbour is too close for "
        "TESS to separate. Of %d candidates whose ATLAS period (Heinze et al. 2018) differs from the TESS period, a harmonic or "
        "sidereal-day alias explains %d, against %.1f expected by chance. ATLAS labels most of these 'dubious'." % (
            head, nbs.get("NO_VIABLE_NEIGHBOUR", 0), nb["stars_assessed"], nbs.get("UNSEPARABLE_NEIGHBOUR", 0),
            al["tested"], al["explained"]["k"], al["chance"]["expected_explained"]))
    L.append("")
    L.append("## 4. Pre-registered predictions")
    L.append("")
    L.append(
        "Of %d candidates considered, %d meet the selection rule: a fitted ephemeris that is not rejected, a primary eclipse in a "
        "Year 9 sector, and a best 1-sigma uncertainty of at most %d min. Ephemerides were fitted by generalised least squares with excess timing "
        "noise. A '%s' grade means an ephemeris fitted to the earliest sectors predicted later ones (%s of the %s "
        "stars in the hold-out test passed); 'Unvalidated' means too few sectors for that test. On %d Prsa et al. (2022) binaries "
        "with a deliberately degraded starting ephemeris the fitted epoch was within 3 sigma in %s of cases. "
        "Table 1 gives the ephemerides. Predicted times are barycentric (BJD_TDB); the frozen bundle lists every eclipse, "
        "including geocentric UTC." % (
            c["candidates_considered"], c["listed"], int(pred["max_sigma_min"]), "Validated", h["n_stars"] - h["n_failed"], h["n_stars"],
            v["n_stars"], pc(v["epoch_within_3sigma_fraction"], 0)))
    L.append("")
    L.append("| TIC | Tmag | Grade | Period (d) | T0 (BJD_TDB) | Sectors | Eclipses | First predicted minimum (BJD_TDB) | 1-sigma (min) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        L.append("| %d | %.2f | %s | %.6f +/- %.6f | %.4f | %s | %d | %s | %.1f |" % (
            x["tic"], x["tmag"], x["grade"], x["period"], x["period_sigma"], x["t0"], x["sectors"], x["n"], bjd(x["first"] - 2457000.0), x["sigma_first"]))
    L.append("")
    L.append("Table 1. Ephemerides and first predicted primary minimum in TESS Year 9. Sector dates are provisional (MIT, NASA), "
             "so sectors 117 to 121 are interpolated. Covariances and all %d predicted minima are in the frozen bundle." % n_ecl)
    L.append("")
    L.append("## 5. Evaluation rule")
    L.append("")
    L.append(
        "When Year 9 data are public, each predicted eclipse that TESS observed will be timed with the same code. It counts as "
        "recovered if the measured mid-eclipse lies within 3 sigma of the prediction, with sigma combined with the "
        "measurement error; as inconsistent if observed outside that; and as insufficient data if not covered. Every "
        "prediction is reported whatever its outcome. The predictions were frozen with SHA-256 hashes and deposited "
        "before the data: [[Zenodo DOI and deposit date, to be inserted after the freeze]].")
    L.append("")
    L.append("## 6. Limits")
    L.append("")
    known = novelty["counts"].get("ALREADY_KNOWN", 0)
    cat = {x["key"]: x for x in xm["catalogs"]}
    ij24, ij21 = cat["ijspeert2024_eb"], cat["ijspeert2021_eb"]
    L.append(
        "The %s on-target stars are entries of the published unvetted list, and %d of them are already in six other "
        "variable-star catalogs (ZTF, CRTS, WISE, ATLAS, ASAS-3, KELT) at the same period. None is in the vetted tables of "
        "Kostov et al. (2025), in Prsa et al. (2022), or in the eclipsing-binary lists of IJspeert et al. (2021, 2024) or "
        "Justesen and Albrecht (2021); but the IJspeert searches covered only %d and %d of the %d stars, so that is weak evidence of "
        "novelty. Earlier checks against VSX, ASAS-SN, Gaia DR3 eclipsing-binary tables and the TOI list are in the repository. Not "
        "yet checked: the 2024 to 2026 machine-learning TESS catalogs and Gaia DR4. Only %d stars have predictions, and only %d are "
        "validated. Pixel checks cannot exclude a neighbour inside the centroid tolerance. The %s recall figure rests on %d stars." % (
            format(f["on_target"], ","), known, ij21["n_in_parent_sample"], ij24["n_in_parent_sample"], xm["candidates"],
            c["listed"], c["listed_validated"], pc(ro["detected"]["rate"], 0), r["counts"]["stars"]))
    L.append("")
    L.append("## Data and code")
    L.append("")
    L.append("Code, data files and the frozen predictions: [[repository URL and Zenodo DOI]].")
    L.append("")
    L.append("## AI-usage disclosure")
    L.append("")
    L.append(
        "[[Author to confirm before submission.]] The AI tool Claude (Anthropic) was used to write and debug the analysis code, "
        "to run the injection tests, and to draft and edit this note. The author checked the code outputs and the numbers "
        "in the text against the data files, and responsibility for the final manuscript text lies entirely with the author.")
    L.append("")
    L.append("## Acknowledgments")
    L.append("")
    L.append("This work uses data from the TESS mission, obtained from the Mikulski Archive for Space Telescopes (MAST), and "
             "catalogs from VizieR.")
    L.append("")
    L.append("## References")
    L.append("")
    L.append("Astropy Collaboration 2022, ApJ, 935, 167")
    L.append("")
    L.append("Heinze, A. N., et al. 2018, AJ, 156, 241")
    L.append("")
    L.append("Kostov, V. B., et al. 2025, ApJS, 279, 50")
    L.append("")
    L.append("Lightkurve Collaboration 2018, Astrophysics Source Code Library, ascl:1812.013")
    L.append("")
    L.append("Prsa, A., et al. 2022, ApJS, 258, 16")
    L.append("")
    L.append("Ricker, G. R., et al. 2015, JATIS, 1, 014003")
    L.append("")
    return "\n".join(L)


def word_count(text):
    """Words in the whole note, tables and references included (the strict reading of the limit)."""
    body = re.sub(r"\|[-| ]+\|", " ", text)
    body = body.replace("|", " ")
    return len(re.findall(r"\S+", body))


def table_count(text):
    return len(re.findall(r"^\|[-| ]+\|$", text, flags=re.M))


def main():
    if len(sys.argv) < 2:
        print("Usage: py draft_rnaas.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    text = render(_load(root, "audit.json"), _load(root, "recovery.json"), _load(root, "atlas_alias.json"),
                  _load(root, "neighbours.json"), _load(root, "predictions.json"),
                  _load(root, "novelty_extra.json"), _load(root, "tess_catalog_xmatch.json"))
    out = root / "docs" / "rnaas_note.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    n = word_count(text)
    print("Wrote %s: %d words (limit %d), %d table(s)" % (out, n, WORD_LIMIT, table_count(text)))
    todo = re.findall(r"\[\[.*?\]\]", text)
    print("%d field(s) for the author to complete:" % len(todo))
    for t in todo:
        print("  " + t)
    if n > WORD_LIMIT or table_count(text) != 1:
        print("ERROR: over the RNAAS limits")
        sys.exit(1)


if __name__ == "__main__":
    main()
