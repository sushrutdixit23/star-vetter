import Link from "next/link";
import { getFindings, getGaiaDr4Plan } from "@/lib/data";
import { getPhysicsFigures } from "@/lib/physics";
import type { StudioStar } from "@/lib/physicsTypes";
import OrbitStudio from "@/components/physics/OrbitStudio";
import PopulationPlot from "@/components/physics/PopulationPlot";
import Countdown from "@/components/physics/Countdown";
import ScrollX from "@/components/physics/ScrollX";
import { EccPeriodPlot, EccentricityDumbbell, MassStrip, ValidationFigure } from "@/components/physics/Figures";
import type { EccPoint } from "@/components/physics/Figures";

export const metadata = {
  title: "Physics - Star Vetter",
  description:
    "A physical eclipse model fitted to the survivor light curves: sizes, tilts and orbit shapes for 17 candidates, tested against a published system and against Gaia, with the limits stated.",
};

const DEFAULT_TIC = 370553309;

function median(v: number[]): number {
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function H2({ id, children }: { id?: string; children: React.ReactNode }) {
  return <h2 id={id} className="scroll-mt-24 font-display text-3xl leading-tight text-fg sm:text-4xl">{children}</h2>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 max-w-3xl text-[15px] leading-relaxed text-muted">{children}</p>;
}

// A text rail on the left and the figure it describes on the right; stacked below the xl breakpoint.
function Split({ left, children }: { left: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] xl:gap-14">
      <div>{left}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const word = (n: number) => (n >= 0 && n < WORDS.length ? WORDS[n] : String(n));
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

export default function PhysicsPage() {
  const f = getFindings();
  const figs = getPhysicsFigures();
  const plan = getGaiaDr4Plan();

  if (!f || !f.physical || !f.physical.spectroscopy || !figs) {
    return (
      <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
        <h1 className="font-display text-4xl text-fg">Physics.</h1>
        <p className="mt-4 text-sm text-faint">Run export_findings.py and export_physics.py to populate this page.</p>
      </main>
    );
  }

  const phys = f.physical;
  const spec = f.physical.spectroscopy;
  const fits = new Map(phys.fits.filter((x) => x.status === "OK").map((x) => [x.tic, x]));
  const orbitBy = new Map(spec.gaia_orbits.map((o) => [o.tic, o]));
  const rvBy = new Map(figs.rv_population.map((r) => [r.tic, r]));
  const eccBy = new Map(spec.e_check_vs_gaia.map((r) => [r.tic, r]));

  const studioStars: StudioStar[] = Object.values(figs.stars)
    .filter((c) => fits.has(c.tic))
    .map((c) => {
      const o = orbitBy.get(c.tic);
      const r = rvBy.get(c.tic);
      const e = eccBy.get(c.tic);
      return {
        tic: c.tic,
        curve: c,
        fit: fits.get(c.tic)!,
        gaia: o ? { type: o.type, period_days: o.gaia_period_days, period_ratio: o.period_ratio, same_period: o.same_period, outer: o.outer_orbit, k1_kms: o.gaia_k1_kms } : null,
        rv: r ? { verdict: r.verdict, range_kms: r.rv_range_kms, n_transits: r.n_transits } : null,
        ecc_check: e ? { gaia_e: e.gaia_e, gaia_e_sigma: e.gaia_e_sigma, fit_e: e.fit_e, diff_sigma: e.difference_sigma, trusted: e.trusted } : null,
      };
    });
  const initial = studioStars.some((s) => s.tic === DEFAULT_TIC) ? DEFAULT_TIC : studioStars[0]?.tic;

  const nFits = studioStars.length;
  const trusted = studioStars.filter((s) => s.fit.e_reliable);
  const eccentric = trusted.filter((s) => (s.fit.e?.median ?? 0) > 0.03);
  const eMin = Math.min(...eccentric.map((s) => s.fit.e!.median));
  const eMax = Math.max(...eccentric.map((s) => s.fit.e!.median));
  const nConverged = studioStars.filter((s) => s.fit.converged).length;
  const sameP = spec.gaia_orbits.filter((o) => o.same_period);
  const outer = spec.gaia_orbits.filter((o) => o.outer_orbit);
  const ai = figs.ai_phe;
  const aiDepthPpt = (1 - ai.min_flux) * 1000;
  const aiMaxRes = Math.max(...ai.residual.map((r) => Math.abs(r))) * 1000;
  const massMedian = figs.mass_check_points.length ? median(figs.mass_check_points.map((m) => m.ratio)) : null;
  const massOk = figs.mass_check_points.filter((m) => m.consistent).length;
  const blend = figs.rv_population.filter((r) => r.verdict === "blend_indicated");
  const rvMoves = figs.rv_population.filter((r) => r.verdict === "moves").length;
  const massRatios = figs.mass_check_points.map((m) => m.ratio);
  const eccPoints: EccPoint[] = studioStars.map((st) => ({
    tic: st.tic,
    period: st.curve.period_days,
    e: st.fit.e?.median ?? 0,
    lo: st.fit.e?.lo ?? 0,
    hi: st.fit.e?.hi ?? 0,
    trusted: !!st.fit.e_reliable,
    lower: Math.abs(st.fit.ecosw?.median ?? 0),
  }));
  const refit = ai.published_refit;
  const tripleFit = fits.get(264099112);
  const ltte = f.timing_drift?.ltte?.[0];
  const e23 = fits.get(237115819);

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="max-w-4xl pb-8">
        <h1 className="font-display text-5xl leading-[1.02] text-fg sm:text-6xl">From a dip in brightness to an orbit.</h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted">
          Every star on this site started as a periodic dip in a TESS light curve. A physical model turns the dip into geometry: how large each star is
          against its orbit, how tilted the orbit is, how stretched. The model was built against one published system and then run on the candidates.
          Choose a star below and watch its eclipses happen.
        </p>
        <p className="mt-5 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-muted">
          <span>{nFits} candidates fitted</span>
          <span>{trusted.length} orbit shapes pass the trust rules</span>
          <span>{sameP.length} with a Gaia orbit at the same period</span>
          <span>0 masses</span>
        </p>
      </header>

      <section id="studio" className="scroll-mt-24">
        {initial !== undefined ? <OrbitStudio stars={studioStars} initialTic={initial} /> : null}
        <p className="mt-5 max-w-3xl text-xs leading-relaxed text-faint">
          How to read it. The top panel is the system as Earth sees it, drawn to scale: star 2&apos;s projected path and both discs. Below it are the two
          eclipses. Dots are binned TESS measurements with one-sigma bars, the blue line is the model, and the grey dots are what the model misses, in parts
          per thousand. The amber marker is where the orbit is now. Both stars are fitted as spheres with quadratic limb darkening; colours are schematic.
          With no velocities there is no mass ratio, so star 2 moves around star 1 and the centre of mass is not drawn.
        </p>
      </section>

      <section id="fits" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <Split
          left={
            <>
              <H2>What the fits say</H2>
              <P>
                {trusted.length} of the {nFits} orbit shapes pass three rules set before looking at the results: the stars are not so close that spheres misjudge the eclipse durations
                (r1 + r2 at most 0.25), the secondary eclipse is strong enough to measure on its own, and two routes to e cos &omega; agree. {cap(word(eccentric.length))} are eccentric, with e from {eMin.toFixed(2)} to {eMax.toFixed(2)};{" "}
                {word(trusted.length - eccentric.length)} are consistent with circular.
              </P>
              <P>
                For the other {nFits - trusted.length} the full eccentricity is not trusted, but e cos &omega; still sets a floor: the triangles show |e cos &omega;|, and the true e is at least that.
              </P>
              <P>
                Only {nConverged} of the {nFits} sampler chains ran long enough to meet the usual convergence test, so uncertainties are marked indicative. Third light is mostly set by its prior rather than by the data, and is
                marked wherever that is true.
              </P>
            </>
          }
        >
          <div className="max-w-3xl rounded-xl border border-line bg-panel p-4">
            <ScrollX min={560}><EccPeriodPlot points={eccPoints} /></ScrollX>
            <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-faint">
              <span><span aria-hidden="true" className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-accent align-middle" />eccentricity passes the trust rules (68% interval)</span>
              <span>&#9651; lower limit from e cos &omega;</span>
            </p>
          </div>
        </Split>
      </section>

      <section id="validation" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <H2>Before trusting it: AI Phoenicis</H2>
        <P>
          AI Phe is a well-studied eclipsing binary whose sizes and orbit are known from spectroscopy plus light curves (Maxted et al. 2020, MNRAS 498, 332). The pipeline was run on its TESS light curve and compared with the
          published solution. The allowed differences are written in f26_ebfit.py. All five checks pass at 2-minute cadence
          {ai.cadence30?.passed ? ", and again with the data degraded to 30-minute cadence, the cadence of TESS full-frame images." : "."}
        </P>
        <P>
          This is a calibration, not a blind test. Several choices in the method (per-eclipse detrending, a prior on third light, a fitted period correction) were added after early runs missed AI Phe&apos;s published values. It shows
          the method can reach a known answer; the Gaia comparison below is the nearest thing to an independent test.
        </P>
        <div className="mt-6">
          <ValidationFigure ai={ai} />
        </div>
        <P>
          {refit
            ? `As a second check, the geometry was held at the published values and only the surface-brightness ratio, third light, limb darkening and timing were refitted (dashed). It leaves ${refit.rms_resid_ppt.toFixed(1)} ppt rms against ${ai.rms_resid_ppt.toFixed(1)} ppt for our own fit, and a chi-square ${Math.abs((refit.chi2 / refit.chi2_ours - 1) * 100).toFixed(0)}% ${refit.chi2 >= refit.chi2_ours ? "higher" : "lower"} over ${refit.n_bins} points: the two solutions describe the same eclipses. `
            : ""}
          The largest binned residual of our fit is {aiMaxRes.toFixed(0)} ppt, {((aiMaxRes / aiDepthPpt) * 100).toFixed(1)}% of the primary eclipse depth, on the eclipse ingress and egress. One system tests the machinery; it does not guarantee every
          candidate, which are fainter, mostly have fewer eclipses, and in some cases are close pairs that spheres describe poorly.
        </P>
      </section>

      <section id="gaia" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <H2>Checked by another instrument: Gaia</H2>
        <P>
          Gaia measured the bright star&apos;s velocity for some survivors, and for a few it fitted a spectroscopic orbit. Those numbers come from a different telescope, method and team, so they are the closest thing to an outside check
          available without new observations.
        </P>

        <div className="mt-10 border-t border-line pt-8">
          <Split
            left={
              <>
                <h3 className="font-display text-2xl text-fg">The eclipses belong to the bright star</h3>
                <P>
                  {cap(word(sameP.length))} survivors have a Gaia spectroscopic orbit whose period matches the TESS eclipse period to within {(Math.max(...sameP.map((o) => Math.abs(o.period_ratio - 1))) * 100).toFixed(2)}%. A bright
                  star that orbits with the eclipse period carries the eclipses itself, which rules out a faint eclipsing binary sitting next to a bright star.
                </P>
              </>
            }
          >
            <div className="max-w-2xl overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[460px] text-left text-sm">
                <thead className="nav-caps font-mono text-[11px] text-muted">
                  <tr><th className="p-3">Star</th><th className="p-3">Gaia period (d)</th><th className="p-3">Gaia / TESS</th><th className="p-3">Gaia K1 (km/s)</th></tr>
                </thead>
                <tbody>
                  {sameP.map((o) => (
                    <tr key={o.tic} className="border-t border-line">
                      <td className="p-3"><Link className="text-fg underline" href={`/candidates/${o.tic}`}>TIC {o.tic}</Link></td>
                      <td className="p-3 font-mono">{o.gaia_period_days.toFixed(4)}</td>
                      <td className="p-3 font-mono">{o.period_ratio.toFixed(4)}</td>
                      <td className="p-3 font-mono">{o.gaia_k1_kms !== null ? o.gaia_k1_kms.toFixed(1) : "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Split>
        </div>

        <div className="mt-10 border-t border-line pt-8">
          <Split
            left={
              <>
                <h3 className="font-display text-2xl text-fg">Eccentricity against Gaia&apos;s</h3>
                <P>
                  Three stars have both a light-curve eccentricity and a Gaia one. Where our value passes the trust rules the two agree within about two sigma. For TIC 43785616 they do not, and our fit fails the rule there because its
                  secondary eclipse is too weak to measure alone. That disagreement is what led to adding the rule, so it is not an independent test of it. Two stars is a spot check, not a calibration.
                </P>
              </>
            }
          >
            <div className="max-w-3xl rounded-xl border border-line bg-panel p-4">
              <ScrollX min={600}><EccentricityDumbbell rows={spec.e_check_vs_gaia} /></ScrollX>
              <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-faint">
                <span><span aria-hidden="true" className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-accent align-middle" />this light-curve fit, filled when trusted</span>
                <span><span aria-hidden="true" className="mr-2 inline-block h-2.5 w-2.5 rotate-45 bg-accent-cool align-middle" />Gaia orbit</span>
              </p>
            </div>
          </Split>
        </div>

        <div className="mt-10 border-t border-line pt-8">
          <Split
            left={
              <>
                <h3 className="font-display text-2xl text-fg">Does the bright star move?</h3>
                <P>
                  For {figs.rv_population.length} survivors Gaia published the range of the bright star&apos;s velocities. In {rvMoves} it clearly moves, so the eclipse is on the target.
                  {blend.length === 1 ? ` One, TIC ${blend[0].tic}, has a ${blend[0].depth_pct.toFixed(1)}% eclipse while its bright star stays within a few km/s: the eclipse very probably belongs to another star in the aperture.` : ""} The rest are
                  not conclusive: a shallow eclipse, near-equal stars whose lines blend, or too few Gaia transits. Hover a point for its numbers and click to open the star.
                </P>
              </>
            }
          >
            <div className="max-w-4xl rounded-xl border border-line bg-panel p-4">
              <ScrollX min={620}><PopulationPlot points={figs.rv_population} /></ScrollX>
            </div>
          </Split>
        </div>
      </section>

      <section id="cases" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <Split
          left={
            <>
              <H2>Where the model disagrees with the simple story</H2>
              <P>A good fit is most useful where it fails to match the obvious picture. These are the cases worth follow-up; none is established.</P>
            </>
          }
        >
          <dl className="max-w-3xl divide-y divide-line border-y border-line">
            {tripleFit ? (
              <div className="grid gap-1 py-5 sm:grid-cols-[11rem_1fr] sm:gap-6">
                <dt><Link className="font-mono text-sm text-fg underline" href="/candidates/264099112">TIC 264099112</Link></dt>
                <dd className="text-sm leading-relaxed text-muted">
                  The fit needs about {Math.round((tripleFit.l3?.median ?? 0) * 100)}% of the light in the aperture to come from a third source, and the data constrain it. No Gaia neighbour near the target is bright enough to supply it.
                  An unresolved third star is the simplest reading; a contaminated aperture is the other. A spectrum or a higher-resolution image would settle it.
                </dd>
              </div>
            ) : null}
            {ltte && e23 ? (
              <div className="grid gap-1 py-5 sm:grid-cols-[11rem_1fr] sm:gap-6">
                <dt><Link className="font-mono text-sm text-fg underline" href="/candidates/237115819">TIC 237115819</Link></dt>
                <dd className="text-sm leading-relaxed text-muted">
                  The period-change candidate. The orbit is circular (e = {e23.e?.median.toFixed(4)}), so there is no apsidal motion to blame. If light travel across a wider orbit explains the timing, a third body would need an orbit of{" "}
                  {ltte.allowed_p3_years[0].toFixed(0)} to {ltte.allowed_p3_years[1].toFixed(0)} years and a minimum mass of {ltte.m3_min_msun_range[0].toFixed(2)} to {ltte.m3_min_msun_range[1].toFixed(1)} solar masses. The fitted third light
                  ({e23.l3_p97_5 != null ? `at most ${e23.l3_p97_5.toFixed(2)} at the 97.5th percentile` : "small"}) disfavours a main-sequence third star near the top of that range; a low-mass or compact companion is not excluded. Its predicted eclipse times are frozen on the{" "}
                  <Link className="text-fg underline" href="/predictions">predictions</Link> page.
                </dd>
              </div>
            ) : null}
            {blend.map((b) => (
              <div key={b.tic} className="grid gap-1 py-5 sm:grid-cols-[11rem_1fr] sm:gap-6">
                <dt><Link className="font-mono text-sm text-fg underline" href={`/candidates/${b.tic}`}>TIC {b.tic}</Link></dt>
                <dd className="text-sm leading-relaxed text-muted">
                  A {b.depth_pct.toFixed(1)}% eclipse, but Gaia sees the bright star move by only {b.rv_range_kms.toFixed(0)} km/s over {b.n_transits} transits. A real eclipsing companion large enough to dim the star by that much would
                  pull it harder. Likely a blend; it stays on the list marked as such.
                </dd>
              </div>
            ))}
            {outer.length > 0 ? (
              <div className="grid gap-1 py-5 sm:grid-cols-[11rem_1fr] sm:gap-6">
                <dt className="font-mono text-sm text-fg">{outer.map((o) => `TIC ${o.tic}`).join(", ")}</dt>
                <dd className="text-sm leading-relaxed text-muted">
                  Gaia holds orbits of {outer.map((o) => `${o.gaia_period_days.toFixed(0)} days`).join(" and ")} for the bright star, hundreds of times longer than the eclipse period: candidate third bodies. Gaia solutions like these are
                  sometimes artefacts of a variable star, so they are unverified.
                </dd>
              </div>
            ) : null}
          </dl>
        </Split>
      </section>

      <section id="masses" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <Split
          left={
            <>
              <H2>What it cannot do: masses</H2>
              <P>
                Sizes as fractions of the orbit, combined with a physical radius from Gaia, give a total mass through Kepler&apos;s third law. That worked as an idea and failed as a measurement. Against the mass that main-sequence stars of the
                same size and brightness would have, the results scatter in both directions, from {massRatios.length ? Math.min(...massRatios).toFixed(1) : "n/a"} to {massRatios.length ? Math.max(...massRatios).toFixed(1) : "n/a"} times, with a median of {massMedian ? massMedian.toFixed(2) : "n/a"}, and only {massOk} of{" "}
                {figs.mass_check_points.length} are consistent.
              </P>
              <P>
                Part of the cause is likely that Gaia&apos;s radius treats two stars as one, which inflates it. So no masses are reported. Real masses need velocities of both stars, from double-lined spectra. TIC 370553309, 59490510 and 264099112 are the most useful first
                targets.
              </P>
            </>
          }
        >
          <div className="max-w-3xl rounded-xl border border-line bg-panel p-4">
            <ScrollX min={620}><MassStrip points={figs.mass_check_points} /></ScrollX>
            <p className="mt-2 text-xs text-faint">Bars: the 10% systematic on the fractional radius plus the radius error. Filled: consistent with main-sequence stars; hollow: not.</p>
          </div>
        </Split>
      </section>

      <section id="next" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <div className="grid gap-8 lg:grid-cols-[14rem_1fr] lg:gap-12">
          <Countdown iso="2026-12-02T00:00:00Z" label="Gaia DR4" />
          <div>
            <H2>The next test is already written down</H2>
            <P>
              Gaia DR4 is due on 2 December 2026, with per-epoch photometry and velocities for the whole sky. The decision rules were fixed before the data exist. For the
              velocity test: fit a sinusoid at the TESS period to each star&apos;s epoch velocities; a chi-square gain of 30 or more counts as the star moving, 6 or less as static. For the
              photometry test: fold Gaia&apos;s epochs on the frozen ephemeris and ask whether the eclipse is there.{" "}
              {plan ? `Only ${plan.testable} of ${plan.stars_with_precise_ephemeris} stars with precise ephemerides are testable by photometry, so the velocity test carries most of the weight.` : ""}
            </P>
            <P>Whatever comes back gets published as it is, including a failed prediction. The steps are in docs/gaia_dr4_release_day.md.</P>
          </div>
        </div>
      </section>

      <section id="method" className="mt-16 scroll-mt-24 border-t border-line pt-10">
        <H2>How it works, and where it stops</H2>
        <div className="mt-6 grid gap-10 lg:grid-cols-2">
          <div>
            <h3 className="font-display text-xl text-fg">The model</h3>
            <ul className="mt-3 max-w-xl list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">
              <li>ellc detached-binary light curves with emcee sampling: sizes, inclination, surface-brightness ratio, e cos &omega; and e sin &omega;, third light, limb darkening.</li>
              <li>Each eclipse divided by a quadratic fitted outside it; eclipses without a baseline on both sides are dropped.</li>
              <li>Exposure smearing per cadence, a free flux level per group of sectors, and a fitted noise scale.</li>
              <li>Quadratic limb darkening, u1 fitted with a prior of 0.40 &plusmn; 0.10 and u2 fixed at 0.22. Third light has a half-normal prior of width 0.10.</li>
              <li>The eccentricity shown is full only when it passes the trust rules above; otherwise e cos &omega; alone.</li>
            </ul>
          </div>
          <div>
            <h3 className="font-display text-xl text-fg">What it does not do</h3>
            <ul className="mt-3 max-w-xl list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">
              <li>No masses, and no true radii in solar units: radii are fractions of the orbit.</li>
              <li>Spheres only, so close pairs (r1 + r2 above 0.25) give an e cos &omega; and no more.</li>
              <li>{nFits} of {phys.fits.length} attempted fits produced a result; the other had too few eclipses with a clean baseline.</li>
              <li>{nFits - nConverged} of {nFits} chains are shorter than 20 autocorrelation times.</li>
              <li>One validation system, and two stars checked against Gaia&apos;s eccentricity.</li>
              <li>Everything here is a candidate or a lower limit until spectra say otherwise.</li>
            </ul>
          </div>
        </div>
        <p className="mt-8 max-w-3xl text-sm leading-relaxed text-muted">
          To rerun it: install requirements-physics.txt (ellc needs a Fortran compiler), then run <code className="font-mono text-fg">py f26_ebfit.py . --validate</code> and <code className="font-mono text-fg">py f26_ebfit.py .</code>.
          The fit results are committed, so reading this page needs none of that. Figures here come from <code className="font-mono text-fg">export_physics.py</code>; its orbit geometry is tested against ellc&apos;s own eclipse timing.
        </p>
      </section>
    </main>
  );
}
