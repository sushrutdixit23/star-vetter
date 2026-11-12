"""Guards on .github/workflows/pipeline.yml (text checks, so no YAML library is needed).

2026-11-12: the first complete run in two weeks failed only because the Vercel account had an overdue balance,
and a push made with GITHUB_TOKEN does not start the Pages workflow. These checks keep the two fixes in place.
"""
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")


def block(name):
    """The text of the step called `name`, up to the next step."""
    start = TEXT.index("      - name: " + name)
    nxt = TEXT.find("\n      - name: ", start + 1)
    nxt2 = TEXT.find("\n      # ", start + 1)
    ends = [e for e in (nxt, nxt2) if e != -1]
    return TEXT[start:min(ends) if ends else len(TEXT)]


def test_vercel_failure_does_not_fail_the_run_but_is_reported():
    deploy = block("Deploy to Vercel")
    assert "continue-on-error: true" in deploy
    assert "id: vercel" in deploy
    warn = block("Say so when the Vercel deploy failed")
    assert "steps.vercel.outcome == 'failure'" in warn
    assert "::warning" in warn and "GITHUB_STEP_SUMMARY" in warn


def test_pages_is_started_after_a_data_commit_only():
    commit = block("Commit pipeline results")
    assert "id: commit" in commit and 'committed=true' in commit and "GITHUB_OUTPUT" in commit
    pages = block("Publish to GitHub Pages")
    assert "steps.commit.outputs.committed == 'true'" in pages
    assert "refs/heads/main" in pages
    assert "gh workflow run pages.yml" in pages


def test_workflow_may_dispatch_other_workflows():
    head = TEXT.split("jobs:")[0]
    assert "actions: write" in head and "contents: write" in head


def test_only_main_commits_and_publishes():
    for name in ("Commit pipeline results", "Deploy to Vercel", "Publish to GitHub Pages"):
        assert "refs/heads/main" in block(name), name
