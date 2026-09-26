import json
import sys
from pathlib import Path


def load_json_safe(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not read {path}: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: py check_site_consistency.py <project_root>")
        sys.exit(1)

    # Runs after every export_*.py script, before the Next.js build. Its only
    # job is to fail loudly (non-zero exit, breaking the CI build step) if
    # two independently-generated exports disagree on the confirmed count -
    # this is the exact 23-vs-26 bug the site once shipped: index.json and
    # pipeline_stats.json are written by two different scripts on two
    # different schedules, and nothing forced them to agree before this
    # check existed.
    project_root = Path(sys.argv[1]).resolve()
    data_dir = project_root / "site" / "public" / "data"

    index = load_json_safe(data_dir / "index.json")
    stats = load_json_safe(data_dir / "pipeline_stats.json")

    if index is None or stats is None:
        print("SKIPPED: index.json or pipeline_stats.json not found yet - "
              "nothing to cross-check on this run.")
        return

    index_confirmed = len(index.get("candidates", []))
    index_generated_stats = index.get("generated_stats", {}).get("n_confirmed")

    funnel_confirmed = None
    for step in stats.get("funnel", []):
        if step.get("label") == "Confirmed on-target":
            funnel_confirmed = step.get("count")
            break

    print("Consistency check:")
    print(f"  index.json candidates array length:        {index_confirmed}")
    print(f"  index.json generated_stats.n_confirmed:     {index_generated_stats}")
    print(f"  pipeline_stats.json 'Confirmed on-target':  {funnel_confirmed}")

    problems = []
    if index_generated_stats is not None and index_generated_stats != index_confirmed:
        problems.append(
            f"index.json's own generated_stats.n_confirmed ({index_generated_stats}) does not "
            f"match its own candidates array length ({index_confirmed})"
        )
    if funnel_confirmed is not None and funnel_confirmed != index_confirmed:
        problems.append(
            f"pipeline_stats.json's 'Confirmed on-target' count ({funnel_confirmed}) does not "
            f"match index.json's candidates array length ({index_confirmed})"
        )

    if problems:
        print("\nFAILED - the site would ship with disagreeing confirmed counts on "
              "different pages:")
        for p in problems:
            print(f"  - {p}")
        print("\nThis usually means one export ran against stale data on disk relative to "
              "the other (for example a merge conflict resolved by keeping an old copy of "
              "one file). Re-run the export scripts from the same, current data on disk and "
              "try again.")
        sys.exit(1)

    print("\nOK - confirmed counts agree everywhere checked.")


if __name__ == "__main__":
    main()