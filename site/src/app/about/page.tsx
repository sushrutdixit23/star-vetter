import Link from "next/link";
import { getPipelineStats } from "@/lib/data";

const STAGES = [
  {
    title: "1. Sample",
    text: "Draw a fresh batch of TESS Input Catalog targets that haven't been looked at in any earlier run, so every batch expands genuinely unexplored territory rather than re-checking old ground.",
  },
  {
    title: "2. Fetch",
    text: "Pull each target's light curve from MAST. Not every TIC has usable data - many were never observed at the right cadence, or the FITS file is unusable - so this stage is a real filter, not a formality.",
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
  const maxCount = stats && stats.funnel.length > 0 ? stats.funnel[0].count : 1;

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

          <section className="mt-12 mb-16">
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

      <div className="mb-16">
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
