import Link from "next/link";
import HeaderSearch from "./HeaderSearch";
import { LogoMark } from "./icons";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/candidates", label: "Candidates" },
  { href: "/about", label: "Methods" },
  { href: "/glossary", label: "Glossary" },
];

export default function SiteHeader({ tics }: { tics: number[] }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1920px] items-center gap-4 px-3 py-3 sm:gap-8 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-3 text-fg">
          <LogoMark className="h-7 w-7" />
          <span className="display-caps hidden text-lg sm:inline">
            Star Vetter
          </span>
        </Link>
        <nav className="flex gap-4 text-sm text-muted sm:gap-6">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="hover:text-fg">
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto hidden md:block">
          <HeaderSearch tics={tics} />
        </div>
      </div>
    </header>
  );
}
