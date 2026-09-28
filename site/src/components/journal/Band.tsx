import type { ReactNode } from "react";

// One journal section: a Roman numeral in the gutter, a spaced-caps serif
// title, a short lede, an optional action, then the section's visual.
// "wide" spans the page (numeral | text | visual); "half" is for the
// two-up rows (numeral beside text, visual underneath).
export default function Band({ num, title, lede, action, children, variant = "wide", id, className = "" }: { num: string; title: string; lede?: ReactNode; action?: ReactNode; children?: ReactNode; variant?: "wide" | "half"; id?: string; className?: string }) {
  const head = (
    <div className="min-w-0">
      <h2 className="font-display text-xl uppercase tracking-[0.16em] text-fg sm:text-2xl">{title}</h2>
      {lede && <div className="mt-2 max-w-md text-sm leading-relaxed text-muted">{lede}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );

  if (variant === "half") {
    return (
      <section id={id} className={`min-w-0 ${className}`}>
        <div className="flex gap-4">
          <div className="w-10 shrink-0 font-display text-3xl leading-none text-faint">{num}</div>
          <div className="min-w-0 flex-1">
            {head}
            <div className="mt-6">{children}</div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section id={id} className={`border-t border-line py-10 ${className}`}>
      <div className="grid gap-6 lg:grid-cols-[3rem_minmax(0,17rem)_minmax(0,1fr)] lg:gap-8">
        <div className="font-display text-3xl leading-none text-faint">{num}</div>
        {head}
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );
}
