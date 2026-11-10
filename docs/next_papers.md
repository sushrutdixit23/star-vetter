# The next publications, in order of readiness

## 1. Ready now: RNAAS note (audit plus pre-registration)

Done and gated. See `docs/publication_readiness.md`.

## 2. Ready after the note is public: VSX entries (wave 1)

`py export_vsx_package.py .` writes `docs/vsx/`. Sixteen stars have ZTF support, no prior record found and no
caveat. Not a paper, but the one outcome that puts these stars in a catalog other people use. It depends on the
note's DOI as the reference.

## 3. Needs data we do not have yet: the systematic-search paper (JAAVSO, OEJV, or AJ/ApJS)

The audit is a sample of 21,369 stars out of 872,720. A full paper needs what the note cannot carry:

| Needed | Why | When / how |
|---|---|---|
| Gaia DR4 cross-match and fixed-ephemeris folds | The only blend test that reaches the far south, and a larger binary catalog | After 2026-12-02 |
| Independent photometry south of declination -30 | Two thirds of survivors have no ZTF coverage | ATLAS forced photometry needs your own ATLAS account and token; ASAS-SN is unreachable from here |
| Spectroscopy cross-match (LAMOST, SDSS) | Radial-velocity amplitude separates binaries from planets and brown dwarfs | Query the public archives; not done |
| Physical light-curve models (ellc or PHOEBE, with MCMC) for a showcase subset of wave-1 stars | Fitted radii and mass ratios exclude planets and give the stars real parameters | Weeks of work; start with the 5 cleanest |
| Blind period recovery in ZTF | The ZTF test starts from the TESS period; it confirms the signal, not the search | A blind run on ZTF alone would show how often the period is found without TESS |
| The Oddo 2026 and Liu 2026 catalogs | The prior-art sweep is incomplete without them | Get the journal tables |
| The graded Year 9 outcomes | The only result that cannot be adjusted after the fact | From 2027-03 |

Realistic timeline: a first draft can follow DR4 plus the blind ZTF run (early 2027); a defensible submission needs the
Year 9 grades and the models (mid to late 2027).

## 4. A methods paper worth considering: injection-recovery against host noise

The finding that recall depends strongly on host-star noise (28 percent overall, 52 percent in quiet hosts,
and 80 percent of misses locked onto the host's own signal) applies to any ML-selected eclipsing-binary catalog,
not just this one. It is the most transferable result in the project and could stand as its own short paper.
It needs the injection into the unflattened light curves (the note says recall for real eclipses is probably lower).
