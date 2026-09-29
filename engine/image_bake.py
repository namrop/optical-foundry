"""Lossless image bake: alpha PNGs pre-split once so LuaTeX embeds them by copy.

LuaTeX cannot pass an alpha PNG through to the PDF. Every time it meets one it
decodes the whole image, splits colour from alpha, and recompresses both — on
every LaTeX run pandoc makes while cross-references settle, in every render. For
a book of 20–25 MB transparent scans that is most of the compile time.

The bake does that split once and stores the result as a one-page PDF whose page
holds exactly one image XObject: the PNG's own 8-bit samples (``DeviceRGB`` or
``DeviceGray``) with its alpha channel as the ``/SMask``, both Flate-compressed.
The pixel data is the decoded PNG, byte for byte — the same objects LuaTeX would
have built — and the page is the image's natural size (the PNG's pHYs resolution,
or 72 dpi when it has none, which is LuaTeX's default), so every placement lands
where it did. Nothing is resampled. Luis-ruled 2026-09-28: the lossless path.

Before a render, ``discover_png_references`` finds the PNGs the render can name —
every ``*.png`` token in the pandoc input, the template and the defaults,
resolved against the same roots LaTeX searches — and ``bake_paths`` bakes the
ones not yet cached. At render time a read-only LuaTeX ``find_image_file``
callback (``lua_callback_source``) redirects each requested PNG to its baked PDF
when the file on disk is the one that was baked (same size and mtime); anything
else renders exactly as before. The callback writes nothing: pandoc runs LaTeX
in a temp directory with ``TEXMFOUTPUT`` pointing there, so kpathsea's
``openout_any = p`` would refuse (silently) any file outside it. An image whose
name is built at compile time, which discovery cannot see, simply is not
redirected. The cache is content-addressed (sha256 of the PNG) under
``cache_dir()``.

Only 8-bit RGBA and 8-bit grey-plus-alpha PNGs are baked. Opaque PNGs are left
to LuaTeX, which embeds them without the split; palette, 16-bit and other modes
are left alone because their exact LuaTeX treatment is not what this module
reproduces.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import zlib

BAKE_VERSION = 1


def cache_dir() -> Path:
    """``$OPTICAL_FOUNDRY_IMAGE_CACHE``, else ``$XDG_CACHE_HOME/optical-foundry/image-bake``."""
    explicit = os.environ.get("OPTICAL_FOUNDRY_IMAGE_CACHE")
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "optical-foundry" / "image-bake"


def _index_path(cache: Path) -> Path:
    return cache / "index.json"


def load_index(cache: Path | None = None) -> dict[str, dict]:
    """Path-keyed index: ``{abs_png: {size, mtime, sha256, pdf}}``."""
    path = _index_path(cache or cache_dir())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_index(index: dict[str, dict], cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    tmp = _index_path(cache).with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(_index_path(cache))


@contextmanager
def _locked(cache: Path):
    """Serialize index read-modify-write: parallel renders bake into one cache."""
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / "index.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def natural_size_points(width_px: int, height_px: int, dpi: tuple[float, float] | None) -> tuple[float, float]:
    """The image's natural size in PDF points, as LuaTeX computes it for a PNG."""
    xdpi, ydpi = (dpi if dpi and dpi[0] and dpi[1] else (72.0, 72.0))
    return width_px * 72.0 / xdpi, height_px * 72.0 / ydpi


def _pdf_bytes(width: int, height: int, colorspace: str, color: bytes, alpha: bytes,
               page_w: float, page_h: float) -> bytes:
    """A one-page PDF drawing one image XObject (with soft mask) across the page."""
    color_z = zlib.compress(color, 6)
    alpha_z = zlib.compress(alpha, 6)
    content = f"q {page_w:.4f} 0 0 {page_h:.4f} 0 0 cm /Im0 Do Q".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.4f} {page_h:.4f}] "
         f"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>").encode("ascii"),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        (f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
         f"/ColorSpace /{colorspace} /BitsPerComponent 8 /SMask 6 0 R "
         f"/Filter /FlateDecode /Length {len(color_z)} >>\nstream\n").encode("ascii") + color_z + b"\nendstream",
        (f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
         f"/ColorSpace /DeviceGray /BitsPerComponent 8 "
         f"/Filter /FlateDecode /Length {len(alpha_z)} >>\nstream\n").encode("ascii") + alpha_z + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def bakeable(png: Path) -> bool:
    """True for the PNGs this module bakes: 8-bit RGBA or 8-bit grey+alpha."""
    from PIL import Image

    try:
        with Image.open(png) as im:
            return im.format == "PNG" and im.mode in ("RGBA", "LA")
    except OSError:
        return False


