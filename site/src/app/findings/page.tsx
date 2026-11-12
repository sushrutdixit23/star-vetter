import Link from "next/link";
import { getFindings, getPeriodChangePredictions } from "@/lib/data";
import { getPhysicsFigures } from "@/lib/physics";

export const metadata = {
  title: "Findings - Star Vetter",
  description:
    "What the survivor light curves show beyond detection: eccentric-orbit candidates, a tidal-circularisation check, and one eclipse-timing period-change candidate with frozen predictions.",
};

function bjdToDate(bjd: number): string {
  // BJD 2440587.5 = 1970-01-01 00:00 UTC (time-scale offsets of about a minute are ignored here)
  return new Date((bjd - 2440587.5) * 86400000).toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

const COVERAGE: Record<string, string> = {
  no_file: "no ZTF data",
  insufficient_points: "too few ZTF points",
  error: "error",
};

export default function FindingsPage() {
  const f = getFindings();
  const phys = getPhysicsFigures();
  const injE = phys?.injection?.overall.by_quantity.e;
  const massCal = phys?.mass_calibration?.summary;
  const pc = getPeriodChangePredictions();

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <header className="pb-8">
        <div className="nav-caps font-mono text-[11px] text-muted">Beyond detection</div>
        <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">Findings.</h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
          Two measurements made on the survivor light curves: how far the secondary eclipse sits from phase one half, and
          whether the eclipse times drift. Both are candidates and lower limits, not confirmed physics. Every number on this
          page is generated from the pipeline&apos;s data files.
        </p>
      </header>

      {!f ? (
        <p className="border-t border-line py-10 text-sm text-faint">Run export_findings.py to populate this page.</p>
      ) : (
        <>
          <section className="mb-10">
            <h2 className="font-display text-2xl text-fg">A period-change candidate</h2>
            {f.timing_drift && f.timing_drift.period_change.length > 0 ? (
              <>
                <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                  Eclipse times were measured per TESS sector and per ZTF season with one shared template. The rule that selects a star
                  needs a parabola that fits well, both instruments on the same curve, at least six times, and a plausible amplitude.
                  {f.timing_drift.calibration
                    ? ` On ${f.timing_drift.calibration.trials} synthetic constant-period light curves with the real sampling and noise, ${f.timing_drift.calibration.flagged} were flagged.`
                    : ""}
                </p>
                <div className="mt-4 overflow-x-auto rounded-xl border border-line">
                  <table className="w-full min-w-[640px] text-left text-sm">
                    <thead className="nav-caps font-mono text-[11px] text-muted">
                      <tr>
                        <th className="p-3">Star</th>
                        <th className="p-3">Period (d)</th>
                        <th className="p-3">Times (TESS / ZTF)</th>
                        <th className="p-3">chi2 line</th>
                        <th className="p-3">chi2 parabola</th>
                        <th className="p-3">Period change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.timing_drift.period_change.map((r) => (
                        <tr key={r.tic} className="border-t border-line">
                          <td className="p-3"><Link className="text-fg underline" href={`/candidates/${r.tic}`}>TIC {r.tic}</Link></td>
                          <td className="p-3">{r.period_days.toFixed(4)}</td>
                          <td className="p-3">{r.n_tess} / {r.n_ztf}</td>
                          <td className="p-3">{r.chi2_line.toFixed(0)} ({r.dof_line} dof)</td>
                          <td className="p-3">{r.chi2_parabola.toFixed(1)} ({r.dof_parabola} dof)</td>
                          <td className="p-3">{r.dP_dt_seconds_per_year > 0 ? "+" : ""}{r.dP_dt_seconds_per_year.toFixed(1)} +- {r.dP_dt_sigma_seconds_per_year.toFixed(1)} s/yr</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                  The cause is not settled: a distant third body, mass exchange and other effects all produce a parabola over a few years.
                  No companion has been seen.
                </p>
                {(f.timing_drift.ltte ?? []).map((l) => (
                  <p key={l.tic} className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                    Light-travel-time test for TIC {l.tic} (circular orbit of a distant companion, {l.extra_parameters_vs_parabola} extra
                    parameters over the parabola): the best fit, P3 = {l.best_p3_years.toFixed(1)} yr, gives chi2 {l.best_chi2.toFixed(1)}
                    against {l.chi2_parabola.toFixed(1)} for the parabola, {l.fits_as_well_as_parabola ? "a gain too small to matter for two extra parameters over" : "no better than"} a constant period change.
                    Orbits from {l.statistically_allowed_p3_years[0].toFixed(1)} to {l.statistically_allowed_p3_years[1].toFixed(0)} yr stay allowed;
                    capping the unseen companion at {l.max_plausible_m3_msun} solar masses leaves {l.allowed_p3_years[0].toFixed(1)} to {l.allowed_p3_years[1].toFixed(1)} yr,
                    a light-time amplitude of {l.amplitude_min_range[0].toFixed(0)} to {l.amplitude_min_range[1].toFixed(0)} min and a minimum companion
                    mass of {l.m3_min_msun_range[0].toFixed(2)} to {l.m3_min_msun_range[1].toFixed(2)} solar masses. Orbits shorter than about{" "}
                    {l.statistically_allowed_p3_years[0].toFixed(1)} yr are ruled out. This does not show a third body exists.
                    {(() => {
                      const fit = f.physical?.fits.find((x) => x.tic === l.tic && x.status === "OK");
                      return fit && fit.l3_p97_5 !== undefined
                        ? ` The light-curve model puts any third light below ${fit.l3_p97_5.toFixed(2)} of the TESS flux (95%), so a main-sequence third star near the top of the allowed mass range, which would be about as bright as the pair, is disfavoured; a low-mass or compact companion is not.`
                        : "";
                    })()}
                  </p>
                ))}
                {pc && Object.values(pc.stars).map((s) => (
                  <div key={s.tic} className="mt-5">
                    <div className="nav-caps font-mono text-[11px] text-muted">Predicted eclipses of TIC {s.tic} (frozen file)</div>
                    <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">{pc.rule} The first year of data cannot tell a
                      parabola from a continued straight line, so a match is a check, not proof.</p>
                    <ul className="mt-2 grid gap-x-8 gap-y-1 font-mono text-xs text-muted sm:grid-cols-2 xl:grid-cols-3">
                      {s.predictions.slice(0, 9).map((p) => (
                        <li key={p.epoch}>{bjdToDate(p.bjd_tdb_parabola)} +- {p.sigma_min.toFixed(0)} min</li>
                      ))}
                    </ul>
                    <p className="mt-2 text-xs text-faint">{s.predictions.length} eclipses in the full file, docs/period_change_predictions.json.</p>
                  </div>
                ))}
              </>
            ) : (
              <p className="mt-3 text-sm text-faint">No star passed every rule.</p>
            )}
          </section>

          <section className="mb-10">
            <h2 className="font-display text-2xl text-fg">Eccentric-orbit candidates</h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
              A secondary eclipse displaced from phase one half gives e cos(omega) = (pi/2)(phase - 0.5), a lower limit on the
              eccentricity. A star is listed only if two independent halves of the TESS data each show the dip at the same phase,
              no third dip exists, and no fast periodic signal is present outside the eclipses. Fast pulsators and period multiples
              are rejected automatically. The ZTF column is an independent re-measure of the secondary using a period refit from
              the primary eclipses only.
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="nav-caps font-mono text-[11px] text-muted">
                  <tr>
                    <th className="p-3">Star</th>
                    <th className="p-3">Period (d)</th>
                    <th className="p-3">e cos w</th>
                    <th className="p-3">Secondary SNR</th>
                    <th className="p-3">ZTF re-measure</th>
                    <th className="p-3">Evidence tier</th>
                  </tr>
                </thead>
                <tbody>
                  {f.candidates.map((r) => (
                    <tr key={r.tic} className="border-t border-line">
                      <td className="p-3"><Link className="text-fg underline" href={`/candidates/${r.tic}`}>TIC {r.tic}</Link>{r.marginal ? <span className="text-faint"> (marginal)</span> : null}</td>
                      <td className="p-3">{r.period_days.toFixed(3)}</td>
                      <td className="p-3">{r.ecosw >= 0 ? "+" : ""}{r.ecosw.toFixed(3)} +- {r.ecosw_sigma.toFixed(3)}</td>
                      <td className="p-3">{r.secondary_snr.toFixed(0)}</td>
                      <td className="p-3">
                        {r.ztf_confirmed === null
                          ? COVERAGE[r.ztf_coverage ?? ""] ?? "n/a"
                          : r.ztf_confirmed
                            ? `confirmed (p=${(r.ztf_p_value ?? 0).toFixed(3)})`
                            : "not confirmed"}
                      </td>
                      <td className="p-3 text-xs text-muted">{r.evidence_tier ?? "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mb-10">
            <h2 className="font-display text-2xl text-fg">A physics check, not a result</h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
              Close binaries should be circular. Offsets of |e cos w| of at least {f.circularisation.threshold_ecosw}: {f.circularisation.k_short} of{" "}
              {f.circularisation.n_short} measured systems at 2 days or less, and {f.circularisation.k_longer} of {f.circularisation.n_longer} above 2 days.
              {f.circularisation.chance_of_none_if_same_rate_as_longer !== null
                ? ` If the short systems had the same rate as the longer ones, the chance of seeing none is ${f.circularisation.chance_of_none_if_same_rate_as_longer.toFixed(4)}.`
                : ""}{" "}
              This reproduces known tidal circularisation, which supports the measurement; it is not a new result.
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-left text-sm">
                <thead className="nav-caps font-mono text-[11px] text-muted">
                  <tr><th className="p-3">Period range (d)</th><th className="p-3">Measured</th><th className="p-3">Offset</th></tr>
                </thead>
                <tbody>
                  {f.period_bins.map((b) => (
                    <tr key={b.p_min} className="border-t border-line">
                      <td className="p-3">{b.p_min} to {b.p_max >= 1000 ? "longer" : b.p_max}</td>
                      <td className="p-3">{b.n_measured}</td>
                      <td className="p-3">{b.n_offset}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {f.physical ? (
            <section className="mb-10">
              <h2 className="font-display text-2xl text-fg">Physical model of the light curves</h2>
              <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                A detached-binary model (ellc: spherical stars, quadratic limb darkening, third light with a weak prior) fitted by MCMC to
                the TESS eclipses after each eclipse is detrended on its own. The two eclipse durations give e sin(omega), so the full
                eccentricity is measured here, not only the lower limit from the eclipse spacing. Radii are fractions of the orbit size;
                absolute sizes and masses need spectra.
              </p>
              {f.physical.validation.map((v) => (
                <p key={v.cadence_min} className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                  Validation on {v.star} against {v.reference}, {v.cadence_min}-minute data: e {v.fit.e.toFixed(3)} (published{" "}
                  {v.truth.e}), r1 {v.fit.r1.toFixed(4)} ({v.truth.r1}), r2 {v.fit.r2.toFixed(4)} ({v.truth.r2}), i {v.fit.incl.toFixed(2)} deg
                  ({v.truth.incl}). {v.passed ? "Every pre-set tolerance was met." : `Failed: ${Object.entries(v.checks).filter(([, ok]) => !ok).map(([k]) => k).join(", ")}.`}
                </p>
              ))}
              {f.physical.fits.length > 0 ? (
                <div className="mt-4 overflow-x-auto rounded-xl border border-line">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="nav-caps font-mono text-[11px] text-muted">
                      <tr>
                        <th className="p-3">Star</th>
                        <th className="p-3">Period (d)</th>
                        <th className="p-3">e</th>
                        <th className="p-3">omega (deg)</th>
                        <th className="p-3">i (deg)</th>
                        <th className="p-3">r1 / r2</th>
                        <th className="p-3">Third light</th>
                        <th className="p-3">Total mass (estimate)*</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.physical.fits.map((r) => (
                        <tr key={r.tic} className="border-t border-line">
                          <td className="p-3"><Link className="text-fg underline" href={`/candidates/${r.tic}`}>TIC {r.tic}</Link></td>
                          {r.status !== "OK" || !r.e ? (
                            <td className="p-3 text-faint" colSpan={7}>{r.status}</td>
                          ) : (
                            <>
                              <td className="p-3">{r.period_days?.toFixed(4)}</td>
                              <td className="p-3">
                                {r.e_reliable
                                  ? <>{r.e.median.toFixed(r.e.hi < 0.001 ? 4 : 3)} <span className="text-faint">+{r.e.hi.toFixed(r.e.hi < 0.001 ? 4 : 3)}/-{r.e.lo.toFixed(r.e.hi < 0.001 ? 4 : 3)}</span>{r.converged ? "" : " (chain short)"}</>
                                  : <span className="text-faint">{r.e_note}; e cos w = {r.ecosw?.median.toFixed(3)}</span>}
                              </td>
                              <td className="p-3">{r.e_reliable ? r.omega_deg?.median.toFixed(0) : "n/a"}</td>
                              <td className="p-3">{r.incl_deg?.median.toFixed(2)}</td>
                              <td className="p-3">{r.r1?.median.toFixed(4)} / {r.r2?.median.toFixed(4)}</td>
                              <td className="p-3">{r.l3?.median.toFixed(2)}{r.l3_constrained ? "" : <span className="text-faint"> (prior)</span>}</td>
                              <td className="p-3">
                                {r.total_mass_msun === undefined
                                  ? "n/a"
                                  : r.total_mass_ms_consistent === false
                                    ? <span className="text-faint">inconsistent ({r.total_mass_msun.toFixed(1)} vs {r.total_mass_ms_expected?.toFixed(1)} expected)</span>
                                    : `${r.total_mass_msun.toFixed(2)} +- ${(r.total_mass_rel_sigma! * 100).toFixed(0)}% Msun`}
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              <p className="mt-2 max-w-3xl text-xs text-faint">
                * From Kepler&apos;s third law with the Gaia DR3 radius of the combined light, corrected for the companion&apos;s light,
                including a 10% systematic on the fractional radius. Checked against two main-sequence stars of the implied radius and
                light ratio; when the two differ by more than a factor 1.6 the value is shown as inconsistent rather than used. Third light marked (prior) is not
                constrained by the data. The full e is shown only when the stars are not too close for spheres (r1 + r2 at most 0.25), the
                secondary eclipse was measured independently, and both values of e cos w agree; otherwise only e cos w is given. &quot;Chain short&quot;: fewer than 20 autocorrelation times, so uncertainties are indicative.
                {injE?.coverage_68 != null && injE.coverage_68 < 0.6
                  ? <> In injection tests the 68% intervals shown here held the true e {Math.round(injE.coverage_68 * 100)}% of the time, so read every interval as a minimum (<Link className="underline" href="/physics#injection">details</Link>).</>
                  : null}
                {massCal && massCal.n > 0 && massCal.median_mass_ratio != null && massCal.median_mass_ratio > 1.1
                  ? <> On {massCal.n} published systems the same method gave a median {massCal.median_mass_ratio.toFixed(2)} times the published total mass (<Link className="underline" href="/physics#masses">details</Link>).</>
                  : null}
                {f.physical.mass_check && f.physical.mass_check.n > 0 && f.physical.mass_check.median_ratio !== null
                  ? ` Across ${f.physical.mass_check.n} stars the Kepler masses run a median ${f.physical.mass_check.median_ratio.toFixed(1)} times the expectation (${f.physical.mass_check.n_consistent} consistent), most likely because Gaia's radius of a two-star source is too large: these are not usable as masses, which still need double-lined spectra.`
                  : ""}
              </p>
              {f.physical.spectroscopy ? (
                <>
                  <h3 className="mt-8 font-display text-xl text-fg">Archival spectroscopy</h3>
                  <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                    No new telescope time: Gaia DR3 radial-velocity summaries and orbits, and APOGEE, GALAH, LAMOST and RAVE spectra already
                    in public archives, matched to every survivor. A bright star that moves at the eclipse period carries the eclipses; one that
                    stays still while the eclipse is deep points to light from another star.
                  </p>
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
                    <li>Gaia spectroscopic orbits at the TESS period: {f.physical.spectroscopy.summary.gaia_orbit_same_period}; astrometric orbits far longer than the eclipses (candidate third bodies, which need checking): {f.physical.spectroscopy.summary.gaia_outer_orbit}.</li>
                    <li>Gaia velocity range available for {f.physical.spectroscopy.summary.with_gaia_rv_range} stars; the bright star clearly moves in {f.physical.spectroscopy.summary.gaia_rv_moves}.</li>
                    <li>Bright star static while the companion mass limit is substellar: {f.physical.spectroscopy.summary.gaia_rv_static_blend_indicated} with a deep eclipse (blend indicated), {f.physical.spectroscopy.summary.gaia_rv_static_substellar_or_blend} with a shallow one (blend or substellar companion), {f.physical.spectroscopy.summary.gaia_rv_static_or_twin} with near-equal eclipses (two similar stars can look static).</li>
                  </ul>
                  {f.physical.spectroscopy.gaia_orbits.filter((o) => o.same_period).length > 0 ? (
                    <div className="mt-4 overflow-x-auto rounded-xl border border-line">
                      <table className="w-full min-w-[640px] text-left text-sm">
                        <thead className="nav-caps font-mono text-[11px] text-muted">
                          <tr>
                            <th className="p-3">Star</th>
                            <th className="p-3">Gaia period (d)</th>
                            <th className="p-3">P Gaia / P TESS</th>
                            <th className="p-3">Gaia e</th>
                            <th className="p-3">e cos w Gaia / TESS</th>
                            <th className="p-3">Gaia K1 (km/s)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {f.physical.spectroscopy.gaia_orbits.filter((o) => o.same_period).map((o) => (
                            <tr key={o.tic} className="border-t border-line">
                              <td className="p-3">TIC {o.tic}</td>
                              <td className="p-3">{o.gaia_period_days.toFixed(4)}</td>
                              <td className="p-3">{o.period_ratio.toFixed(4)}</td>
                              <td className="p-3">{o.gaia_e !== null ? `${o.gaia_e.toFixed(3)} +- ${(o.gaia_e_sigma ?? 0).toFixed(3)}` : "n/a"}</td>
                              <td className="p-3">{o.gaia_ecosw !== null ? o.gaia_ecosw.toFixed(3) : "n/a"} / {o.photometric_ecosw !== null ? o.photometric_ecosw.toFixed(3) : "n/a"}</td>
                              <td className="p-3">{o.gaia_k1_kms !== null ? o.gaia_k1_kms.toFixed(1) : "n/a"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  {f.physical.spectroscopy.e_check_vs_gaia.length > 0 ? (
                    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                      Light-curve eccentricity against Gaia&apos;s spectroscopic one, an independent check of the model:{" "}
                      {f.physical.spectroscopy.e_check_vs_gaia.map((r) => `TIC ${r.tic}: ${r.fit_e.toFixed(3)} vs ${r.gaia_e.toFixed(3)} +- ${r.gaia_e_sigma.toFixed(3)} (${r.difference_sigma.toFixed(1)} sigma apart; light-curve e ${r.trusted ? "trusted" : "not trusted by the rule"})`).join("; ")}.
                    </p>
                  ) : null}
                  {f.physical.spectroscopy.static.filter((r) => r.verdict === "BLEND_INDICATED").map((r) => (
                    <p key={r.tic} className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                      TIC {r.tic}: a {((r.eclipse_depth ?? 0) * 100).toFixed(1)}% eclipse, yet the bright star moves by less than{" "}
                      {r.k1_upper_kms.toFixed(1)} km/s over {r.n_transits} Gaia transits (companion below {r.m2_max_msun.toFixed(3)} solar masses).
                      The eclipses very probably come from another star in the aperture.
                    </p>
                  ))}
                </>
              ) : null}
            </section>
          ) : null}

          {f.validation ? (
            <section className="mb-10">
              <h2 className="font-display text-2xl text-fg">Checked against other people&apos;s numbers</h2>
              <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
                The eccentricity code was run on {f.validation.n_tested} eclipsing binaries from the Prsa et al. 2022 TESS catalog, whose
                secondary-eclipse phases were fitted by other code. Only the published period and epoch were given as input, on the first 26
                sectors the catalog used. Median difference in secondary phase: {f.validation.median_abs_phase_error === null ? "n/a" : f.validation.median_abs_phase_error.toFixed(4)};{" "}
                {f.validation["fraction_within_0.01"] === null ? "n/a" : `${(100 * f.validation["fraction_within_0.01"]).toFixed(0)}%`} of measured systems agree within 0.01 in phase.
                Published as circular: {f.validation.circular_truth} systems, {f.validation.false_positive_eccentric} called eccentric here.
                Published as eccentric: {f.validation.eccentric_truth} systems, {f.validation.recovered_eccentric} recovered here; the others were
                vetoed or had too few secondary eclipses to test, by design: the rule prefers a miss to a false claim.
              </p>
              <ul className="mt-3 list-disc pl-5 text-xs text-muted">
                {Object.entries(f.validation.eccentric_truth_verdicts).map(([k, n]) => (<li key={k}>Published eccentric, here {k}: {n}</li>))}
              </ul>
            </section>
          ) : null}

          <section className="border-t border-line pt-6">
            <h2 className="font-display text-xl text-fg">Limits</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
              {f.limits.map((l) => (<li key={l}>{l}</li>))}
              <li>No spectroscopy and no physical light-curve model: masses, radii and true eccentricities are unknown.</li>
              <li>These stars are in the Kostov et al. 2025 list by construction; nothing here claims they are new binaries.</li>
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
