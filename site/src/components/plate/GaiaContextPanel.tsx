import type { GaiaContext } from "@/lib/types";

// ESA Gaia DR3 context for a candidate - measurements from a different
// spacecraft using a different technique, matched to the TIC position.
// Distance comes from parallax and is shown only when the parallax is
// measured well. Absolute brightness and colour place the star on a
// colour-magnitude diagram beside every other survivor Gaia can place,
// with the Sun for scale. RUWE says how well Gaia's position measurements
// fit a single point of light; above ~1.4 the fit is poor, which often
// means more than one star - but an eclipsing pair a few days apart is
// usually far too tight to move Gaia's image, so a poor fit more likely
// points to a wider third star or an unresolved neighbour. It is context,
// not independent confirmation.

const LY_PER_PC = 3.26156;
const SUN_BP_RP = 0.82;
const SUN_ABS_G = 4.67;
const W = 360;
const H = 250;
const PL = 34;
const PR = 12;
const PT = 12;
const PB = 30;

const COLOUR_STOPS: [number, number, number, number][] = [
  [-0.2, 160, 190, 255],
  [0.4, 215, 228, 255],
  [0.8, 255, 240, 205],
  [1.3, 255, 200, 130],
  [2.0, 255, 150, 85],
  [3.2, 255, 110, 60],
];

function colourFor(bpRp: number): string {
  const t = Math.min(3.2, Math.max(-0.2, bpRp));
  let i = 0;
  while (i < COLOUR_STOPS.length - 2 && t > COLOUR_STOPS[i + 1][0]) i++;
  const a = COLOUR_STOPS[i];
  const b = COLOUR_STOPS[i + 1];
  const f = (t - a[0]) / (b[0] - a[0]);
  const mix = (x: number, y: number) => Math.round(x + (y - x) * f);
  return `rgb(${mix(a[1], b[1])},${mix(a[2], b[2])},${mix(a[3], b[3])})`;
}

const r1 = (v: number) => Math.round(v * 10) / 10;
const fmt = (v: number) => Math.round(v).toLocaleString("en-US");

export interface GaiaVerdict {
  kind: "pass" | "warn";
  label: string;
  note: string;
  rows: [string, string][];
}

export function gaiaVerdict(g: GaiaContext | null): GaiaVerdict | null {
  if (!g) return null;
  const rows: [string, string][] = [];
  if (g.distance_reliable && g.distance_pc) {
    const err = g.parallax_mas && g.parallax_error_mas ? (g.distance_pc * g.parallax_error_mas) / g.parallax_mas : null;
    rows.push(["Distance", err ? `${fmt(g.distance_pc)} +/- ${fmt(err)} pc` : `${fmt(g.distance_pc)} pc`]);
    rows.push(["Light-travel time", `~${fmt(g.distance_pc * LY_PER_PC)} years`]);
  } else {
    rows.push(["Distance", "not reliable"]);
  }
  if (g.phot_g_mean_mag !== null) rows.push(["Apparent G", g.phot_g_mean_mag.toFixed(2)]);
  if (g.abs_g_mag !== null && g.abs_g_mag !== undefined) rows.push(["Absolute G", g.abs_g_mag.toFixed(2)]);
  if (g.bp_rp !== null) rows.push(["Colour BP-RP", g.bp_rp.toFixed(2)]);
  if (g.ruwe !== null) rows.push(["RUWE", g.ruwe.toFixed(2)]);
  if (g.separation_arcsec !== null) rows.push(["Match offset", `${g.separation_arcsec.toFixed(2)} arcsec`]);
  if (g.ruwe === null) {
    return { kind: "warn", label: "Limited Gaia data", note: "Gaia has no astrometric solution for this source, so it adds no information about extra stars.", rows };
  }
  if (g.elevated_ruwe) {
    return { kind: "warn", label: "Worth a closer look", note: `Gaia's position measurements fit this source poorly (RUWE ${g.ruwe.toFixed(2)}, above the usual 1.4). That often means more than one star is there - most likely a wider third star or an unresolved neighbour, since a tight eclipsing pair barely moves Gaia's image. Context, not confirmation.`, rows };
  }
  return { kind: "pass", label: "Single-star fit", note: `Gaia's measurements fit a single point of light well (RUWE ${g.ruwe.toFixed(2)}), as expected for a pair too close for Gaia to separate.`, rows };
}