def bake_png(png: Path, out_pdf: Path) -> None:
    """Write the lossless baked PDF for one 8-bit RGBA / LA PNG."""
    from PIL import Image

    with Image.open(png) as im:
        if im.mode not in ("RGBA", "LA"):
            raise ValueError(f"not a bakeable PNG ({im.mode}): {png}")
        im.load()
        width, height = im.size
        page_w, page_h = natural_size_points(width, height, im.info.get("dpi"))
        alpha = im.getchannel("A").tobytes()
        if im.mode == "RGBA":
            color, space = im.convert("RGB").tobytes(), "DeviceRGB"
        else:
            color, space = im.getchannel("L").tobytes(), "DeviceGray"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_pdf.with_suffix(f".pdf.{os.getpid()}.tmp")
    tmp.write_bytes(_pdf_bytes(width, height, space, color, alpha, page_w, page_h))
    tmp.replace(out_pdf)


@dataclass
class BakeReport:
    baked: int = 0
    reused: int = 0
    skipped: int = 0


def bake_paths(paths, cache: Path | None = None) -> BakeReport:
    """Bake every bakeable PNG in ``paths`` into the cache and index it."""
    cache = cache or cache_dir()
    with _locked(cache):
        return _bake_paths_locked(paths, cache)


def _bake_paths_locked(paths, cache: Path) -> BakeReport:
    index = load_index(cache)
    report = BakeReport()
    for raw in sorted({str(Path(p).resolve()) for p in paths}):
        png = Path(raw)
        try:
            st = png.stat()
        except OSError:
            report.skipped += 1
            continue
        entry = index.get(raw)
        if entry and entry.get("size") == st.st_size and entry.get("mtime") == int(st.st_mtime) \
                and Path(entry.get("pdf", "")).is_file() and entry.get("version") == BAKE_VERSION:
            report.reused += 1
            continue
        if not bakeable(png):
            report.skipped += 1
            continue
        digest = _sha256(png)
        pdf = cache / "pdf" / digest[:2] / f"{digest}.v{BAKE_VERSION}.pdf"
        if pdf.is_file():
            report.reused += 1
        else:
            bake_png(png, pdf)
            report.baked += 1
        index[raw] = {"size": st.st_size, "mtime": int(st.st_mtime), "sha256": digest,
                      "pdf": str(pdf), "version": BAKE_VERSION}
    _save_index(index, cache)
    return report


PNG_REFERENCE = re.compile(r"""[^\s{}\[\]()"'<>|,;=`*]+\.png""", re.IGNORECASE)


def discover_png_references(texts, roots) -> list[Path]:
    """Existing PNG files that ``texts`` name, resolved against ``roots``.

    Absolute references are taken as they are; relative ones are tried against
    every root, and every existing match is returned (over-inclusion only costs a
    bake; the callback redirects whichever file LaTeX actually opens).
    """
    refs: set[str] = set()
    for text in texts:
        refs.update(PNG_REFERENCE.findall(text or ""))
    found: set[Path] = set()
    for ref in refs:
        path = Path(ref)
        if path.is_absolute():
            if path.is_file():
                found.add(path.resolve())
            continue
        for root in roots:
            candidate = Path(root) / path
            if candidate.is_file():
                found.add(candidate.resolve())
    return sorted(found)


def _lua_string(value: str) -> str:
    return "[==[" + value + "]==]"


def lua_callback_source(cache: Path | None = None) -> str:
    """Lua that registers the read-only ``find_image_file`` redirect for one render.

    The current index is inlined as a table, so the callback does no file I/O
    beyond one ``lfs.attributes`` per requested PNG.
    """
    index = load_index(cache or cache_dir())
    rows = []
    for png, entry in sorted(index.items()):
        if Path(entry.get("pdf", "")).is_file():
            rows.append(
                f"  [ {_lua_string(png)} ] = {{size = {int(entry['size'])}, mtime = {int(entry['mtime'])}, "
                f"pdf = {_lua_string(entry['pdf'])}}},"
            )
    table = "\n".join(rows)
    return f"""-- Optical Foundry lossless image bake (engine/image_bake.py), generated per render.
local of_bake = {{
{table}
}}
local function of_bake_abs(name)
  if name:sub(1, 1) == "/" then return name end
  local found = kpse.find_file(name, "graphic/figure") or name
  if found:sub(1, 1) == "/" then return found end
  return lfs.currentdir() .. "/" .. found
end
luatexbase.add_to_callback("find_image_file", function(name)
  if not name or not name:lower():match("%.png$") then return name end
  local path = of_bake_abs(name)
  local entry = of_bake[path]
  if entry then
    local attr = lfs.attributes(path)
    if attr and attr.size == entry.size and math.floor(attr.modification) == entry.mtime then
      return entry.pdf
    end
  end
  return name
end, "optical-foundry-image-bake")
"""
