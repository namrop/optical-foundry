"""The vendored glyph registry: render-only substitutes for characters the profile fonts lack.

Keeper ruling 2026-09-01 23:32 EDT (promotion map §7): "The glyphs should grow to
support what is needed." The fail-closed missing-character lint stays; instead of
relaxing it, the registry grows to cover what the corpus actually uses.

Two kinds of entry, both recorded in ``profiles/40_latex_import/assets/glyph_registry.json``:

* **emoji** — a Unicode emoji sequence lowered to a vendored vector image (Noto
  Emoji SVG converted to PDF). The source text keeps its emoji; the PDF shows the
  image. Host emoji fonts are never required.
* **fallback fonts** — a small Foundry-owned font file subset to exactly the
  registered code points (CJK ideographs and kana, so far). Runs of those
  characters are set in it, so they stay real, searchable text.

``grow_registry`` (CLI ``glyphs grow``) adds what a set of source files needs, from
pinned upstream sources; ``scan_needed`` (CLI ``glyphs scan``) reports it without
writing. Registry paths are relative to the profile assets root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = _REPO_ROOT / "profiles" / "40_latex_import" / "assets"
REGISTRY_PATH = ASSETS_ROOT / "glyph_registry.json"
REGISTRY_SCHEMA = "glyph_registry_v1"

VS16 = 0xFE0F
ZWJ = 0x200D

# Scripts that take a fallback font rather than an image: they are text.
_FALLBACK_RANGES = (
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0xFF66, 0xFF9F),  # Halfwidth Katakana
)

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_INLINE_CODE_RE = re.compile(r"(`+)(.*?)(\1)")


def is_fallback_codepoint(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _FALLBACK_RANGES)


# ──────────────────────────────────────────────
#  Registry I/O
# ──────────────────────────────────────────────


def load_registry(path: Path | None = None) -> dict[str, Any]:
    path = path or REGISTRY_PATH
    if not path.is_file():
        return {"schema": REGISTRY_SCHEMA, "emoji": {}, "fallback_fonts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != REGISTRY_SCHEMA:
        raise ValueError(f"{path}: not a {REGISTRY_SCHEMA} file")
    data.setdefault("emoji", {})
    data.setdefault("fallback_fonts", [])
    return data


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    path = path or REGISTRY_PATH
    data = dict(data)
    data["emoji"] = dict(sorted(data["emoji"].items()))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def emoji_key(sequence: Iterable[int]) -> str:
    """Noto's file-name key for a sequence: lowercase hex, VS16 dropped, joined by ``_``."""
    return "_".join(f"{cp:x}" for cp in sequence if cp != VS16)


def key_sequence(key: str) -> tuple[int, ...]:
    return tuple(int(part, 16) for part in key.split("_"))


# ──────────────────────────────────────────────
#  Matching (shared by scan, grow and render)
# ──────────────────────────────────────────────


@dataclass
class _Trie:
    children: dict[int, "_Trie"] = field(default_factory=dict)
    key: str | None = None


def _build_trie(keys: Iterable[str]) -> _Trie:
    root = _Trie()
    for key in keys:
        node = root
        for cp in key_sequence(key):
            node = node.children.setdefault(cp, _Trie())
        node.key = key
    return root


def _match_at(text: str, i: int, trie: _Trie) -> tuple[str, int] | None:
    """Longest registered sequence starting at ``text[i]``; VS16 is optional anywhere in it."""
    node = trie
    best: tuple[str, int] | None = None
    j = i
    while j < len(text):
        cp = ord(text[j])
        if cp == VS16 and j > i:
            j += 1
            if node.key is not None:
                best = (node.key, j)
            continue
        nxt = node.children.get(cp)
        if nxt is None:
            break
        node = nxt
        j += 1
        if node.key is not None:
            # absorb one trailing VS16
            end = j + 1 if j < len(text) and ord(text[j]) == VS16 else j
            best = (node.key, end)
    return best


