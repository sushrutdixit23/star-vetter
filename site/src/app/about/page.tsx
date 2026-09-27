import Link from "next/link";
import { getAboutContent, getModelMetrics, getPipelineStats } from "@/lib/data";

const STAGES = [
  {
    title: "1. Sample",
    text: "Draw a fresh batch of TESS Input Catalog targets that haven't been looked at in any earlier run, so every batch expands genuinely unexplored territory rather than re-checking old ground.",
  },
  {
    title: "2. Fetch",
    text: "Pull each target's light curve from MAST. Not every TIC has usable data - many were never observed at the right cadence, or the FITS file is unusable - so this stage is a real filter, nota formality.",
  },
  {
    title: "3. Statistical vetting",
    text: "Run every light curve through the physical vetting gates below: eclipse count, odd/even depth consistency, robust detection significance, secondary-eclipse search, and BLS signal-to-noise. Most light curves are noise, instrumental artifacts, or non-eclipsing variability, and are rejected here.",
  },
  {
    title: "4. Catalog cross-match",
    text: "Every statistically-passing candidate is checked against 6 variable-star and eclipsing-binary catalogs. A match means the star is already known and vetting stops there; only unmatched candidates are carried forward as novel.",
  },
  {
    title: "5. Contamination check",
    text: "Before spending a pixel-level check on a candidate, its TESS aperture is checked for bright catalog neighbours close enough to plausibly be the true source of the dimming.",
  },
  {
    title: "6. Pixel-level confirmation",
    text: "The only stage that looks at pixels rather than the summed light curve: difference imaging between in- and out-of-eclipse cadences, checked against the 6 pixel-level gates below, to confirm the dimming genuinely comes from the target and not a blended neighbour.",
  },
  {
    title: "7. Dossier",
    text: "Every confirmed candidate gets a full written dossier - ephemeris, every gate value, the catalog cross-match table, and the pixel-check imagery - generated automatically, with no manual write-up step.",
  },
];

