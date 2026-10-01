"""A2 — selection manifests: choose sources by predicate, emit the bundle manifest.

Keeper rulings 2026-09-01 (promotion map §7): "Selector before spine compiler is
good. But ideally there would not be a spine compiler if possible. Manifest should
be authoritative." So the selector does not build a spine. It reads a small
selection file (``kind: selection``), finds the Atrium files that match, orders
and groups them, and writes an ordinary ``composite_bundle`` manifest. That
manifest is the composition record: it is committed, reviewed and rendered like
any hand-written one, and it says where it came from (its ``selection:`` block).

Selection file::

    kind: selection
    schema_version: selection_manifest_v1
    selection_id: keeper-capture-book
    emit: keeper_capture_book.composite-bundle.yaml   # relative to this file
    select:
      roots: [../../notes]  # relative to this file
      recursive: false            # or true, or a list of sub-directory names
      include: ["*.md"]
      exclude: [BEAM.md, INDEX.md, SYNTHESIS.md]
      where:                      # every key must hold; lists mean "any of"
        kind: [note]
        note_role: [keeper_capture]   # compared normalized: case, quotes, - vs _
        status: [active]
        tags_any: [governance]
        created: {from: 2025-10-01, to: 2026-09-30}
    order:
      by: created                 # created | path | title | uid
      undated: last               # first | last
      pin: [{path: a.md, position: 1}]
    group:
      by: month                   # month | year | directory | none
      divider: {title: "{month_name} {year}", subtitle: "{count} capture{plural}", force_right_page: true}
    sources:                      # per-source defaults
      chapter_opener: true        # title from the body's title H1, else frontmatter title, else file name
      include_frontmatter: none
    bundle: {...}                 # passed through: profile, presentation, render, validation, ...

Dates: ``created`` from frontmatter, else a ``YYYY-MM-DD`` in the file name,
else undated. Which one each source used is recorded in the emitted manifest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import fnmatch
import hashlib
import os
from pathlib import Path
import re
from typing import Any

import yaml

from engine.manifest_compiler import title_heading

SELECTION_KIND = "selection"
SELECTION_SCHEMA = "selection_manifest_v1"
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
_FILENAME_DATE_RE = re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})")
_SUPPORTED_WHERE = {"kind", "note_role", "status", "beam_home", "tags_any", "tags_all", "created"}


class SelectionError(ValueError):
    pass


@dataclass
class Candidate:
    path: Path
    frontmatter: dict[str, Any]
    body: str
    date: dt.date | None
    date_origin: str  # created | filename | undated
    title: str
    title_origin: str  # leading_h1 | frontmatter | filename
    has_leading_h1: bool


@dataclass
class SelectionResult:
    manifest: dict[str, Any]
    selected: list[Candidate]
    excluded: list[tuple[Path, str]] = field(default_factory=list)


def normalize_value(value: Any) -> str:
    """note_role and friends: case, surrounding quotes, and - vs _ do not distinguish."""
    return str(value).strip().strip("\"'").strip().lower().replace("-", "_").replace(" ", "_")


def _split(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        data = {}
    body = text[end + 4:]
    body = body[1:] if body.startswith("\n") else body
    return (data if isinstance(data, dict) else {}), body


def plain_title(text: str) -> str:
    """A heading's text without Markdown emphasis, code ticks or link syntax: the
    opener sets its title as plain text, so ``**x**`` would print its asterisks."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1", r"\2", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        match = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", value)
        if match:
            try:
                return dt.date(*map(int, match.groups()))
            except ValueError:
                return None
    return None


def read_candidate(path: Path) -> Candidate:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split(text)
    date, origin = _as_date(fm.get("created")), "created"
    if date is None:
        match = _FILENAME_DATE_RE.search(path.name)
        date, origin = None, "undated"
        if match:
            try:
                date, origin = dt.date(*map(int, match.groups())), "filename"
            except ValueError:
                pass
    h1 = title_heading(body)
    if h1:
        title, title_origin = plain_title(h1[2]), "leading_h1"
    elif str(fm.get("title") or "").strip():
        title, title_origin = str(fm["title"]).strip(), "frontmatter"
    else:
        title, title_origin = path.stem.replace("_", " "), "filename"
    return Candidate(path, fm, body, date, origin, title, title_origin, bool(h1))


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _matches(c: Candidate, where: dict[str, Any]) -> str | None:
    """None when ``c`` satisfies ``where``; otherwise the reason it does not."""
    fm = c.frontmatter
    for key in ("kind", "note_role", "status", "beam_home"):
        if key in where:
            wanted = {normalize_value(v) for v in _list(where[key])}
            if key not in fm:
                return f"no {key}"
            if normalize_value(fm[key]) not in wanted:
                return f"{key}={fm[key]!r}"
    tags = {normalize_value(t) for t in _list(fm.get("tags"))}
    if "tags_any" in where and not tags & {normalize_value(t) for t in _list(where["tags_any"])}:
        return "no matching tag"
    if "tags_all" in where and not {normalize_value(t) for t in _list(where["tags_all"])} <= tags:
        return "missing a required tag"
    if "created" in where:
        window = where["created"] or {}
        lo, hi = _as_date(window.get("from")), _as_date(window.get("to"))
        if c.date is None:
            return "undated"
        if (lo and c.date < lo) or (hi and c.date > hi):
            return f"created {c.date} outside window"
    return None


