"""
upstream.py - guards for the pipeline's dependence on remote catalog services.

WHY THIS EXISTS (2026-11-07 incident)
From 2026-10-28 the CDS Strasbourg services (VizieR, XMatch) stopped answering
from GitHub's runners. Two things went wrong:
  1. f4f_novelty.py treated every timed-out cross-match as "zero matches", so
     every star looked uncatalogued, and that wrong result was committed
     (commit ae4939e: NOVEL 2906 -> 3197, VSX matches 333 -> 0).
  2. Each of the ~45 per-star ASAS-SN queries burned 3 x 60 s of timeouts, so
     one stage took 147 minutes and runs hit the 4-hour job limit, were
     cancelled, and committed nothing for 10 days.

The rule this module supports: if an upstream service is down, STOP, say so,
and write nothing. A missing answer must never be recorded as a "no match".

Exit code 3 (EXIT_UPSTREAM_DOWN) means "a required remote service is
unavailable". f6_orchestrator.py does not retry it and stops the run.

COMMAND LINE (used as the first step of the GitHub workflow)
    python upstream.py                 check MAST, CDS XMatch and CDS VizieR
    python upstream.py mast xmatch     check only the named services
Exit code 0 if every checked service answered, 3 if any did not.
Uses only the standard library so it can run before dependencies install.
"""
import os
import sys
import threading
import time
import urllib.error
import urllib.request

EXIT_UPSTREAM_DOWN = 3

# name -> (label, url). A service counts as up if it answers at all with an
# HTTP status below 500. Connection errors, timeouts and 5xx count as down.
SERVICES = {
    "mast": ("MAST (TIC catalog + TESS data)", "https://mast.stsci.edu/"),
    "xmatch": ("CDS XMatch (VSX + Gaia cross-match)",
               "http://cdsxmatch.u-strasbg.fr/xmatch/api/v1/sync/tables"),
    "vizier": ("CDS VizieR (ASAS-SN + TESS EB catalog)", "https://vizier.cds.unistra.fr/"),
}


class UpstreamDown(RuntimeError):
    """A required remote service did not answer after retries."""


def call_with_timeout(fn, args=(), kwargs=None, timeout=60):
    """Run fn(*args, **kwargs) with a hard wall-clock deadline; raise
    TimeoutError if it does not finish. Daemon thread on purpose: a stuck
    call must not block interpreter shutdown (same reasoning as the copies of
    this function in f4f_novelty.py and diag_blend.py)."""
    kwargs = kwargs or {}
    box = {"value": None, "error": None}

    def runner():
        try:
            box["value"] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised below
            box["error"] = exc

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"call did not finish within {timeout}s")
    if box["error"] is not None:
        raise box["error"]
    return box["value"]


def chunked(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def query_tic_chunked(fetch, tic_ids, chunk_size=300, timeout=120, retries=2,
                      delay=5, log=print):
    """Look up many TIC IDs in several small MAST requests instead of one huge
    one (a single 3,350-ID request timed out on 2026-11-06).

    fetch(ids) must return an astropy Table. Each chunk is retried `retries`
    times; if a chunk still fails, raises UpstreamDown rather than returning a
    partial table, because a silently shorter table would drop stars.
    """
    from astropy.table import vstack

    tables = []
    chunks = list(chunked(tic_ids, chunk_size))
    for n, ids in enumerate(chunks, start=1):
        last_err = None
        for attempt in range(retries + 1):
            try:
                tables.append(call_with_timeout(fetch, args=(ids,), timeout=timeout))
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001 - any failure is retryable here
                last_err = exc
                if attempt < retries:
                    time.sleep(delay)
        if last_err is not None:
            raise UpstreamDown(
                f"MAST TIC lookup failed on chunk {n}/{len(chunks)} after "
                f"{retries + 1} attempts: {str(last_err)[:160]}")
        if len(chunks) > 1:
            log(f"    TIC lookup chunk {n}/{len(chunks)} done")
    non_empty = [t for t in tables if len(t) > 0]
    if not non_empty:
        return tables[0] if tables else None
    return vstack(non_empty, metadata_conflicts="silent")


class FailureBreaker:
    """Trips after `limit` consecutive failures. Use around a loop of
    independent remote queries: when the service is down, stop after a handful
    of failures instead of timing out on every remaining item."""

    def __init__(self, limit=5):
        self.limit = limit
        self.consecutive = 0

    def record(self, ok):
        self.consecutive = 0 if ok else self.consecutive + 1
        return self.tripped

    @property
    def tripped(self):
        return self.consecutive >= self.limit


def probe(url, timeout=20, attempts=2):
    """Returns (is_up, detail, seconds)."""
    detail = "no attempt made"
    start = time.time()
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "star-vetter-preflight"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
            if status < 500:
                return True, f"HTTP {status}", time.time() - start
            detail = f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True, f"HTTP {exc.code}", time.time() - start
            detail = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - timeouts, DNS, TLS, resets
            detail = f"{type(exc).__name__}: {str(exc)[:100]}"
        time.sleep(2)
    return False, detail, time.time() - start


def preflight(names):
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    down = []
    for name in names:
        label, url = SERVICES[name]
        up, detail, secs = probe(url)
        print(f"  {'UP  ' if up else 'DOWN'}  {label}  ({detail}, {secs:.1f}s)")
        if not up:
            down.append(label)
            if on_github:
                print(f"::error title=Upstream service down::{label} did not answer "
                      f"({detail}). Skipping this run so nothing wrong is committed.")
    return down


def main(argv):
    names = argv[1:] or list(SERVICES)
    unknown = [n for n in names if n not in SERVICES]
    if unknown:
        print(f"Unknown service(s): {unknown}. Choose from: {sorted(SERVICES)}")
        return 1
    print("Star Vetter pre-flight: are the remote catalog services up?")
    down = preflight(names)
    if down:
        print(f"\n{len(down)} required service(s) unreachable. Stopping before any work is "
              f"done; nothing will be written or committed. Re-run when they are back.")
        return EXIT_UPSTREAM_DOWN
    print("\nAll required services answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
