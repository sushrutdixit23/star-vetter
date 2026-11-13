# Noise model v2 of the eclipse fitter

Status: tested as registered; NOT adopted. v2 improves the eccentricity intervals where it runs but not the radii or the
inclination, and it produced a fit for only 43 of 96 injections. v1 remains the version the site uses. The full account
is in `data/benchmarks/f33_run_log.md`; the criteria are in `data/benchmarks/f33_preregistration.json`.

## Why

The injection test of the v1 fitter (`data/processed/f30_injection.json`, 48 synthetic binaries injected into three
candidates' own noise) found the fitted values unbiased but the quoted intervals far too narrow: the 68% interval
contained the injected value 40% of the time for e, 27% for e cos w, 27% and 21% for the two radii, 38% for the
inclination. Chains that had not converged were worse. Because the injected systems were made with the model that
fits them, the cause is the noise treatment and the sampler, not missing physics.

v1 divides each eclipse by a baseline fitted to its own wings and treats the result as exact, folded in phase, with
white noise. That discards the baseline's uncertainty and assumes no correlated noise.

## What v2 does differently

- Every primary and secondary eclipse is kept as its own event, undivided.
- Each event's quadratic baseline is integrated out of the likelihood (flat prior), including the log-determinant
  term that carries the baseline uncertainty into depth, duration and inclination.
- One white-noise scale per sector instead of per cadence (consecutive sectors share one when a star has more than 8,
  so a 42-sector star does not get 42 noise parameters).
- A Matern-3/2 Gaussian process inside each event (amplitude and timescale shared by the star) for correlated noise.
- No light-ratio prior. Without spectra it would feed an assumption back as a result.

The physical model, the priors on limb darkening and third light, the sampler and the trust rule are unchanged.
Timing: `ellc` is evaluated once per likelihood on a 2-minute grid over the occupied part of the orbit and integrated
over each point's exposure, so the cost does not grow with the number of events.

## Two bugs found while building it

Both were found on synthetic data, before any real run, and are fixed:

1. `scipy.optimize.least_squares` takes finite-difference steps of 1.5e-8, below the numerical noise of `ellc`, and
   stopped far from the minimum (cost 53000 where the truth has 760). v2 uses a step of 1e-4. v1 keeps the default,
   so v1 fits may have started their chains from a poor point; whether that contributed to the narrow intervals is not
   known, and the registered test does not separate it from the other changes.
2. A 5-point running-median clip, with a threshold set by the quiet baseline, deleted ingress and egress points of
   deep eclipses and biased the scatter estimate 20% low. v2 compares each point with the line between its neighbours.
   v1 uses a different clip and is not affected.

## How to run

```
py f26_ebfit.py . --tics 370553309 --converge --noise v2 --out out.json      # one star
py f26_ebfit.py . --validate --noise v2                                      # AI Phe, needs MAST access
```

The registered test is the GitHub workflow `Physics v2` (`.github/workflows/physics-v2.yml`): the four benchmark
systems at two cadences, the 48 injections of the v1 study (paired) and 48 fresh ones (seed 33). Results go to
artifacts and, when merged, to `f29_benchmarks_v2.json` and `f30_injection_v2.json`. The site reads neither.

## How the result will be read

See `criteria` in the registration file. In short: v2 is adopted only if, on the fresh injections, the quoted 68%
interval contains the truth between 55% and 81% of the time for e, r1, r2 and inclination (the 95% band for 48
injections), the bias is no worse, and no more benchmark runs fail than under v1. Otherwise the site keeps v1 and
the outcome is published either way.

## What v2 does not fix

Spherical stars (rsum above 0.25 stays flagged), no spectroscopy so no masses, and the limb-darkening and third-light
priors. The injections use the same model as the fit, so they cannot reveal model mismatch; the four published
benchmark systems can.