def _walk(root: Path, recursive: Any, include: list[str], exclude: list[str]) -> list[Path]:
    if recursive is True:
        candidates = root.rglob("*")
    elif recursive in (False, None):
        candidates = root.glob("*")
    else:
        allowed = set(_list(recursive))
        candidates = [p for p in root.rglob("*")
                      if p.parent == root or p.relative_to(root).parts[0] in allowed]
    out = []
    for p in candidates:
        if not p.is_file():
            continue
        if not any(fnmatch.fnmatch(p.name, pat) for pat in include):
            continue
        rel = p.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(p.name, pat) or fnmatch.fnmatch(rel, pat) for pat in exclude):
            continue
        out.append(p)
    return sorted(out)


def _slug(text: str, n: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n]


def _group_key(c: Candidate, by: str, root_of: dict[Path, Path]) -> tuple[str, dict[str, Any]]:
    if by == "none":
        return "", {}
    if by == "directory":
        rel = c.path.parent.relative_to(root_of[c.path]).as_posix()
        name = "." if rel == "." else rel
        return name, {"directory": name if name != "." else root_of[c.path].name}
    if c.date is None:
        return "undated", {"undated": True}
    if by == "year":
        return f"{c.date.year:04d}", {"year": c.date.year}
    if by == "month":
        return (f"{c.date.year:04d}-{c.date.month:02d}",
                {"year": c.date.year, "month": c.date.month, "month_name": MONTHS[c.date.month - 1]})
    raise SelectionError(f"group.by must be month, year, directory or none, not {by!r}")


def _format(template: str, fields: dict[str, Any]) -> str:
    try:
        return template.format(**fields)
    except (KeyError, IndexError) as exc:
        raise SelectionError(f"divider template {template!r} uses an unknown field {exc}") from None


