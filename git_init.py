import os
import stat
import sys
import subprocess
import shutil
from pathlib import Path

GITIGNORE = """# --- Python ---
__pycache__/
*.pyc

# --- Superseded/scratch pipeline scripts, not part of the live pipeline ---
# (see f6_orchestrator.py for the scripts that actually run)
w[0-9]*.py
deliver*.py
diag[0-9]*.py
patch_*.py
fix_*.py
make_*.py
write_*.py
f2_fetch_lightcurves.py
f2b_fetch_lightcurves.py
f3_vet.py
f3b_vet.py
f3c_vet.py
f3d_vet.py
f3e_vet.py
f3f_vet.py
f3g_vet.py
f3h_vet.py
f4b_novelty.py
f4c_novelty.py
f4d_novelty.py
f4e_novelty.py
diag_check.py
diag_depth.py
diag_epoch.py
diag_epochs.py
diag_recheck2.py
diag_robust.py
diag_scan10.py

# --- Pipeline working data: regenerated fresh by each run, never needs to
# persist between runs. What must persist (sample history, vetting result
# CSVs, catalogs, dossiers, the deployed site data) is NOT listed here. ---
/data/raw/
/data/lightcurves/
/data/pixel_check/
/data/logs/

# --- Next.js site ---
/site/node_modules/
/site/.next/
/site/out/
/site/.env*.local
"""

REQUIREMENTS = """# star-vetter pipeline dependencies.
# Left unpinned on purpose: pip resolves the latest mutually
# compatible versions at the time each GitHub Actions run installs
# them, which is simpler to maintain than hand-pinning versions.
numpy
pandas
astropy
astroquery
lightkurve
matplotlib
"""


def run(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, check=check,
                           capture_output=True, text=True)


def remove_git_dir(path):
    # Git marks many of its own object files read-only, especially on
    # Windows. shutil.rmtree cannot delete a read-only file until that
    # flag is cleared, so walk the tree and clear it everywhere first.
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            p = os.path.join(root, name)
            try:
                os.chmod(p, stat.S_IWRITE)
            except OSError:
                pass
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    shutil.rmtree(path)


def main():
    if len(sys.argv) != 2:
        print("Usage: py git_init.py <project_root>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.exists():
        print(f"ERROR: {root} does not exist.")
        sys.exit(1)

    site_git = root / "site" / ".git"
    outer_git = root / ".git"

    # 1. Strip the embedded repo under site/, if present. Without this,
    # a git init at the root would record "site" as an empty gitlink
    # instead of tracking the files inside it.
    if site_git.exists():
        try:
            remove_git_dir(site_git)
            print(f"Removed embedded repo: {site_git}")
        except OSError as e:
            print(f"\nERROR: could not remove {site_git}: {e}")
            print("Close any program that might have a file open in there")
            print("(a running dev server, an editor, antivirus scan), then")
            print("delete it manually and re-run this script:")
            print(f'  Remove-Item -Recurse -Force "{site_git}"')
            sys.exit(1)
    else:
        print("No embedded site/.git found (already clean).")

    # 2. Write .gitignore and requirements.txt (overwritten every run,
    # so re-running this script after editing the lists above is safe).
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
    print("Wrote .gitignore")
    (root / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8", newline="\n")
    print("Wrote requirements.txt")

    # 3. Initialize git at the root, if not already done.
    if not outer_git.exists():
        r = run(["git", "init"], cwd=root)
        print(r.stdout.strip())
    else:
        print("Git repo already initialized at project root, skipping init.")

    # 4. Make sure git knows who is committing. If not, stop with a
    # clear instruction rather than letting the commit fail cryptically.
    name_check = run(["git", "config", "user.name"], cwd=root, check=False)
    email_check = run(["git", "config", "user.email"], cwd=root, check=False)
    if not name_check.stdout.strip() or not email_check.stdout.strip():
        print("\nERROR: git does not know your name/email yet.")
        print("Run these two commands once, then re-run this script:")
        print('  git config --global user.name "Your Name"')
        print('  git config --global user.email "you@example.com"')
        sys.exit(1)

    # 5. Stage everything (the .gitignore above keeps the big/regenerable
    # stuff out) and commit if there is anything new to commit.
    run(["git", "add", "."], cwd=root)
    status = run(["git", "status", "--porcelain"], cwd=root)
    if not status.stdout.strip():
        print("\nNothing new to commit (working tree already matches the last commit).")
    else:
        commit_msg = "Initial commit: star-vetter pipeline + site"
        r = run(["git", "commit", "-m", commit_msg], cwd=root)
        print(r.stdout.strip())

    # 6. Make sure the branch is named "main" (older local git installs
    # still default a fresh init to "master").
    branch = run(["git", "branch", "--show-current"], cwd=root).stdout.strip()
    if branch and branch != "main":
        run(["git", "branch", "-M", "main"], cwd=root)
        print(f"Renamed branch '{branch}' to 'main'")

    # 7. Report what actually ended up tracked, so this can be checked
    # against what was intended before anything is pushed anywhere.
    tracked = run(["git", "ls-files"], cwd=root).stdout.splitlines()
    py_tracked = sorted(f for f in tracked if f.endswith(".py") and "/" not in f)
    print(f"\n{'=' * 70}")
    print(f"Tracked files: {len(tracked)} total")
    print(f"Tracked top-level .py scripts ({len(py_tracked)}):")
    for f in py_tracked:
        print(f"  {f}")
    size = run(["git", "count-objects", "-v"], cwd=root).stdout
    print(f"\n{size.strip()}")
    print(f"{'=' * 70}")
    print("\nNext steps (after you create the empty GitHub repo):")
    print("  git remote add origin <YOUR_REPO_URL>")
    print("  git push -u origin main")


if __name__ == "__main__":
    main()
