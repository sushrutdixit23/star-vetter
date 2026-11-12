import type { AiPheCurve, MassPoint } from "@/lib/physicsTypes";
import { EclipseWindow, eclipseCentres, fluxRange } from "./charts";

const MONO = "var(--font-geist-mono)";
const rd = (v: number) => Math.round(v * 100) / 100;

// ---------------------------------------------------------------- AI Phe validation

const CHECK_ROWS: { key: string; label: string; unit?: string; tolKey: string; kind: "abs" | "rel"; digits: number }[] = [
  { key: "e", label: "Eccentricity e", tolKey: "e", kind: "abs", digits: 4 },
  { key: "esinw", label: "e sin \u03c9", tolKey: "esinw", kind: "abs", digits: 4 },
  { key: "r1", label: "Radius of star 1 (a)", tolKey: "r_frac", kind: "rel", digits: 4 },
  { key: "r2", label: "Radius of star 2 (a)", tolKey: "r_frac", kind: "rel", digits: 4 },
  { key: "incl", label: "Inclination", unit: "\u00b0", tolKey: "incl", kind: "abs", digits: 2 },
];

export function ValidationFigure({ ai }: { ai: AiPheCurve }) {
  const [yMin, yMax] = fluxRange(ai);
  const c = eclipseCentres(ai);
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-line bg-panel p-3">
          <EclipseWindow curve={ai} centre={c.primary} yMin={yMin} yMax={yMax} title="AI Phe, primary eclipse" label="TESS 2-minute data" published={ai.published_model} modelName="ours / published" />
        </div>
        <div className="rounded-xl border border-line bg-panel p-3">
          <EclipseWindow curve={ai} centre={c.secondary} yMin={yMin} yMax={yMax} title="AI Phe, secondary eclipse" label="TESS 2-minute data" published={ai.published_model} modelName="ours / published" />
        </div>
      </div>
      <p className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        <span><span aria-hidden="true" className="mr-2 inline-block h-0.5 w-6 bg-accent align-middle" />our fit</span>
        <span><span aria-hidden="true" className="mr-2 inline-block w-6 border-t-2 border-dashed border-accent-cool align-middle" />published geometry (Maxted et al. 2020; surface-brightness ratio borrowed from our fit, as it is not among the compared quantities)</span>
      </p>
      <div className="mt-5 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="nav-caps font-mono text-[11px] text-muted">
            <tr>
              <th className="p-3">Quantity</th>
              <th className="p-3">Published</th>
              <th className="p-3">This pipeline, 2 min</th>
              <th className="p-3">Allowed difference</th>
              <th className="p-3">2 min</th>
              <th className="p-3">30 min</th>
            </tr>
          </thead>
          <tbody>
            {CHECK_ROWS.map((r) => {
              const truth = ai.truth[r.key];
              const ours = ai.fit_summary[r.key];
              const tol = ai.tolerance?.[r.tolKey];
              const diff = ours - truth;
              const ok = ai.checks[r.key];
              const ok30 = ai.cadence30?.checks?.[r.key];
              return (
                <tr key={r.key} className="border-t border-line">
                  <td className="p-3 text-muted">{r.label}</td>
                  <td className="p-3 font-mono text-fg">{truth.toFixed(r.digits)}{r.unit ?? ""}</td>
                  <td className="p-3 font-mono text-fg">{ours.toFixed(r.digits)}{r.unit ?? ""} <span className="text-faint">({diff >= 0 ? "+" : "-"}{r.kind === "rel" ? `${Math.abs((diff / truth) * 100).toFixed(1)}%` : Math.abs(diff).toFixed(r.digits)})</span></td>
                  <td className="p-3 font-mono text-muted">{tol === undefined ? "n/a" : r.kind === "rel" ? `${(tol * 100).toFixed(0)}%` : `${tol}${r.unit ?? ""}`}</td>
                  <td className="p-3 font-mono">{ok ? <span className="text-fg">pass</span> : <span className="text-accent-kill">fail</span>}</td>
                  <td className="p-3 font-mono">{ok30 === undefined ? <span className="text-faint">n/a</span> : ok30 ? <span className="text-fg">pass</span> : <span className="text-accent-kill">fail</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- eccentricity against Gaia

export interface EccRow {
  tic: number;
  fit_e: number;
  fit_e_err: number;
  gaia_e: number;
  gaia_e_sigma: number;
  trusted: boolean;
  difference_sigma: number;
}

export function EccentricityDumbbell({ rows }: { rows: EccRow[] }) {
  const W = 700, rowH = 58, T = 28, L = 120, R = 112;
  const H = T + rows.length * rowH + 34;
  const xmax = 0.45;
  const sx = (v: number) => rd(L + (v / xmax) * (W - L - R));
  const ticks = [0, 0.1, 0.2, 0.3, 0.4];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Eccentricity from this light-curve fit compared with Gaia's spectroscopic orbit, with one-sigma bars, for three stars.">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={sx(t)} x2={sx(t)} y1={T - 10} y2={H - 30} className="stroke-line" />
          <text x={sx(t)} y={H - 14} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t.toFixed(1)}</text>
        </g>
      ))}
      <text x={(L + W - R) / 2} y={H - 1} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>eccentricity</text>
      {rows.map((r, i) => {
        const y = T + i * rowH + 14;
        const yf = y - 8, yg = y + 10;
        const lo = (v: number, e: number) => sx(Math.max(0, v - e));
        const hi = (v: number, e: number) => sx(Math.min(xmax, v + e));
        return (
          <g key={r.tic}>
            <text x={8} y={y + 3} className="fill-fg" fontSize="12" fontFamily={MONO}>TIC {r.tic}</text>
            <line x1={lo(r.fit_e, r.fit_e_err)} x2={hi(r.fit_e, r.fit_e_err)} y1={yf} y2={yf} className="stroke-accent" strokeWidth="2" />
            <circle cx={sx(r.fit_e)} cy={yf} r="5.5" className={r.trusted ? "fill-accent" : "fill-canvas stroke-accent"} strokeWidth="2" />
            <line x1={lo(r.gaia_e, r.gaia_e_sigma)} x2={hi(r.gaia_e, r.gaia_e_sigma)} y1={yg} y2={yg} className="stroke-accent-cool" strokeWidth="2" />
            <rect x={sx(r.gaia_e) - 5} y={yg - 5} width="10" height="10" transform={`rotate(45 ${sx(r.gaia_e)} ${yg})`} className="fill-accent-cool" />
            <text x={W - R + 10} y={y + 3} className={r.trusted ? "fill-muted" : "fill-faint"} fontSize="11.5" fontFamily={MONO}>{r.difference_sigma.toFixed(1)} sigma</text>
            {!r.trusted ? <text x={W - R + 10} y={y + 17} className="fill-faint" fontSize="10.5" fontFamily={MONO}>not trusted</text> : null}
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------- Kepler masses against expectation

export function MassStrip({ points }: { points: MassPoint[] }) {
  const pts = [...points].sort((a, b) => a.ratio - b.ratio);
  const W = 700, rowH = 26, T = 30, L = 120, R = 24;
  const H = T + pts.length * rowH + 40;
  const lo = Math.log(0.15), hi = Math.log(5);
  const sx = (v: number) => rd(L + ((Math.log(Math.min(5, Math.max(0.15, v))) - lo) / (hi - lo)) * (W - L - R));
  const ticks = [0.25, 0.5, 1, 2, 4];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="For each of twelve stars, the total mass from Kepler's third law divided by the mass main-sequence stars of that size would have. A value of one is agreement.">
      <rect x={sx(1 / 1.6)} y={T - 12} width={sx(1.6) - sx(1 / 1.6)} height={pts.length * rowH + 8} className="fill-accent" opacity="0.08" />
      {ticks.map((t) => (
        <g key={t}>
          <line x1={sx(t)} x2={sx(t)} y1={T - 12} y2={T + pts.length * rowH - 4} className={t === 1 ? "stroke-muted" : "stroke-line"} strokeWidth={t === 1 ? 1.5 : 1} />
          <text x={sx(t)} y={H - 18} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t}</text>
        </g>
      ))}
      <text x={(L + W - R) / 2} y={H - 3} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>Kepler mass / main-sequence expectation (shaded: within a factor 1.6)</text>
      {pts.map((p, i) => {
        const y = T + i * rowH + 6;
        const e = p.ratio * p.rel_sigma;
        return (
          <g key={p.tic}>
            <text x={8} y={y + 4} className="fill-muted" fontSize="11.5" fontFamily={MONO}>TIC {p.tic}</text>
            <line x1={sx(Math.max(0.15, p.ratio - e))} x2={sx(p.ratio + e)} y1={y} y2={y} className="stroke-muted" strokeWidth="1.5" />
            <circle cx={sx(p.ratio)} cy={y} r="5" className={p.consistent ? "fill-accent" : "fill-canvas stroke-accent-kill"} strokeWidth="2" />
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------- eccentricity against period

export interface EccPoint {
  tic: number;
  period: number;
  e: number;
  lo: number;
  hi: number;
  trusted: boolean;
  lower: number; // |e cos omega|, a floor on e whether or not e itself is trusted
}

export function EccPeriodPlot({ points }: { points: EccPoint[] }) {
  const W = 640, H = 400, L = 56, R = 16, T = 16, B = 50;
  const x0 = 1.5, x1 = 25, ymax = 0.55;
  const sx = (v: number) => rd(L + ((Math.log(v) - Math.log(x0)) / (Math.log(x1) - Math.log(x0))) * (W - L - R));
  const sy = (v: number) => rd(T + (1 - Math.min(v, ymax) / ymax) * (H - T - B));
  const xt = [2, 3, 5, 10, 20];
  const yt = [0, 0.1, 0.2, 0.3, 0.4, 0.5];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Eccentricity against orbital period for the fitted candidates. Filled circles are eccentricities that pass the trust rules; triangles are lower limits from e cos omega alone.">
      {yt.map((t) => (
        <g key={`y${t}`}>
          <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="stroke-line" />
          <text x={L - 8} y={sy(t) + 4} textAnchor="end" className="fill-faint" fontSize="11" fontFamily={MONO}>{t.toFixed(1)}</text>
        </g>
      ))}
      {xt.map((t) => (
        <g key={`x${t}`}>
          <line x1={sx(t)} x2={sx(t)} y1={T} y2={H - B} className="stroke-line" />
          <text x={sx(t)} y={H - B + 17} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t}</text>
        </g>
      ))}
      <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>orbital period (days)</text>
      <text x={14} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`} className="fill-faint" fontSize="11" fontFamily={MONO}>eccentricity</text>
      {points.map((p) => {
        const x = sx(p.period);
        if (p.trusted) {
          return (
            <g key={p.tic}>
              <line x1={x} x2={x} y1={sy(p.e - p.lo)} y2={sy(p.e + p.hi)} className="stroke-accent" strokeWidth="1.5" />
              <circle cx={x} cy={sy(p.e)} r="5" className="fill-accent" />
            </g>
          );
        }
        const y = sy(p.lower);
        return (
          <g key={p.tic}>
            <line x1={x} x2={x} y1={y} y2={sy(ymax)} className="stroke-muted" strokeWidth="1" strokeDasharray="2 3" />
            <path d={`M${x} ${y - 7}L${rd(x + 6)} ${y + 4}L${rd(x - 6)} ${y + 4}Z`} fill="none" className="stroke-muted" strokeWidth="1.6" />
          </g>
        );
      })}
    </svg>
  );
}
