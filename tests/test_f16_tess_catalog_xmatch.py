import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f16_tess_catalog_xmatch as x  # noqa: E402


def test_parse_tics_skips_comments_and_headers():
    text = "#comment\nTIC\n---\n 123456\n98765432\nnot a number\n12\n"
    assert x.parse_tics(text) == {123456, 98765432}


def test_build_reports_footprint_separately_from_matches():
    out = x.build({1, 2, 3, 4}, {"a": {1, 9}, "b": {7}}, {"a": {1, 2, 3}}, {"a": "A"})
    a = next(r for r in out["catalogs"] if r["key"] == "a")
    b = next(r for r in out["catalogs"] if r["key"] == "b")
    assert a["n_in_catalog"] == 1 and a["candidates_in_catalog"] == [1]
    assert a["n_in_parent_sample"] == 3 and a["parent_size"] == 3
    assert b["n_in_catalog"] == 0 and b["n_in_parent_sample"] is None
    assert out["candidates"] == 4 and out["not_covered"]


class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_retries_empty_answers_and_never_caches_them(tmp_path, monkeypatch):
    good = "#h\n" + "\n".join(str(1000000 + i) for i in range(150))
    answers = iter(["#empty\n", "#empty\n", good])
    monkeypatch.setattr(x.urllib.request, "urlopen", lambda *a, **k: _Resp(next(answers)))
    monkeypatch.setattr(x.time, "sleep", lambda s: None)
    cache = tmp_path / "c.txt"
    tics = x.fetch_tics("J/x", cache)
    assert len(tics) == 150 and cache.exists()
    assert len(x.parse_tics(cache.read_text())) == 150


def test_fetch_gives_up_without_writing_a_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(x.urllib.request, "urlopen", lambda *a, **k: _Resp("#empty\n"))
    monkeypatch.setattr(x.time, "sleep", lambda s: None)
    cache = tmp_path / "c.txt"
    with pytest.raises(RuntimeError):
        x.fetch_tics("J/x", cache, attempts=3)
    assert not cache.exists()
