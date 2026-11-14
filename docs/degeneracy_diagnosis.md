# Why the v2 radius and inclination intervals are too narrow: diagnosis

Status: diagnosis only. No fitter code was changed; `f26_ebfit.py` stays frozen by `data/benchmarks/f33_preregistration.json`.
Everything below is reproducible from the checked-in scripts and the files in `data/benchmarks/f34_diagnosis/`.
This is a diagnosis of 2 hosts and 4 regenerated injections, not a calibration study; section 7 lists what it cannot show.

## Summary

1. The failure is host-specific. On host 370553309 (30-minute data, 2 sectors) the v2 radius and inclination intervals are close
   to calibrated (median |z| about 1). On host 318887646 (30- and 10-minute sectors) they are not (median |z| 3.4 to 5.4).
   Host 43785616 (2-minute) produced no fit at all. The pooled "4 to 6 times too narrow" mixed these three situations.
2. The errors move along the classical partial-eclipse degeneracies (radius sum against inclination, radius ratio against
   surface-brightness ratio). Third light is a weaker axis than I assumed.
3. In the bad case the likelihood itself prefers the wrong geometry, so this is not an optimiser failure. On exactly
   Gaussian noise the true and fitted geometries are close to equally likely and the profile in the radius sum is flat
   over 0.16 to 0.26. The honest interval there is the whole range; the sampler reported plus or minus 0.0015.
4. A separate bug kills about one injection in eight: for overlapping stars ellc returns a finite sentinel, -1.797e308, that
   passes the `isfinite` guard and later becomes NaN.
5. Pixel-level crowding will not fix third light on these hosts: CROWDSAP is 0.9975 and 0.9963.

## 1. The failure is host-specific

