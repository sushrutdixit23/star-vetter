# Upstream outages: what stops the daily pipeline, and what does not

The daily pipeline (`.github/workflows/pipeline.yml`) depends on remote catalog services. Its rule is fixed:
**if a required service is down, stop and write nothing.** A missing answer must never be recorded as "no match",
because that turns an already-catalogued star into a "novel" one (the 2026-11-07 incident, see `upstream.py`).

## What happened on 28 Oct - 12 Nov 2026

Every scheduled run failed in the first minute, at the pre-flight step, and sent a red "All jobs have failed" email.
Two separate things were wrong at CDS Strasbourg:

| Service | What it did | What the old pre-flight saw |
|---|---|---|
| CDS XMatch (`cdsxmatch`) | HTTP 503, or no answer | down (correct) |
| CDS VizieR query endpoint (`viz-bin/votable`) | HTTP 404 | **up** (it only fetched the home page, which still answered 200) |

The pre-flight did its job on XMatch. The VizieR half was a second, hidden outage that would have failed the next
stage (ASAS-SN) had XMatch come back first.

## What changed

* `upstream.py` probes the real query endpoints (a one-row VizieR query, 2xx required) instead of home pages.
* A working **VizieR server** is now required; **XMatch is optional**. The Harvard-CfA mirror
  (`vizier.cfa.harvard.edu`) is used when CDS VizieR does not answer. This repo already used that mirror in
  `f14`, `f16`, `f19`, `f27` and two validation scripts.
* `crossmatch.py` does XMatch's job through VizieR: VSX, Gaia DR3 `veb` and `vclassre`, nearest row within the same
  5 arcsec, all three catalogs through one path (never mixed).
* `f4f_novelty.py` tries XMatch first, falls back to `crossmatch.py`, and records the path used in
  `data/processed/f4f_crossmatch_path.json`. If neither works it still exits 3 and writes nothing.
* A cut-off VizieR response counts as a failed request. astroquery would otherwise warn and return an empty table,
  which reads as "no matches for any of these stars". astroquery's disk cache is off for these requests so a retry
  cannot replay a cut-off answer.
* The pre-flight writes the chosen server and an "XMatch is down" flag to later workflow steps and to the job summary.

## Did the fallback give the same answers?

`validate_crossmatch_fallback.py` re-asks the three questions for the 3,305 stars in
`data/processed/f4f_novelty_results.csv` (produced through XMatch before the outage) and counts every difference.
Result (`data/processed/crossmatch_fallback_check.json`, run three times with the same outcome):

| Catalog | Stars matched through XMatch | Through the mirror | Differences in matched fields |
|---|---|---|---|
| VSX | 334 | 334 | 0 (name, type, period) |
| Gaia DR3 classifier (`vclassre`) | 244 | 244 | 0 (class, score) |
| Gaia DR3 eclipsing binaries (`veb`) | 0 | 0 | 0 |

The comparison also caught a real problem in the first version of the fallback. The mirror sometimes answers
HTTP 200 with a VOTable that says `QUERY_STATUS = ERROR` ("Postgres connect error, no server is available") and no
table. astroquery reads that as an empty result. In one run it silently lost 180 of the 334 known VSX matches, and
the only reason this was noticed is that the answers were checked against the stored ones. The request layer now raises
on any error reported inside a response, on a response that is cut off, and does not use astroquery's disk cache. In a
40-request test against the live mirror 25 requests raised and 15 succeeded, with none silently empty. Failures are
retried (7 times, growing pauses), then the request is split in half and retried, then the run stops with exit code 3.

Limit: this protects against failures the server reports or a response that is cut off. A server that silently returned
a clean but incomplete table would not be caught by it. The check against 3,305 stored answers is the evidence that
this does not happen on the mirror today; re-run `validate_crossmatch_fallback.py` if the pipeline's results ever look
too empty.

## What still stops a run (by design)

MAST down; no VizieR server (CDS and the mirror both failed); a request that still fails after retries and after
splitting it into smaller ones; more than 2% of per-star ASAS-SN queries unresolved. Each exits with code 3 and writes
nothing. Re-run when the service is back (`workflow_dispatch` on "Star Vetter Pipeline").