def select(spec: dict[str, Any], *, spec_path: Path) -> SelectionResult:
    if spec.get("kind") != SELECTION_KIND or spec.get("schema_version") != SELECTION_SCHEMA:
        raise SelectionError(f"expected kind: {SELECTION_KIND}, schema_version: {SELECTION_SCHEMA}")
    base = spec_path.resolve().parent
    sel = spec.get("select") or {}
    roots = [(base / r).resolve() if not Path(r).is_absolute() else Path(r) for r in _list(sel.get("roots"))]
    if not roots:
        raise SelectionError("select.roots must name at least one directory")
    for root in roots:
        if not root.is_dir():
            raise SelectionError(f"select.roots: not a directory: {root}")
    where = sel.get("where") or {}
    unknown = set(where) - _SUPPORTED_WHERE
    if unknown:
        raise SelectionError(f"select.where: unsupported key(s) {sorted(unknown)}; supported: {sorted(_SUPPORTED_WHERE)}")
    include = _list(sel.get("include")) or ["*.md"]
    exclude = _list(sel.get("exclude"))

    root_of: dict[Path, Path] = {}
    pool: list[Candidate] = []
    excluded: list[tuple[Path, str]] = []
    for root in roots:
        for path in _walk(root, sel.get("recursive", False), include, exclude):
            if path in root_of:
                continue
            root_of[path] = root
            cand = read_candidate(path)
            reason = _matches(cand, where)
            if reason:
                excluded.append((path, reason))
            else:
                pool.append(cand)

    order = spec.get("order") or {}
    by = order.get("by", "created")
    undated_last = order.get("undated", "last") != "first"
    if by == "created":
        def key(c: Candidate):
            missing = c.date is None
            return (missing if undated_last else not missing, c.date or dt.date.min, c.path.name)
    elif by == "path":
        def key(c: Candidate):
            return (c.path.as_posix(),)
    elif by == "title":
        def key(c: Candidate):
            return (c.title.casefold(), c.path.name)
    elif by == "uid":
        def key(c: Candidate):
            return (str(c.frontmatter.get("uid", "")), c.path.name)
    else:
        raise SelectionError(f"order.by must be created, path, title or uid, not {by!r}")
    pool.sort(key=key)
    for pin in _list(order.get("pin")):
        target = (base / pin["path"]).resolve()
        found = next((c for c in pool if c.path.resolve() == target), None)
        if found is None:
            raise SelectionError(f"order.pin: {pin['path']} is not among the selected sources")
        pool.remove(found)
        pool.insert(max(0, int(pin.get("position", 1)) - 1), found)

    defaults = dict(spec.get("sources") or {})
    want_opener = defaults.pop("chapter_opener", True)
    group = spec.get("group") or {}
    group_by = group.get("by", "none")
    divider_cfg = dict(group.get("divider") or {})
    title_tpl = divider_cfg.pop("title", "{month_name} {year}" if group_by == "month" else "{year}")
    subtitle_tpl = divider_cfg.pop("subtitle", None)
    undated_title = divider_cfg.pop("undated_title", "Undated")

    groups: dict[str, list[Candidate]] = {}
    group_fields: dict[str, dict[str, Any]] = {}
    for c in pool:
        gkey, fields = _group_key(c, group_by, root_of)
        groups.setdefault(gkey, []).append(c)
        group_fields[gkey] = fields

    sources: list[dict[str, Any]] = []
    dividers: list[dict[str, Any]] = []
    seen_group = None
    for i, c in enumerate(pool, start=1):
        uid = f"{_slug(spec.get('selection_id', 'sel'), 12)}-{i:03d}-{_slug(c.path.stem)}"
        gkey, _ = _group_key(c, group_by, root_of)
        if group_by != "none" and gkey != seen_group:
            seen_group = gkey
            count = len(groups[gkey])
            fields = {**group_fields[gkey], "count": count, "plural": "" if count == 1 else "s"}
            title = undated_title if fields.get("undated") else _format(title_tpl, fields)
            divider = {"uid": f"group-{_slug(gkey) or 'root'}", "before_source_uid": uid, "title": title}
            if subtitle_tpl:
                divider["subtitle"] = _format(subtitle_tpl, fields)
            divider.update(divider_cfg)
            dividers.append(divider)
        entry: dict[str, Any] = {
            "uid": uid,
            "path": str(c.path),
            "role": "primary_anchor",
            "title": c.title,
            "order": i,
            "include_frontmatter": "none",
            "suppress_frontmatter": True,
        }
        entry["strip_body_metadata_blocks"] = True
        entry.update(defaults)
        if want_opener:
            entry["chapter_opener"] = {"title": c.title}
            if c.has_leading_h1:
                # The opener now carries the title; drop the body's copy.
                entry["strip_leading_heading"] = True
        entry["selection"] = {
            "date": c.date.isoformat() if c.date else None,
            "date_origin": c.date_origin,
            "title_origin": c.title_origin,
        }
        sources.append(entry)

    bundle = dict(spec.get("bundle") or {})
    presentation = dict(bundle.get("presentation") or {})
    # A composed book is dated by its composition unless the selection says otherwise.
    presentation.setdefault("date", dt.date.today().isoformat())
    bundle["presentation"] = presentation
    if "resource_roots" not in bundle:
        bundle["resource_roots"] = sorted({str(r) for r in roots})
    manifest: dict[str, Any] = {
        "kind": bundle.pop("kind", "composite_bundle"),
        "schema_version": bundle.pop("schema_version", "bundle_manifest_v1"),
        "bundle_id": bundle.pop("bundle_id", spec.get("selection_id", "selection")),
        **bundle,
        "sources": sources,
        "section_dividers": dividers,
        "selection": {
            "selection_file": str(spec_path.resolve()),
            "selection_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest() if spec_path.is_file() else None,
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "selected": len(pool),
            "excluded_by_predicate": len(excluded),
            "date_origins": {o: sum(1 for c in pool if c.date_origin == o)
                             for o in ("created", "filename", "undated")},
            "title_origins": {o: sum(1 for c in pool if c.title_origin == o)
                              for o in ("leading_h1", "frontmatter", "filename")},
        },
    }
    return SelectionResult(manifest=manifest, selected=pool, excluded=excluded)


def emit(spec_path: Path, out_path: Path | None = None) -> tuple[Path, SelectionResult]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    result = select(spec, spec_path=spec_path)
    if out_path is None:
        if not spec.get("emit"):
            raise SelectionError("no output path: give --output or set emit: in the selection file")
        out_path = spec_path.resolve().parent / spec["emit"]
    # Recorded relative to the manifest, so the record survives a checkout move.
    result.manifest["selection"]["selection_file"] = os.path.relpath(
        spec_path.resolve(), out_path.resolve().parent
    )
    header = (
        f"# Composed by `python3 -m cli select {spec_path.name}` (A2 selection manifest).\n"
        "# This file is the authoritative composition record: review and commit it; re-run the\n"
        "# selector to recompose. The `selection:` block says what produced it.\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        header + yaml.safe_dump(result.manifest, sort_keys=False, allow_unicode=True, width=200),
        encoding="utf-8",
    )
    return out_path, result
