"""A cross-match that did not finish must never be worded as "no match" on a candidate page (text check)."""
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "site" / "src" / "app" / "candidates" / "[tic]" / "page.tsx").read_text(encoding="utf-8")


def test_no_match_wording_needs_an_explicit_no_match_verdict():
    i = SRC.index("No match in the catalogs searched")
    line_start = SRC.rfind("\n", 0, i)
    line = SRC[line_start:i]
    assert 'n.verdict === "NO_MATCH"' in line


def test_incomplete_is_worded_as_not_checked():
    assert "was incomplete for this star" in SRC and "not checked yet" in SRC
