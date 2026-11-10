import { getAudit, getRecovery, getAtlasAlias, getNeighbours, getEvidence, getZtf, getGaia, getPriorArt, getGaiaDr4Plan } from "@/lib/data";
import type { RateInterval, MedianInterval, RecoveryCell } from "@/lib/types";
import Band from "@/components/journal/Band";
import CountUp from "@/components/CountUp";

export const metadata = {
  title: "The audit - Star Vetter",
  description: "A quantified audit of the Kostov et al. 2025 unvetted eclipsing-binary list: what the pipeline recovers, what it misses, and how often it is fooled.",
};

const pc = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "n/a" : `${(100 * x).toFixed(d)}%`);
const ci = (r: RateInterval, d = 1) => `${pc(r.rate, d)} (${pc(r.lo, d)} to ${pc(r.hi, d)})`;
const mi = (m: MedianInterval, d = 1) => `${pc(m.median, d)} (${pc(m.lo, d)} to ${pc(m.hi, d)})`;
const n0 = (n: number) => n.toLocaleString("en-US");

const GATE_LABEL: Record<string, string> = {
  too_few_eclipses: "Fewer than 3 usable eclipses",
  insufficient_intransit_points: "Fewer than 10 points in eclipse",
  below_noise_floor: "Signal-to-noise too low",
  robust_depth_mismatch: "Median depth disagrees with the fit",
  noisy_photometry: "Noisy photometry",
  inhomogeneous_photometry: "Uneven segments",
  depth_too_small: "Depth too small",
  non_finite_bls_result: "Fit failed",
};

function Bar({ value, max, i = 0 }: { value: number; max: number; i?: number }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-panel-2">
      <div className="sv-grow h-full rounded-full bg-accent/70" style={{ width: `${Math.max(2, (value / (max || 1)) * 100)}%`, "--i": i } as React.CSSProperties} />
    </div>
  );
}

function RecallRows({ rows, label }: { rows: RecoveryCell[]; label: (c: RecoveryCell) => string }) {
  return (
    <div className="space-y-3">
      {rows.map((c, i) => (
        <div key={`${label(c)}-${i}`}>
          <div className="mb-1.5 flex items-baseline justify-between gap-4 text-sm">
            <span className="text-muted">{label(c)}</span>
            <span className="font-mono text-xs text-fg">{c.n > 0 ? `${c.detected.k} of ${c.n} - ${pc(c.detected.rate, 0)}` : "none tested"}</span>
          </div>
          <Bar value={c.detected.rate ?? 0} max={1} />
        </div>
      ))}
    </div>
  );
}

