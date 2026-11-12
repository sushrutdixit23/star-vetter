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

2026-11-12 follow-up: the pre-flight reported "CDS VizieR UP" because it only
fetched the VizieR home page (HTTP 200). VizieR's query endpoint (viz-bin/votable)
was answering 404 and CDS XMatch was answering 503, so every scheduled run since
28 Oct stopped here. The probes now run a one-row query against the real
endpoint, and the pipeline no longer depends on CDS alone: the Harvard-CfA
VizieR mirror serves the same catalogs (see crossmatch.py). XMatch is optional,
a working VizieR server is required.

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

# name -> (label, url, strict). A non-strict service counts as up if it answers at
# all with an HTTP status below 500. A strict one must answer 2xx: used for query
# endpoints, where a 404 means the service is gone even though its front page is up.
# Connection errors, timeouts and 5xx always count as down.
CDS_SERVER = "vizier.cds.unistra.fr"
MIRROR_SERVER = "vizier.cfa.harvard.edu"
_VIZIER_PROBE = "/viz-bin/votable?-source=B/vsx/vsx&-c=102.6056,1.0450&-c.rs=10&-out.max=1"
SERVICES = {
    "mast": ("MAST (TIC catalog + TESS data)", "https://mast.stsci.edu/", False),
    "xmatch": ("CDS XMatch (VSX + Gaia cross-match)",
               "http://cdsxmatch.u-strasbg.fr/xmatch/api/v1/sync/tables", False),
    "vizier": ("CDS VizieR query endpoint", "https://" + CDS_SERVER + _VIZIER_PROBE, True),
    "vizier_mirror": ("Harvard-CfA VizieR mirror query endpoint", "https://" + MIRROR_SERVER + _VIZIER_PROBE, True),
}
VIZIER_SERVERS = {"vizier": CDS_SERVER, "vizier_mirror": MIRROR_SERVER}


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


def probe(url, timeout=20, attempts=2, strict=False):
    """Returns (is_up, detail, seconds). strict: only a 2xx answer counts as up."""
    detail = "no attempt made"
    start = time.time()
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "star-vetter-preflight"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
            if status < (300 if strict else 500):
                return True, f"HTTP {status}", time.time() - start
            detail = f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            if exc.code < (0 if strict else 500):
                return True, f"HTTP {exc.code}", time.time() - start
            detail = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - timeouts, DNS, TLS, resets
            detail = f"{type(exc).__name__}: {str(exc)[:100]}"
        time.sleep(2)
    return False, detail, time.time() - start


def preflight(names):
    """Probe each named service. Returns {name: (up, detail)}."""
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    status = {}
    for name in names:
        label, url, strict = SERVICES[name]
        up, detail, secs = probe(url, strict=strict)
        print(f"  {'UP  ' if up else 'DOWN'}  {label}  ({detail}, {secs:.1f}s)")
        status[name] = (up, detail)
        if not up and on_github:
            print(f"::warning title=Upstream service down::{label} did not answer ({detail}).")
    return status


def problems(status, explicit):
    """What stops a run. Named on the command line: every named service is required (old behaviour).
    Default (all services): MAST is required, a working VizieR server (CDS or the mirror) is required, and
    XMatch is optional because crossmatch.py can do its job through VizieR."""
    up = {n: ok for n, (ok, _) in status.items()}
    if explicit:
        return [SERVICES[n][0] for n, ok in up.items() if not ok]
    out = []
    if not up.get("mast", True):
        out.append(SERVICES["mast"][0])
    if not (up.get("vizier") or up.get("vizier_mirror")):
        out.append("a VizieR server (CDS and the Harvard-CfA mirror both failed)")
    return out


def pick_vizier_server(probe_fn=None):
    """The VizieR host to use for this run: CDS if its query endpoint works, else the mirror, else None.
    STAR_VETTER_VIZIER_SERVER overrides (set by the workflow after the pre-flight, so later steps agree with it)."""
    forced = os.environ.get("STAR_VETTER_VIZIER_SERVER")
    if forced:
        return forced
    probe_fn = probe_fn or probe
    for name in ("vizier", "vizier_mirror"):
        up, _, _ = probe_fn(SERVICES[name][1], strict=True)
        if up:
            return VIZIER_SERVERS[name]
    return None


def _export_for_later_steps(status):
    """On GitHub: tell the next steps which path to take, and leave a note in the job summary."""
    env_file = os.environ.get("GITHUB_ENV")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    server = next((VIZIER_SERVERS[n] for n in ("vizier", "vizier_mirror") if status.get(n, (False,))[0]), None)
    lines = []
    if env_file:
        with open(env_file, "a", encoding="utf-8", newline="\n") as fh:
            if server:
                fh.write(f"STAR_VETTER_VIZIER_SERVER={server}\n")
            if not status.get("xmatch", (True,))[0]:
                fh.write("STAR_VETTER_SKIP_XMATCH=1\n")
    if summary_file:
        lines.append("### Pre-flight\n")
        for n, (ok, detail) in status.items():
            lines.append(f"- {'up' if ok else '**down**'}: {SERVICES[n][0]} ({detail})")
        if not status.get("xmatch", (True,))[0]:
            lines.append("\nCDS XMatch is down; the cross-match runs through VizieR on `%s` instead (crossmatch.py)." % server)
        with open(summary_file, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")


def main(argv):
    names = argv[1:] or list(SERVICES)
    unknown = [n for n in names if n not in SERVICES]
    if unknown:
        print(f"Unknown service(s): {unknown}. Choose from: {sorted(SERVICES)}")
        return 1
    print("Star Vetter pre-flight: are the remote catalog services up?")
    status = preflight(names)
    explicit = len(argv) > 1
    down = problems(status, explicit)
    if down:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            for label in down:
                print(f"::error title=Upstream service down::{label} did not answer. "
                      f"Skipping this run so nothing wrong is committed.")
        print(f"\n{len(down)} required service(s) unreachable. Stopping before any work is "
              f"done; nothing will be written or committed. Re-run when they are back.")
        return EXIT_UPSTREAM_DOWN
    _export_for_later_steps(status)
    optional_down = [SERVICES[n][0] for n, (ok, _) in status.items() if not ok]
    if optional_down and not explicit:
        print("\nNOT required and down (a fallback is used): " + "; ".join(optional_down))
    print("\nAll required services answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