export default function AboutPage() {
  const stats = getPipelineStats();
  const metrics = getModelMetrics();
  const aboutContent = getAboutContent();
  const maxCount = stats && stats.funnel.length > 0 ? stats.funnel[0].count : 1;
  const chosen = metrics ? metrics.models[metrics.chosen_model] : null;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-12 sm:py-16">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-sky-400/80">
        Methodology
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
        How Star Vetter decides
      </h1>

      <div className="mt-6 grid max-w-3xl gap-6 rounded-xl border border-white/10 bg-white/[0.03] p-6 sm:grid-cols-3 sm:p-7">
        <div>
          <h2 className="text-xs font-medium uppercase tracking-wide text-sky-400/80">
            What this is
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-white/70">
            A piece of software that looks through public space-telescope
            data on its own, star by star, checking each one for two stars
            orbiting so closely that each dims the other&apos;s light on a
            repeating schedule.
          </p>
        </div>
        <div>
          <h2 className="text-xs font-medium uppercase tracking-wide text-sky-400/80">
            How it works
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-white/70">
            Seven stages, sample to dossier - sampling, fetching, statistical
            vetting, catalog cross-matching, a contamination check, a
            pixel-level confirmation, then a written write-up. Laid out in
            full below.
          </p>
        </div>
        <div>
          <h2 className="text-xs font-medium uppercase tracking-wide text-sky-400/80">
            Why it exists
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-white/70">
            TESS has observed hundreds of millions of stars and only a
            fraction have ever been checked by a person. This covers more of
            that ground automatically, and is itself an unattended, fully
            logged agentic workflow - not a script a person babysits.
          </p>
        </div>
      </div>

      <p className="mt-8 max-w-2xl text-base leading-relaxed text-white/60">
        Star Vetter runs unattended, end to end, from sampling a fresh batch
        of TESS targets through to a written dossier for every confirmed
        candidate. No step is manually curated: every number on this page
        and in every candidate&apos;s dossier comes directly from the
        pipeline&apos;s own output, and every stage transition is logged
        with the reasoning behind it. Unfamiliar term? Everything technical
        below is also in the{" "}
        <Link href="/glossary" className="text-sky-400/90 hover:text-sky-300">
          glossary
        </Link>
        .
      </p>

      {stats && stats.funnel.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
            Where targets go, cumulative to date
          </h2>
          <div className="space-y-3">
            {stats.funnel.map((step) => (
              <div key={step.label}>
                <div className="mb-1 flex items-baseline justify-between text-sm">
                  <span className="text-white/70">{step.label}</span>
                  <span className="font-mono text-white/90">
                    {step.count.toLocaleString("en-US")}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-sky-400/70"
                    style={{
                      width: `${Math.max(2, (step.count / maxCount) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mt-12">
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
          Pipeline stages
        </h2>
        <div className="space-y-6">
          {STAGES.map((s) => (
            <div key={s.title}>
              <h3 className="text-sm font-semibold text-white">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-white/60">
                {s.text}
              </p>
            </div>
          ))}
        </div>
      </section>

      {stats && (
        <>
          <section className="mt-12">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
              Statistical vetting gates
            </h2>
            <div className="space-y-4">
              {stats.vetting_gates.map((g) => (
                <div key={g.name}>
                  <h3 className="text-sm font-semibold text-white">
                    {g.name}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-white/60">
                    {g.text}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-12">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
              Pixel-level gates
            </h2>
            <div className="space-y-4">
              {stats.pixel_gates.map((g) => (
                <div key={g.name}>
                  <h3 className="text-sm font-semibold text-white">
                    {g.name}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-white/60">
                    {g.text}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-12">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
              Catalogs cross-matched
            </h2>
            <ul className="grid grid-cols-1 gap-2 text-sm text-white/70 sm:grid-cols-2">
              {stats.catalogs.map((c) => (
                <li
                  key={c}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2"
                >
                  {c}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {metrics && chosen && (
        <section className="mt-12 mb-16">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
            ML screening model
          </h2>
          <p className="max-w-2xl text-sm leading-relaxed text-white/60">
            An experimental second opinion: a model trained on this
            pipeline&apos;s own labeled history to predict the pixel-check
            outcome before it runs. It does not currently skip any pixel
            check - every novel candidate still gets the full check - this
            only measures whether the model could, safely, do that one day.
            Chosen model:{" "}
            <span className="font-mono text-white/90">{metrics.chosen_model}</span>
            , cross-validated on {metrics.n_training_samples.toLocaleString("en-US")}{" "}
            labeled candidates ({metrics.n_training_positive} confirmed
            on-target, {metrics.n_training_negative} not).
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs uppercase tracking-wide text-white/50">
                Rule baseline
              </div>
              <div className="mt-1 font-mono text-sm text-white/90">
                recall {metrics.baseline.recall.toFixed(3)} / precision{" "}
                {metrics.baseline.precision.toFixed(3)}
              </div>
              <p className="mt-1 text-[11px] text-white/50">
                send every candidate to the pixel check
              </p>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs uppercase tracking-wide text-white/50">
                Chosen model (cross-validated)
              </div>
              <div className="mt-1 font-mono text-sm text-white/90">
                recall {chosen.recall_mean.toFixed(3)} / precision{" "}
                {chosen.precision_mean.toFixed(3)}
              </div>
              <p className="mt-1 text-[11px] text-white/50">
                ROC AUC {chosen.roc_auc_mean.toFixed(3)}
              </p>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs uppercase tracking-wide text-white/50">
                Beats the baseline?
              </div>
              <div className="mt-1 font-mono text-sm text-white/90">
                {metrics.beats_baseline ? "Yes" : "Not yet"}
              </div>
              <p className="mt-1 text-[11px] text-white/50">
                ROC AUC meaningfully above 0.5 (a coin flip)
              </p>
            </div>
          </div>

          {metrics.screening_value.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-white">
                Screening value
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-white/60">
                How much of the pixel-check download could be skipped, at a
                given minimum recall, if the model were used to screen
                candidates - a cross-validated, out-of-fold estimate, never
                measured on the model&apos;s own training data.
              </p>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-xs uppercase tracking-wide text-white/50">
                      <th className="py-1 pr-4">Target recall</th>
                      <th className="py-1 pr-4">Threshold</th>
                      <th className="py-1 pr-4">Achieved recall</th>
                      <th className="py-1">Downloads skipped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.screening_value.map((row) => (
                      <tr key={row.target_recall} className="border-t border-white/10">
                        <td className="py-1.5 pr-4 font-mono text-white/90">
                          {row.target_recall.toFixed(2)}
                        </td>
                        <td className="py-1.5 pr-4 font-mono text-white/70">
                          {row.threshold.toFixed(2)}
                        </td>
                        <td className="py-1.5 pr-4 font-mono text-white/70">
                          {row.recall.toFixed(3)}
                        </td>
                        <td className="py-1.5 font-mono text-white/90">
                          {(row.fraction_screened_out * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {metrics.feature_importance.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-white">Top features</h3>
              <ul className="mt-2 grid grid-cols-1 gap-1.5 text-sm text-white/70 sm:grid-cols-2">
                {metrics.feature_importance.slice(0, 6).map((row) => (
                  <li
                    key={row.feature}
                    className="flex justify-between gap-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5"
                  >
                    <span className="font-mono text-white/80">{row.feature}</span>
                    <span className="font-mono text-white/50">
                      {row.importance_mean.toFixed(4)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {aboutContent && (
        <section className="mt-12">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
            In plain English
          </h2>
          <p className="max-w-2xl text-base leading-relaxed text-white/70">
            {aboutContent.narrative}
          </p>
        </section>
      )}

      {aboutContent && aboutContent.faqs.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-white/50">
            Frequently asked questions
          </h2>
          <div className="space-y-5">
            {aboutContent.faqs.map((qa, i) => (
              <div key={i}>
                <h3 className="text-sm font-semibold text-white">{qa.question}</h3>
                <p className="mt-1 text-sm leading-relaxed text-white/60">{qa.answer}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="mt-12 mb-16">
        <Link
          href="/"
          className="font-mono text-xs uppercase tracking-wide text-sky-400/80 hover:text-sky-300"
        >
          &larr; view confirmed candidates
        </Link>
      </div>
    </main>
  );
}