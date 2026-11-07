import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import writeup_guard as wg  # noqa: E402


def ts_blocked():
    src = (ROOT / "site/src/lib/writeup.ts").read_text(encoding="utf-8")
    body = re.search(r"const BLOCKED = \[(.*?)\];", src, re.S).group(1)
    return re.findall(r'"([^"]+)"', body)


def test_python_and_site_lists_are_identical():
    assert wg.BLOCKED == ts_blocked()


def test_blocks_discovery_and_hype_language():
    for bad in [
        "A newly discovered eclipsing binary.",
        "A high-confidence secondary eclipse.",
        "Detected with unprecedented clarity.",
        "This confirms the binary nature of the pair.",
        "A previously unknown system.",
    ]:
        assert not wg.is_safe(bad), bad


def test_accepts_plain_candidate_language_and_blocks_wrong_tic():
    ok = "TIC 123 is a candidate. Its period is 2.5 days."
    assert wg.is_safe(ok, 123)
    assert not wg.is_safe(ok, 456)
    assert not wg.is_safe("")
    assert not wg.is_safe(None)


def test_published_standouts_pass_the_guard():
    d = json.loads((ROOT / "site/public/data/discoveries.json").read_text(encoding="utf-8"))
    for x in d["discoveries"]:
        assert wg.is_safe(x["headline"], x["tic"]) and wg.is_safe(x["blurb"], x["tic"]), x["tic"]


def test_published_detail_writeups_pass_the_guard():
    bad = []
    for f in (ROOT / "site/public/data/detail").glob("TIC*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("writeup") and not wg.is_safe(d["writeup"], d["tic"]):
            bad.append(d["tic"])
    assert bad == []
