# From findings to publishable science: what only a person can do

Numbers here come from `docs/novelty_findings.md` (generated). This file lists the actions.

## What the pipeline now supports

1. A list of stars with a displaced secondary eclipse (e cos w lower limits) that pass every veto.
   Two of them are also re-measured independently in ZTF.
2. A period-change candidate, TIC 237115819: eclipse times that follow one smooth parabola in TESS
   and in ZTF; the older per-eclipse timing in the repository shows the same trend. The rule that selects it was run on
   synthetic constant-period light curves with the real sampling and noise (see the findings file).
3. A frozen list of its next eclipse times: `docs/period_change_predictions.json`.

## What is still missing for a real discovery claim

| Gap | Why it matters | Who can close it |
|---|---|---|
| No spectroscopy | Only e cos w is measured; masses, radii, true eccentricity and the nature of any third body need radial velocities | Author with a collaborator, or a TFOP request |
| Cause of the period change unknown | A distant third body, mass exchange and others all give a parabola over a few years | More timing over years; a spectrum for a third set of lines |
| Eccentric stars are mostly TESS-only | Two are re-measured in ZTF; the rest rely on two halves of TESS data | ATLAS or ASAS-SN photometry (needs your account) |
| No physical light-curve model | Depths and durations are not turned into stellar parameters | A follow-up paper with PHOEBE or ellc plus MCMC |

## Actions for you, in order

1. **Deposit the prediction file.** Upload `docs/period_change_predictions.json` to Zenodo in the same
   way as the first pre-registration (web upload; never paste a token anywhere). Record the DOI in
   the file `docs/author_fields.json` under a new field when you have it. The sha256 is printed by
   `py predict_period_change.py .`; keep the file byte-identical.
2. **Read `docs/novelty_findings.md` as the responsible author.** Check the table against the
   plots on the site. Anything you cannot defend, remove before it goes in a note.
3. **Find one professional co-author or mentor** in eclipsing-binary timing or TESS follow-up
   (for example through the TESS Eclipsing Binary Working Group or the AAVSO). A second pair of
   eyes is the cheapest way to raise credibility, and they can request spectra.
4. **Ask for spectra** of the best targets: TIC 264099112, 308578336, 59387976 (northern, ZTF
   supported, no prior literature found) and TIC 237115819. Even two velocities per star separate
   a real eccentric binary from a blend. Check LAMOST and Gaia archives first (free).
5. **Search ADS and SIMBAD** for each listed TIC number before any claim of novelty (the sandbox
   cannot reach ADS).
6. **Second research note** (RNAAS, 1,500 words, one table) on the period-change candidate only
   after steps 1 and 2. The note must say: candidate, cause unknown, predictions deposited.

## What not to say yet

- "Discovery of new eclipsing binaries": the stars are in Kostov et al. 2025 by construction.
- "Third body detected": no light-travel-time orbit has been fitted and no companion seen.
- True eccentricities: only the projection e cos w is measured.
