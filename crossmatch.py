"""crossmatch.py - catalog cross-match through VizieR, used when CDS XMatch is down.

WHY THIS EXISTS (2026-11-12)
The daily pipeline had been stopping at its pre-flight check for about two weeks. Two things were wrong at CDS
Strasbourg, and only one of them was visible:
  * CDS XMatch (cdsxmatch) answers HTTP 503 / times out. The pre-flight caught this and (correctly) stopped.
  * CDS VizieR's query endpoint (viz-bin/votable) answers HTTP 404, although its home page still answers 200,
    so the pre-flight called VizieR "UP". Everything that queries VizieR through astroquery's default server
    (the ASAS-SN step, the TESS EB step) would have failed next.
The Harvard-CfA VizieR mirror (vizier.cfa.harvard.edu) serves the same catalogs, and the rest of this repo already
uses it (f14, f16, f19, f27). This module does the same job as XMatch.query(cat1, "vizier:<id>", max_distance=...)
through that mirror: one request per chunk of positions, nearest catalog row within the radius per input star.

Contract (same as the rest of the fail-closed design in upstream.py):
  * a request that cannot be completed after retries (and after splitting the chunk) raises UpstreamDown; a partial
    answer is never returned, because a missing answer must never be recorded as "no match";
  * a cut-off VOTable counts as a failed request (astroquery would otherwise return an empty table for it);
  * the result has the same columns the XMatch path produced for the catalogs f4f_novelty.py reads, plus
    angDist in arcsec, sorted so the nearest match per star comes first.
validate_crossmatch_fallback.py compares this path with the answers the XMatch path produced before the outage.
"""
import time
import warnings

import numpy as np
import pandas as pd

from upstream import CDS_SERVER, MIRROR_SERVER, UpstreamDown, call_with_timeout  # noqa: F401 - re-exported

# catalog -> (RA column, Dec column) used to measure the separation ourselves; VizieR's own _r column is rounded.
CATALOG_COORDS = {
    "B/vsx/vsx": ("RAJ2000", "DEJ2000"),
    "I/358/veb": ("RA_ICRS", "DE_ICRS"),
    "I/358/vclassre": ("RA_ICRS", "DE_ICRS"),
}


class VizierServerError(RuntimeError):
    """VizieR answered HTTP 200 but the document says the query failed, or the document is cut off."""


def check_vizier_response(resp, *args, **kwargs):
    """Requests response hook: turn VizieR's in-document failures into exceptions.

    Found 2026-11-12: the Harvard-CfA mirror sometimes answers HTTP 200 with a VOTable that contains
    <INFO name="QUERY_STATUS" value="ERROR"> ("Postgres connect error", "No server is available for connection")
    and no table. astroquery reads that as an empty result, i.e. "no catalog entry here". In one run of the
    3,305-star comparison this lost 180 of 334 known VSX matches without any error. A failure the server reports
    in the document must be a failure here too.
    """
    try:
        text = resp.text
    except Exception:  # noqa: BLE001 - binary or undecodable: not a VOTable we can judge
        return resp
    if "<VOTABLE" not in text:
        return resp
    if 'name="QUERY_STATUS" value="ERROR"' in text or 'name="Error"' in text:
        why = " ".join(text.split('name="Error" value="')[1:3]).replace('"/>', "").strip()[:120] or "QUERY_STATUS=ERROR"
        raise VizierServerError("VizieR reported an error inside a 200 response: " + why)
    if not text.rstrip().endswith("</VOTABLE>"):
        raise VizierServerError("VizieR response is cut off (no closing </VOTABLE>)")
    return resp


def harden(v, server=MIRROR_SERVER):
    """Point an astroquery Vizier object at `server` and make it raise on in-document errors."""
    v.VIZIER_SERVER = server
    session = getattr(v, "_session", None)
    if session is not None and check_vizier_response not in session.hooks["response"]:
        session.hooks["response"].append(check_vizier_response)
    return v


def vizier_for(server=MIRROR_SERVER, **kwargs):
    """An astroquery Vizier object that talks to `server` (the default would be CDS)."""
    from astroquery.vizier import Vizier

    return harden(Vizier(**kwargs), server)


