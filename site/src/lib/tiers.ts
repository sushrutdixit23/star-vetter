import type { Tier } from "./types";

// Same five tiers as the PDF dossiers (f5_dossier.py). Each class string
// carries a light-theme colour plus a dark: override, so badges stay
// readable in both themes. Keep the hue mapping in sync with the pipeline.

interface TierStyle {
  label: string;
  text: string;
  bg: string;
  border: string;
  dot: string;
  chart: string;
  blurb: string;
}

// Mildest to most severe - the same severity order f5_dossier.py uses to
// pick a star's badge when it carries more than one caveat.
export const TIER_ORDER: Tier[] = [
  "CLEAN",
  "PERIOD ALIAS",
  "MARGINAL",
  "AMBIGUOUS PHOTOMETRY",
  "THIN MARGIN",
];

export const TIER_STYLE: Record<Tier, TierStyle> = {
  CLEAN: {
    label: "Clean",
    text: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-500/10 dark:bg-emerald-400/10",
    border: "border-emerald-600/30 dark:border-emerald-400/30",
    dot: "bg-emerald-500 dark:bg-emerald-400",
    chart: "#34d399",
    blurb: "Passed every gate with a comfortable margin. No caveats.",
  },
  "PERIOD ALIAS": {
    label: "Period alias",
    text: "text-sky-700 dark:text-sky-300",
    bg: "bg-sky-500/10 dark:bg-sky-400/10",
    border: "border-sky-600/30 dark:border-sky-400/30",
    dot: "bg-sky-500 dark:bg-sky-400",
    chart: "#38bdf8",
    blurb: "Odd and even eclipses differ in depth: the true period is double the BLS period.",
  },
  "THIN MARGIN": {
    label: "Thin margin",
    text: "text-rose-700 dark:text-rose-300",
    bg: "bg-rose-500/10 dark:bg-rose-400/10",
    border: "border-rose-600/30 dark:border-rose-400/30",
    dot: "bg-rose-500 dark:bg-rose-400",
    chart: "#fb7185",
    blurb: "The dimming centroid sits almost as close to a bright neighbour as to the target.",
  },
  MARGINAL: {
    label: "Marginal",
    text: "text-amber-700 dark:text-amber-300",
    bg: "bg-amber-500/10 dark:bg-amber-400/10",
    border: "border-amber-600/30 dark:border-amber-400/30",
    dot: "bg-amber-500 dark:bg-amber-400",
    chart: "#fbbf24",
    blurb: "The pixel-level detection sits right at the SNR gate.",
  },
  "AMBIGUOUS PHOTOMETRY": {
    label: "Ambiguous",
    text: "text-amber-700 dark:text-amber-300",
    bg: "bg-amber-500/10 dark:bg-amber-400/10",
    border: "border-amber-600/30 dark:border-amber-400/30",
    dot: "bg-amber-500 dark:bg-amber-400",
    chart: "#fbbf24",
    blurb: "Strong in pixel imaging, but simple-aperture photometry shows no dip.",
  },
};
