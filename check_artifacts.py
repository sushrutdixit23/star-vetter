import json
from pathlib import Path
root = Path.cwd()
idx = json.loads((root / "site/public/data/index.json").read_text(encoding="utf-8"))
tics = [str(c["tic"]) for c in idx["candidates"]]
checks = [
    ("site/public/data/detail", "TIC{}.json"),
    ("site/public/dossiers", "TIC{}_dossier.pdf"),
    ("data/dossiers", "TIC{}_dossier.pdf"),
]
for folder, pat in checks:
    d = root / folder
    if not d.exists():
        print("[MISS] folder not found:", folder)
        continue
    missing = [t for t in tics if not (d / pat.format(t)).exists()]
    tag = "[OK]" if not missing else "[MISS]"
    print(tag, folder, "%d/%d" % (len(tics) - len(missing), len(tics)), " ".join(missing))