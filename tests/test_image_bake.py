from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
Image = pytest.importorskip("PIL.Image")

from engine import image_bake as ib


def _rgba_png(path: Path, size=(40, 30), dpi=None) -> Path:
    im = Image.new("RGBA", size)
    px = im.load()
    for x in range(size[0]):
        for y in range(size[1]):
            # partial transparency everywhere: the case PyMuPDF's own insert altered
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, (x * y) % 256, (x * 13 + y * 3) % 256)
    kwargs = {"dpi": dpi} if dpi else {}
    im.save(path, **kwargs)
    return path


def _embedded(pdf: Path):
    doc = fitz.open(str(pdf))
    xref, smask = doc[0].get_images(full=True)[0][:2]
    return fitz.Pixmap(doc, xref).samples, fitz.Pixmap(doc, smask).samples, doc[0].rect


def test_bake_is_lossless_and_natural_size(tmp_path):
    png = _rgba_png(tmp_path / "a.png")
    out = tmp_path / "a.pdf"
    ib.bake_png(png, out)
    rgb, alpha, rect = _embedded(out)
    src = Image.open(png)
    assert rgb == src.convert("RGB").tobytes()
    assert alpha == src.getchannel("A").tobytes()
    assert (rect.width, rect.height) == (40, 30)  # no pHYs: 72 dpi, LuaTeX's default


def test_natural_size_honours_png_resolution(tmp_path):
    png = _rgba_png(tmp_path / "a.png", size=(400, 300), dpi=(400, 400))
    out = tmp_path / "a.pdf"
    ib.bake_png(png, out)
    _, _, rect = _embedded(out)
    assert rect.width == pytest.approx(72.0, abs=0.05)
    assert rect.height == pytest.approx(54.0, abs=0.05)


def test_only_alpha_pngs_are_bakeable(tmp_path):
    rgba = _rgba_png(tmp_path / "rgba.png")
    rgb = tmp_path / "rgb.png"
    Image.new("RGB", (4, 4)).save(rgb)
    assert ib.bakeable(rgba)
    assert not ib.bakeable(rgb)


def test_bake_paths_reuses_and_indexes(tmp_path):
    cache = tmp_path / "cache"
    png = _rgba_png(tmp_path / "a.png")
    first = ib.bake_paths([png], cache)
    assert (first.baked, first.reused) == (1, 0)
    second = ib.bake_paths([png], cache)
    assert (second.baked, second.reused) == (0, 1)
    entry = ib.load_index(cache)[str(png.resolve())]
    assert entry["sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    assert Path(entry["pdf"]).is_file()
    # a copy with the same bytes shares the baked PDF
    copy = tmp_path / "b.png"
    shutil.copy2(png, copy)
    third = ib.bake_paths([copy], cache)
    assert (third.baked, third.reused) == (0, 1)


def test_lua_source_lists_the_index(tmp_path):
    cache = tmp_path / "cache"
    png = _rgba_png(tmp_path / "a.png")
    ib.bake_paths([png], cache)
    lua = ib.lua_callback_source(cache)
    assert f"[ [==[{png.resolve()}]==] ]" in lua
    assert "find_image_file" in lua
    assert "io.open" not in lua  # read-only: LaTeX may not write outside its temp dir


def test_discover_png_references_resolves_against_roots(tmp_path):
    book = tmp_path / "book"
    profile = tmp_path / "profile"
    (book / "assets").mkdir(parents=True)
    (profile / "assets").mkdir(parents=True)
    a = _rgba_png(book / "assets" / "plate.png")
    b = _rgba_png(profile / "assets" / "mark.png")
    absolute = _rgba_png(tmp_path / "abs.png")
    texts = [
        "\\OFSectionDividerBackground{assets/plate.png}\n![x](assets/mark.png)\n",
        f"\\includegraphics{{{absolute}}} and assets/missing.png",
    ]
    found = ib.discover_png_references(texts, [book, profile])
    assert found == sorted([a.resolve(), b.resolve(), absolute.resolve()])


@pytest.mark.skipif(not shutil.which("lualatex"), reason="lualatex not available")
def test_callback_redirects_in_lualatex_with_identical_image_data(tmp_path):
    """End to end: the redirected embed carries the same image data as the direct one."""
    cache = tmp_path / "cache"
    work = tmp_path / "work"
    work.mkdir()
    png = _rgba_png(tmp_path / "img.png", size=(60, 45))
    ib.bake_paths(ib.discover_png_references([f"\\includegraphics{{{png}}}"], []), cache)
    lua = tmp_path / "bake.lua"
    lua.write_text(ib.lua_callback_source(cache))

    def compile_once(tag: str, with_bake: bool) -> Path:
        hook = f"\\directlua{{dofile(\"{lua}\")}}\n" if with_bake else ""
        (work / f"{tag}.tex").write_text(
            "\\documentclass{article}\\usepackage{graphicx}\n" + hook
            + f"\\begin{{document}}\\includegraphics[width=2in]{{{png}}}\\end{{document}}\n"
        )
        subprocess.run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", f"{tag}.tex"],
                       cwd=work, check=True, capture_output=True)
        return work / f"{tag}.pdf"

    direct, baked = compile_once("direct", False), compile_once("baked", True)

    def embedded(pdf):
        d = fitz.open(str(pdf))
        x, s = d[0].get_images(full=True)[0][:2]
        return fitz.Pixmap(d, x).samples, fitz.Pixmap(d, s).samples, d[0].get_image_info()[0]["bbox"]

    def is_form_wrapped(pdf):  # the baked page arrives as a Form XObject
        d = fitz.open(str(pdf))
        return any(d.xref_get_key(x, "Subtype")[1] == "/Form" for x in range(1, d.xref_length()))

    assert embedded(direct) == embedded(baked)
    assert is_form_wrapped(baked) and not is_form_wrapped(direct)
