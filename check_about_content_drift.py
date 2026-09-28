"""
check_about_content_drift.py

Compares the live confirmed-candidate count (site/public/data/index.json's
generated_stats.n_confirmed) against the count that was live when the About
page content (data/processed/f9_about_content.json) was last generated.

f9_generate_about_content.py only calls the Claude API when --force is
passed or its cache file does not exist yet - by design, to avoid an API
call on every automated run. That means the About page narrative silently
drifts out of date every time new candidates are confirmed, unless someone
remembers to re-run f9 with --force. This script closes that gap: it is
meant to run automatically on every pipeline cycle, in place of calling f9
directly.

Usage:
  py check_about_content_drift.py <project_root> [--auto-fix]

Exit codes:
  0 = no drift found, or --auto-fix successfully regenerated
  1 = drift found and --auto-fix was not passed (no action taken)
  2 = usage or setup error
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    args = [a for a in sys.argv[1:] if a != "--auto-fix"]
    auto_fix = "--auto-fix" in sys.argv
    if len(args) != 1:
        print("Usage: py check_about_content_drift.py <project_root> [--auto-fix]")
        sys.exit(2)

    root = Path(args[0]).resolve()
    index_path = root / "site" / "public" / "data" / "index.json"
    cache_path = root / "data" / "processed" / "f9_about_content.json"
    f9_script = root / "f9_generate_about_content.py"

    if not index_path.exists():
        print(f"ERROR: {index_path} not found - cannot check the live count.")
        sys.exit(2)

    index = json.loads(index_path.read_text(encoding="utf-8"))
    live_count = index.get("generated_stats", {}).get("n_confirmed")
    if live_count is None:
        print(f"ERROR: {index_path} has no generated_stats.n_confirmed - cannot check drift.")
        sys.exit(2)

    stored_count = None
    if not cache_path.exists():
        print(f"No cached About content yet at {cache_path}. Treating as drift (needs first generation).")
    else:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        stored_count = cached.get("n_confirmed_at_generation")
        if stored_count is None:
            print(f"{cache_path.name} predates the drift-tracking field - treating as drift (will backfill it).")

    if stored_count == live_count:
        print(f"About content is current: n_confirmed={live_count} matches the last generation.")
        sys.exit(0)

    if stored_count is None:
        print(f"Drift check: live n_confirmed={live_count}, no stored count on record.")
    else:
        print(f"Drift detected: live n_confirmed={live_count}, About content was generated at n_confirmed={stored_count}.")

    if not auto_fix:
        print("Pass --auto-fix to regenerate now, or run f9_generate_about_content.py --force yourself.")
        sys.exit(1)

    if not f9_script.exists():
        print(f"ERROR: {f9_script} not found - cannot auto-fix.")
        sys.exit(2)

    print("Auto-fixing: running f9_generate_about_content.py --force ...")
    result = subprocess.run([sys.executable, str(f9_script), str(root), "--force"])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()