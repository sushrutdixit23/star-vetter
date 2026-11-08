# An audit of the unvetted TESS Ten Thousand eclipsing-binary list, with pre-registered eclipse times for TESS Year 9

Sushrut Dixit [[ORCID and affiliation, e.g. Independent researcher, Lucknow, India]]

## Abstract

Kostov et al. (2025) published about 873,000 eclipsing-binary detections from TESS full-frame images without vetting them. I ran an independent pipeline on a random sample of 21,369 of those stars. 13,775 had a usable light curve; 307 were confirmed on-target in difference images, 2.22% (95% interval 1.98 to 2.48%) of usable stars. These are entries of the published list that survived an independent check, not new detections. Injecting artificial binaries into real light curves shows the pipeline recovers about 28% of those it could reach, so the rate is a lower bound. I also give pre-registered mid-eclipse times, with uncertainties and an outcome rule, for 21 primary eclipses of 4 stars in TESS Year 9.

## 1. Purpose

Kostov et al. (2025) describe the bulk of their list as unvetted and unvalidated neural-network detections. A random-sample audit gives one estimate of what an independent check recovers, and a frozen list of timing predictions gives a test that no later analysis can adjust.

## 2. Sample and audit

Stars were drawn at random, stratified by TESS magnitude into fifths of the list (seeded, 21,369 stars, 2.4% of the list), and population figures are re-weighted by each fifth's share. Light curves from SPOC, QLP or GSFC-ELEANOR-LITE were flattened and searched with box least squares, then passed through gates on eclipse count, in-eclipse points, signal-to-noise, depth consistency and photometric quality (Lightkurve Collaboration 2018; Astropy Collaboration 2022). Stars with no catalog match were then checked in TESS difference images for whether the dimming lies on the target.

Of 21,369 sampled stars, 13,775 (64%) had a usable light curve. Of those, 23.9% passed the statistical gates and 307 were confirmed on-target: 2.22% (95% interval 1.98 to 2.48%). The rate falls from 3.6% for the brightest fifth (Tmag up to 13.03) to 0.5% for the faintest (Tmag above 14.72).

## 3. How much the pipeline misses

To measure recall I injected 360 artificial binaries (trapezoid eclipses, circular orbits, period 0.65 to 39.8 d, primary depth 0.2 to 50%) into real light curves of 60 sampled stars whose unmodified light curves fail the gates, and ran the unchanged gates. Of the 306 injections the search range could reach, 87 of 306 (28%) passed with a period correct or half or double the true one. Recall rises with depth, from 0% for depths under 0.5% to 61% above 10% (57 of 94). The gate most often responsible for misses was the requirement of at least three usable eclipses. Copies of the real light curves cut into one-day chunks and shuffled passed the gates in 9 of 120 cases (7.5%), a measure of false alarms from noise.

Injections were made after flattening, so recall for real eclipses is probably lower. Recall depends on the injected mix of periods and depths and is meant to be compared across bins, not quoted as one number.

Neighbour contamination was assessed with TESS Input Catalog neighbours within 63 arcsec. A neighbour counts if it is bright enough, after allowing for the fraction of its light in the aperture, and consistent with the measured centroid to within an assumed 6 arcsec. For 236 of 307 stars no neighbour qualifies; for 42 a qualifying neighbour is too close for TESS to separate. Of 37 candidates whose ATLAS period (Heinze et al. 2018) differs from the TESS period, a harmonic or sidereal-day alias explains 8, against 3.1 expected by chance. ATLAS labels most of these 'dubious'.

## 4. Pre-registered predictions

Of 169 candidates considered, 4 meet the selection rule: a fitted ephemeris that is not rejected, a primary eclipse in a Year 9 sector, and a best 1-sigma uncertainty of at most 120 min. Ephemerides were fitted by generalised least squares with excess timing noise. A 'Validated' grade means an ephemeris fitted to the earliest sectors predicted later ones (24 of the 25 stars in the hold-out test passed); 'Unvalidated' means too few sectors for that test. On 24 Prsa et al. (2022) binaries with a deliberately degraded starting ephemeris the fitted epoch was within 3 sigma in 100% of cases. Table 1 gives the ephemerides. Predicted times are barycentric (BJD_TDB); the frozen bundle lists every eclipse, including geocentric UTC.

| TIC | Tmag | Grade | Period (d) | T0 (BJD_TDB) | Sectors | Eclipses | First predicted minimum (BJD_TDB) | 1-sigma (min) |
|---|---|---|---|---|---|---|---|---|
| 66732476 | 12.48 | Unvalidated | 3.112104 +/- 0.000061 | 2459568.9168 | 115 | 9 | 2461479.7489 | 53.9 |
| 264099112 | 11.74 | Unvalidated | 5.977851 +/- 0.000272 | 2460497.6050 | 118 | 5 | 2461561.6624 | 69.8 |
| 59387976 | 13.02 | Validated | 22.520950 +/- 0.000020 | 2460031.4994 | 119, 120 | 2 | 2461607.9659 | 2.3 |
| 41996755 | 13.01 | Validated | 9.563156 +/- 0.000007 | 2459888.8597 | 120, 121 | 5 | 2461619.7910 | 3.9 |

Table 1. Ephemerides and first predicted primary minimum in TESS Year 9. Sector dates are provisional (MIT, NASA), so sectors 117 to 121 are interpolated. Covariances and all 21 predicted minima are in the frozen bundle.

## 5. Evaluation rule

When Year 9 data are public, each predicted eclipse that TESS observed will be timed with the same code. It counts as recovered if the measured mid-eclipse lies within 3 sigma of the prediction, with sigma combined with the measurement error; as inconsistent if observed outside that; and as insufficient data if not covered. Every prediction is reported whatever its outcome. The predictions were frozen with SHA-256 hashes and deposited before the data: [[Zenodo DOI and deposit date, to be inserted after the freeze]].

## 6. Limits

The 307 on-target stars are entries of the published unvetted list, and 9 of them are already in six other variable-star catalogs (ZTF, CRTS, WISE, ATLAS, ASAS-3, KELT) at the same period. None is in the vetted tables of Kostov et al. (2025), in Prsa et al. (2022), or in the eclipsing-binary lists of IJspeert et al. (2021, 2024) or Justesen and Albrecht (2021); but the IJspeert searches covered only 3 and 20 of the 307 stars, so that is weak evidence of novelty. Earlier checks against VSX, ASAS-SN, Gaia DR3 eclipsing-binary tables and the TOI list are in the repository. Not yet checked: the 2024 to 2026 machine-learning TESS catalogs and Gaia DR4. Only 4 stars have predictions, and only 2 are validated. Pixel checks cannot exclude a neighbour inside the centroid tolerance. The 28% recall figure rests on 60 stars.

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
