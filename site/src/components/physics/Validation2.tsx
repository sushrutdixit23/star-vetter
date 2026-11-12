import type { BenchmarkRow, ConvergenceRow, InjectionMetrics, InjectionPoint, MassCalibrationRow } from "@/lib/physicsTypes";

const MONO = "var(--font-geist-mono)";
const rd = (v: number) => Math.round(v * 100) / 100;
const pct = (v: number | null | undefined, d = 0) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
const sgn = (v: number, d: number) => `${v >= 0 ? "+" : "\u2212"}${Math.abs(v).toFixed(d)}`;

// ---------------------------------------------------------------- blind benchmarks

const CHECKS: { key: string; label: string; tol: string; diff: string; kind: "abs" | "rel" }[] = [
  { key: "e", label: "e", tol: "e_abs", diff: "e", kind: "abs" },
  { key: "abs_esinw", label: "|e sin \u03c9|", tol: "abs_esinw_abs", diff: "abs_esinw", kind: "abs" },
  { key: "ecosw", label: "e cos \u03c9", tol: "ecosw_abs", diff: "ecosw", kind: "abs" },
  { key: "r1", label: "r\u2081", tol: "r_frac", diff: "r1_frac", kind: "rel" },
  { key: "r2", label: "r\u2082", tol: "r_frac", diff: "r2_frac", kind: "rel" },
  { key: "incl", label: "i", tol: "incl_deg", diff: "incl", kind: "abs" },
];

function Mark({ k, x, y, ok }: { k: number; x: number; y: number; ok: boolean }) {
  const cls = ok ? "fill-accent stroke-accent" : "fill-accent-kill stroke-accent-kill";
  const s = 5;
  switch (k) {
    case 0: return <circle cx={x} cy={y} r={s} className={cls} />;
    case 1: return <rect x={x - s} y={y - s} width={2 * s} height={2 * s} className={cls} />;
    case 2: return <rect x={x - s} y={y - s} width={2 * s} height={2 * s} transform={`rotate(45 ${x} ${y})`} className={cls} />;
    case 3: return <path d={`M${x} ${y - s - 1}L${x + s + 1} ${y + s}L${x - s - 1} ${y + s}Z`} className={cls} />;
    case 4: return <path d={`M${x} ${y + s + 1}L${x + s + 1} ${y - s}L${x - s - 1} ${y - s}Z`} className={cls} />;
    default: return <path d={`M${x - s} ${y - s}L${x + s} ${y + s}M${x + s} ${y - s}L${x - s} ${y + s}`} strokeWidth="2.5" className={ok ? "stroke-accent" : "stroke-accent-kill"} />;
  }
}

