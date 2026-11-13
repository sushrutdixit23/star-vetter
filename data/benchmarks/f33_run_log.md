# Run log for the registered test of noise model v2 (f33_preregistration.json)

The registration is not edited after results are read; what happened is recorded here.

## Run 1, GitHub Actions run 43428126618 (main at 27296f3), started 2026-11-13

- All 57 jobs ended "success", but every one of the 96 injection fits (48 paired, 48 fresh) returned status ERROR
  after 0.2 s with "The truth value of an array with more than one element is ambiguous". No fit was executed, so no
  injection result of any kind was produced or seen.
- Cause: a bug in the plumbing added for the run, in f30_injection.py. `run()` took a new argument called `noise` (the
  noise-model name) and a few lines later assigned the host's noise ARRAY to the same name, so the array was passed to
  `fit_star(noise=...)`. f26_ebfit.py is not involved and its registered SHA-256 is unchanged. The unit tests did not
  call `run()` with real data; a regression test now does (tests/test_benchmark_injection.py).
- The 8 benchmark fits did run (f29_benchmarks_v2.json). They are kept as the registered benchmark result and are
  not repeated.
- Why the injections may be rerun: the registration asks that the fresh injections be "fitted once so nothing can be
  tuned". Run 1 fitted none of them, nothing about v2 was learned from it, and the rerun uses the same code, constants,
  seeds, hosts and indices. Only the variable name in f30_injection.py changed.

## Run 2 (injections only), run 43487966973, branch physics-run-v2/injections-rerun

Result files: data/processed/f30_injection_v2.json (this run) and data/processed/f29_benchmarks_v2.json (run 1). The
site reads neither. Judged against the criteria exactly as registered:

| criterion | outcome |
|---|---|
| calibrated (fresh seed 33: coverage_68 in 0.55-0.81 for e, r1, r2, i) | NO. e 0.58 yes; r1 0.37, r2 0.16, i 0.42 no. Only 19 of 48 fresh injections gave a fit. |
| improved (higher than v1 on BOTH seeds for e, r1, r2, i; v1 0.40, 0.27, 0.21, 0.38) | NO. e yes (0.63, 0.58). r1 no (0.25 on seed 29). r2 no (0.21 = v1 on seed 29, 0.16 on seed 33). i no (0.33 on seed 29). |
| bias_not_worse | yes on the fits that ran: median error of e 0.000, of i -0.018 deg; no median absolute error above v1's. |
| benchmark_not_worse (>= 3 of 8 pass, V505 Per both cadences) | yes: 4 of 8 pass (MU Cas and V505 Per at both cadences). V1022 Cas 30 min ended in an error; V1022 Cas 2 min and V454 Aur at both cadences do not pass. |
| adoption (calibrated AND bias AND benchmark) | NOT MET. v1 stays the version the site uses. |

### What else the run shows (reported whatever the verdict)

- v2 produced a fit for only 43 of 96 injections (45%); v1 fitted all 48 of its injections.
  - host 43785616: 0 of 32. Every one ended TOO_FEW_ECLIPSES_WITH_BASELINE. v2 needs at least 4 eclipse events with 5 points
    on both sides of the eclipse; v1 only needs 50 points in total and fitted 16 of 16 there.
  - 12 errors "array must not contain infs or NaNs" (the same error ended one benchmark run) and 9 OPTIMISER_FAILED, on
    the other two hosts. The failed injections have smaller radii (median rsum 0.13 against 0.15-0.17 for the fitted
    ones), so coverage computed on the fits that ran describes an easier subset and is flattering.
- On the same 24 seed-29 injections that both versions fitted: coverage_68 of e 0.33 (v1) to 0.63 (v2), error
  inflation 3.9 to 1.3, median absolute error of e 0.0049 to 0.0021. For r1 (0.25 to 0.25), r2 (0.13 to 0.21) and
  inclination (0.29 to 0.33) the quoted intervals stay 4 to 6 times too narrow.
- Chains: 40 of the 43 fits converged (v1: 25 of 48).
- The trust rule accepted 20 fits, 95% of them good (v1: 11, 91%).
- Not reported: the fitted red-noise amplitude per injection (the registration asked for it). The rows do not store it;
  that was an omission in f30_injection.py.

### Reading

The part of the hypothesis that the noise treatment, not the physics, makes the eccentricity intervals too narrow
is supported: e and e cos w improve clearly where v2 ran. The radii and the inclination do not improve, so their
overconfidence is not mainly a baseline or red-noise problem; the likelier causes are the r1-r2-inclination-third-light
degeneracy and the priors on it, which v2 deliberately left alone. And v2 as built fails on a third to a half of the
cases a pipeline would meet, which has to be fixed before it can be judged on all of them.

Any change to v2 (an event rule that fits host 43785616, the NaN error) changes f26_ebfit.py and therefore needs a new
registration with a new set of fresh injections; the 48 used here are spent.
