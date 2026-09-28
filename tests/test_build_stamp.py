from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.build_stamp import (
    BuildLedger,
    BuildStampError,
    distinct_stamps,
    git_head_short,
    managed_block,
    rewrite_managed_region,
    run_id_number_guard,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "a.md").write_text("a\n")
    (tmp_path / "other.txt").write_text("x\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_managed_block_round_trip(tmp_path):
    src = tmp_path / "colophon.md"
    src.write_text("before\n" + managed_block("X-STAMP", "old", managed_by="tool.py") + "\nafter\n")
    changed = rewrite_managed_region(src, "X-STAMP", managed_block("X-STAMP", "new", managed_by="tool.py"))
    assert changed
    text = src.read_text()
    assert "new" in text and "old" not in text
    assert text.startswith("before\n<!-- X-STAMP:BEGIN — managed by tool.py, do not hand-edit")
    assert text.endswith("<!-- X-STAMP:END -->\nafter\n")
    # Rewriting the same content is a no-op.
    assert not rewrite_managed_region(src, "X-STAMP", managed_block("X-STAMP", "new", managed_by="tool.py"))


def test_managed_region_missing_anchor_fails_loud(tmp_path):
    src = tmp_path / "c.md"
    src.write_text("no anchor\n")
    with pytest.raises(BuildStampError, match="missing X-STAMP anchor"):
        rewrite_managed_region(src, "X-STAMP", "b")


def test_managed_region_must_occur_once(tmp_path):
    src = tmp_path / "c.md"
    block = managed_block("X-STAMP", "b", managed_by="t")
    src.write_text(block + "\n" + block + "\n")
    with pytest.raises(BuildStampError, match="exactly one"):
        rewrite_managed_region(src, "X-STAMP", block)


def test_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "c.md"
    src.write_text(managed_block("X-STAMP", "old", managed_by="t"))
    before = src.read_text()
    assert not rewrite_managed_region(src, "X-STAMP", managed_block("X-STAMP", "new", managed_by="t"), dry_run=True)
    assert src.read_text() == before


def test_git_head_dirty_is_scoped(repo):
    sha = git_head_short(repo, "work")
    assert sha and not sha.endswith("-dirty")
    (repo / "other.txt").write_text("changed\n")
    assert git_head_short(repo, "work") == sha  # outside the scope
    (repo / "work" / "a.md").write_text("changed\n")
    assert git_head_short(repo, "work") == f"{sha}-dirty"
    with pytest.raises(BuildStampError, match="require-clean"):
        git_head_short(repo, "work", require_clean=True)


LEDGER = """# Human header survives.
# second line

next_build: 7
builds:
- build: 6
  date: '2026-08-01'
  run_dir: volumes-a
  edition: johannah
  git_head: abc
  rendered: then
  notes: first
"""


def test_ledger_claims_next_and_preserves_header(tmp_path):
    path = tmp_path / "ledger.yaml"
    path.write_text(LEDGER)
    ledger = BuildLedger.load(path)
    claim = ledger.claim("volumes-b", {"date": "d", "run_dir": "volumes-b", "edition": "johannah", "git_head": "h", "rendered": "r", "notes": "n"})
    assert (claim.build, claim.reused) == (7, False)
    assert list(claim.entry) == ["build", "date", "run_dir", "edition", "git_head", "rendered", "notes"]
    ledger.save()
    text = path.read_text()
    assert text.startswith("# Human header survives.\n# second line\n\n")
    reloaded = BuildLedger.load(path)
    assert reloaded.next_build == 8


def test_ledger_reclaim_is_idempotent_and_refreshes_only_named_keys(tmp_path):
    path = tmp_path / "ledger.yaml"
    path.write_text(LEDGER)
    ledger = BuildLedger.load(path)
    claim = ledger.claim(
        "volumes-a",
        {"date": "new-d", "git_head": "new-h", "rendered": "new-r", "notes": "default"},
        match={"edition": "johannah"},
    )
    assert (claim.build, claim.reused) == (6, True)
    assert claim.entry["git_head"] == "new-h"
    assert claim.entry["notes"] == "first"  # not in refresh
    assert ledger.next_build == 7


def test_ledger_edition_mismatch_is_a_new_run(tmp_path):
    path = tmp_path / "ledger.yaml"
    path.write_text(LEDGER)
    ledger = BuildLedger.load(path)
    claim = ledger.claim("volumes-a", {"edition": "witness"}, match={"edition": "witness"})
    assert (claim.build, claim.reused) == (7, False)


def test_ledger_refuses_to_issue_a_recorded_number(tmp_path):
    path = tmp_path / "ledger.yaml"
    path.write_text(LEDGER.replace("next_build: 7", "next_build: 6"))
    ledger = BuildLedger.load(path)
    with pytest.raises(BuildStampError, match="build 6 is already recorded"):
        ledger.claim("volumes-new", {"date": "d"})
    # Re-stamping the run that owns the number is still fine.
    assert ledger.claim("volumes-a", {"date": "d"}).build == 6


def test_run_id_number_guard():
    run_id_number_guard("build70-floating", 70)
    run_id_number_guard("volumes-no-number", 70)
    with pytest.raises(BuildStampError, match="embeds build69"):
        run_id_number_guard("build69-all-plates-floating", 70)


def test_distinct_stamps(tmp_path):
    pattern = r"^\*.*· git .*\.\*$"
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("text\n*Proof build 9 · git abc · rendered t.*\n")
    b.write_text("*Proof build 9 · git abc · rendered t.*\nmore\n")
    assert distinct_stamps([a, b], pattern) == ["*Proof build 9 · git abc · rendered t.*"]
    b.write_text("*Proof build 9 · git abd · rendered t.*\n")
    assert len(distinct_stamps([a, b], pattern)) == 2