/** Each check as |difference| / allowed difference, on a log axis: left of the line passes. */
export function BenchmarkMargins({ rows, rule }: { rows: BenchmarkRow[]; rule: Record<string, number | string> }) {
  const W = 760, L = 150, R = 20, T = 30, rowH = 34, B = 46;
  const H = T + rows.length * rowH + B;
  const lo = Math.log10(0.01), hi = Math.log10(100);
  const sx = (v: number) => rd(L + ((Math.log10(Math.min(100, Math.max(0.01, v))) - lo) / (hi - lo)) * (W - L - R));
  const ticks = [0.01, 0.1, 1, 10, 100];
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="For each blind benchmark run, each checked quantity's difference from the published value divided by the allowed difference. Values below one pass.">
        <rect x={L} y={T - 12} width={sx(1) - L} height={rows.length * rowH + 8} className="fill-accent" opacity="0.07" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={T - 12} y2={T + rows.length * rowH - 4} className={t === 1 ? "stroke-muted" : "stroke-line"} strokeWidth={t === 1 ? 1.5 : 1} />
            <text x={sx(t)} y={H - 26} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t}</text>
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>|difference from published| / allowed difference (left of 1: passes)</text>
        {rows.map((r, i) => {
          const y = T + i * rowH + rowH / 2 - 8;
          return (
            <g key={`${r.name}-${r.cadence_min}`}>
              <text x={8} y={y + 4} className="fill-fg" fontSize="12" fontFamily={MONO}>{r.name}</text>
              <text x={96} y={y + 4} className="fill-faint" fontSize="11" fontFamily={MONO}>{r.cadence_min} min</text>
              {r.status !== "OK" || !r.differences ? (
                <text x={L + 8} y={y + 4} className="fill-accent-kill" fontSize="11.5" fontFamily={MONO}>no fit ({r.status.toLowerCase().replace(/_/g, " ")})</text>
              ) : (
                CHECKS.map((c, k) => {
                  const d = Math.abs(r.differences![c.diff] ?? 0);
                  const tol = Number(rule[c.tol]);
                  const v = d / tol;
                  return (
                    <g key={c.key}>
                      <title>{`${r.name} ${r.cadence_min} min, ${c.label}: ${c.kind === "rel" ? pct(r.differences![c.diff], 1) : sgn(r.differences![c.diff], 4)} (allowed ${c.kind === "rel" ? pct(tol, 0) : tol})`}</title>
                      <Mark k={k} x={sx(v)} y={y} ok={v <= 1} />
                    </g>
                  );
                })
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-muted">
        {CHECKS.map((c, k) => (
          <span key={c.key} className="inline-flex items-center gap-1.5">
            <svg viewBox="0 0 14 14" className="h-3.5 w-3.5" aria-hidden="true"><Mark k={k} x={7} y={7} ok /></svg>
            {c.label}
          </span>
        ))}
        <span>blue: within the allowed difference; red: outside it</span>
      </figcaption>
    </figure>
  );
}

export function BenchmarkTable({ rows }: { rows: BenchmarkRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="nav-caps font-mono text-[11px] text-muted">
          <tr className="border-b border-line">
            <th className="p-3 font-normal">System</th>
            <th className="p-3 font-normal">e: published / ours</th>
            <th className="p-3 font-normal">r&#8321; / r&#8322; off by</th>
            <th className="p-3 font-normal">i off by</th>
            <th className="p-3 font-normal">Trust rule</th>
            <th className="p-3 font-normal">Result</th>
          </tr>
        </thead>
        <tbody className="font-mono text-[13px]">
          {rows.map((r) => (
            <tr key={`${r.name}-${r.cadence_min}`} className="border-b border-line last:border-0">
              <td className="p-3 text-fg">{r.name} <span className="text-faint">{r.cadence_min} min</span></td>
              {r.status === "OK" && r.fit && r.differences ? (
                <>
                  <td className="p-3 text-muted">{r.truth.e.toFixed(3)} / <span className="text-fg">{r.fit.e.median.toFixed(3)}</span> <span className="text-faint">&plusmn;{(0.5 * (r.fit.e.lo + r.fit.e.hi)).toFixed(3)}</span></td>
                  <td className="p-3 text-muted">{pct(r.differences.r1_frac, 1)} / {pct(r.differences.r2_frac, 1)}</td>
                  <td className="p-3 text-muted">{sgn(r.differences.incl, 2)}&deg;</td>
                  <td className="p-3 text-muted">{r.trusted ? "accepts e" : "e cos \u03c9 only"}</td>
                </>
              ) : (
                <td colSpan={4} className="p-3 text-muted">no fit: {r.status.toLowerCase().replace(/_/g, " ")}</td>
              )}
              <td className={`p-3 ${r.passed ? "text-fg" : "text-accent-kill"}`}>{r.passed ? "\u2713 pass" : "\u2715 fail"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- injection-recovery

const QLABEL: Record<string, string> = { e: "e", ecosw: "e cos \u03c9", r1: "r\u2081", r2: "r\u2082", incl: "i" };

/** Fraction of injections whose quoted interval contains the truth, against the fraction it should be. */
export function CoverageBars({ m }: { m: InjectionMetrics }) {
  const qs = ["e", "ecosw", "r1", "r2", "incl"];
  const W = 700, L = 110, R = 60, T = 26, rowH = 46, B = 40;
  const H = T + qs.length * rowH + B;
  const sx = (v: number) => rd(L + v * (W - L - R));
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="For each fitted quantity, the share of injections whose 68% and 95% intervals contain the injected value, with the share they should contain marked.">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={T - 10} y2={T + qs.length * rowH - 6} className="stroke-line" />
            <text x={sx(t)} y={H - 22} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t * 100}%</text>
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>share of injections inside the quoted interval</text>
        {qs.map((q, i) => {
          const y = T + i * rowH;
          const c68 = m.by_quantity[q]?.coverage_68 ?? 0, c95 = m.by_quantity[q]?.coverage_95 ?? 0;
          return (
            <g key={q}>
              <text x={8} y={y + 14} className="fill-fg" fontSize="12.5" fontFamily={MONO}>{QLABEL[q]}</text>
              <rect x={L} y={y} width={sx(c68) - L} height={14} rx={2} className="fill-accent" />
              <line x1={sx(0.68)} x2={sx(0.68)} y1={y - 3} y2={y + 17} className="stroke-fg" strokeWidth="2" />
              <text x={sx(Math.max(c68, 0.68)) + 8} y={y + 11} className="fill-muted" fontSize="11" fontFamily={MONO}>68%: {pct(c68)}</text>
              <rect x={L} y={y + 18} width={sx(c95) - L} height={8} rx={2} className="fill-accent" opacity="0.45" />
              <line x1={sx(0.95)} x2={sx(0.95)} y1={y + 15} y2={y + 29} className="stroke-fg" strokeWidth="1.5" />
              <text x={sx(Math.max(c95, 0.95)) + 8} y={y + 27} className="fill-faint" fontSize="10.5" fontFamily={MONO}>95%: {pct(c95)}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 font-mono text-[11px] text-muted">Bars: share of injections whose 68% (thick) and 95% (thin) intervals contain the injected value. Vertical ticks: where honest error bars would put them.</figcaption>
    </figure>
  );
}

function HostMark({ shape, x, y, filled }: { shape: number; x: number; y: number; filled: boolean }) {
  const cls = filled ? "fill-accent stroke-accent" : "fill-none stroke-muted";
  if (shape === 1) return <rect x={x - 4.5} y={y - 4.5} width={9} height={9} className={cls} strokeWidth="1.5" />;
  if (shape === 2) return <path d={`M${x} ${y - 6}L${x + 5.5} ${y + 4}L${x - 5.5} ${y + 4}Z`} className={cls} strokeWidth="1.5" />;
  return <circle cx={x} cy={y} r={4.5} className={cls} strokeWidth="1.5" />;
}

/** Injected against recovered eccentricity, with 68% bars; the band is the "good" tolerance. */
export function InjectionScatter({ points, hosts }: { points: InjectionPoint[]; hosts: { tic: number; label: string }[] }) {
  const shapeOf = new Map(hosts.map((h, i) => [h.tic, i] as const));
  const W = 560, H = 480, L = 56, R = 16, T = 16, B = 50;
  const mx = 0.6;
  const sx = (v: number) => rd(L + (Math.min(v, mx) / mx) * (W - L - R));
  const sy = (v: number) => rd(T + (1 - Math.min(Math.max(v, 0), mx) / mx) * (H - T - B));
  const ticks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6];
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Injected eccentricity against the eccentricity the fit recovered, with 68% intervals. Points on the diagonal are perfect recoveries.">
        <path d={`M${sx(0)} ${sy(0.03)}L${sx(mx - 0.03)} ${sy(mx)}L${sx(mx)} ${sy(mx)}L${sx(mx)} ${sy(mx - 0.03)}L${sx(0.03)} ${sy(0)}L${sx(0)} ${sy(0)}Z`} className="fill-accent" opacity="0.08" />
        <line x1={sx(0)} y1={sy(0)} x2={sx(mx)} y2={sy(mx)} className="stroke-muted" strokeDasharray="4 4" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="stroke-line" opacity="0.6" />
            <text x={L - 8} y={sy(t) + 4} textAnchor="end" className="fill-faint" fontSize="11" fontFamily={MONO}>{t.toFixed(1)}</text>
            <text x={sx(t)} y={H - B + 17} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t.toFixed(1)}</text>
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>injected e</text>
        <text x={14} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`} className="fill-faint" fontSize="11" fontFamily={MONO}>recovered e</text>
        {points.map((p) => {
          const x = sx(p.t.e), y = sy(p.f.e.median);
          return (
            <g key={`${p.host}-${p.i}`}>
              <title>{`host TIC ${p.host}, injection ${p.i}: injected e ${p.t.e.toFixed(3)}, recovered ${p.f.e.median.toFixed(3)} (+${p.f.e.hi.toFixed(3)}/-${p.f.e.lo.toFixed(3)}); r1+r2 ${p.t.rsum.toFixed(2)}; ${p.trusted ? "trust rule accepts" : "trust rule rejects"}`}</title>
              <line x1={x} x2={x} y1={sy(p.f.e.median - p.f.e.lo)} y2={sy(p.f.e.median + p.f.e.hi)} className="stroke-muted" opacity="0.6" />
              <HostMark shape={shapeOf.get(p.host) ?? 0} x={x} y={y} filled={p.trusted} />
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-muted">
        {hosts.map((h, i) => (
          <span key={h.tic} className="inline-flex items-center gap-1.5">
            <svg viewBox="0 0 14 14" className="h-3.5 w-3.5" aria-hidden="true"><HostMark shape={i} x={7} y={7.5} filled={false} /></svg>
            {h.label}
          </span>
        ))}
        <span>filled: the trust rule accepts e</span>
        <span>band: within 0.03 of the truth</span>
      </figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------- convergence before / after

export function ConvergenceDumbbell({ rows }: { rows: ConvergenceRow[] }) {
  const W = 700, L = 120, R = 120, T = 26, rowH = 26, B = 40;
  const H = T + rows.length * rowH + B;
  const mx = 0.6;
  const sx = (v: number) => rd(L + (Math.min(Math.max(v, 0), mx) / mx) * (W - L - R));
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="For each candidate, the fitted eccentricity from the original 1500-step chain and from the longer chain, with the longer chain's 68% interval.">
        {[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6].map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={T - 10} y2={T + rows.length * rowH - 8} className="stroke-line" />
            <text x={sx(t)} y={H - 22} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t.toFixed(1)}</text>
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>eccentricity (hollow: 1500-step chain; filled: longer chain, 68% bar)</text>
        {rows.map((r, i) => {
          const y = T + i * rowH;
          const moved = Math.abs(r.after.median - r.before.median) > 0.5 * (r.after.lo + r.after.hi);
          return (
            <g key={r.tic}>
              <text x={8} y={y + 4} className="fill-muted" fontSize="11.5" fontFamily={MONO}>TIC {r.tic}</text>
              <line x1={sx(r.before.median)} x2={sx(r.after.median)} y1={y} y2={y} className="stroke-faint" />
              <line x1={sx(r.after.median - r.after.lo)} x2={sx(r.after.median + r.after.hi)} y1={y} y2={y} className="stroke-accent" strokeWidth="2" />
              <circle cx={sx(r.before.median)} cy={y} r={4} className="fill-none stroke-muted" strokeWidth="1.5" />
              <circle cx={sx(r.after.median)} cy={y} r={4.5} className="fill-accent" />
              <text x={W - R + 10} y={y + 4} className={moved ? "fill-fg" : "fill-faint"} fontSize="10.5" fontFamily={MONO}>
                {r.steps_after} steps{r.converged_after ? "" : ", short"}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

// ---------------------------------------------------------------- mass method on known systems

export function MassCalibrationTable({ rows }: { rows: MassCalibrationRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="nav-caps font-mono text-[11px] text-muted">
          <tr className="border-b border-line">
            <th className="p-3 font-normal">System</th>
            <th className="p-3 font-normal">Star 1 radius: Gaia method / published</th>
            <th className="p-3 font-normal">Total mass: Kepler from Gaia / published</th>
          </tr>
        </thead>
        <tbody className="font-mono text-[13px]">
          {rows.map((r) => (
            <tr key={r.name} className="border-b border-line last:border-0">
              <td className="p-3 text-fg">{r.name}</td>
              {r.status === "OK" ? (
                <>
                  <td className="p-3 text-muted">{r.R1_from_gaia?.toFixed(2)} / {r.published?.R1.toFixed(2)} R&#9737; <span className="text-fg">({sgn(((r.R1_ratio ?? 1) - 1) * 100, 1)}%)</span></td>
                  <td className="p-3 text-muted">{r.kepler_mass_from_gaia?.toFixed(2)} / {r.published_total_mass?.toFixed(2)} M&#9737; <span className="text-fg">(&times;{r.mass_ratio?.toFixed(2)})</span></td>
                </>
              ) : (
                <td colSpan={2} className="p-3 text-faint">{r.status === "NO_GAIA_RADIUS" ? "no Gaia radius (Gaia flags it as a binary)" : "Gaia archive unavailable at run time"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