export default function GaiaContextPanel({ gaia, all, tic }: { gaia: GaiaContext | null; all: Record<string, GaiaContext> | null; tic: number }) {
  if (!gaia) {
    return <p className="text-sm text-muted">The latest Gaia context file does not include this candidate yet, so there is no Gaia view to show.</p>;
  }

  const pts = Object.entries(all ?? {})
    .filter(([, v]) => v.distance_reliable && v.bp_rp !== null && v.abs_g_mag !== null && v.abs_g_mag !== undefined)
    .map(([k, v]) => ({ tic: k, x: v.bp_rp as number, y: v.abs_g_mag as number, elevated: Boolean(v.elevated_ruwe) }));
  const me = pts.find((p) => p.tic === String(tic)) ?? null;
  const xsAll = [...pts.map((p) => p.x), SUN_BP_RP];
  const ysAll = [...pts.map((p) => p.y), SUN_ABS_G];
  const xmin = Math.floor((Math.min(...xsAll) - 0.15) * 2) / 2;
  const xmax = Math.ceil((Math.max(...xsAll) + 0.15) * 2) / 2;
  const ymin = Math.floor(Math.min(...ysAll) - 0.5);
  const ymax = Math.ceil(Math.max(...ysAll) + 0.5);
  const sx = (x: number) => r1(PL + ((x - xmin) / (xmax - xmin || 1)) * (W - PL - PR));
  const sy = (y: number) => r1(PT + ((y - ymin) / (ymax - ymin || 1)) * (H - PT - PB));
  const xticks: number[] = [];
  for (let v = Math.ceil(xmin * 2) / 2; v <= xmax + 0.001; v += 0.5) xticks.push(Math.round(v * 10) / 10);
  const yticks: number[] = [];
  for (let v = Math.ceil(ymin / 2) * 2; v <= ymax; v += 2) yticks.push(v);

  const ly = gaia.distance_reliable && gaia.distance_pc ? gaia.distance_pc * LY_PER_PC : null;
  const absG = gaia.abs_g_mag ?? null;
  const ratio = absG !== null ? Math.pow(10, (SUN_ABS_G - absG) / 2.5) : null;
  let lightSentence: string | null = null;
  if (ratio !== null) {
    lightSentence = ratio >= 1
      ? `Together the two stars give off about ${ratio < 10 ? ratio.toFixed(1) : fmt(ratio)} times the Sun's light in Gaia's band - before correcting for interstellar dust, which only makes distant stars look fainter.`
      : `Together the two stars give off about ${(1 / ratio).toFixed(1)} times less light than the Sun in Gaia's band, before correcting for interstellar dust.`;
  }
  let colourSentence: string | null = null;
  if (gaia.bp_rp !== null) {
    colourSentence = gaia.bp_rp < SUN_BP_RP - 0.15
      ? "Its colour is bluer than the Sun's, which usually means hotter."
      : gaia.bp_rp > SUN_BP_RP + 0.15
        ? "Its colour is redder than the Sun's, which usually means cooler - though dust along the way also reddens light."
        : "Its colour is close to the Sun's.";
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,560px)_minmax(0,1fr)] xl:items-start">
      <figure className="min-w-0">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label="Colour-magnitude diagram of the survivors Gaia can place, with this star highlighted">
          <rect x={PL} y={PT} width={W - PL - PR} height={H - PT - PB} fill="none" className="stroke-line" strokeWidth={0.8} />
          {xticks.map((v) => (
            <g key={`x${v}`}>
              <line x1={sx(v)} x2={sx(v)} y1={PT} y2={H - PB} className="stroke-line" strokeWidth={0.4} strokeDasharray="2 3" />
              <text x={sx(v)} y={H - PB + 10} fontSize={7} textAnchor="middle" className="fill-faint">{v.toFixed(1)}</text>
            </g>
          ))}
          {yticks.map((v) => (
            <g key={`y${v}`}>
              <line x1={PL} x2={W - PR} y1={sy(v)} y2={sy(v)} className="stroke-line" strokeWidth={0.4} strokeDasharray="2 3" />
              <text x={PL - 4} y={sy(v) + 2.5} fontSize={7} textAnchor="end" className="fill-faint">{v}</text>
            </g>
          ))}
          <text x={(PL + W - PR) / 2} y={H - 4} fontSize={7.5} textAnchor="middle" className="fill-muted">Gaia colour BP-RP (bluer to redder)</text>
          <text x={9} y={(PT + H - PB) / 2} fontSize={7.5} textAnchor="middle" className="fill-muted" transform={`rotate(-90 9 ${(PT + H - PB) / 2})`}>Absolute G (brighter is up)</text>
          {pts.filter((p) => p.tic !== String(tic)).map((p) => (
            <g key={p.tic}>
              <circle cx={sx(p.x)} cy={sy(p.y)} r={2.4} fill={colourFor(p.x)} opacity={0.75} />
              {p.elevated && <circle cx={sx(p.x)} cy={sy(p.y)} r={4.4} fill="none" stroke="#ffb061" strokeWidth={0.7} opacity={0.8} />}
            </g>
          ))}
          <circle cx={sx(SUN_BP_RP)} cy={sy(SUN_ABS_G)} r={4} fill="none" stroke="#ffe08a" strokeWidth={0.9} />
          <circle cx={sx(SUN_BP_RP)} cy={sy(SUN_ABS_G)} r={1} fill="#ffe08a" />
          <text x={sx(SUN_BP_RP) + 6} y={sy(SUN_ABS_G) + 2.5} fontSize={7.5} fill="#ffe08a" stroke="#07090f" strokeWidth={2.5} style={{ paintOrder: "stroke" }}>Sun</text>
          {me && (
            <g>
              <circle cx={sx(me.x)} cy={sy(me.y)} r={7.5} fill="none" className="stroke-accent" strokeWidth={1.2} />
              <circle cx={sx(me.x)} cy={sy(me.y)} r={3.4} fill={colourFor(me.x)} />
              <text x={sx(me.x) > W * 0.6 ? sx(me.x) - 10 : sx(me.x) + 10} y={sy(me.y) - 6} fontSize={8} textAnchor={sx(me.x) > W * 0.6 ? "end" : "start"} className="fill-fg" stroke="#07090f" strokeWidth={2.5} style={{ paintOrder: "stroke" }}>TIC {tic}</text>
            </g>
          )}
        </svg>
        <figcaption className="mt-2 text-[11px] leading-relaxed text-faint">Every survivor Gaia can place, by colour and true brightness; the Sun is marked for scale. Amber rings mark RUWE above 1.4. No stellar model is drawn - only the measurements.</figcaption>
      </figure>
      <div className="space-y-3 text-sm leading-relaxed text-muted">
        {ly !== null && <p>It is about {fmt(ly)} light years away: the light TESS recorded left it around {fmt(ly)} years ago.</p>}
        {lightSentence && <p>{lightSentence}</p>}
        {colourSentence && <p>{colourSentence}</p>}
        {!me && <p>Not plotted on the diagram: its distance is not measured well enough to place it.</p>}
        {gaia.note && <p className="text-[11px] text-faint">Gaia note: {gaia.note}</p>}
        <p className="text-[11px] text-faint">Source: ESA Gaia DR3{gaia.gaia_source_id ? `, source ${gaia.gaia_source_id}` : ""}.</p>
      </div>
    </div>
  );
}
