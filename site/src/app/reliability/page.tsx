import Link from "next/link";
import { getBenchmark } from "@/lib/data";
import Band from "@/components/journal/Band";

export const metadata = {
  title: "How reliable is this? - Star Vetter",
};

// Known eclipsing binaries, run blind through the unmodified pipeline in an
// isolated copy. Every number here comes from benchmark.json; none are
// written into the text.

const STAGE_LABEL: Record<string, string> = {
  fetch: "Fetch",
  vetting: "Vetting",
  novelty: "Catalog check",
  pixel: "Pixel check",
};

const TMAG_LABEL: Record<string, string> = {
  "<12": "Brighter than 12",
  "12-13": "12 to 13",
  "13-14": "13 to 14",
  "14+": "Fainter than 14",
};

const pct = (n: number, d: number) => (d > 0 ? `${((100 * n) / d).toFixed(1)}%` : "n/a");

function Bar({ value, max, tone = "accent" }: { value: number; max: number; tone?: "accent" | "kill" }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-panel-2">
      <div className={`h-full rounded-full ${tone === "kill" ? "bg-accent-kill/70" : "bg-accent/70"}`} style={{ width: `${Math.max(2, (value / (max || 1)) * 100)}%` }} />
    </div>
  );
}

function CountList({ title, items, note }: { title: string; items: { key: string; count: number }[]; note?: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="nav-caps font-mono text-[11px] text-accent">{title}</h3>
      {note && <p className="mt-1 text-[11px] text-faint">{note}</p>}
      <dl className="mt-3 space-y-1.5 font-mono text-xs">
        {items.map((it) => (
          <div key={it.key} className="flex justify-between gap-3 border-b border-line pb-1">
            <dt className="text-muted">{it.key}</dt>
            <dd className="text-fg">{it.count}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function ReliabilityPage() {
  const b = getBenchmark();
  const tfe = b ? b.too_few_eclipses : null;
  const tfeGate = b ? b.gates.find((g) => g.gate === "too_few_eclipses") ?? null : null;
  const tfeTop = Boolean(b && tfeGate && b.gates.every((g) => g.count <= tfeGate.count));
  let tfeText: string | null = null;
  if (tfe && tfe.median_period_flagged !== null && tfe.median_period_rest !== null && tfe.median_period_flagged > 0) {
    const expected = Math.floor(27 / tfe.median_period_flagged);
    const base = `Known binaries stopped by the fewer-than-3-eclipses gate have a median catalogue period of ${tfe.median_period_flagged.toFixed(2)} days (${tfe.n_flagged} stars), against ${tfe.median_period_rest.toFixed(2)} days for the rest (${tfe.n_rest}). One TESS sector covers about 27 days, so a ${tfe.median_period_flagged.toFixed(1)}-day binary would show around ${expected} eclipses in a single sector.`;
    tfeText = expected >= 3
      ? `${base} Coverage alone does not explain these losses${tfeTop ? " - and this gate stops more vetted binaries than any other, which makes it the first thing to investigate" : ""}.`
      : `${base} That is fewer than 3, so this gate is at least partly a coverage limit rather than a vetting failure.`;
  }

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="grid gap-6 pb-10 lg:grid-cols-[3rem_minmax(0,1fr)]">
        <div className="font-display text-3xl leading-none text-faint">IV</div>
        <div>
          <div className="nav-caps font-mono text-[11px] text-muted">The instrument, calibrated</div>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">How reliable is <em>this</em>?</h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">To measure how often the pipeline misses a real eclipsing binary, known ones were run blind through the unmodified pipeline - in an isolated copy that cannot touch the real results - and counted at every stage.</p>
        </div>
      </header>

      {!b ? (
        <p className="border-t border-line py-10 text-sm text-faint">The benchmark results have not been published yet. They appear here automatically once the pipeline exports them.</p>
      ) : (
        <>
          <Band num="I" title="The result" lede={b.definition}>
            <div className="font-display text-6xl leading-none text-fg">{b.recall.recovered} <span className="text-3xl text-muted">of {b.recall.sampled}</span></div>
            <div className="mt-2 font-mono text-[11px] text-muted">known eclipsing binaries came out the other end ({pct(b.recall.recovered, b.recall.sampled)})</div>
            <p className="mt-6 max-w-3xl text-sm leading-relaxed text-muted">{`The ${b.sample.n} were drawn from ${b.sample.source}. ${b.sample.selection}.`} A low number here means the pipeline misses many real binaries; the stages below show where. It does not tell you how many of the site&apos;s candidates are false - that needs a different test, such as injecting artificial eclipses with known answers.</p>
          </Band>

          <Band num="II" title="Where they were lost" lede="Each stage, and how many known binaries it stopped.">
            <div className="space-y-4">
              {b.funnel.map((step, i) => {
                const prev = i > 0 ? b.funnel[i - 1].count : null;
                const dropped = prev !== null ? prev - step.count : 0;
                return (
                  <div key={step.label}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-4 text-sm">
                      <span className="text-muted">{step.label}</span>
                      <span className="font-mono text-fg">
                        {step.count}
                        {dropped > 0 && <span className="ml-2 text-accent-kill">-{dropped}</span>}
                      </span>
                    </div>
                    <Bar value={step.count} max={b.funnel[0]?.count ?? 1} />
                  </div>
                );
              })}
            </div>
            <div className="mt-10 grid gap-8 md:grid-cols-2 xl:grid-cols-3">
              <CountList title="Fetch outcomes" items={b.fetch_status} />
              <CountList title="Vetting gates tripped" note="A star can trip more than one gate." items={b.gates.map((g) => ({ key: g.label, count: g.count }))} />
              <CountList title="Pixel-check verdicts" items={b.pixel} />
            </div>
          </Band>

          {b.by_tmag.length > 0 && (
            <Band num="III" title="Brightness matters" lede="Recovery by TESS magnitude - bigger numbers are fainter stars.">
              <div className="max-w-3xl space-y-4">
                {b.by_tmag.map((t) => (
                  <div key={t.bin}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-4 text-sm">
                      <span className="text-muted">{TMAG_LABEL[t.bin] ?? t.bin}</span>
                      <span className="font-mono text-fg">{t.recovered} of {t.n} ({pct(t.recovered, t.n)})</span>
                    </div>
                    <Bar value={t.recovered} max={t.n} />
                  </div>
                ))}
              </div>
            </Band>
          )}

          {tfeText && (
            <Band num="IV" title="The eclipse-count gate" lede="What the fewer-than-3-eclipses gate is really stopping.">
              <p className="max-w-3xl text-sm leading-relaxed text-muted">{tfeText}</p>
            </Band>
          )}

          <Band num="V" title="Calibration controls" lede={b.controls_note}>
            {b.controls.length === 0 ? (
              <p className="text-sm text-faint">No control results were found in this benchmark run.</p>
            ) : (
              <dl className="grid max-w-3xl gap-3 sm:grid-cols-2">
                {b.controls.map((c, i) => (
                  <div key={i} className="rounded-lg border border-line bg-panel/60 p-4 font-mono text-xs">
                    <dt className="text-fg">{c.TIC ? `TIC ${c.TIC}` : "Control"}{c.role ? ` - ${c.role}` : ""}</dt>
                    <dd className="mt-2 text-muted">Verdict: <span className="text-fg">{c.verdict ?? "-"}</span></dd>
                    {(c.expected ?? c.expected_verdict) && <dd className="text-muted">Expected: <span className="text-fg">{c.expected ?? c.expected_verdict}</span></dd>}
                    {(c.note ?? c.reason) && <dd className="mt-1 text-faint">{c.note ?? c.reason}</dd>}
                  </div>
                ))}
              </dl>
            )}
          </Band>

          <Band num="VI" title="Every star" lede="Where each known binary stopped, and why.">
            <details>
              <summary className="nav-caps cursor-pointer font-mono text-[11px] text-accent">Show all {b.stars.length}</summary>
              <div className="mt-4 overflow-x-auto rounded-lg border border-line">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead>
                    <tr className="font-mono text-[10px] uppercase tracking-wider text-faint">
                      <th className="px-3 py-2 font-normal">TIC</th>
                      <th className="px-3 py-2 font-normal">TESS mag</th>
                      <th className="px-3 py-2 font-normal">Catalogue period</th>
                      <th className="px-3 py-2 font-normal">Stopped at</th>
                      <th className="px-3 py-2 font-normal">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...b.stars].sort((x, y) => Number(y.recovered) - Number(x.recovered)).map((s) => (
                      <tr key={s.tic} className="border-t border-line">
                        <td className="px-3 py-2 font-mono text-fg">{s.tic}</td>
                        <td className="px-3 py-2 font-mono text-muted">{s.tmag !== null ? s.tmag.toFixed(2) : "-"}</td>
                        <td className="px-3 py-2 font-mono text-muted">{s.true_period_days !== null ? `${s.true_period_days.toFixed(3)} d` : "-"}</td>
                        <td className="px-3 py-2 text-muted">{s.recovered ? "-" : STAGE_LABEL[s.stage] ?? s.stage}</td>
                        <td className={`px-3 py-2 ${s.recovered ? "text-accent" : "text-muted"}`}>
                          {s.recovered ? "Recovered (ON_TARGET)" : s.outcome}
                          {s.gates.length > 0 && <span className="block text-[11px] text-faint">{s.gates.join("; ")}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </Band>
        </>
      )}

      <div className="flex gap-8 border-t border-line py-10">
        <Link href="/about" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">&larr; How the pipeline works</Link>
        <Link href="/candidates" className="nav-caps font-mono text-[11px] text-accent hover:text-fg">View the candidates &rarr;</Link>
      </div>
    </main>
  );
}
