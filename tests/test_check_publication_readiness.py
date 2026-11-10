import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_publication_readiness as cr  # noqa: E402


def test_empty_tree_is_not_ready(tmp_path):
    res = cr.analysis_checks(tmp_path)
    assert res and not all(r["ok"] for r in res)
    assert any(r["check"].startswith("RNAAS note exists") for r in res)


def test_overclaim_phrase_is_caught(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rnaas_note.md").write_text("We discovered 307 new binary stars.\n", encoding="utf-8")
    res = {r["check"]: r for r in cr.analysis_checks(tmp_path)}
    r = res["no overclaiming phrases in the note or site pages"]
    assert not r["ok"] and "new binary stars" in r["detail"]


def test_author_actions_count_unfilled_fields_and_days(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rnaas_note.md").write_text("a [[x]] b [[y]]\n", encoding="utf-8")
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    items = dict(cr.author_actions(tmp_path, now=now))
    assert any("Fill the 2 [[...]] fields" in k for k in items)
    assert any("16 days before Year 9" in k for k in items)
    assert not any(items.values())          # nothing is ever marked done automatically here


def test_year9_jd_matches_the_calendar():
    assert abs(cr.JD_YEAR9_START - 2461370.5) < 1e-6
