import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import { getAllTics, getPipelineStats } from "@/lib/data";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const displaySerif = Instrument_Serif({
  variable: "--font-display-serif",
  subsets: ["latin"],
  weight: ["400"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Star Vetter",
  description:
    "An unattended AI pipeline that screens unvetted TESS candidates for real eclipsing binary stars - statistical vetting, catalog cross-matching, and pixel-level source confirmation, with every decision logged.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const tics = getAllTics();
  const funnel = getPipelineStats()?.funnel ?? [];
  const run = funnel.length >= 6 ? { sampled: funnel[0].count, confirmed: funnel[5].count } : null;
  return (
    <html
      lang="en"
      data-theme="dark"
      className={`${geistSans.variable} ${geistMono.variable} ${displaySerif.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SiteHeader tics={tics} run={run} />
        {children}
        <footer className="mt-auto border-t border-line">
          <div className="mx-auto flex max-w-[1920px] flex-wrap items-center justify-between gap-3 px-3 py-6 text-xs text-faint sm:px-6">
            <span>
              Star Vetter - built on public TESS data from MAST. Every number
              shown is produced by the pipeline itself.
            </span>
            <nav className="flex gap-4">
              <Link href="/standouts" className="nav-caps hover:text-muted">
                Standouts
              </Link>
              <Link href="/glossary" className="nav-caps hover:text-muted">
                Glossary
              </Link>
            </nav>
            <span className="font-mono">TESS / MAST / Gaia</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
