import Link from "next/link";
import HeaderSearch from "./HeaderSearch";

// Four sections, numbered like the journal itself. Standouts and Glossary
// live in the footer.
const NAV = [
  { href: "/", num: "I", label: "Journal" },
  { href: "/candidates", num: "II", label: "Candidates" },
  { href: "/sky", num: "III", label: "Sky" },
  { href: "/about", num: "IV", label: "Instrument" },
];

function StarMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M12 1 L13.3 10.7 L23 12 L13.3 13.3 L12 23 L10.7 13.3 L1 12 L10.7 10.7 Z" fill="currentColor" />
    </svg>
  );
}

export default function SiteHeader({ tics, run }: { tics: number[]; run?: { sampled: number; confirmed: number } | null }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-4 py-3 sm:gap-8 sm:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-3 text-fg">
          <StarMark className="h-6 w-6" />
          <span className="display-caps hidden text-base sm:inline">Star Vetter</span>
        </Link>
        <nav className="flex flex-1 justify-center gap-4 overflow-x-auto text-[11px] text-muted sm:gap-8">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="nav-caps shrink-0 font-mono transition-colors hover:text-fg"><span className="text-faint">{n.num}.</span> {n.label}</Link>
          ))}
        </nav>
        <div className="hidden lg:block">
          <HeaderSearch tics={tics} />
        </div>
        {run && (
          <Link href="/#latest-run" className="hidden shrink-0 items-center gap-2 rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-muted transition-colors hover:border-accent/60 hover:text-fg md:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            <span className="nav-caps">Latest run</span>
            <span className="text-fg">{run.sampled.toLocaleString("en-US")} &rarr; {run.confirmed.toLocaleString("en-US")}</span>
          </Link>
        )}
      </div>
    </header>
  );
}
