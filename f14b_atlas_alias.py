import sys
import json
from math import comb
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ATLAS alias test.
#
# 37 candidates have an ATLAS (Heinze et al. 2018) period that differs from the
# TESS period by more than the simple 1 / 0.5 / 2 ratios f14_novelty_extra
# already tests. Heinze et al. say their detached-EB periods are often wrong,
# and describe their search: the Lomb-Scargle frequency axis is rescaled so
# periods are doubled, trial periods include multiples (x1 to x6), and
# sidereal-day aliases of +-0.5, +-1, +-2, +-3 cycles per day are searched. A
# wrong ATLAS period can therefore be a harmonic and/or a sidereal-day alias
# of the true one. This module asks, per star, whether
#
#     1/P_TESS = | 1/(f * P_ATLAS) + s * j / 0.99727 d |
#
# for a small multiplier f, a sidereal order j and a sign s, to within the
# frequency resolution of the ATLAS data (1 / baseline).
#
# That space of hypotheses is large (80 combinations), so a few matches are
# expected by chance. The honest question is therefore not "does an alias
# exist" but "do MORE stars have one than chance predicts". The chance rate is
# measured here by pairing each star's ATLAS period with the TESS period of
# every OTHER candidate; the observed count is compared with it.

SIDEREAL_DAY = 0.99727
ATLAS_BASELINE_DAYS = 620.0                      # median DR1 span (Heinze et al. 2018)
TOL_FREQ = 1.0 / ATLAS_BASELINE_DAYS             # cycles per day
MULTIPLIERS = (1.0 / 3.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
SIDEREAL_ORDERS = (0.0, 0.5, 1.0, 2.0, 3.0)
SIGNS = (1.0, -1.0)
OTHER_PERIOD_STATUS = "SAME_STAR_OTHER_PERIOD"
MATCH_STATUS = "SAME_STAR_PERIOD_MATCH"


def hypotheses():
    """(order, multiplier, sidereal order, sign), simplest first: pure
    harmonics before sidereal aliases, then smaller multipliers."""
    out = []
    for j in SIDEREAL_ORDERS:
        for f in MULTIPLIERS:
            for s in SIGNS:
                if j == 0.0 and s < 0:
                    continue
                out.append((f, j, s))
    out.sort(key=lambda h: (h[1] != 0.0, h[1], abs(h[0] - 1.0) if h[0] >= 1 else 1.0 / h[0], -h[2]))
    return out


def predicted_frequency(p_atlas, f, j, s):
    return abs(1.0 / (f * p_atlas) + s * j / SIDEREAL_DAY)


def explain(p_tess, p_atlas, tol=TOL_FREQ):
    """First hypothesis (simplest first) that reproduces 1/P_TESS, or None."""
    if not (p_tess and p_atlas and p_tess > 0 and p_atlas > 0):
        return None
    nu = 1.0 / p_tess
    for f, j, s in hypotheses():
        pred = predicted_frequency(p_atlas, f, j, s)
        if pred > 0 and abs(pred - nu) <= tol:
            return {"multiplier": f, "sidereal_order": j, "sign": int(s),
                    "kind": "harmonic" if j == 0.0 else "sidereal",
                    "freq_error": float(abs(pred - nu))}
    return None


def binom_tail(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    return float(sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def chance_rate(atlas_periods, tess_periods_by_tic, own_tics):
    """Fraction of (ATLAS period of star i, TESS period of star k != i) pairs
    that some hypothesis explains."""
    hit = tot = 0
    for tic_i, pa in zip(own_tics, atlas_periods):
        for tic_k, pt in tess_periods_by_tic.items():
            if tic_k == tic_i:
                continue
            tot += 1
            if explain(pt, pa) is not None:
                hit += 1
    return hit, tot


def build(extra, tess_periods, now=None):
    """extra: f14_extra_catalogs rows; tess_periods: {tic: period_days}."""
    a = extra[extra["catalog"].str.lower() == "atlas"].copy()
    a["tic"] = a["tic"].astype(int)
    a = a[a["tic"].isin(tess_periods)]
    other = a[a["status"] == OTHER_PERIOD_STATUS].sort_values("tic")
    stars = []
    for r in other.itertuples(index=False):
        pt, pa = float(tess_periods[r.tic]), float(r.nearest_period_d)
        ex = explain(pt, pa)
        stars.append({"tic": int(r.tic), "atlas_class": r.nearest_class,
                      "atlas_period": pa, "tess_period": pt, "ratio_atlas_over_tess": pa / pt,
                      "explained": ex is not None, "explanation": ex})
    n = len(stars)
    k = sum(s["explained"] for s in stars)
    k_h = sum(1 for s in stars if s["explained"] and s["explanation"]["kind"] == "harmonic")
    chance_hit, chance_tot = chance_rate([s["atlas_period"] for s in stars], tess_periods, [s["tic"] for s in stars])
    p0 = chance_hit / chance_tot if chance_tot else 0.0
    matched = a[a["status"] == MATCH_STATUS]
    by_class = other["nearest_class"].value_counts().to_dict()
    return {
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": {
            "relation": "1/P_TESS = |1/(f*P_ATLAS) + s*j/0.99727|",
            "multipliers": list(MULTIPLIERS), "sidereal_orders": list(SIDEREAL_ORDERS),
            "hypotheses": len(hypotheses()),
            "frequency_tolerance_per_day": TOL_FREQ,
            "tolerance_basis": "1 / %.0f-day ATLAS DR1 median baseline (Heinze et al. 2018)" % ATLAS_BASELINE_DAYS,
            "chance_rate_basis": "ATLAS period of each star against the TESS period of every other candidate",
        },
        "tested": n,
        "atlas_class_of_tested": by_class,
        "explained": {"k": k, "n": n, "harmonic_only": k_h, "with_sidereal": k - k_h},
        "chance": {"pair_rate": p0, "expected_explained": p0 * n,
                   "p_value_at_least_observed": binom_tail(k, n, p0) if n else None},
        "already_matching_ratio_1_half_2": int(len(matched)),
        "stars": stars,
        "reading": (
            "ATLAS labels 'dubious' mean the variability may not be real (Heinze et al. 2018), and its detached-EB "
            "periods are often wrong. A star counts as 'explained' only if a harmonic or sidereal alias reproduces the "
            "TESS period to within the ATLAS frequency resolution; compare the explained count with the chance count, "
            "not with zero."
        ),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: py f14b_atlas_alias.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    extra = pd.read_csv(root / "data" / "processed" / "f14_extra_catalogs.csv")
    dash = json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))
    tess = {int(s["tic"]): float(s["period_days"]) for s in dash["sky"]}
    out = build(extra, tess)
    path = root / "site" / "public" / "data" / "atlas_alias.json"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    e, c = out["explained"], out["chance"]
    print("ATLAS different-period matches tested: %d" % out["tested"])
    print("Explained by a harmonic or sidereal alias: %d (harmonic only %d)" % (e["k"], e["harmonic_only"]))
    print("Expected by chance: %.1f (pair rate %.1f%%), P(>= observed) = %.3g" % (c["expected_explained"], 100 * c["pair_rate"], c["p_value_at_least_observed"]))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
