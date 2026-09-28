"""Build identity for bound artifacts: build ledger, git stamp, managed regions.

Promoted from the Codex 0 build (``codex0_v5/build/stamp_colophon.py``,
2026-09-28). A bound artifact claims a build number, stamps the git head of the
tree it rendered from into its own sources once, and records the render at the
moment it happens. Nobody has to remember to write the number down.

What is generic and lives here:

- **The build ledger.** A YAML file carrying ``next_build`` and a ``builds`` list.
  Claiming is idempotent per run: re-claiming the same run reuses its number and
  refreshes the entry. The human-authored comment header survives every rewrite.
- **The run-id number guard.** Run ids are caller-chosen and tend to embed the
  number the caller expects. If a run id embeds ``build<N>`` and the ledger is
  claiming a different number, refuse before writing, so a refused launch burns
  no number and ``generated/`` never lies about its build.
- **The honest hash.** The stamped head carries ``-dirty`` whenever the scoped
  tree has uncommitted changes, because a bare hash would name a tree that is not
  the one that rendered. ``require_clean`` turns that into a refusal (for the
  bind; a proof may carry ``-dirty``).
- **Managed regions.** ``<!-- NAME:BEGIN ... -->`` / ``<!-- NAME:END -->`` blocks
  rewritten wholesale. The anchor must already exist and occur exactly once; a
  source that cannot be stamped is never silently skipped.
- **One stamp per build (CC14).** Every artifact of one build must carry a
  byte-identical stamp line. Two distinct stamps mean the sources moved mid-build
  and the build is a chimera.

What is not generic and stays with the work: which files carry the stamp, what
the stamp line says, and any prose the work derives from the build number.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


class BuildStampError(RuntimeError):
    """Loud failure: a source could not be stamped or a build could not be claimed."""


# ---------------------------------------------------------------------------
# Managed regions
# ---------------------------------------------------------------------------

def region_markers(name: str) -> tuple[str, str]:
    """Return the (begin-prefix, end) markers for a managed region ``name``."""
    return f"<!-- {name}:BEGIN", f"<!-- {name}:END -->"


def region_pattern(name: str) -> re.Pattern[str]:
    """Regex matching one whole managed region, markers included."""
    n = re.escape(name)
    return re.compile(rf"<!-- {n}:BEGIN.*?{n}:END -->", re.DOTALL)


def managed_block(name: str, body: str, *, managed_by: str) -> str:
    """Render a managed region carrying ``body`` between its markers."""
    begin, end = region_markers(name)
    return (
        f"{begin} — managed by {managed_by}, do not hand-edit between markers -->\n"
        f"{body}\n"
        f"{end}"
    )


def rewrite_managed_region(
    path: Path,
    name: str,
    block: str,
    *,
    what: str | None = None,
    missing_hint: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Replace the one managed region ``name`` in ``path`` with ``block``.

    Returns True when the file content changed (always False on ``dry_run``).
    Raises BuildStampError when the file is missing, the anchor is absent, or the
    region does not occur exactly once.
    """
    what = what or name
    path = Path(path)
    if not path.exists():
        raise BuildStampError(f"stamp source not found: {path}")
    begin, end = region_markers(name)
    text = path.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        hint = missing_hint or (
            f"  expected a managed block delimited by:\n"
            f"    {begin} ... {end}\n"
            f"  refusing to render a source that cannot be stamped."
        )
        raise BuildStampError(f"missing {what} anchor in {path}\n{hint}")
    new_text, n = region_pattern(name).subn(lambda _m: block, text)
    if n != 1:
        raise BuildStampError(f"expected exactly one {what} block in {path}, found {n}.")
    if dry_run or new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Git identity
# ---------------------------------------------------------------------------

