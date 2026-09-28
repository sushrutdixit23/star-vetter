import Link from "next/link";
import { getDiscoveries } from "@/lib/data";
import { safeWriteup } from "@/lib/writeup";

export const metadata = {
  title: "Standouts - Star Vetter",
};

export default function StandoutsPage() {
  const data = getDiscoveries();
  const standouts = data?.discoveries ?? [];

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-10 sm:px-8">
      <header className="pb-10">
        <div className="nav-caps font-mono text-[11px] text-muted">From the survivors</div>
        <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">Standouts.</h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">A handful of standout candidates, picked by real objective measurements the pipeline already computed - not curated by hand. Only candidates with no open caveats are eligible, and each one below leads its category. These are candidates, not confirmed eclipsing binaries.</p>
      </header>

      {standouts.length === 0 ? (
        <p className="border-t border-line py-10 text-sm text-faint">Run f10_generate_discoveries.py to populate this page.</p>
      ) : (
        <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 xl:grid-cols-3">
          {standouts.map((d) => {
            const headline = safeWriteup(d.headline, d.tic) ?? d.category_label;
            const blurb = safeWriteup(d.blurb, d.tic);
            return (
              <Link key={`${d.category}-${d.tic}`} href={`/candidates/${d.tic}`} className="group flex flex-col bg-canvas p-6 transition-colors hover:bg-panel">
                <div className="nav-caps font-mono text-[10px] text-accent">{d.category_label}</div>
                <h2 className="mt-3 font-display text-2xl leading-snug text-fg">{headline}</h2>
                {blurb && <p className="mt-3 text-sm leading-relaxed text-muted">{blurb}</p>}
                <div className="mt-auto flex items-center justify-between gap-3 pt-6 font-mono text-[11px]">
                  <span className="text-faint">{d.stat_text}</span>
                  <span className="text-accent transition-colors group-hover:text-fg">TIC {d.tic} &rarr;</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      <div className="mt-10 border-t border-line py-10">
        <Link href="/candidates" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">View all candidates &rarr;</Link>
      </div>
    </main>
  );
}
