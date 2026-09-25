import type { Metadata } from "next";
import { Geist, Geist_Mono, Cormorant_Garamond } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import { getAllTics } from "@/lib/data";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const displaySerif = Cormorant_Garamond({
  variable: "--font-display-serif",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Star Vetter",
  description:
    "An unattended AI pipeline that screens unvetted TESS candidates for real eclipsing binary stars - statistical vetting, catalog cross-matching, and pixel-level source confirmation, with every decision logged.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const tics = getAllTics();
  return (
    <html
      lang="en"
      data-theme="dark"
      className={`${geistSans.variable} ${geistMono.variable} ${displaySerif.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SiteHeader tics={tics} />
        {children}
        <footer className="mt-auto border-t border-line">
          <div className="mx-auto flex max-w-[1920px] flex-wrap items-center justify-between gap-2 px-3 py-6 text-xs text-faint sm:px-6">
            <span>
              Star Vetter - built on public TESS data from MAST. Every number
              shown is produced by the pipeline itself.
            </span>
            <span className="font-mono">TESS / MAST / Gaia</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
