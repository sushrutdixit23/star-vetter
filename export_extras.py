import sys
import json
import shutil
from datetime import datetime
from pathlib import Path

# Copies the real PDF dossiers (written by f5_dossier.py) into the site so
# visitors can download them, and records when the orchestrator last ran
# (read from the timestamped log files it writes) so the site can show a
# real "last run" time instead of a fake "live" badge.


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_extras.py <project_root>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    site_data = root / "site" / "public" / "data"
    index_path = site_data / "index.json"
    if not index_path.exists():
        print(f"ERROR: {index_path} not found - run export_site_data.py first.")
        sys.exit(1)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    tics = [int(c["tic"]) for c in index["candidates"]]

    # --- dossier PDFs ---
    src_dir = root / "data" / "dossiers"
    dst_dir = root / "site" / "public" / "dossiers"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = []
    for tic in tics:
        src = src_dir / f"TIC{tic}_dossier.pdf"
        if src.exists():
            shutil.copyfile(src, dst_dir / src.name)
            copied += 1
        else:
            missing.append(tic)
    combined_src = src_dir / "star_vetter_dossiers.pdf"
    has_combined = combined_src.exists()
    if has_combined:
        shutil.copyfile(combined_src, dst_dir / combined_src.name)
    print(f"Copied {copied}/{len(tics)} dossier PDFs" + (" plus the combined PDF." if has_combined else "."))
    if missing:
        print(f"  WARNING: no dossier PDF found for: {missing} (run f5_dossier.py to build them)")

    # --- last orchestrator run ---
    log_dir = root / "data" / "logs"
    logs = sorted(log_dir.glob("orchestrator_*.log")) if log_dir.exists() else []
    last_run = None
    for log in reversed(logs):
        stamp = log.stem.replace("orchestrator_", "")
        try:
            dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S").astimezone()
        except ValueError:
            continue
        offset = dt.strftime("%z")
        offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "local time"
        last_run = {
            "iso": dt.isoformat(),
            "display": dt.strftime("%d %b %Y, %H:%M") + f" ({offset})",
            "log_file": log.name,
        }
        break
    if last_run:
        print(f"Last orchestrator run: {last_run['display']} ({last_run['log_file']})")
    else:
        print("WARNING: no orchestrator logs found under data/logs - last run time left blank.")

    meta = {
        "last_run": last_run,
        "runs_logged": len(logs),
        "dossiers_available": [t for t in tics if t not in missing],
        "combined_dossier": "/dossiers/star_vetter_dossiers.pdf" if has_combined else None,
    }
    out = site_data / "site_meta.json"
    out.write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()