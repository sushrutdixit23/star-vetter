import Link from "next/link";
import { glossaryByCategory } from "@/lib/glossary";
import Band from "@/components/journal/Band";

export const metadata = {
  title: "Glossary - Star Vetter",
  description: "Plain-English definitions for every technical term used on Star Vetter.",
};

const NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

export default function GlossaryPage() {
  const groups = glossaryByCategory();

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="pb-10">
        <div className="nav-caps font-mono text-[11px] text-muted">Reference</div>
        <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">Glossary.</h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">Every technical term used anywhere on this site, in plain English. The same definitions also show up inline wherever a term appears on a candidate page - click the dotted underline.</p>
      </header>

      {groups.map((g, gi) => (
        <Band key={g.category} num={NUMERALS[gi] ?? String(gi + 1)} title={g.label}>
          <dl className="grid gap-x-10 gap-y-5 md:grid-cols-2">
            {g.terms.map(({ id, entry }) => (
              <div key={id} id={id} className="scroll-mt-24 border-t border-line pt-3">
                <dt className="text-sm font-medium text-fg">{entry.term}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-muted">{entry.def}</dd>
              </div>
            ))}
          </dl>
        </Band>
      ))}

      <div className="flex gap-8 border-t border-line py-10">
        <Link href="/about" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">&larr; How the pipeline works</Link>
        <Link href="/candidates" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">View the candidates &rarr;</Link>
      </div>
    </main>
  );
}
