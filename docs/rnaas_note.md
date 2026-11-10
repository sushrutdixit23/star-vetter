# An audit of the unvetted TESS Ten Thousand eclipsing-binary list, with pre-registered eclipse times for TESS Year 9

Sushrut Dixit [[ORCID and affiliation, e.g. Independent researcher, Lucknow, India]]

## Abstract

Kostov et al. (2025) published about 873,000 eclipsing-binary detections from TESS full-frame images without vetting them. I ran an independent pipeline on a random sample of 21,369 of those stars. 13,775 had a usable light curve; 307 were confirmed on-target in difference images, 2.22% (95% interval 1.98 to 2.48%) of usable stars. These are entries of the published list that survived an independent check, not new detections. Injected binaries are recovered 28% to 52% of the time, depending on how noisy the host star is, so the rate is a lower bound; correcting for recall gives 4% to 10%. Independent ZTF photometry recovers the eclipses of 34 of the 44 stars it could have tested. I also give pre-registered mid-eclipse times, with uncertainties and an outcome rule, for 21 primary eclipses of 4 stars in TESS Year 9.

## 1. Purpose

Kostov et al. (2025) describe the bulk of their list as unvetted and unvalidated neural-network detections. A random-sample audit gives one estimate of what an independent check recovers, and a frozen list of timing predictions gives a test that no later analysis can adjust.

## 2. Sample and audit

Stars were drawn at random, stratified by TESS magnitude into fifths of the list (seeded, 21,369 stars, 2.4% of the list), and population figures are re-weighted by each fifth's share. Light curves from SPOC, QLP or GSFC-ELEANOR-LITE were flattened and searched with box least squares, then passed through gates on eclipse count, in-eclipse points, signal-to-noise, depth consistency and photometric quality (Lightkurve Collaboration 2018; Astropy Collaboration 2022). Stars with no catalog match were then checked in TESS difference images for whether the dimming lies on the target.

Of 21,369 sampled stars, 13,775 (64%) had a usable light curve. Of those, 23.9% passed the statistical gates and 307 were confirmed on-target: 2.22% (95% interval 1.98 to 2.48%). The rate falls from 3.6% for the brightest fifth (Tmag up to 13.03) to 0.5% for the faintest (Tmag above 14.72).

## 3. How much the pipeline misses

To measure recall I injected 360 artificial binaries (trapezoid eclipses, circular orbits, period 0.65 to 39.8 d, primary depth 0.2 to 50%) into real light curves of 60 sampled stars whose unmodified light curves fail the gates, and ran the unchanged gates. Of the 306 injections the search range could reach, 87 of 306 (28%) passed with a period correct or half or double the true one. Recall rises with depth, from 0% for depths under 0.5% to 61% above 10% (57 of 94). The gate most often responsible for misses was the requirement of at least three usable eclipses. Copies of the real light curves cut into one-day chunks and shuffled passed the gates in 9 of 120 cases (7.5%), a measure of false alarms from noise.

Injections were made after flattening, so recall for real eclipses is probably lower, and recall depends on the host: in the quietest quarter of the host stars it is 52% (153 of 293), against 28% overall. Most misses (174 of 217) lock onto the host star's own periodic signal. Relaxing the eclipse-count gate to two raises the shuffled false-alarm rate from 7.5% to 30.8%, so the gate stays at three.

Neighbour contamination was assessed with TESS Input Catalog neighbours within 63 arcsec. A neighbour counts if it is bright enough, after allowing for the fraction of its light in the aperture, and consistent with the measured centroid to within an assumed 6 arcsec. For 236 of 307 stars no neighbour qualifies; for 42 a qualifying neighbour is too close for TESS to separate. Of 37 candidates whose ATLAS period (Heinze et al. 2018) differs from the TESS period, a harmonic or sidereal-day alias explains 8, against 3.1 expected by chance.

## 4. Independent checks

To test the survivors without TESS pixels, I ran a local box-least-squares scan on public ZTF light curves around each TESS period. A star counts as recovered when its signal-to-noise exceeds that of at least 99% of 300 control periods (p <= 0.01) with a depth within a factor of three of TESS; a non-detection counts against the star only when injected eclipses of the same depth are recovered at least half the time. ZTF has usable data for 66 of 307 stars (it does not cover most of the far south). Of the 44 where injected eclipses could be recovered, 34 (77%, 95% interval 63% to 87%) are recovered; 22 have data but too little power to tell, and 10 are not seen despite adequate power. It tests the signal at the TESS period, not the period search.

