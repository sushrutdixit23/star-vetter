# After the note is published: what happens, in order

Dates are real where the calendar fixes them and estimates where they depend on others.
Facts about RNAAS come from the journal's own guidelines (journals.aas.org/research-note-preparation-guidelines):
1,500 words including title, headers, captions and references (150 reserved for the abstract), either one
figure or one table, not peer reviewed (an editor moderates for appropriateness and format), no author
charge at present, usually published within 72 hours of receipt, CC-BY 4.0.

## Phase 1: the note (this week)

| Step | Who | Notes |
|---|---|---|
| Read the note, set `ai_usage_confirmed` to true in `docs/author_fields.json`, run `py draft_rnaas.py .` | You | The last `[[...]]` field goes away. The note counts 1,485 words by the strict rule (table included); RNAAS excludes table contents, so there is room. |
| ADS check for 2025 to 2026 papers on the four predicted stars and on TESS full-frame eclipsing binaries | You | Not reachable from the sandbox. A paper that already lists these stars changes the novelty wording. |
| Add your ORCID to the Zenodo record | You | Edit the published record; the DOI does not change. |
| Submit at journals.aas.org/research-notes with the AI-usage disclosure | You | Moderation, not peer review. A format fix request is likely; a rejection for not being a research result is possible. |
| If rejected or stalled | Both | Post the same text as a Zenodo preprint and on arXiv (astro-ph.SR), and send the systematic-audit version to JAAVSO or OEJV. Nothing is lost: the frozen predictions already carry their own DOI. |

## Phase 2: right after it is public (days)

1. Put the note's DOI in the repository: README, the site's About page, `docs/vsx/README.md`, and the Zenodo record's "related works" field (is supplemented by).
2. Check that ADS has indexed it (usually within days). Add it to your ORCID record.
3. VSX wave 1 (see `docs/vsx/README.md`): look every star up in the live VSX database first, then submit
   the stars that are still absent, one by one, citing the note and quoting the ZTF evidence.
   Expect some rejections; VSX distrusts TESS-only evidence and these rows rely on ZTF.
4. Announce factually: candidates that survived an independent audit, predictions frozen in public,
   misses will be published. Do not use the words discovery, new binaries or confirmed.

## Phase 3: fixed dates in the next months

| Date | Event | What to do |
|---|---|---|
| 2026-11-26 | TESS Year 9 begins (Sector 111) | Nothing to publish; the freeze is already deposited. |
| 2026-12-02 | Gaia DR4 released | Write `load_epoch_photometry` in `f21_gaia_dr4_ready.py` and run the fixed-ephemeris fold on the testable stars (2 of 72 with a precise ephemeris). Re-run Gaia cross-matches on all 307 survivors: DR4 adds epoch photometry and a larger binary catalog. Update `gaia_dr3.json`-style files for DR4. |
| 2027-03-15 and later | First predicted eclipses (TIC 66732476 in Sector 115, 54 minute uncertainty; Sectors 118 to 120 for the others) | Wait for the sector's light curves to be public in MAST, time each eclipse with the f13 routines, write the measurements CSV, run `py grade_predictions.py <frozen zip> measurements.csv grades.json`. Publish every outcome, misses first. |

The grader implements only the frozen rule (3 sigma, 3-minute QLP term, nothing dropped). The step that times
each eclipse in new data is not written yet because it needs real data to test; the rule says it uses the same
code as the predictions, so it reuses `f13_ephemeris.py`.

## Phase 4: what the results will mean

- If most validated predictions are recovered and the unvalidated ones scatter more: the ephemeris method works and
  its uncertainty model is honest. That is a real, citable result about how far TESS ephemerides can be carried.
- If many are inconsistent: the quoted uncertainties are too small or the periods drift. That is also a result, and
  the z-score rms in `grades.json` quantifies it. It would not mean the stars are not binaries.
- Neither outcome says anything about whether the 307 are real binaries. That question is answered by ZTF, Gaia and
  later spectroscopy, not by timing.

## What could go wrong (and the response)

| Risk | Likelihood | Response |
|---|---|---|
| Moderator calls the note not a research result | Moderate | Reframe as the audit method plus pre-registration; or post as a preprint and aim at JAAVSO. |
| A 2025 or 2026 paper already lists some survivors | Real (Oddo and Liu 2026 catalogs were not checked) | Check them when the tables are available; downgrade those stars to KNOWN and say so. |
| VSX rejects TESS-only or thinly supported entries | High for wave 2 | Submit only wave 1; use ZTF folds as figures. |
| Predictions miss | Likely for the unvalidated pair | They are pre-registered as unvalidated; publish them anyway. |
| A star is later found to be a blend or a planet | Real | The tiers already say which ones carry caveats; correct the record publicly. |
