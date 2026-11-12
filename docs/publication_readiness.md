# Publication readiness

Run `py check_publication_readiness.py .` for the live status. It checks everything the pipeline
can settle by itself and lists what only the author can do. Numbers are not repeated here so
they cannot drift from the data files; see `site/public/data/evidence.json`, `ztf_independent.json`
and `docs/rnaas_note.md`.

## What the note may claim

- A random-sample audit of Kostov et al. (2025) table2_unvetted: usable fraction, on-target
  fraction, and a recall-corrected range (not a single number).
- Survivors of independent checks, labelled by what was actually shown:
  `INDEPENDENTLY_SUPPORTED` (ZTF recovers the eclipses at the TESS period, or a Gaia DR3 SB1
  orbit carries the period), `TESS_ONLY_CLEAN`, `TESS_ONLY_CAVEATS`, `DISFAVOURED`.
- Pre-registered eclipse times for the stars that meet the selection rule, with an outcome rule
  frozen before the data exist.

## What the note must not claim

- New binary stars or a discovery. Absence from catalogs is largely by construction (Kostov et al.
  removed everything within 21 arcsec of a known eclipsing binary before publishing the list).
- That the ZTF test confirms the period search. It starts from the TESS period and duration, so
  it confirms the signal only.
- A population eclipsing-binary rate. The corrected rate is a range driven by recall, which
  depends strongly on host-star noise.
- That blends under about 0.2 pixel, planets or brown dwarfs are excluded. No physical
  light-curve model was fitted.

## Done in this repository

- Injection-recovery with host-noise dependence, shuffled false-alarm rate, and rejected gate
  variants (two-eclipse gate, finer period grid).
- ZTF independent test with calibrated power (CONFIRMED / NOT_SEEN / INCONCLUSIVE / NO_DATA).
- Gaia DR3 cross-match: SB1 period matches, astrometric orbits, RUWE, Gaia-based neighbour test.
- Post-2025 prior-art sweep: SIMBAD types, TOI list, Kostov et al. 2026 quadruple candidates.
- Evidence tiers and novelty labels per star, shown on the Audit page and each candidate page.
- Predictions with QLP timing term in the grading rule, verified sector assignments.
- Gaia DR4 plan: which stars can be tested with a fixed-ephemeris fold on release day.
- Findings from the light curves (`docs/novelty_findings.md`, generated): e cos w lower limits for stars that pass
  vetoes against fast pulsators and period multiples, a tidal-circularisation sanity check, and a calibrated
  eclipse-timing search (one smooth period-change candidate). Next actions: `docs/novelty_next_steps.md`.

## Not possible from this environment

| Item | Why | Who |
|---|---|---|
| Independent photometry for stars south of declination -30 | ZTF does not cover them; ATLAS needs an account and token; ASAS-SN API unreachable | Author (optional) |
| Gaia DR4 epoch photometry | Released 2 December 2026; the loader is the one function left to write on the day | Day of release |
| LAMOST / SDSS spectra | Not queried | Optional follow-up |
| Oddo et al. 2026 and Liu et al. 2026 catalogs | Not in VizieR; need the journal tables | Author or follow-up |
| Physical light-curve models (ellc/PHOEBE with MCMC) | Reserved for a showcase subset | Follow-up paper |
| Final ADS prior-art check | ADS is not reachable | Author |

## Author actions before submission

Done: PRs merged to main; predictions frozen 2026-11-10 from commit d85f405 (bundle hash on the
Predictions page); deposited on Zenodo as doi:10.5281/zenodo.24115848; ORCID and affiliation filled
from `docs/author_fields.json`.

Still yours:
1. Read the whole note as the person responsible for it. Then set `ai_usage_confirmed` to `true` in
   `docs/author_fields.json` and run `py draft_rnaas.py .` to remove the last `[[...]]` field.
2. Add your ORCID to the Zenodo record once Zenodo can find it (Edit the published record).
3. Check ADS for 2025 to 2026 papers on the listed TIC numbers (not reachable from the sandbox).
4. Submit to RNAAS with the AI-usage disclosure.

See also: `docs/after_publication.md` (what happens after submission, with dates), `docs/next_papers.md`
(what each later paper needs), `docs/vsx/` (submission package), `grade_predictions.py` (Year 9 grading).

## Path after the note

1. RNAAS (1,500 words, one table, moderated, DOI).
2. Report the independently supported subset to VSX only after the note is public, with ZTF or
   ATLAS evidence (VSX does not accept TESS-only evidence).
3. Year 9 outcomes arrive from March 2027 (first predicted eclipse is in Sector 115).
4. A full paper (AJ or ApJS) only after a calibrated post-DR4 audit.