def iter_prose_segments(text: str) -> Iterable[tuple[str, bool]]:
    """Yield ``(segment, is_prose)``; fenced blocks and inline code spans are not prose."""
    in_fence = False
    fence = ""
    for line in text.splitlines(keepends=True):
        match = _FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence, fence = True, marker[:3]
                yield line, False
                continue
            if marker.startswith(fence):
                in_fence, fence = False, ""
                yield line, False
                continue
        if in_fence:
            yield line, False
            continue
        pos = 0
        for code in _INLINE_CODE_RE.finditer(line):
            yield line[pos : code.start()], True
            yield code.group(0), False
            pos = code.end()
        yield line[pos:], True


# ──────────────────────────────────────────────
#  Render-time lowering
# ──────────────────────────────────────────────


@dataclass
class GlyphLowering:
    text: str
    emoji_counts: dict[str, int] = field(default_factory=dict)
    fallback_counts: dict[str, int] = field(default_factory=dict)  # family -> characters set
    fallback_missing: list[str] = field(default_factory=list)


def lower_glyphs(text: str, registry: dict[str, Any], *, emoji_macro, fallback_macro) -> GlyphLowering:
    """Replace registered emoji with ``emoji_macro(key)`` and wrap fallback runs with ``fallback_macro(family, run)``.

    Only prose is touched: fenced blocks and inline code spans pass through.
    """
    trie = _build_trie(registry["emoji"].keys())
    fallback_of: dict[int, str] = {}
    for font in registry["fallback_fonts"]:
        for cp in font.get("codepoints", []):
            fallback_of.setdefault(int(cp), font["family"])
    result = GlyphLowering(text="")
    out: list[str] = []
    missing: set[str] = set()
    for segment, prose in iter_prose_segments(text):
        if not prose:
            out.append(segment)
            continue
        i = 0
        while i < len(segment):
            match = _match_at(segment, i, trie) if trie.children else None
            if match:
                key, end = match
                out.append(emoji_macro(key))
                result.emoji_counts[key] = result.emoji_counts.get(key, 0) + 1
                i = end
                continue
            cp = ord(segment[i])
            family = fallback_of.get(cp)
            if family:
                j = i + 1
                while j < len(segment) and fallback_of.get(ord(segment[j])) == family:
                    j += 1
                out.append(fallback_macro(family, segment[i:j]))
                result.fallback_counts[family] = result.fallback_counts.get(family, 0) + (j - i)
                i = j
                continue
            if is_fallback_codepoint(cp):
                missing.add(f"U+{cp:04X}")
            out.append(segment[i])
            i += 1
    result.text = "".join(out)
    result.fallback_missing = sorted(missing)
    return result


# ──────────────────────────────────────────────
#  Scan and grow
# ──────────────────────────────────────────────


def font_coverage(font_files: Iterable[Path]) -> set[int]:
    """Code points covered by ``font_files`` (fontconfig's charset; no Python font deps)."""
    covered: set[int] = set()
    for font in font_files:
        out = subprocess.run(
            ["fc-query", "-f", "%{charset}", str(font)], capture_output=True, text=True, check=True
        ).stdout
        for token in out.split():
            if "-" in token:
                lo, hi = token.split("-")
                covered.update(range(int(lo, 16), int(hi, 16) + 1))
            else:
                covered.add(int(token, 16))
    return covered


def default_coverage_fonts() -> list[Path]:
    """The Sol runtime body font (the fallback for Helvetica et al., see the renderer)."""
    found = subprocess.run(
        ["fc-match", "-f", "%{file}", "DejaVu Sans"], capture_output=True, text=True
    ).stdout.strip()
    return [Path(found)] if found else []


def noto_svg_keys(noto_source: Path) -> set[str]:
    return {p.stem[len("emoji_u"):] for p in (noto_source / "svg").glob("emoji_u*.svg")}


@dataclass
class Needs:
    emoji: dict[str, dict[str, Any]] = field(default_factory=dict)  # key -> {count, files}
    fallback: dict[int, dict[str, Any]] = field(default_factory=dict)
    unresolved: dict[int, dict[str, Any]] = field(default_factory=dict)


