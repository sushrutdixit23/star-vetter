import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import f17_ztf_independent as z

# Publishes the per-star ZTF results (data/processed/f17_ztf/TIC*.json) as one compact
# site file, with the summary and the settings that produced it.


def compact(r):
    o = r.get("obs") or {}
    oe = r.get("odd_even_at_2P")
    sec = r.get("secondary")
    return {"status": r["status"], "n_points": r.get("n_points", 0), "tier": r.get("tier"),
            "tess_period": r.get("tess_period"), "refined_period": o.get("period"), "epochs": r.get("epochs_with_points"),
            "snr": o.get("snr"), "p_value": r.get("p_value"), "power": r.get("power"),
            "depth_ratio": r.get("depth_ratio"), "depth_ratio_err": r.get("depth_ratio_err"),
            "odd_even_z": None if not oe else oe.get("z"), "secondary_z": None if not sec else sec.get("z"),
            "span_days": r.get("ztf_span_days")}


def build(results):
    stars = {str(r["tic"]): compact(r) for r in results}
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": z.summarise(results),
        "method": {
            "data": "ZTF forced-aperture light curves from IRSA (catflags mask %d, error <= %.2f mag), all filters pooled as relative flux" % (z.BAD_CATFLAGS_MASK, z.MAX_MAGERR),
            "test": "box least squares scan within +-%.1f percent of the TESS period, durations %s x the TESS duration" % (100 * z.SCAN_HALF_WIDTH, list(z.DURATION_FACTORS)),
            "null": "%d control periods per star, away from harmonics of the TESS period; p = share of controls with signal-to-noise at least the observed" % z.N_CONTROLS,
            "power": "%d injected eclipses of the TESS depth per star; power = share recovered above the %.0f-percentile of the controls" % (z.N_INJECTIONS, 100 * z.CONTROL_QUANTILE),
            "confirmed": "p <= %.2f, at least %d eclipse epochs with points, and depth ratio to TESS inside %s allowing 2 sigma" % (z.P_CONFIRM, z.MIN_EVENTS, list(z.DEPTH_RATIO_RANGE)),
            "not_seen": "power >= %.1f and not confirmed: ZTF could have seen it and did not" % z.POWER_TESTABLE,
            "inconclusive": "power < %.1f and not confirmed: ZTF could not have told" % z.POWER_TESTABLE,
            "no_data": "fewer than %d clean points or under 30 days of baseline (ZTF does not cover most of the far south)" % z.MIN_POINTS,
            "not_independent_of": "the TESS period and duration, which are the test's starting point",
        },
        "stars": stars,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_independent.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "data" / "processed" / "f17_ztf").glob("TIC*.json"))]
    rep = build(results)
    path = root / "site" / "public" / "data" / "ztf_independent.json"
    path.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rep["summary"], indent=1)[:1500])
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
