# VSX submission package

Built by `export_vsx_package.py` from the pipeline's own files. Nothing here has been sent to VSX.

## What is in it

| File | Rows | What it is | Safe to submit? |
|---|---|---|---|
| vsx_wave1.csv | 16 | ZTF-confirmed, no prior record found, no caveat of any kind | Yes, after the RNAAS note is public (cite its DOI) |
| vsx_wave2_caveats.csv | 19 | Same, but each has at least one caveat (period alias, RUWE above 1.4, neighbour, odd/even) | Not yet: resolve the caveat first |
| vsx_check_existing.csv | 16 | ZTF-confirmed but already listed as a variable somewhere, possibly at another period | No new entry: look up the existing VSX record, then submit a period correction if it differs |

Stars already known as eclipsing binaries or as spectroscopic binaries are left out: they are catalogued.

## How VSX works (check the current form, it changes)

1. You need a free AAVSO account. Submissions go through the "Submit new variable star" form on VSX
   (aavso.org/vsx), one star at a time, or a bulk spreadsheet through the VSX team for larger lists.
2. For each star VSX asks for coordinates, type, period, epoch, amplitude, and a reference.
   Type `E` means eclipsing, unclassified. Do not guess EA/EB/EW without a light-curve model.
3. The reference should be the RNAAS note's DOI (after it is published) and the Zenodo record
   doi:10.5281/zenodo.24115848 for the frozen predictions. Do not submit before the note is public.
4. Epochs here are BJD_TDB; VSX asks for HJD. The two differ by under 10 minutes, so say BJD_TDB in the remarks.
5. VSX moderators may reject a star on TESS-only evidence. The ZTF evidence is the reason these rows are here.
   Quote the ZTF p-value, number of epochs and baseline from the CSV.

## Do not submit

- Any star from wave 2 or `existing` as a new entry.
- Any star for which you have not looked at the ZTF folded light curve yourself.
- Any star the VSX search by coordinates (3 arcsec) already returns, even under another name.
  Run that search for every wave-1 star first; the pipeline checked SIMBAD and VizieR but not VSX's
  own live database, which is the authority.

`ztf_p_value` of 0.0033 is the floor of the test (no control period out of 300 matched the signal), not a measured value.
Quote it as "p < 0.01".

Period columns: `period_days` is the ZTF-refined period when it agrees with TESS to 0.2 percent
(a baseline of years pins the period far better than 27 days of TESS), otherwise the TESS period.