def scan_needed(
    paths: Iterable[Path],
    *,
    covered: set[int],
    registry: dict[str, Any],
    noto_keys: set[str] | None = None,
) -> Needs:
    """What ``paths`` need that neither the coverage fonts nor the registry supply.

    An emoji sequence counts only when it contains a code point the coverage fonts
    lack: a covered character (©, ↔, ✓) stays text. With ``noto_keys`` the longest
    available Noto sequence is chosen; without, single code points are reported.
    """
    registered_trie = _build_trie(registry["emoji"].keys())
    noto_trie = _build_trie(noto_keys) if noto_keys else None
    fallback_registered = {int(cp) for f in registry["fallback_fonts"] for cp in f.get("codepoints", [])}
    needs = Needs()

    def note(table: dict, key, name: str) -> None:
        entry = table.setdefault(key, {"count": 0, "files": set()})
        entry["count"] += 1
        entry["files"].add(name)

    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        for segment, prose in iter_prose_segments(text):
            if not prose:
                continue
            i = 0
            while i < len(segment):
                if registered_trie.children and (m := _match_at(segment, i, registered_trie)):
                    i = m[1]
                    continue
                cp = ord(segment[i])
                if cp in covered or cp in (VS16, ZWJ) or cp < 0x20:
                    i += 1
                    continue
                if is_fallback_codepoint(cp):
                    if cp not in fallback_registered:
                        note(needs.fallback, cp, Path(path).name)
                    i += 1
                    continue
                m = _match_at(segment, i, noto_trie) if noto_trie else None
                if m:
                    note(needs.emoji, m[0], Path(path).name)
                    i = m[1]
                    continue
                note(needs.unresolved, cp, Path(path).name)
                i += 1
    return needs


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vendor_emoji(key: str, noto_source: Path, *, noto_version: str) -> dict[str, Any]:
    """Copy one Noto SVG into the registry tree and convert it to a vector PDF."""
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        raise RuntimeError("rsvg-convert is required to vendor emoji assets")
    svg_src = noto_source / "svg" / f"emoji_u{key}.svg"
    svg_dst = ASSETS_ROOT / "emoji" / "noto" / "svg" / svg_src.name
    pdf_dst = ASSETS_ROOT / "emoji" / "noto" / "pdf" / f"emoji_u{key}.pdf"
    svg_dst.parent.mkdir(parents=True, exist_ok=True)
    pdf_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(svg_src, svg_dst)
    subprocess.run([rsvg, "-f", "pdf", "-o", str(pdf_dst), str(svg_dst)], check=True)
    return {
        "emoji": "".join(chr(cp) for cp in key_sequence(key)),
        "svg": svg_dst.relative_to(ASSETS_ROOT).as_posix(),
        "pdf": pdf_dst.relative_to(ASSETS_ROOT).as_posix(),
        "source": f"googlefonts/noto-emoji {noto_version}",
        "license": "Apache-2.0",
        "svg_sha256": _sha256(svg_dst),
    }


def subset_fallback_font(
    family_entry: dict[str, Any], codepoints: set[int], *, faces: dict[str, tuple[Path, int]]
) -> dict[str, Any]:
    """(Re)subset each face of a fallback family to ``codepoints``. Needs fontTools (via uv)."""
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to subset fallback fonts (fontTools runs through it)")
    # U+0020 always: XeTeX asks the current font for the space glyph when it
    # sets interword glue next to a run, and a subset without it fails the lint.
    unicodes = ",".join(f"U+{cp:04X}" for cp in sorted(set(codepoints) | {0x20}))
    outputs: dict[str, str] = {}
    for face, (source, number) in faces.items():
        out = ASSETS_ROOT / "fonts" / "glyph_fallback" / f"{family_entry['family']}-{face}.otf"
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [uv, "run", "-q", "--with", "fonttools", "pyftsubset", str(source),
             f"--font-number={number}", f"--unicodes={unicodes}", "--layout-features=*",
             "--name-IDs=*", "--notdef-outline", f"--output-file={out}"],
            check=True,
        )
        outputs[face] = out.relative_to(ASSETS_ROOT).as_posix()
    entry = dict(family_entry)
    entry["faces"] = outputs
    entry["codepoints"] = sorted(codepoints)
    entry["characters"] = "".join(chr(cp) for cp in sorted(codepoints))
    return entry
