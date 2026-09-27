import Link from "next/link";
import { getDiscoveries } from "@/lib/data";

export default function DiscoveriesPage() {
  const data = getDiscoveries();
  const discoveries = data?.discoveries ?? [];

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-12 sm:py-16">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-sky-400/80">
        Showcase
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
        Discoveries
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-relaxed text-white/60">
        A handful of standouts from the confirmed candidates, picked by real
        objective measurements the pipeline already computed for every
        star - not curated by hand. Each one below leads its category.
      </p>

      {discoveries.length === 0 ? (
        <p className="mt-12 text-sm text-white/50">
          Run f10_generate_discoveries.py to populate this page.
        </p>
      ) : (
        <div className="mt-10 grid gap-6 sm:grid-cols-2">
          {discoveries.map((d) => (
            <Link
              key={d.tic}
              href={`/candidates/${d.tic}`}
              className="block rounded-xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-sky-400/40"
            >
              <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400/80">
                {d.category_label}
              </div>
              <h2 className="mt-2 text-lg font-semibold text-white">
                {d.headline}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-white/70">
                {d.blurb}
              </p>
              <div className="mt-4 flex items-center justify-between text-[11px] text-white/50">
                <span className="font-mono">{d.stat_text}</span>
                <span className="font-mono text-sky-400/80">TIC {d.tic} &rarr;</span>
              </div>
            </Link>
          ))}
        </div>
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