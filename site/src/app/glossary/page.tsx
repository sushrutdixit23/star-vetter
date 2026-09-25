import Link from "next/link";
import { glossaryByCategory } from "@/lib/glossary";

export const metadata = {
  title: "Glossary - Star Vetter",
  description: "Plain-English definitions for every technical term used on Star Vetter.",
};

export default function GlossaryPage() {
  const groups = glossaryByCategory();

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12 sm:py-16">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent/80">
        Reference
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
        Glossary
      </h1>
      <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted">
        Every technical term used anywhere on this site, in plain English.
        The same definitions also show up inline wherever a term appears in
        a candidate&apos;s dossier - click the dotted underline.
      </p>

      <div className="mt-12 space-y-12">
        {groups.map((g) => (
          <section key={g.category}>
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-faint">
              {g.label}
            </h2>
            <dl className="space-y-5">
              {g.terms.map(({ id, entry }) => (
                <div key={id} id={id} className="scroll-mt-20">
                  <dt className="text-sm font-semibold text-fg">{entry.term}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-muted">{entry.def}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <div className="mb-16 mt-12 flex gap-6">
        <Link href="/about" className="font-mono text-xs uppercase tracking-wide text-accent/80 hover:text-accent">
          &larr; how the pipeline works
        </Link>
        <Link href="/" className="font-mono text-xs uppercase tracking-wide text-accent/80 hover:text-accent">
          view confirmed candidates
        </Link>
      </div>
    </main>
  );
}
