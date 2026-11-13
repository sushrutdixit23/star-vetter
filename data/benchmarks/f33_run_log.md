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

## Run 2 (injections only)

Branch physics-run-v2/injections-rerun (benchmarks skipped by the workflow). Results are reported in the pull request
that adds them, against the criteria in the registration, whatever they are.