def _vizier_query(server):
    v = vizier_for(server, columns=["**"], row_limit=-1)

    def query(coords, radius, src):
        # astroquery turns a cut-off VOTable into a warning and an EMPTY result. Taken at face value that is
        # "no matches for any of these stars", the exact error this module exists to prevent, so a parse
        # warning is a failed request.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # cache=False: astroquery's on-disk cache would replay a cut-off answer on every retry
            res = v.query_region(coords, radius=radius, catalog=src, cache=False)
        bad = [str(w.message) for w in caught if "VOTABLE parsing" in str(w.message)]
        if bad:
            raise RuntimeError("truncated VOTable from VizieR: " + bad[0][:120])
        return res[0] if len(res) else None

    return query


def crossmatch(df, source, radius_arcsec, server=MIRROR_SERVER, chunk=200, min_split=25, timeout=180, retries=7,
               delay=2, id_col="TIC", ra_col="ra", dec_col="dec", log=print, query=None):
    """Nearest `source` row within radius_arcsec of every row of df (columns id_col, ra_col, dec_col, degrees).

    Returns a DataFrame with id_col, every catalog column and angDist (arcsec); one row per matched star, nearest
    first. Each request is retried `retries` times with growing pauses; a request that still fails is split in two
    (down to `min_split` stars) before giving up with UpstreamDown. `query` is a test hook with the signature
    query(coords, radius, source) -> astropy Table or None (default: Vizier.query_region on `server`).
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    if source not in CATALOG_COORDS:
        raise ValueError("no coordinate columns known for %s; add it to CATALOG_COORDS" % source)
    ra_name, dec_name = CATALOG_COORDS[source]
    df = df.reset_index(drop=True)
    query = query or _vizier_query(server)

    def fetch(sub):
        """-> list of (sub, coords, table) covering every star of `sub`."""
        coords = SkyCoord(sub[ra_col].to_numpy(float) * u.deg, sub[dec_col].to_numpy(float) * u.deg)
        last = None
        for attempt in range(retries + 1):
            try:
                tab = call_with_timeout(query, args=(coords, radius_arcsec * u.arcsec, source), timeout=timeout)
                return [(sub, coords, tab)]
            except Exception as exc:  # noqa: BLE001 - every failure is retryable here
                last = exc
                if attempt < retries:
                    time.sleep(delay * (attempt + 1))
        if len(sub) > min_split:
            h = len(sub) // 2
            log("    %s: a %d-star request failed (%s); splitting it" % (source, len(sub), str(last)[:70]))
            return fetch(sub.iloc[:h]) + fetch(sub.iloc[h:])
        raise UpstreamDown("VizieR (%s) cross-match with %s failed for %d star(s) after %d attempts: %s"
                           % (server, source, len(sub), retries + 1, str(last)[:160] or type(last).__name__))

    pieces = []
    n_chunks = max(1, int(np.ceil(len(df) / float(chunk))))
    for k in range(n_chunks):
        for sub, coords, tab in fetch(df.iloc[k * chunk:(k + 1) * chunk]):
            if tab is None or len(tab) == 0:
                continue
            t = tab.to_pandas()
            if ra_name not in t.columns or dec_name not in t.columns:
                raise UpstreamDown("VizieR (%s) answer for %s has no %s/%s columns; refusing to guess"
                                   % (server, source, ra_name, dec_name))
            idx = t["_q"].to_numpy(int) - 1                  # VizieR numbers the input positions from 1
            cat = SkyCoord(t[ra_name].to_numpy(float) * u.deg, t[dec_name].to_numpy(float) * u.deg)
            t["angDist"] = coords[idx].separation(cat).arcsec
            t[id_col] = sub[id_col].to_numpy()[idx]
            t = t[t["angDist"] <= radius_arcsec + 1e-9]
            pieces.append(t.drop(columns=[c for c in ("_q", "_r") if c in t.columns]))
        if n_chunks > 1:
            log("    %s: chunk %d/%d done" % (source, k + 1, n_chunks))
    if not pieces:
        return pd.DataFrame(columns=[id_col, "angDist"])
    out = pd.concat(pieces, ignore_index=True).sort_values("angDist")
    return out.drop_duplicates(subset=id_col, keep="first").reset_index(drop=True)
