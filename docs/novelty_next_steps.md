# From findings to publishable science: what only a person can do

Numbers here come from `docs/novelty_findings.md` (generated). This file lists the actions.

## What the pipeline now supports

1. A list of stars with a displaced secondary eclipse (e cos w lower limits) that pass every veto,
   including a rule that each half of the data holds at least two secondary eclipses (a star with fewer is
   reported as INSUFFICIENT_FOR_HALVES, not as circular). Two of them are also re-measured independently in ZTF.
   The eccentricity measurement was checked against the published phases of 50 Prsa et al. 2022
   systems (see `docs/novelty_findings.md`).
2. A period-change candidate, TIC 237115819: eclipse times that follow one smooth parabola in TESS
   and in ZTF; the older per-eclipse timing in the repository shows the same trend. The rule that selects it was run on
   synthetic constant-period light curves with the real sampling and noise (see the findings file).
3. A frozen list of its next eclipse times: `docs/period_change_predictions.json`.

## What is still missing for a real discovery claim

| Gap | Why it matters | Who can close it |
|---|---|---|
| No dedicated spectroscopy | Archival spectra now give: Gaia orbits at the eclipse period (4 stars, two of which check the light-curve e), Gaia velocity ranges (93; 60 move, 25 static), APOGEE visit orbits (3). Masses are NOT recovered: Kepler masses from the Gaia radius run about 1.5 times too high | Double-lined radial velocities: a collaborator or TFOP request for the best few; Gaia DR4 epoch velocities (2 December 2026, `f25_gaia_dr4_run.py`) for motion tests |
| Cause of the period change unknown | A light-travel-time orbit with P3 of 6 to 22 yr fits as well as the parabola but does not beat it; mass exchange and others also fit | More timing over years; a spectrum for a third set of lines |
| Eccentric stars are mostly TESS-only | Two are re-measured in ZTF; the rest rely on two halves of TESS data | ATLAS or ASAS-SN photometry (needs your account) |
| Physical light-curve model is photometry-only | `f26_ebfit.py` (ellc + MCMC) now gives e, omega, i, r1, r2 and light ratio, validated on AI Phe; limb darkening and third light are the main systematics | Spectroscopic temperatures for limb darkening; double-lined velocities for masses |

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
4. **Ask for spectra** of the best targets: TIC 264099112 and 308578336 (independently supported,
   no prior literature found), TIC 394805902 (large offset, no prior found) and TIC 237115819. Even two velocities per star separate
   a real eccentric binary from a blend. Check LAMOST and Gaia archives first (free).
5. **Search ADS and SIMBAD** for each listed TIC number before any claim of novelty (the sandbox
   cannot reach ADS).
6. **Second research note** (RNAAS, 1,500 words, one table) on the period-change candidate only
   after steps 1 and 2. The note must say: candidate, cause unknown, predictions deposited.

## What not to say yet

- "Discovery of new eclipsing binaries": the stars are in Kostov et al. 2025 by construction.
- "Third body detected": a light-travel-time orbit fits no better than a parabola and no companion is seen.
- Masses or radii in solar units as if measured: they come from the Gaia radius and Kepler's law, so they are estimates.
- "Blend confirmed" for a static star: a static bright star with a deep eclipse is strong evidence, not proof.
- "Triple confirmed" for a Gaia astrometric orbit: those solutions can be spurious for variable stars.
