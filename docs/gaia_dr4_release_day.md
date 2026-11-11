# Gaia DR4 release day (2 December 2026)

Purpose: for the survivors whose eclipse times can be carried back to 2014-2020, check whether the
eclipse is also seen on the Gaia target itself. An eclipse on the TESS aperture that is absent on the
Gaia target (0.7 arcsec) points to a blend. Gaia has about 70 points per star, so this is a test at a
fixed ephemeris, not a period search.

The decision rule is fixed in `f25_gaia_dr4_run.py` before any DR4 data are seen:

- SUPPORTED: in-eclipse points are fainter, z >= 3 and permutation p <= 0.01.
- CONTRADICTED: the TESS depth would have been seen at z >= 5 with these Gaia errors, but the measured
  depth is below a quarter of it at 3 sigma.
- INCONCLUSIVE: anything else. Silence is not evidence.

On pure noise the SUPPORTED rule fired in 1 of 200 synthetic trials (tests check this).

## Steps

1. `py f21_gaia_dr4_ready.py .` (lists the stars whose ephemeris is precise enough; currently 2 testable).
2. In the Gaia archive, retrieve G-band epoch photometry for the Gaia source ids listed in
   `site/public/data/gaia_dr4_plan.json` (testable stars only) and save one file per star named
   `<gaia_source_id>.csv` (or .ecsv, .vot, .fits) in one folder.
3. `py f25_gaia_dr4_run.py . <folder>`
4. If a star reports UNKNOWN_LAYOUT, the DR4 column names differ from DR3. The message lists the columns
   found; add the names to `TIME_COLS`, `FLUX_COLS`, `ERR_COLS` in `f25_gaia_dr4_run.py`, and check the
   time scale (the script converts DR3-style Gaia days, MJD and full JD, and refuses anything else).
5. Results: `data/processed/f25_gaia_dr4_results.json`. Do not change the rule after seeing them.

## Not verified

How DR4 delivers epoch photometry is unknown until release, so the file reader has been tested only on
synthetic tables in the DR3 layout and two common variants. Only 2 stars are currently testable, so this
cannot rescue the whole sample.