Source: `diag_f34_by_host.py` on the registered v2 injections (`data/processed/f30_injection_v2.json`, PR #11), output
`data/benchmarks/f34_diagnosis/by_host.json`. z = (fitted median - injected truth) / (half the quoted 68% interval). A calibrated
interval has median |z| near 0.67 and 95% coverage near 0.95.

| Host | Fitted / injected | median abs z: e | r2 | rsum | incl | 95% coverage: e | r2 | incl |
|---|---|---|---|---|---|---|---|---|
| 370553309 | 20 / 32 | 0.45 | 1.29 | 1.11 | 0.97 | 0.95 | 0.70 | 0.70 |
| 318887646 | 23 / 32 | 1.11 | 5.40 | 4.69 | 4.90 | 0.61 | 0.09 | 0.35 |
| 43785616 | 0 / 32 | no fit: all 32 returned TOO_FEW_ECLIPSES_WITH_BASELINE | | | | | | |

With 20 and 23 fits the coverage figures carry errors of about 0.1. The hosts differ in several things at once (cadence mix,
sectors, number of events, noise), so this cannot say which property matters.

## 2. The errors line up along known degenerate directions

Spearman correlation of the errors (fit minus truth) over the 43 fitted injections: radius sum against inclination -0.81,
r2 against surface-brightness ratio J +0.70, r2 against inclination -0.59, r2 against radius sum +0.59. Third light against r1
-0.45, against radius sum -0.39, against inclination +0.38. The 43 fits come from two hosts and are dominated by 318887646, so
these are indications of direction, not estimates of strength.

## 3. The likelihood, not the optimiser, prefers the wrong answer

`diag_f34_likelihood.py lnl`: regenerate one registered injection, then compare ln P at the optimiser's best fit with ln P at the
true geometry, timing and noise parameters re-optimised at both. On correct data, 11 free parameters give a difference of about
5.5 with a spread of 2.3 (half of a chi-square with 11 degrees of freedom).

| Injection | Noise | Best fit: rsum, k, J, l3 | Truth: rsum, k, J, l3 | ln P(best) - ln P(truth) |
|---|---|---|---|---|
| 370553309 seed 29 #9 (control) | host's own | 0.149, 0.81, 0.57, 0.10 | 0.149, 0.81, 0.57, 0.11 | +8.5 |
| 318887646 seed 29 #13 | host's own | 0.081, 0.46, 0.01, 0.31 | 0.186, 0.66, 0.52, 0.02 | +23.0 |
| 318887646 seed 29 #13 | Gaussian | 0.042, 0.73, 0.07, 0.00 | 0.186, 0.66, 0.52, 0.02 | +9.0 |
| 318887646 seed 29 #3 | Gaussian | 0.136, 2.54, 1.20, 0.02 | 0.151, 0.80, 0.77, 0.09 | +1.5 |

The control recovers the truth. On Gaussian noise the wrong geometries are within noise of the truth (+9.0 and +1.5), which
means the data cannot tell them apart. With the host's real noise the difference rises to +23.0, about 7 sigma above what
correct data would give: the host's real residual structure pulls the fit. In #3 the best fit has the radius ratio inverted
(k 2.5 against 0.8); whether that is an exact symmetry twin of the truth is not tested.

## 4. What the honest interval is: profile likelihood in the radius sum

`diag_f34_likelihood.py profile`: maximise ln P over everything else on a grid of rsum, from four starts (best, truth, and an
inverted-ratio start for each).

- Control (370553309 #9): maximum at rsum = 0.14, ln P 24 lower at 0.16 and 250 lower at 0.12. The radius sum is tightly
  constrained, consistent with the quoted interval being honest there.
- 318887646 #13 on Gaussian noise: ln P is 1869.3 at 0.04, 1866.0 at 0.06, then 1861.2 to 1861.3 across 0.16 to 0.22 and
  1859.7 at 0.26, falling to 1838 at 0.30. Every value from 0.16 to 0.26 is within 1.5 of the other, and within 9.5 of the maximum.
  The dip between 0.08 and 0.14 (down to 1754) is the optimiser failing from four starts, not the data: the profile is a lower
  bound. The truth, 0.186, sits on the plateau.

So an honest interval for this case spans at least 0.04 to 0.26, against a reported plus or minus 0.0015. The profile ignores prior
volume, and I did not run the sampler on this case, so "the sampler does not explore the valley" is an inference from the
profile, not an observation.

## 5. A crash bug: ellc's finite error sentinel

For overlapping stars ellc returns -1.797e308 (-DBL_MAX), not NaN. `f26._event_models` checks `np.isfinite` on that grid, which
passes; the cumulative sum then overflows, the event model is non-finite, and `_event_loglike` raises "array must not contain
infs or NaNs". This is the ERROR status in the registered v2 run (12 of 96 injections, and one benchmark run). Reproduced
inside the prior: e = 0.77, rsum = 0.375, k = 0.37 (periastron separation 0.23, below the radius sum). The prior has no detachment
condition, so the optimiser and sampler meet such geometries routinely: the clean-noise profile in section 4 hit it 29,760
times and the diagnostic script has to catch it. Pinned by `tests/test_ellc_overlap_sentinel.py`. The fix (reject model values
below zero; add a detachment condition to the prior) changes f26 and needs a new registration. The control profile ran before
the counter was added and reports no count.

## 6. Pixel-level third light

SPOC header CROWDSAP, read from MAST: TIC 318887646 0.99746 (TESS-SPOC, sector 4), TIC 43785616 0.99628 (SPOC, sector 32). Neighbour
contamination is under 0.4%, so a crowding-based value cannot constrain third light here; what remains would be a physical
companion, which pixels do not measure. TIC 370553309 has no SPOC or TESS-SPOC product in MAST (only QLP, eleanor-lite, T16,
TGLC). The trusted-eccentric and benchmark stars were not read.

## 7. What this does not show

- Cases #13 and #3 were picked from the worst of the 43 by |z|. The profile and the likelihood comparison describe worst
  cases, not typical ones. The control is one case.
- Two hosts, one noise realisation each; the closed-loop test used Gaussian noise only, not red noise.
- The sampler was not run on these cases (about an hour each), so the width the sampler would report was not re-measured.
- The correlations are Spearman over fits that cluster by host.
- The 2-minute cadence has never been tested by v2.

## 8. What the next registration should test

Dropping fixed third light as the lead idea. Candidates, each needing its own pre-registered test on fresh injections:
(a) the sentinel guard and a detachment prior; (b) an interval for the geometry that spans the valley (profile-based, or a
sampler that explores it) instead of the local curvature; (c) an identifiability flag per star: a 14-point profile in the
radius sum costs about 15 to 25 minutes on two CPUs, and a plateau wider than a set fraction of the prior would label radii and inclination
"not identified" and withhold them from the site; (d) the event rule that rejected all 32 injections on the 2-minute host.

Files: `diag_f34_by_host.py`, `diag_f34_likelihood.py`, `tests/test_ellc_overlap_sentinel.py`,
`data/benchmarks/f34_diagnosis/` (by_host.json, four lnl_*.json, two profile_*.json).
