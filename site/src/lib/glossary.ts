// Plain-English definitions for the technical terms used across the site.
// Grounded in what the pipeline actually computes - nothing here describes
// a check the pipeline doesn't really run. Shown two ways: as a click-to-
// reveal note next to a term where it appears (see components/Term.tsx),
// and in full on /glossary.

export interface GlossaryEntry {
  term: string;
  def: string;
  category: "mission" | "signal" | "period" | "pixel" | "result";
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  tess: {
    term: "TESS (Transiting Exoplanet Survey Satellite)",
    def: "A NASA space telescope that has been continuously photographing the sky in wide strips, called sectors, since 2018 - mainly to find planets, but its data works just as well for finding eclipsing binary stars, which is what this pipeline looks for.",
    category: "mission",
  },
  tic: {
    term: "TIC (TESS Input Catalog)",
    def: "The master list of roughly 1.7 billion stars TESS could observe, each with a unique TIC number. Every candidate on this site is identified by its TIC number.",
    category: "mission",
  },
  sector: {
    term: "Sector",
    def: "One continuous block of TESS observing time, about 27 days, pointed at one region of sky. A star can appear in more than one sector if TESS revisits that part of the sky later.",
    category: "mission",
  },
  cadence: {
    term: "Cadence",
    def: "How often TESS records a brightness measurement for a target - about every 30 minutes for the candidates on this site. A very short eclipse can be hard to measure well if it barely lasts longer than one cadence step.",
    category: "mission",
  },
  light_curve: {
    term: "Light curve",
    def: "A record of a star's brightness measured over time. A dip that repeats on a regular schedule is the signature this pipeline searches for.",
    category: "mission",
  },
  eclipsing_binary: {
    term: "Eclipsing binary",
    def: "Two stars orbiting each other closely enough, and aligned edge-on to Earth closely enough, that each one periodically blocks some of the other's light - producing the repeating dips this pipeline searches for.",
    category: "mission",
  },
  bls: {
    term: "BLS (Box Least Squares)",
    def: "The period-search algorithm this pipeline uses. It looks specifically for box-shaped dips - a good match for eclipses, which have a flat bottom and sharp edges, unlike the smooth rise-and-fall of a pulsating star.",
    category: "period",
  },
  period_bls: {
    term: "Period (BLS)",
    def: "The orbital period the BLS algorithm found by testing many candidate periods and keeping the one whose repeating dips line up best.",
    category: "period",
  },
  period_true: {
    term: "Period (true)",
    def: "The period actually used for this candidate's ephemeris. It's the same as the BLS period, unless the odd/even depth test found evidence BLS had locked onto half the real period - in which case this is corrected to double it.",
    category: "period",
  },
  ephemeris: {
    term: "Ephemeris",
    def: "A period plus a reference eclipse time - together, the two numbers that predict when every future eclipse of this star will happen.",
    category: "period",
  },
  epoch: {
    term: "Epoch",
    def: "One numbered cycle of the orbital period, counting forward or backward from the reference eclipse time. Epoch shift measures how far an eclipse actually observed at the pixel level falls from where the ephemeris predicted it.",
    category: "period",
  },
  phase: {
    term: "Phase",
    def: "Where a moment in time falls within one orbital cycle, on a scale of 0 to 1. Folding a light curve on its period means re-plotting every cycle on top of each other using phase instead of raw time - which is how a faint repeating dip becomes visible.",
    category: "period",
  },
  aliased: {
    term: "Aliased period",
    def: "A period that is a simple fraction of a star's real orbital period, mistaken for the real one. Caught here by the odd/even depth test, which flags when BLS has locked onto half the true period.",
    category: "period",
  },
  lomb_scargle: {
    term: "Lomb-Scargle",
    def: "A separate periodicity search, run independently of BLS, that looks for any strong smooth sinusoidal signal. Used here as a check for stars whose variability might come from a pulsating or spotted star rather than a genuine eclipsing pair.",
    category: "period",
  },
  duration: {
    term: "Eclipse duration",
    def: "How long each eclipse lasts, taken from the width of the box-shaped dip BLS fit to the folded light curve.",
    category: "signal",
  },
  depth: {
    term: "Eclipse depth",
    def: "How much the star's brightness drops during an eclipse, shown here as a percent of its normal brightness.",
    category: "signal",
  },
  secondary_eclipse: {
    term: "Secondary eclipse",
    def: "A second, usually shallower dip roughly halfway through the orbit, caused by the dimmer of the two stars passing in front of the brighter one. Finding one is strong independent evidence the signal is a genuine eclipsing binary rather than some other kind of variability.",
    category: "signal",
  },
  odd_even: {
    term: "Odd/even depth test",
    def: "Checks whether eclipses at odd-numbered epochs are the same depth as eclipses at even-numbered epochs. If they aren't, it usually means the true orbital period is twice what BLS found, alternating between the primary and secondary eclipse - which the pipeline then corrects for.",
    category: "signal",
  },
  snr: {
    term: "SNR (signal-to-noise ratio)",
    def: "How strong a detection is compared to the noise in the data, expressed as a multiple of the noise level (sigma). A higher SNR means the detection is less likely to be a statistical fluke.",
    category: "signal",
  },
  sigma: {
    term: "Sigma",
    def: "A unit of statistical significance - how many multiples of the noise level a measurement stands away from zero. 5 sigma or higher is the pipeline's usual bar for trusting a detection.",
    category: "signal",
  },
  robust_depth: {
    term: "Robust depth / sigma",
    def: "A depth and significance measured with outlier-resistant statistics (the median and a robust spread measure) instead of a plain mean and standard deviation, so a handful of bad data points can't distort the result.",
    category: "signal",
  },
  difference_imaging: {
    term: "Difference imaging",
    def: "Subtracting an averaged in-eclipse pixel image from an averaged out-of-eclipse image. What's left over shows exactly where on the sky the dimming pixel is coming from - the pipeline's way of checking the signal at the pixel level, not just in the combined light curve.",
    category: "pixel",
  },
  centroid_offset: {
    term: "Centroid offset",
    def: "How far the photometric center of the dimming, measured pixel by pixel, sits from the target star's own catalog position. A large offset means the eclipse-like signal is probably coming from a different star nearby, not the target.",
    category: "pixel",
  },
  compactness: {
    term: "Compactness",
    def: "Whether the difference-image dimming looks like a single point of light (consistent with one real star) or a smeared, multi-peaked blob (consistent with light from more than one source blending together).",
    category: "pixel",
  },
  contamination: {
    term: "Contamination",
    def: "A brighter neighbouring star, close enough to fall inside TESS's photometric aperture, that could itself be producing the dip credited to the target.",
    category: "pixel",
  },
  novelty: {
    term: "Novelty / catalog cross-match",
    def: "Checking a candidate's coordinates against known variable-star and eclipsing-binary catalogs. A match means the star is already documented and vetting stops there; no match means the candidate is carried forward as novel.",
    category: "result",
  },
  dossier: {
    term: "Dossier",
    def: "The full written report generated for a confirmed candidate - ephemeris, every gate value, the catalog cross-match table, and the pixel-check imagery - produced automatically, with no manual write-up step.",
    category: "result",
  },
  tier: {
    term: "Tier",
    def: "The pipeline's own confidence classification for a candidate, based on how cleanly it passed the statistical and pixel-level gates.",
    category: "result",
  },
  tess_mag: {
    term: "TESS magnitude (Tmag)",
    def: "How bright a star appears to TESS's camera specifically. Lower numbers are brighter; it's on the same reversed, logarithmic scale as ordinary astronomical magnitude.",
    category: "mission",
  },
  gaia: {
    term: "Gaia",
    def: "A European Space Agency satellite that has measured precise positions, distances, and brightnesses for roughly two billion stars. This pipeline pulls a candidate's distance, temperature, and radius from Gaia-derived catalog values.",
    category: "mission",
  },
  teff: {
    term: "Effective temperature (Teff)",
    def: "The star's surface temperature in kelvin, taken from its catalog entry - a rough proxy for its color and spectral type.",
    category: "mission",
  },
};

export type GlossaryId = keyof typeof GLOSSARY;

const CATEGORY_LABEL: Record<GlossaryEntry["category"], string> = {
  mission: "The mission & the data",
  period: "Finding the orbit",
  signal: "Is the eclipse real?",
  pixel: "Is it really this star?",
  result: "What comes out the other end",
};

export function glossaryByCategory() {
  const groups = new Map<GlossaryEntry["category"], { id: string; entry: GlossaryEntry }[]>();
  for (const [id, entry] of Object.entries(GLOSSARY)) {
    const list = groups.get(entry.category) ?? [];
    list.push({ id, entry });
    groups.set(entry.category, list);
  }
  const order: GlossaryEntry["category"][] = ["mission", "period", "signal", "pixel", "result"];
  return order
    .filter((c) => groups.has(c))
    .map((c) => ({
      category: c,
      label: CATEGORY_LABEL[c],
      terms: (groups.get(c) ?? []).sort((a, b) => a.entry.term.localeCompare(b.entry.term)),
    }));
}
