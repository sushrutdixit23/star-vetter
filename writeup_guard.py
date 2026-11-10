"""Language guard for text that is published on the site.

The site's display layer (site/src/lib/writeup.ts) refuses to show any text
that contains discovery or certainty language. This is the same rule on the
Python side, so such text is never even published in the JSON files. The two
lists must match: tests/test_writeup_guard.py compares them.

Usage (one-off scrub of already-published write-ups):
    python writeup_guard.py --scrub <project_root>
"""

import json
import re
import sys
from pathlib import Path

# Keep in sync with BLOCKED in site/src/lib/writeup.ts (a test checks this).
BLOCKED = [
    "discover",
    "genuine",
    "astronomer",
    "previously unknown",
    "escaped detection",
    "our catalog",
    "catalog of known",
    "high confidence",
    "highly likely",
    "real astronomical",
    "independent methods",
    "independent checks confirm",
    "new find",
    "ground-based",
    "follow-up observations confirmed",
    "high-confidence",
    "unprecedented",
    "extraordinary",
    "remarkabl",
    "confirming the binary",
    "confirms the binary",
    "confirmed binary",
    "rare insight",
    "cosmic dance",
]

def is_safe(text, tic=None):
    """True if text is publishable: no blocked phrase, and it does not name a
    different star than the page it is for."""
    if not text or not text.strip():
        return False
    lower = text.lower()
    if any(b in lower for b in BLOCKED):
        return False
    if tic is not None:
        for m in re.findall(r"TIC ?([0-9]+)", text):
            if m != str(tic):
                return False
    return True


def scrub(root):
    """Null out already-published detail write-ups that fail the guard."""
    detail = Path(root) / "site/public/data/detail"
    n_total = n_bad = 0
    for f in sorted(detail.glob("TIC*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        w = d.get("writeup")
        if not w:
            continue
        n_total += 1
        if not is_safe(w, d.get("tic")):
            d["writeup"] = None
            f.write_text(json.dumps(d, separators=(",", ":"), ensure_ascii=True), encoding="utf-8", newline="\n")
            n_bad += 1
    print(f"{n_total} write-ups checked, {n_bad} removed")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--scrub":
        scrub(sys.argv[2])
    else:
        print(__doc__)
