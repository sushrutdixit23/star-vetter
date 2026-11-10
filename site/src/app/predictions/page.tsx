import Link from "next/link";
import Panel from "@/components/Panel";
import PredictionsBoard from "@/components/predictions/PredictionsBoard";
import { getPredictions } from "@/lib/data";

export const metadata = {
  title: "Predictions - Star Vetter",
  description:
    "Falsifiable predictions of when candidate eclipsing binaries will next dim, each with an honest uncertainty and a retrospective test, to be graded in public once TESS Year 9 data are released.",
};

const REASONS: Record<string, string> = {
  PERIOD_ALIAS: "Period could be a harmonic of the true orbit",
  PREDICTED_ECLIPSE_MISSING: "An eclipse the pipeline expected was absent",
  PIPELINE_CHECK_FLAGGED: "The pipeline raised a check on this star",
  TOO_FEW_ECLIPSES: "Fewer than two eclipses could be timed",
  NO_YEAR9_ECLIPSE: "No primary eclipse falls in a Year 9 sector the star is observed in",
  UNCERTAINTY_TOO_LARGE: "Best prediction uncertainty is too large to test anything",
  NO_DATA: "No usable 2-minute light curve",
  NO_TEMPLATE: "Could not build a clean eclipse template",
  ERROR: "Download or processing error",
};

