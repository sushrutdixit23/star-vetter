import Link from "next/link";
import { getAboutContent, getModelMetrics, getPipelineStats } from "@/lib/data";
import { safeWriteup } from "@/lib/writeup";
import Band from "@/components/journal/Band";

export const metadata = {
  title: "Instrument - Star Vetter",
};

const STAGES = [
  {
    title: "Sample",
    text: "Draw a fresh batch of TESS Input Catalog targets that haven't been looked at in any earlier run, so every batch expands genuinely unexplored territory rather than re-checking old ground.",
  },
  {
    title: "Fetch",
    text: "Pull each target's light curve from MAST. Not every TIC has usable data - many were never observed at the right cadence, or the FITS file is unusable - so this stage is a real filter, not a formality.",
  },
  {
    title: "Statistical vetting",
    text: "Run every light curve through the physical vetting gates below: eclipse count, odd/even depth consistency, robust detection significance, secondary-eclipse search, and BLS signal-to-noise. Most light curves are noise, instrumental artifacts, or non-eclipsing variability, and are rejected here.",
  },
  {
    title: "Catalog cross-match",
    text: "Every statistically-passing candidate is checked against 6 variable-star and eclipsing-binary catalogs. A match means the star is already known and vetting stops there; only unmatched candidates are carried forward as novel.",
  },
  {
    title: "Contamination check",
    text: "Before spending a pixel-level check on a candidate, its TESS aperture is checked for bright catalog neighbours close enough to plausibly be the true source of the dimming.",
  },
  {
    title: "Pixel-level confirmation",
    text: "The only stage that looks at pixels rather than the summed light curve: difference imaging between in- and out-of-eclipse cadences, checked against the 6 pixel-level gates below, to confirm the dimming comes from the target and not a blended neighbour.",
  },
  {
    title: "Dossier",
    text: "Every surviving candidate gets a full written dossier - ephemeris, every gate value, the catalog cross-match table, and the pixel-check imagery - generated automatically, with no manual write-up step.",
  },
];