def tree_dirty(repo_root: Path, scope: Path | str | None = None) -> list[str]:
    """Uncommitted paths under ``scope`` (relative to ``repo_root``), if any.

    Scope it to the work, not the whole repository: in a shared repository other
    lanes write constantly, and a tainted stamp should mean "the work was edited
    and not committed", never "a cron job appended a row".
    """
    cmd = ["git", "-C", str(repo_root), "status", "--porcelain"]
    if scope is not None:
        cmd += ["--", str(scope)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise BuildStampError(f"could not read git status for {repo_root}: {exc}") from exc
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def git_head_short(
    repo_root: Path,
    scope: Path | str | None = None,
    *,
    require_clean: bool = False,
) -> str:
    """Short HEAD, suffixed ``-dirty`` when the scoped tree is not clean."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise BuildStampError(f"could not read git HEAD for {repo_root}: {exc}") from exc
    sha = out.stdout.strip()
    dirty = tree_dirty(repo_root, scope)
    if not dirty:
        return sha
    if require_clean:
        listing = "\n".join(f"    {ln}" for ln in dirty[:20])
        more = f"\n    ... and {len(dirty) - 20} more" if len(dirty) > 20 else ""
        raise BuildStampError(
            f"--require-clean: the tree has {len(dirty)} uncommitted "
            f"change(s), so git {sha} does not identify the text being "
            f"rendered.\n{listing}{more}\n"
            f"  Commit the sources (or drop --require-clean for a proof)."
        )
    return f"{sha}-dirty"


def render_datetime() -> str:
    """Local render time as printed in stamps, e.g. ``2026-08-15 05:25 EDT``."""
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


# ---------------------------------------------------------------------------
# Build ledger
# ---------------------------------------------------------------------------

def _leading_comment(text: str) -> str:
    kept = []
    for ln in text.splitlines():
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            kept.append(ln)
        else:
            break
    header = "\n".join(kept).rstrip("\n")
    return header + "\n\n" if header else ""


def run_id_number_guard(run: str, build: int) -> None:
    """Refuse a run id that embeds a build number other than the one claimed."""
    embedded = re.search(r"build(\d+)", run)
    if embedded and int(embedded.group(1)) != build:
        raise BuildStampError(
            f"run id '{run}' embeds build{embedded.group(1)} but the "
            f"ledger is claiming build {build} (another run took "
            f"{embedded.group(1)} first). Relaunch with a run id naming "
            f"{build}, or one carrying no number, so generated/ does not "
            "lie about its build."
        )


@dataclass
class Claim:
    build: int
    entry: dict[str, Any]
    reused: bool


@dataclass
class BuildLedger:
    """A YAML build ledger: ``next_build`` plus a ``builds`` list of entries."""

    path: Path
    data: dict[str, Any] = field(default_factory=dict)
    header: str = ""

    @classmethod
    def load(cls, path: Path) -> "BuildLedger":
        import yaml

        path = Path(path)
        if not path.exists():
            raise BuildStampError(f"build ledger not found: {path}")
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise BuildStampError(f"build ledger is not a mapping: {path}")
        return cls(path=path, data=data, header=_leading_comment(text))

    @property
    def builds(self) -> list[dict[str, Any]]:
        return self.data.setdefault("builds", [])

    @property
    def next_build(self) -> int:
        return int(self.data.get("next_build", len(self.builds) + 1))

    def find_run(self, run: str, **match: Any) -> dict[str, Any] | None:
        """The entry whose ``run_dir`` (or its last path segment) is ``run``.

        Extra keyword pairs must also match; an entry lacking a key matches by
        default, so older entries written before a key existed still resolve.
        """
        for entry in self.builds:
            rd = str(entry.get("run_dir", ""))
            if rd != run and rd.rsplit("/", 1)[-1] != run:
                continue
            if all(str(entry.get(k, v)) == str(v) for k, v in match.items()):
                return entry
        return None

    def claim(
        self,
        run: str,
        entry: dict[str, Any],
        *,
        match: dict[str, Any] | None = None,
        refresh: Iterable[str] = ("date", "git_head", "rendered"),
    ) -> Claim:
        """Claim a build number for ``run``, idempotently.

        A run already in the ledger keeps its number; only the ``refresh`` keys of
        its entry are updated from ``entry``. A new run
        takes ``next_build`` after the run-id number guard, and is appended as
        ``build`` followed by the given fields in order (``run_dir`` is added at
        the end if ``entry`` does not place it).
        """
        existing = self.find_run(run, **(match or {}))
        if existing is not None:
            for key in refresh:
                if key in entry:
                    existing[key] = entry[key]
            return Claim(build=int(existing["build"]), entry=existing, reused=True)
        build = self.next_build
        taken = next((e for e in self.builds if str(e.get("build")) == str(build)), None)
        if taken is not None:
            raise BuildStampError(
                f"{self.path}: next_build is {build}, but build {build} is already recorded "
                f"(run_dir {taken.get('run_dir')!r}). An entry was appended without advancing "
                f"next_build; set next_build past the highest recorded build before stamping."
            )
        run_id_number_guard(run, build)
        new_entry: dict[str, Any] = {"build": build, **entry}
        new_entry.setdefault("run_dir", run)
        self.builds.append(new_entry)
        self.data["next_build"] = build + 1
        return Claim(build=build, entry=new_entry, reused=False)

    def dump(self) -> str:
        import yaml

        return self.header + yaml.safe_dump(
            self.data, sort_keys=False, allow_unicode=True, width=100
        )

    def save(self) -> None:
        self.path.write_text(self.dump(), encoding="utf-8")


# ---------------------------------------------------------------------------
# One stamp per build (CC14)
# ---------------------------------------------------------------------------

def distinct_stamps(paths: Iterable[Path], pattern: str | re.Pattern[str]) -> list[str]:
    """Sorted distinct lines matching ``pattern`` across ``paths``.

    One build is sound only when this returns exactly one line.
    """
    rx = re.compile(pattern, re.MULTILINE) if isinstance(pattern, str) else pattern
    found: set[str] = set()
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if rx.search(line):
                found.add(line)
    return sorted(found)
