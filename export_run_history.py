import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_run_history.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    runs_dir = project_root / "data" / "runs"
    out_path = project_root / "site" / "public" / "data" / "run_history.json"

    # data/runs/<run_id>.json is written by f6_orchestrator.py at the end of
    # every run (clean finish, "nothing new to sample", or a failed stage) -
    # this script does no computation of its own, it only collects those
    # files into the one JSON array the website's run-history page reads.
    # Unlike data/logs/ and data/lightcurves/, data/runs/ is NOT gitignored,
    # so unlike the orchestrator's own text log, this survives every CI
    # checkout and accumulates across runs.
    if not runs_dir.exists():
        print(f"NOTE: {runs_dir} does not exist yet (no run has produced a record). "
              f"Writing an empty run history.")
        records = []
    else:
        records = []
        for p in sorted(runs_dir.glob("*.json")):
            try:
                records.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"WARNING: could not read {p}: {e} - skipping this run record.")

    # Filenames are the run's own timestamp (YYYYMMDD_HHMMSS), so a plain
    # sort is already chronological; reverse for newest-first, and keep only
    # the most recent 30 in the site JSON so this file stays small forever -
    # every run's own record still lives on disk in data/runs/ regardless.
    records.sort(key=lambda r: r.get("run_id", ""), reverse=True)
    KEEP = 30
    trimmed = records[:KEEP]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"runs": trimmed}, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )

    print(f"Wrote {out_path}")
    print(f"{len(records)} run record(s) on disk in {runs_dir}, "
          f"{len(trimmed)} included in the site JSON (most recent {KEEP}).")
    for r in trimmed[:5]:
        cr = r.get("this_run") or {}
        print(f"  {r.get('run_id')}  status={r.get('status')}  "
              f"new_sampled={cr.get('new_sampled')}  new_confirmed={cr.get('new_confirmed')}  "
              f"duration={r.get('duration_seconds')}s")


if __name__ == "__main__":
    main()