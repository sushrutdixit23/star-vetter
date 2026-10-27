# Star Vetter

An unattended pipeline that screens unvetted NASA TESS targets for eclipsing
binary stars, checks each survivor against six catalogs, and then checks at the
pixel level that the signal really comes from the target star. It runs every
6 hours on GitHub Actions and publishes its results to a live site.

**Live site:** https://star-vetter.vercel.app

Everything it reports is a **candidate**. Nothing here has been peer reviewed
or independently followed up.

## Snapshot (26 Oct 2026)

These numbers change every run. The live site always has the current ones.

| Step | Targets |
|---|---|
| Sampled and fetch attempted | 20,920 of 872,720 catalog targets (2.4%) |
| Usable light curve obtained | 13,491 |
| Passed statistical vetting gates | 3,244 |
| Reached the pixel-level check | 3,092 (2,854 with no catalog match, 238 already catalogued as other variable types) |
| Confirmed on-target | 303 (299 with no catalog match, 4 catalogued as other variable types) |

"Confirmed on-target" means the eclipse signal was localized to the target
star's pixels. It does not mean the star has been classified or validated as an
eclipsing binary by anyone other than this pipeline.

## How it works

```
catalog -> sample -> fetch light curves -> statistical vetting
        -> novelty cross-match (6 catalogs) -> contamination check
        -> pixel-level check -> dossier PDFs -> site + write-ups
```

| Stage | Scripts | What it does |
|---|---|---|
| Ingest | `f1_ingest.py`, `f1b_sample.py` | Loads the unvetted TESS eclipsing-binary candidate table and draws a new batch stratified by TESS magnitude |
| Fetch | `f2c_fetch_lightcurves.py` | Downloads TESS light curves; resumable, skips rows already done |
| Vet | `f3i_vet.py` | Box Least Squares period search plus gates: eclipse count, odd/even depth consistency, outlier-robust significance, independent secondary-eclipse search |
| Novelty | `f4f_novelty.py` | Cross-matches VSX, ASAS-SN, the Gaia eclipsing-binary table, the Gaia variable classification, the TESS EB catalog (Prsa+2022) and the ExoFOP TOI list |
| Contamination | `diag_blend.py`, `diag_pixel.py` | Catalog-based blend check, then a difference-image check on the target pixels (dip reappears in-sector, compact source, timing agrees with the light curve) |
| Dossiers | `f5_dossier.py` | One PDF per confirmed candidate |
| Classifier | `f7a`, `f7b`, `f7c` | Predicts pixel-check outcome before the expensive check runs (see below) |
| Write-ups | `f8_generate_writeups.py`, `f10_generate_discoveries.py` | Calls the Claude API once per confirmed candidate for a plain-English paragraph, grounded only in that candidate's computed numbers and cached so it is never regenerated |
| Orchestrator | `f6_orchestrator.py` | Runs all of the above in order with retries; writes a run record to `data/runs/` |
| Site data | `export_*.py` | Writes the JSON the Next.js site in `site/` reads |

`diag_*.py` are live pipeline stages, not scratch files.
`resolve_merge_conflicts.py` is used by CI to merge bot commits with local
pushes by unioning the processed CSVs by TIC.

## The ML component

`f7b_train_classifier.py` trains two classifiers to predict, from features known
before the pixel check, whether a candidate will be confirmed on-target. It is
compared against a baseline of "send every candidate to the pixel check".

Trained on 3,092 pixel-checked candidates (303 positive, 2,789 negative), 5-fold
cross-validation:

| Model | ROC-AUC | Precision | Recall |
|---|---|---|---|
| Logistic regression | 0.740 +/- 0.024 | 0.205 | 0.627 |
| Gradient-boosted trees (chosen) | 0.808 +/- 0.038 | 0.509 | 0.106 |
| Baseline (check everything) | n/a | 0.098 | 1.000 |

The useful number is the screening trade-off. Choosing a score threshold of 0.03
would skip 42.6% of pixel checks while keeping 91.1% of the confirmed
candidates (cross-validated estimate).

Limits, stated plainly:

- **The classifier is in record-only mode.** It scores candidates but never
  filters them. It will only start filtering once more labeled runs accumulate.
- **Labels come from this pipeline's own pixel check**, not from independent
  ground truth, so the model learns to imitate that check.
- The classes are about 90% negative, so accuracy is not a meaningful metric
  here and is not reported.

## Run it

Needs Python 3.12 and network access to MAST. Dependencies are unpinned on
purpose; see `requirements.txt`.

```bash
pip install -r requirements.txt
python f6_orchestrator.py /path/to/this/repo
```

`ANTHROPIC_API_KEY` is only needed for the write-up stages (`f8`, `f10`). The
core pipeline runs without it.

The scheduled run is defined in `.github/workflows/pipeline.yml`: cron
`13 */6 * * *`, default batch of 150 new targets, then data export, site build,
commit, and deploy.

## Layout

```
f*.py                pipeline stages, in order (f1 ... f12)
diag_*.py            contamination and pixel-level checks (live stages)
export_*.py          write site data JSON
check_*.py           consistency checks on artifacts and site content
data/processed/      pipeline CSVs and model metrics
data/dossiers/       per-candidate PDFs
site/                Next.js site deployed to Vercel
.github/workflows/   the 6-hourly pipeline
```

## Data and credit

Light curves and pixel data come from NASA's TESS mission via MAST and
`lightkurve`. The input candidate table is from Kostov et al. (2025). Catalog
cross-matching uses VSX, ASAS-SN, Gaia, Prsa et al. (2022) and ExoFOP.