export default function AuditPage() {
  const a = getAudit();
  const r = getRecovery();
  const al = getAtlasAlias();
  const nb = getNeighbours();
  const headline = nb ? String(nb.method.headline_floor_arcsec) : "6";
  const nbSum = nb?.summary_by_floor[headline] ?? null;
  const funnelMax = a?.funnel[0]?.count ?? 1;
  const ev = getEvidence();
  const zt = getZtf();
  const gx = getGaia();
  const pa = getPriorArt();
  const dr4 = getGaiaDr4Plan();
  const TIERS: [string, string][] = [
    ["INDEPENDENTLY_SUPPORTED", "Independently supported"],
    ["TESS_ONLY_CLEAN", "TESS only, no caveats"],
    ["TESS_ONLY_CAVEATS", "TESS only, with caveats"],
    ["DISFAVOURED", "Evidence against"],
  ];
  const NOVELTY: [string, string][] = [
    ["KNOWN_ECLIPSING", "Already known as eclipsing"],
    ["KNOWN_BINARY", "Known binary, not as eclipsing"],
    ["KNOWN_VARIABLE", "Known variable"],
    ["NO_PRIOR_FOUND", "Nothing found"],
  ];

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="grid gap-6 pb-10 lg:grid-cols-[3rem_minmax(0,1fr)]">
        <div className="font-display text-3xl leading-none text-faint">VI</div>
        <div>
          <div className="nav-caps font-mono text-[11px] text-muted">What was measured, and how far to trust it</div>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">The <em>audit</em></h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">Every candidate on this site is already an entry in Kostov et al. (2025), which published about 873,000 unvetted eclipsing-binary detections without checking them. Star Vetter is an independent check of a random sample of that list. These are not new detections; they are the entries that survived an independent check. This page says how often that check finds a real binary, misses one, or is fooled.</p>
        </div>
      </header>

      {!a ? (
        <p className="border-t border-line py-10 text-sm text-faint">The audit has not been published yet.</p>
      ) : (
        <>
          <Band num="I" title="The funnel" lede={`A seeded random sample of ${n0(a.frame.sampled)} stars (${pc(a.frame.sampled_fraction, 1)} of the list), re-weighted by brightness.`}>
            <div className="space-y-4">
              {a.funnel.map((step, i) => (
                <div key={step.key}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-4 text-sm">
                    <span className="text-muted">{step.label}</span>
                    <span className="font-mono text-fg"><CountUp value={step.count} /></span>
                  </div>
                  <Bar value={step.count} max={funnelMax} i={i} />
                </div>
              ))}
            </div>
            <div className="mt-8 font-display text-5xl leading-none text-fg"><CountUp value={100 * a.rates.on_target_per_usable.median} decimals={2} suffix="%" /> <span className="text-xl text-muted">(95% interval {pc(a.rates.on_target_per_usable.lo, 2)} to {pc(a.rates.on_target_per_usable.hi, 2)})</span></div>
            <div className="mt-2 font-mono text-[11px] text-muted">of stars with a usable light curve are confirmed on-target, 95% interval</div>
            <p className="mt-5 max-w-3xl text-sm leading-relaxed text-muted">This is the rate at which <em>this pipeline</em> recovers a binary, not the share of the list that is real. It is a lower bound: the pipeline misses most binaries (section III), the pixel check only ran on stars with no catalog match, and stars with no usable light curve ({pc(1 - a.rates.usable_per_sampled.median, 0)} of the sample) cannot be assessed at all.</p>
            {a.provisional_correction && (
              <p className="mt-4 max-w-3xl border-l-2 border-accent/40 pl-4 text-sm leading-relaxed text-muted">
                <span className="text-fg">Provisional correction: {mi(a.provisional_correction.value, 0)}</span> using the recall on {a.recall.usable} known binaries ({pc(a.recall.given_usable.rate ?? 0, 0)}). {a.provisional_correction.with_injection_recall && (<>Using the recall on injected binaries instead ({pc(a.provisional_correction.with_injection_recall.recall.rate ?? 0, 0)}) gives {mi(a.provisional_correction.with_injection_recall.value, 0)}; the two recall estimates {a.provisional_correction.with_injection_recall.consistent_with_benchmark ? "agree within their intervals" : "disagree"}. </>)}{a.provisional_correction.with_quiet_host_recall && (<>Injecting into the quietest quarter of host stars raises recall to {pc(a.provisional_correction.with_quiet_host_recall.recall.rate ?? 0, 0)} and lowers the corrected rate to {mi(a.provisional_correction.with_quiet_host_recall.value, 0)}, so the rate depends on how noisy the stars are. </>)}{a.provisional_correction.assumption}
              </p>
            )}
          </Band>

          <Band num="II" title="Brightness" lede="Fainter stars give fewer on-target candidates, partly because fewer have usable light curves and partly because signals are weaker.">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[34rem] border-collapse font-mono text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-faint">
                    <th className="py-2 pr-4 font-normal">Brightness (Tmag)</th>
                    <th className="py-2 pr-4 text-right font-normal">Sampled</th>
                    <th className="py-2 pr-4 text-right font-normal">Usable</th>
                    <th className="py-2 pr-4 text-right font-normal">Passed gates</th>
                    <th className="py-2 pr-4 text-right font-normal">On-target</th>
                    <th className="py-2 text-right font-normal">On-target per usable</th>
                  </tr>
                </thead>
                <tbody>
                  {a.strata.map((s) => (
                    <tr key={s.stratum} className="border-b border-line text-fg">
                      <td className="py-2 pr-4 text-muted">{s.label.replace("Tmag ", "")}</td>
                      <td className="py-2 pr-4 text-right">{n0(s.sampled)}</td>
                      <td className="py-2 pr-4 text-right">{n0(s.usable)}</td>
                      <td className="py-2 pr-4 text-right">{n0(s.passed_gates)}</td>
                      <td className="py-2 pr-4 text-right">{n0(s.on_target)}</td>
                      <td className="py-2 text-right">{ci(s.on_target_per_usable, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Band>
        </>
      )}

      {r && (
        <Band num="III" title="What it misses" lede={`${n0(r.counts.injections)} artificial binaries were added to real light curves of ${r.counts.stars} sampled stars, then run through the real gates.`}>
          <div className="font-display text-5xl leading-none text-fg"><CountUp value={100 * (r.recall_overall.detected.rate ?? 0)} suffix="%" /></div>
          <div className="mt-2 font-mono text-[11px] text-muted">of injected binaries that the search range could reach got through ({r.recall_overall.detected.k} of {r.recall_overall.n}; 95% {pc(r.recall_overall.detected.lo, 0)} to {pc(r.recall_overall.detected.hi, 0)})</div>
          <p className="mt-5 max-w-3xl text-sm leading-relaxed text-muted">How often a binary is found depends heavily on how deep its eclipses are and how often they are seen, so compare the bins below instead of quoting one number. The figure depends on the mix of periods and depths that was injected.</p>
          <div className="mt-8 grid gap-10 md:grid-cols-2">
            <div>
              <h3 className="nav-caps font-mono text-[11px] text-accent">By eclipse depth</h3>
              <div className="mt-3"><RecallRows rows={r.recall_by_depth} label={(c) => c.bin ?? ""} /></div>
            </div>
            <div>
              <h3 className="nav-caps font-mono text-[11px] text-accent">By orbital period</h3>
              <div className="mt-3"><RecallRows rows={r.recall_by_period} label={(c) => c.bin ?? ""} /></div>
            </div>
            {r.recall_by_points_per_eclipse.length > 0 && (
              <div>
                <h3 className="nav-caps font-mono text-[11px] text-accent">By measurements per eclipse</h3>
                <div className="mt-3"><RecallRows rows={r.recall_by_points_per_eclipse} label={(c) => `${c.bin ?? ""} points`} /></div>
              </div>
            )}
            <div>
              <h3 className="nav-caps font-mono text-[11px] text-accent">Why the misses were missed</h3>
              <p className="mt-1 text-[11px] text-faint">A miss can trip more than one gate.</p>
              <dl className="mt-3 space-y-1.5 font-mono text-xs">
                {r.miss_reasons.filter((m) => m.missed_flagged.k > 0).sort((x, y) => y.missed_flagged.k - x.missed_flagged.k).map((m) => (
                  <div key={m.gate} className="flex justify-between gap-3 border-b border-line pb-1">
                    <dt className="text-muted">{GATE_LABEL[m.gate] ?? m.gate}</dt>
                    <dd className="text-fg">{pc(m.missed_flagged.rate, 0)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
          <p className="mt-8 max-w-3xl text-sm leading-relaxed text-muted">
            <span className="text-fg">False alarms.</span> The same light curves were cut into one-day chunks and shuffled, which keeps the real noise but destroys any periodic signal. {r.false_alarm_shuffle.k} of {r.false_alarm_shuffle.n} shuffled copies ({pc(r.false_alarm_shuffle.rate, 1)}) still got through the gates, so a small share of passes is noise rather than eclipses. Passes with an unrelated period were {pc(r.passed_with_unrelated_period.rate, 1)} of injections.
          </p>
          <ul className="mt-6 max-w-3xl list-disc space-y-1.5 pl-5 text-xs leading-relaxed text-faint">
            <li>Based on {r.counts.stars} stars, mostly 30-minute full-frame light curves; the bins hold few injections each, so the intervals are wide.</li>
            {r.missed_on_host_signal && r.missed_on_host_signal.n > 0 && (
              <li>The host stars were chosen because they fail the gates unaided, so they lean toward noisy or variable stars. In {r.missed_on_host_signal.k} of {r.missed_on_host_signal.n} misses ({pc(r.missed_on_host_signal.rate, 0)}) the search locked onto a signal the star already had, so recall on quiet stars is probably higher.</li>
            )}
            <li>The artificial eclipses were added after the survey&apos;s flattening step, so real eclipses are probably recovered less often than shown.</li>
            <li>Not tested: the pixel check, eccentric orbits, limb-darkened eclipse shapes, and periods beyond half the data span ({pc(1 - (r.searchable_fraction.rate ?? 0), 0)} of injections).</li>
          </ul>
        </Band>
      )}

      {al && (
        <Band num="IV" title="Old catalog periods" lede="Some candidates sit on an ATLAS variable with a different period. Is the ATLAS period just an alias?">
          <div className="font-display text-5xl leading-none text-fg"><CountUp value={al.explained.k} /> <span className="text-3xl text-muted">of {al.tested}</span></div>
          <div className="mt-2 font-mono text-[11px] text-muted">disagreeing periods are explained by a harmonic or sidereal-day alias; chance alone gives about {al.chance.expected_explained.toFixed(1)}</div>
          <p className="mt-5 max-w-3xl text-sm leading-relaxed text-muted">ATLAS marks {al.atlas_class_of_tested["dubious"] ?? 0} of these as &quot;dubious&quot;, which means the variability itself may not be real, and its detached-binary periods are often wrong. Aliases account for a few more stars than luck would, so a handful of the disagreements are probably ATLAS period errors. The remaining {al.tested - al.explained.k} are not explained by aliasing, and TESS does not show that ATLAS is wrong for them. The honest claim is only that TESS establishes a period for stars whose ATLAS detection was low-significance.</p>
        </Band>
      )}

      {nb && nbSum && (
        <Band num="V" title="Neighbouring stars" lede="TESS pixels are 21 arcseconds wide, so a nearby star can be the true source of an eclipse.">
          <div className="grid gap-6 sm:grid-cols-3">
            {(["NO_VIABLE_NEIGHBOUR", "UNSEPARABLE_NEIGHBOUR", "VIABLE_NEIGHBOUR_AT_OFFSET"] as const).map((k) => (
              <div key={k}>
                <div className="font-display text-5xl leading-none text-fg"><CountUp value={nbSum[k] ?? 0} /></div>
                <div className="mt-2 text-sm leading-relaxed text-muted">{nb.statuses[k]}</div>
              </div>
            ))}
          </div>
          <p className="mt-6 max-w-3xl text-sm leading-relaxed text-muted">A neighbour counts only if it is bright enough to produce the eclipse after allowing for how little of its light reaches the aperture, <em>and</em> sits where the measured centre of the dimming is. The tolerance on that centre is an assumption ({headline} arcseconds here; {nb.method.centroid_floors_arcsec.join(", ")} give {nb.method.centroid_floors_arcsec.map((f) => nb.summary_by_floor[String(f)]?.NO_VIABLE_NEIGHBOUR ?? 0).join(", ")} stars with no viable neighbour). Only stars in the TESS Input Catalog are considered. TESS cannot rule out a neighbour inside that tolerance; ground-based imaging can.</p>
        </Band>
      )}

      {ev && zt && gx && pa && (
        <Band num="VI" title="Independent evidence" lede="Every earlier check used TESS pixels this pipeline processed. These use other telescopes and other measurements.">
          <div className="grid gap-6 sm:grid-cols-4">
            {TIERS.map(([k, label]) => (
              <div key={k}>
                <div className="font-display text-5xl leading-none text-fg"><CountUp value={ev.summary.by_evidence_tier[k] ?? 0} /></div>
                <div className="mt-2 font-mono text-[11px] text-fg">{label}</div>
                <div className="mt-1 text-xs leading-relaxed text-muted">{ev.definitions[k]}</div>
              </div>
            ))}
          </div>

          <div className="mt-10 grid gap-8 lg:grid-cols-2">
            <div>
              <h3 className="nav-caps font-mono text-[11px] text-accent">ZTF: did another telescope see the eclipses?</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{zt.summary.stars - (zt.summary.by_status.NO_DATA ?? 0)} of {zt.summary.stars} stars have enough ZTF data (it does not cover most of the far south). For each, the search ran on ZTF alone around the TESS period, was compared with {zt.method.null.split(" ")[0]} control periods, and was tested for power by injecting an eclipse of the TESS depth. Of the {zt.summary.testable} stars where ZTF could have seen the eclipse, <span className="text-fg">{zt.summary.confirmed_among_testable.k} were confirmed</span>, {ci(zt.summary.confirmed_among_testable, 0)}, and {zt.summary.testable - zt.summary.confirmed_among_testable.k} were not seen. {zt.summary.by_status.INCONCLUSIVE ?? 0} more were too faint or sparse in ZTF to tell either way.</p>
              <p className="mt-2 text-xs leading-relaxed text-faint">That confirmed share is a direct estimate for the testable survivors only. ZTF can only test the brighter, deeper-eclipse stars, so it is not a rate for all {zt.summary.stars}.</p>
            </div>
            <div>
              <h3 className="nav-caps font-mono text-[11px] text-accent">Gaia DR3: a second measurement</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{gx.summary.in_gaia_nss_orbit} stars have a Gaia two-body orbit. Where its period equals the TESS period (or half or double it) that is a radial-velocity measurement agreeing with the photometry, and it also means the star was already known to be a binary. {gx.summary.ruwe_elevated} of {gx.summary.matched + gx.summary.ambiguous} have a Gaia RUWE above 1.4, which hints at an unresolved companion. Repeating the neighbour test with Gaia gives {gx.summary.contamination_status_gaia.NO_VIABLE_NEIGHBOUR ?? 0} stars with no viable neighbour, close to the TESS Input Catalog answer.</p>
              {dr4 && <p className="mt-2 text-xs leading-relaxed text-faint">Gaia DR4 (2 December 2026) covers the whole sky, but a fixed-ephemeris test needs an ephemeris good enough to carry back to 2014 to 2020; only {dr4.testable} of {dr4.stars_with_precise_ephemeris} stars with a precise timing fit qualify.</p>}
            </div>
          </div>

          <div className="mt-10">
            <h3 className="nav-caps font-mono text-[11px] text-accent">What is already known</h3>
            <div className="mt-3 grid gap-6 sm:grid-cols-4">
              {NOVELTY.map(([k, label]) => (
                <div key={k}>
                  <div className="font-display text-4xl leading-none text-fg"><CountUp value={ev.summary.by_novelty[k] ?? 0} /></div>
                  <div className="mt-2 font-mono text-[11px] text-fg">{label}</div>
                </div>
              ))}
            </div>
            <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted">{pa.note} Sources checked: {pa.sources.filter((s) => s.status === "CHECKED").map((s) => s.name).join("; ")}. {pa.sources.some((s) => s.status === "NOT_CHECKED") ? `Not checked: ${pa.sources.filter((s) => s.status === "NOT_CHECKED").map((s) => `${s.name} (${s.reason})`).join("; ")}.` : ""}</p>
          </div>
        </Band>
      )}
    </main>
  );
}