function pct(x: number | null | undefined, digits = 0): string {
  return x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(digits)}%`;
}

export default function PredictionsPage() {
  const data = getPredictions();

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="pb-8">
        <div className="nav-caps font-mono text-[11px] text-muted">Written down before the data exist</div>
        <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">Predictions.</h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
          Each line below is a falsifiable statement: this star&apos;s primary eclipse will happen at this time, give or take
          this much. TESS Year 9 begins with Sector 111 on 26 November 2026. When its data are public, every prediction
          here will be timed with the same code and graded by the rule further down, with the misses published alongside the hits.
          These are candidate eclipsing binaries, not confirmed ones, and this page makes no claim that any of them is new.
        </p>
      </header>

      {!data ? (
        <p className="border-t border-line py-10 text-sm text-faint">Run f13_ephemeris.py and export_predictions.py to populate this page.</p>
      ) : (
        <>
          <div className="mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
            {[
              [String(data.counts.listed), "stars with a published prediction"],
              [String(data.counts.listed_validated), "validated over a comparable distance"],
              [String(data.counts.rejected_failed_holdout), "failed it, and are named below"],
              [String(data.stars.reduce((n, s) => n + s.predictions.length, 0)), "eclipses to be graded"],
            ].map(([n, label]) => (
              <div key={label} className="bg-canvas p-4 sm:p-5">
                <div className="font-display text-3xl text-fg">{n}</div>
                <div className="mt-1 text-xs text-muted">{label}</div>
              </div>
            ))}
          </div>

          {data.stars.length === 0 ? (
            <p className="border-t border-line py-10 text-sm text-faint">No star met the selection rule in this run.</p>
          ) : (
            <PredictionsBoard stars={data.stars} />
          )}

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            <Panel title="The hold-out test" subtitle="Does the clock predict data it has not seen?">
              <p className="text-sm leading-relaxed text-muted">
                Two tests, both retrospective. First, one TESS sector at a time is hidden and predicted from the rest. Second, the
                ephemeris is fitted to only the earliest sectors and asked to predict every later one, which is how a forecast
                is actually used. Both compare prediction with measurement using the full covariance of the errors (eclipses in one
                sector err together), and a star that fails any test at a family-wise 1% level is rejected.
              </p>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                A star is called Validated only if the new predictions reach no more than three times as far beyond its data as the
                test did. Passing a 27-day test says little about a prediction four years out, because real eclipse timing drifts, so
                those stars are labelled Not validated and shown anyway. A star with a single connected sector cannot be tested at all.
              </p>
              {data.holdout_calibration && (
                <p className="mt-3 text-xs leading-relaxed text-faint">
                  False-alarm check: the same tests were run on {data.holdout_calibration.n_stars} published binaries that were not used to
                  set them, and rejected {data.holdout_calibration.n_failed}
                  {data.holdout_calibration.n_failed > 0
                    ? ` (its eclipse times scatter by ${data.holdout_calibration.failed_timing_scatter_min.join(", ")} min, so it is not a steady clock)`
                    : ""}.
                </p>
              )}
            </Panel>

            <Panel title="Checked against published clocks" subtitle="Known binaries, other people's numbers">
              {data.validation ? (
                <>
                  <p className="text-sm leading-relaxed text-muted">
                    The same code was run on {data.validation.n_stars} known eclipsing binaries whose period and epoch were published
                    by other researchers, starting each search from a deliberately degraded ephemeris. The median epoch error was{" "}
                    <span className="font-mono text-fg">{data.validation.median_abs_epoch_error_min?.toFixed(1)} min</span>, within
                    3&sigma; of the published value for{" "}
                    <span className="font-mono text-fg">{pct(data.validation.epoch_within_3sigma_fraction)}</span> of them.
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-faint">{data.validation.source}.</p>
                </>
              ) : (
                <p className="text-sm text-faint">The validation against published ephemerides has not been run for this export.</p>
              )}
            </Panel>

            <Panel title="What a clear catalog check means" subtitle="Weaker than it sounds">
              {data.extra_catalog_recall ? (
                <p className="text-sm leading-relaxed text-muted">
                  Six extra variable-star catalogs (ZTF, CRTS, WISE, ATLAS, ASAS-3, KELT) were searched. Run on {data.extra_catalog_recall.n_known_ebs} known
                  eclipsing binaries of similar brightness, they listed only{" "}
                  <span className="font-mono text-fg">{pct(data.extra_catalog_recall.recall_period_match)}</span> with a matching period (95% interval{" "}
                  {pct(data.extra_catalog_recall.recall_period_match_ci95[0])} to {pct(data.extra_catalog_recall.recall_period_match_ci95[1])}). So &quot;not
                  listed&quot; here is weak evidence that a star is new. A listing, on the other hand, is informative, and is flagged on the row.
                </p>
              ) : (
                <p className="text-sm text-faint">The recall of the extra catalog check has not been measured for this export.</p>
              )}
            </Panel>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="How a prediction is graded" subtitle="Fixed now, applied later">
              <dl className="space-y-3 text-sm leading-relaxed text-muted">
                <div><dt className="nav-caps font-mono text-[10px] text-faint">Outcome</dt><dd>{data.conventions.outcome_rule}</dd></div>
                <div><dt className="nav-caps font-mono text-[10px] text-faint">Uncertainty</dt><dd>{data.conventions.sigma}</dd></div>
                <div><dt className="nav-caps font-mono text-[10px] text-faint">Time</dt><dd>{data.conventions.time_scale}</dd></div>
                <div><dt className="nav-caps font-mono text-[10px] text-faint">Scope</dt><dd>{data.conventions.eclipse} {data.conventions.approximate_sectors}</dd></div>
              </dl>
            </Panel>

            <Panel title="Who is on this page, and who is not" subtitle="A mechanical rule, applied to every candidate">
              <p className="text-sm text-muted">A star is listed only if all of these hold:</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-muted">
                {data.selection_rule.map((r) => <li key={r}>{r}</li>)}
              </ol>
              <div className="mt-4 text-xs text-faint">
                Of {data.counts.candidates_considered} candidates considered, {data.counts.listed} are listed. Left out:
              </div>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {Object.entries(data.excluded).map(([k, n]) => (
                  <li key={k} className="flex justify-between gap-4 text-muted">
                    <span>{REASONS[k] ?? k}</span><span className="text-fg">{n}</span>
                  </li>
                ))}
                <li className="flex justify-between gap-4 text-muted">
                  <span>Failed the hold-out (named below)</span><span className="text-fg">{data.counts.rejected_failed_holdout}</span>
                </li>
              </ul>
            </Panel>
          </div>

          {data.rejected.length > 0 && (
            <Panel
              className="mt-4"
              title="Ephemerides that failed"
              subtitle="Their eclipse times did not follow a straight line, so no prediction is made. Left visible on purpose."
            >
              <div className="flex flex-wrap gap-2">
                {data.rejected.map((r) => (
                  <Link key={r.tic} href={`/candidates/${r.tic}`} className="rounded-md border border-line px-2.5 py-1 font-mono text-[11px] text-muted transition-colors hover:border-accent/60 hover:text-fg">
                    TIC {r.tic}
                  </Link>
                ))}
              </div>
            </Panel>
          )}

          <p className="mt-8 text-[11px] text-faint">Generated {data.generated_utc.replace("T", " ").replace("Z", " UTC")}.</p>
        </>
      )}

      <div className="mt-10 border-t border-line py-10">
        <Link href="/candidates" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">View all candidates &rarr;</Link>
      </div>
    </main>
  );
}
