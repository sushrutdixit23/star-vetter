"""Measure tidal / heating signals in each candidate's folded light curve.

Writes site/public/data/surface_evidence.json. The plate draws a star as
tidally stretched, or its inner face as heated, ONLY where this file says the
signal was measured. Nothing is invented for stars without evidence.

Method. Mask the primary and secondary eclipses (1.5x their half-width),
then fit the out-of-eclipse points (phase 0 = primary eclipse) with

    f = c + a1 cos(phi) + b1 sin(phi) + a2 cos(2 phi) + b2 sin(2 phi),
    phi = 2 pi phase.

  ellipsoidal amplitude   A_ell = -a2   (a tidally stretched star is faintest
                                         at conjunctions, phase 0 and 0.5)
  reflection amplitude    A_ref = -a1   (heated inner faces: brightest at 0.5)
  beaming                 b1

Errors are least-squares errors from the residual scatter, inflated by
ERR_INFLATION because folded stellar variability is not white noise.

Gates (all must hold) for each flag:
  tides:   A_ell > 0 with A_ell/err >= MIN_SNR, the quadrature term b2 is
           small (|b2| <= 0.5 A_ell: a tide is locked to the eclipses),
           A_ell <= MAX_AMP, and the curve is eclipse-shaped (not flagged
           sinusoidal) with at least MIN_FRAC of points left after masking.
  heating: A_ref > 0 with A_ref/err >= MIN_SNR and the same shape checks.

LIMITS (stated in the output): a single folded curve cannot separate tides
from starspots that stay locked to the orbit, and cannot say which star is
heated. The plate states both.

Usage:  python export_surface_evidence.py <root>
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

MIN_SNR = 8.0
ERR_INFLATION = 2.0
MAX_AMP = 0.3
MIN_FRAC = 0.4
MASK_FACTOR = 1.5
# elongation (long axis / short axis - 1) ~ ELONG_PER_AMP * A_ell: an
# equilibrium-tide estimate, good to about a factor of two.
ELONG_PER_AMP = 1.2
MAX_ELONG = 0.35


def _circ(d):
    return np.abs((d + 0.5) % 1.0 - 0.5)


def measure(phase, flux, duration_frac, sec_phase=None):
    """Return a dict of harmonic amplitudes and errors, or None if unusable.

    phase in cycles (any range), duration_frac = eclipse duration / period.
    """
    ph = np.asarray(phase, float)
    fl = np.asarray(flux, float)
    ok = np.isfinite(ph) & np.isfinite(fl)
    ph, fl = ph[ok], fl[ok]
    if ph.size < 100:
        return None
    half = MASK_FACTOR * duration_frac / 2.0
    keep = _circ(ph) > half
    if sec_phase is not None:
        keep &= _circ(ph - sec_phase) > half
    frac = float(keep.mean())
    if keep.sum() < 60 or frac < MIN_FRAC:
        return None
    x, y = ph[keep], fl[keep]
    # robust: clip 4-sigma outliers once (flares, bad points)
    phi = 2 * math.pi * x
    X = np.column_stack([np.ones_like(phi), np.cos(phi), np.sin(phi), np.cos(2 * phi), np.sin(2 * phi)])
    for _ in range(2):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ beta
        s = 1.4826 * np.median(np.abs(r - np.median(r))) or float(r.std())
        good = np.abs(r) < 4 * max(s, 1e-12)
        if good.all():
            break
        X, y = X[good], y[good]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    dof = max(1, len(y) - 5)
    sig = float(np.sqrt((r @ r) / dof))
    try:
        cov = sig ** 2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None
    err = ERR_INFLATION * np.sqrt(np.diag(cov))
    c = float(beta[0]) or 1.0
    return {
        "n_used": int(len(y)),
        "frac_used": round(frac, 3),
        "a_ell": float(-beta[3] / c),
        "b_ell": float(beta[4] / c),
        "a_ref": float(-beta[1] / c),
        "b_beam": float(beta[2] / c),
        "err_ell": float(err[3] / c),
        "err_ref": float(err[1] / c),
        "resid_rms": round(sig / c, 6),
    }


def judge(m, sinusoidal=False):
    """Apply the gates. Returns (tides, heating, elongation)."""
    if m is None or sinusoidal:
        return False, False, 0.0
    tides = (
        m["a_ell"] > 0
        and m["a_ell"] / m["err_ell"] >= MIN_SNR
        and abs(m["b_ell"]) <= 0.5 * m["a_ell"]
        and m["a_ell"] <= MAX_AMP
    )
    heating = (
        m["a_ref"] > 0
        and m["a_ref"] / m["err_ref"] >= MIN_SNR
        and m["a_ref"] <= MAX_AMP
    )
    elong = min(MAX_ELONG, ELONG_PER_AMP * m["a_ell"]) if tides else 0.0
    return bool(tides), bool(heating), round(float(elong), 4)


def main(root):
    root = Path(root)
    out = {}
    for f in sorted((root / "site/public/data/detail").glob("TIC*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        fold = d.get("fold") or {}
        raw = fold.get("raw")
        p = d.get("period_true_days")
        dur = d.get("duration_days")
        if not raw or not p or not dur:
            continue
        sec = d.get("secondary") or {}
        sec_ph = sec.get("phase") if sec.get("detected") else 0.5
        arr = np.asarray(raw, float)
        m = measure(arr[:, 0], arr[:, 1], dur / p, sec_ph)
        sinus = bool((d.get("periodicity") or {}).get("flag"))
        tides, heating, elong = judge(m, sinus)
        rec = {"tides": tides, "heating": heating, "elongation": elong, "sinusoidal": sinus}
        if m:
            rec.update({
                "ellipsoidal_amp": round(m["a_ell"], 5),
                "ellipsoidal_err": round(m["err_ell"], 5),
                "ellipsoidal_quadrature": round(m["b_ell"], 5),
                "reflection_amp": round(m["a_ref"], 5),
                "reflection_err": round(m["err_ref"], 5),
                "frac_used": m["frac_used"],
            })
        out[str(d["tic"])] = rec
    n_t = sum(v["tides"] for v in out.values())
    n_h = sum(v["heating"] for v in out.values())
    doc = {
        "method": __doc__.split("Usage:")[0].strip(),
        "thresholds": {"min_snr": MIN_SNR, "err_inflation": ERR_INFLATION, "max_amp": MAX_AMP, "elong_per_amp": ELONG_PER_AMP},
        "counts": {"stars": len(out), "tides": n_t, "heating": n_h},
        "limits": [
            "A folded light curve cannot separate tides from starspots locked to the orbit.",
            "It cannot say which of the two stars carries the heating; the plate puts it on the companion, the usual case.",
            "Elongation is an equilibrium-tide estimate from the amplitude, good to about a factor of two.",
        ],
        "stars": out,
    }
    path = root / "site/public/data/surface_evidence.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(out)} stars: tides {n_t}, heating {n_h} -> {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