export default function AboutPage() {
  const stats = getPipelineStats();
  const metrics = getModelMetrics();
  const aboutContent = getAboutContent();
  const maxCount = stats && stats.funnel.length > 0 ? stats.funnel[0].count : 1;
  const chosen = metrics ? metrics.models[metrics.chosen_model] : null;
  const narrative = aboutContent ? safeWriteup(aboutContent.narrative) : null;
  const faqs = aboutContent ? aboutContent.faqs.map((qa) => ({ question: qa.question, answer: safeWriteup(qa.answer) })).filter((qa) => qa.answer !== null) : [];

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-10 sm:px-8">
      <header className="grid gap-6 pb-10 lg:grid-cols-[3rem_minmax(0,1fr)]">
        <div className="font-display text-3xl leading-none text-faint">IV</div>
        <div>
          <div className="nav-caps font-mono text-[11px] text-muted">The instrument</div>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">How Star Vetter <em>decides</em>.</h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
            Star Vetter runs unattended, end to end, from sampling a fresh batch of TESS targets through to a written dossier for every surviving candidate. No step is manually curated: every number on this page and in every candidate&apos;s dossier comes directly from the pipeline&apos;s own output, and every stage transition is logged with the reasoning behind it. Unfamiliar term? Everything technical here is also in the{" "}
            <Link href="/glossary" className="text-accent hover:underline">glossary</Link>.
          </p>
          <div className="mt-8 grid gap-6 border-t border-line pt-6 sm:grid-cols-3">
            <div>
              <h2 className="nav-caps font-mono text-[11px] text-accent">What this is</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">A piece of software that looks through public space-telescope data on its own, star by star, checking each one for two stars orbiting so closely that each dims the other&apos;s light on a repeating schedule.</p>
            </div>
            <div>
              <h2 className="nav-caps font-mono text-[11px] text-accent">How it works</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">Seven stages, sample to dossier - sampling, fetching, statistical vetting, catalog cross-matching, a contamination check, a pixel-level confirmation, then a written dossier. Laid out in full below.</p>
            </div>
            <div>
              <h2 className="nav-caps font-mono text-[11px] text-accent">Why it exists</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">TESS has observed hundreds of millions of stars and only a fraction have ever been checked by a person. This covers more of that ground automatically, as an unattended, fully logged agentic workflow - not a script a person babysits.</p>
            </div>
          </div>
        </div>
      </header>

      {stats && stats.funnel.length > 0 && (
        <Band num="I" title="Where targets go" lede="Cumulative across every run to date.">
          <div className="space-y-4">
            {stats.funnel.map((step) => (
              <div key={step.label}>
                <div className="mb-1.5 flex items-baseline justify-between gap-4 text-sm">
                  <span className="text-muted">{step.label}</span>
                  <span className="font-mono text-fg">{step.count.toLocaleString("en-US")}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-panel-2">
                  <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.max(2, (step.count / maxCount) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Band>
      )}

      <Band num="II" title="Seven stages" lede="Sample to dossier, with no manual step anywhere.">
        <ol className="grid gap-x-10 gap-y-6 md:grid-cols-2">
          {STAGES.map((s, i) => (
            <li key={s.title} className="border-t border-line pt-4">
              <div className="flex items-baseline gap-3">
                <span className="font-display text-2xl leading-none text-faint">{i + 1}</span>
                <h3 className="nav-caps font-mono text-[11px] text-fg">{s.title}</h3>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-muted">{s.text}</p>
            </li>
          ))}
        </ol>
      </Band>

      {stats && (
        <>
          <Band num="III" title="The gates" lede="What a signal has to pass - first in the light curve, then in the pixels.">
            <div className="grid gap-10 md:grid-cols-2">
              <div>
                <h3 className="nav-caps font-mono text-[11px] text-accent">Statistical vetting</h3>
                <dl className="mt-4 space-y-4">
                  {stats.vetting_gates.map((g) => (
                    <div key={g.name} className="border-t border-line pt-3">
                      <dt className="text-sm font-medium text-fg">{g.name}</dt>
                      <dd className="mt-1 text-sm leading-relaxed text-muted">{g.text}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div>
                <h3 className="nav-caps font-mono text-[11px] text-accent">Pixel level</h3>
                <dl className="mt-4 space-y-4">
                  {stats.pixel_gates.map((g) => (
                    <div key={g.name} className="border-t border-line pt-3">
                      <dt className="text-sm font-medium text-fg">{g.name}</dt>
                      <dd className="mt-1 text-sm leading-relaxed text-muted">{g.text}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </Band>

          <Band num="IV" title="Catalogs cross-matched" lede="A match in any of them means the star is already known.">
            <ul className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {stats.catalogs.map((c) => (
                <li key={c} className="rounded-md border border-line bg-panel/60 px-3 py-2 text-fg">{c}</li>
              ))}
            </ul>
          </Band>
        </>
      )}

      {metrics && chosen && (
        <Band num="V" title="The learning layer" lede="An experimental second opinion. It does not skip anything yet.">
          <p className="max-w-3xl text-sm leading-relaxed text-muted">
            A model trained on this pipeline&apos;s own labeled history to predict the pixel-check outcome before it runs. It does not currently skip any pixel check - every novel candidate still gets the full check - this only measures whether the model could, safely, do that one day. Chosen model: <span className="font-mono text-fg">{metrics.chosen_model}</span>, cross-validated on {metrics.n_training_samples.toLocaleString("en-US")} labeled candidates ({metrics.n_training_positive} confirmed on-target, {metrics.n_training_negative} not).
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-line bg-panel/60 p-4">
              <div className="nav-caps font-mono text-[10px] text-faint">Rule baseline</div>
              <div className="mt-2 font-mono text-sm text-fg">recall {metrics.baseline.recall.toFixed(3)} / precision {metrics.baseline.precision.toFixed(3)}</div>
              <p className="mt-1 text-[11px] text-muted">send every candidate to the pixel check</p>
            </div>
            <div className="rounded-lg border border-line bg-panel/60 p-4">
              <div className="nav-caps font-mono text-[10px] text-faint">Chosen model, cross-validated</div>
              <div className="mt-2 font-mono text-sm text-fg">recall {chosen.recall_mean.toFixed(3)} / precision {chosen.precision_mean.toFixed(3)}</div>
              <p className="mt-1 text-[11px] text-muted">ROC AUC {chosen.roc_auc_mean.toFixed(3)}</p>
            </div>
            <div className="rounded-lg border border-line bg-panel/60 p-4">
              <div className="nav-caps font-mono text-[10px] text-faint">Beats the baseline?</div>
              <div className="mt-2 font-mono text-sm text-fg">{metrics.beats_baseline ? "Yes" : "Not yet"}</div>
              <p className="mt-1 text-[11px] text-muted">ROC AUC meaningfully above 0.5 (a coin flip)</p>
            </div>
          </div>

          {metrics.screening_value.length > 0 && (
            <div className="mt-8">
              <h3 className="nav-caps font-mono text-[11px] text-accent">Screening value</h3>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">How much of the pixel-check download could be skipped, at a given minimum recall, if the model were used to screen candidates - a cross-validated, out-of-fold estimate, never measured on the model&apos;s own training data.</p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="font-mono text-[10px] uppercase tracking-wider text-faint">
                      <th className="py-2 pr-4 font-normal">Target recall</th>
                      <th className="py-2 pr-4 font-normal">Threshold</th>
                      <th className="py-2 pr-4 font-normal">Achieved recall</th>
                      <th className="py-2 font-normal">Downloads skipped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.screening_value.map((row) => (
                      <tr key={row.target_recall} className="border-t border-line">
                        <td className="py-2 pr-4 font-mono text-fg">{row.target_recall.toFixed(2)}</td>
                        <td className="py-2 pr-4 font-mono text-muted">{row.threshold.toFixed(2)}</td>
                        <td className="py-2 pr-4 font-mono text-muted">{row.recall.toFixed(3)}</td>
                        <td className="py-2 font-mono text-fg">{(row.fraction_screened_out * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {metrics.feature_importance.length > 0 && (
            <div className="mt-8">
              <h3 className="nav-caps font-mono text-[11px] text-accent">Top features</h3>
              <ul className="mt-3 grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
                {metrics.feature_importance.slice(0, 6).map((row) => (
                  <li key={row.feature} className="flex justify-between gap-2 rounded-md border border-line bg-panel/60 px-3 py-1.5">
                    <span className="font-mono text-fg">{row.feature}</span>
                    <span className="font-mono text-faint">{row.importance_mean.toFixed(4)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Band>
      )}

      {(narrative || faqs.length > 0) && (
        <Band num="VI" title="In plain English" lede="The whole thing, without the jargon, and the questions people ask.">
          {narrative && <p className="max-w-3xl text-base leading-relaxed text-fg/90">{narrative}</p>}
          {faqs.length > 0 && (
            <dl className="mt-8 grid gap-x-10 gap-y-6 md:grid-cols-2">
              {faqs.map((qa, i) => (
                <div key={i} className="border-t border-line pt-4">
                  <dt className="font-display text-lg leading-snug text-fg">{qa.question}</dt>
                  <dd className="mt-2 text-sm leading-relaxed text-muted">{qa.answer}</dd>
                </div>
              ))}
            </dl>
          )}
        </Band>
      )}

      <div className="border-t border-line py-10">
        <Link href="/candidates" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">View the candidates &rarr;</Link>
      </div>
    </main>
  );
}