Gaia DR3 gives a second independent line: 4 stars have a spectroscopic-binary orbit whose period equals the TESS period (or half or double it), so they are already known binaries, and 2 have long-period astrometric orbits that suggest an unresolved third body. 88 of 307 have Gaia RUWE above 1.4. Taking every line together, 37 stars are independently supported, 10 are disfavoured, and 260 remain TESS-only.

## 5. Pre-registered predictions

Of 169 candidates considered, 4 meet the selection rule: a fitted ephemeris that is not rejected, a primary eclipse in a Year 9 sector, and a best 1-sigma uncertainty of at most 120 min. Ephemerides were fitted by generalised least squares with excess timing noise. A 'Validated' grade means an ephemeris fitted to the earliest sectors predicted later ones (24 of the 25 stars in the hold-out test passed); 'Unvalidated' means too few sectors for that test. On 24 Prsa et al. (2022) binaries with a deliberately degraded starting ephemeris the fitted epoch was within 3 sigma in 100% of cases. Predicted times (Table 1) are barycentric (BJD_TDB); the frozen bundle lists every eclipse, including geocentric UTC.

| TIC | Tmag | Grade | Period (d) | T0 (BJD_TDB) | Sectors | Eclipses | First predicted minimum (BJD_TDB) | 1-sigma (min) |
|---|---|---|---|---|---|---|---|---|
| 66732476 | 12.48 | Unvalidated | 3.112104 +/- 0.000061 | 2459568.9168 | 115 | 9 | 2461479.7489 | 53.9 |
| 264099112 | 11.74 | Unvalidated | 5.977851 +/- 0.000272 | 2460497.6050 | 118 | 5 | 2461561.6624 | 69.8 |
| 59387976 | 13.02 | Validated | 22.520950 +/- 0.000020 | 2460031.4994 | 119, 120 | 2 | 2461607.9659 | 2.3 |
| 41996755 | 13.01 | Validated | 9.563156 +/- 0.000007 | 2459888.8597 | 120, 121 | 5 | 2461619.7910 | 3.9 |

Table 1. Ephemerides and first predicted primary minimum in TESS Year 9. Sector dates are provisional (MIT, NASA), so sectors 117 to 121 are interpolated. Covariances and all 21 predicted minima are in the frozen bundle.

## 6. Evaluation rule

When Year 9 data are public, each predicted eclipse that TESS observed will be timed with the same code. It counts as recovered if the measured mid-eclipse lies within 3 sigma of the prediction, with sigma combined in quadrature with the measurement error and, for QLP light curves, a 3-minute term for known QLP timing errors (Kostov et al. 2025), SPOC data being preferred; as inconsistent if observed outside that; and as insufficient data if not covered. Every prediction is reported whatever its outcome. The predictions were frozen with SHA-256 hashes and deposited before the data: [[Zenodo DOI and deposit date, to be inserted after the freeze]].

## 7. Limits

Of the 307 on-target stars, 14 are already known as eclipsing binaries (a catalog match, a SIMBAD type, or a post-2025 list), 50 more as binaries or variables; 243 have no prior record in the sources I checked. Absence from catalogs is largely by construction: Kostov et al. removed every target within 21 arcsec of a known eclipsing binary before publishing the unvetted list. The IJspeert et al. (2021, 2024) searches covered only 3 and 20 of the 307 stars. Not checked: the 2026 catalogs of Oddo et al. and Liu et al. (not in VizieR), ATLAS and ASAS-SN in the south, LAMOST and SDSS spectra, and Gaia DR4 (due 2 December 2026). No physical light-curve model was fitted, so planets, brown dwarfs and sub-0.2-pixel blends are not excluded. Only 4 stars have predictions, and 2 are validated. The recall figures rest on 60 host stars.

## Data and code

Code, data files and the frozen predictions: [[repository URL and Zenodo DOI]].

## AI-usage disclosure

[[Author to confirm before submission.]] The AI tool Claude (Anthropic) was used to write and debug the analysis code, to run the injection tests, and to draft and edit this note. The author checked the code outputs and the numbers in the text against the data files, and responsibility for the final manuscript text lies entirely with the author.

## Acknowledgments

This work uses data from the TESS mission, obtained from the Mikulski Archive for Space Telescopes (MAST), and catalogs from VizieR.

## References

Astropy Collaboration 2022, ApJ, 935, 167

Heinze, A. N., et al. 2018, AJ, 156, 241

Kostov, V. B., et al. 2025, ApJS, 279, 50

Lightkurve Collaboration 2018, Astrophysics Source Code Library, ascl:1812.013

Prsa, A., et al. 2022, ApJS, 258, 16

Ricker, G. R., et al. 2015, JATIS, 1, 014003
