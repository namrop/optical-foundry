"""Ornament slots, rails and profile packages (D1, D2; rulings 01a0f951-dc5d, 01a0f99a-b2db)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from engine import ornaments
from engine.profile_package import ProfilePackageError, load_package, profile_repositories
from engine.profile_resolver import resolve_profile

LINE, WIDTH = 0.18816, 0.5


def _piece(path: Path, w: int, h: int, *, margin: int = 10, alpha: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA" if alpha else "RGB", (w + 2 * margin, h + 2 * margin), (0, 0, 0, 0) if alpha else "white")
    ImageDraw.Draw(im).ellipse([margin, margin, margin + w, margin + h], fill=(90, 40, 140, 255) if alpha else "purple")
    im.save(path)
    return path


def _rail(path: Path, lines: int) -> Path:
    aspect = lines * LINE / WIDTH * 1.05
    h = int(300 * lines * LINE * 1.2) + 20
    return _piece(path, max(int(h / aspect), 12), h)


# --- rules -------------------------------------------------------------------

def test_engine_rules_are_codex0s_law():
    assert {n: (s["top"], s["foot"]) for n, s in ornaments.BAND_SLOTS.items()} == {
        "whisper": ("drop", "drop"), "breath": ("drop", "drop"), "hinge": ("drop", "drop"),
        "passage_rule": ("drop", "drop"), "tailpiece": ("keep", "keep_first"), "threshold": ("keep", "keep_first"),
    }


def test_a_profile_may_tighten_a_rule(tmp_path):
    plan = ornaments.plan_ornaments({"slots": {"threshold": {"top": "drop", "foot": "drop"}}}, tmp_path)
    assert plan.record["law"]["6"] == {"name": "threshold", "top": "drop", "foot": "drop"}


@pytest.mark.parametrize("slot, rule, value", [("breath", "top", "keep"), ("breath", "foot", "keep_first"),
                                               ("tailpiece", "foot", "keep")])
def test_a_profile_may_not_loosen_a_rule(tmp_path, slot, rule, value):
    with pytest.raises(ornaments.OrnamentError, match="loosen|not one of"):
        ornaments.plan_ornaments({"slots": {slot: {rule: value}}}, tmp_path)


def test_unknown_and_not_yet_placed_slots_are_refused(tmp_path):
    with pytest.raises(ornaments.OrnamentError, match="unknown slot"):
        ornaments.plan_ornaments({"slots": {"fleuron": {}}}, tmp_path)
    with pytest.raises(ornaments.OrnamentError, match="not yet placed"):
        ornaments.plan_ornaments({"slots": {"folio_chip": {}}}, tmp_path)


def test_no_ornaments_means_no_plan(tmp_path):
    assert ornaments.plan_ornaments(None, tmp_path) is None
    assert ornaments.plan_ornaments({}, tmp_path) is None


# --- art ---------------------------------------------------------------------

def test_art_checks(tmp_path):
    good = _piece(tmp_path / "good.png", 300, 300)
    assert ornaments.check_art(good).errors == []
    assert ornaments.check_art(_piece(tmp_path / "flat.png", 300, 300, alpha=False)).errors == ["no alpha channel"]
    touching = _piece(tmp_path / "edge.png", 300, 300, margin=0)
    assert "not contained" in ornaments.check_art(touching).errors[0]
    assert "dpi" in ornaments.check_art(good, placed_height_in=2.0).errors[0]   # 300px over 2in = 150 dpi


def test_aspect_decides_the_rung(tmp_path):
    piece = _rail(tmp_path / "rails" / "r12.png", 12)
    plan = ornaments.plan_ornaments({"rails": {"art": ["rails/r12.png"]}}, tmp_path)
    assert plan.record["rails"]["pieces_by_rung"] == {"12": 1}
    with pytest.raises(ornaments.OrnamentError, match="cannot fill rung 20"):
        ornaments.plan_ornaments({"rails": {"art": [{"path": "rails/r12.png", "rung": 20}]}}, tmp_path)
    assert piece.exists()


def test_rails_default_to_codex0_numbers(tmp_path):
    plan = ornaments.plan_ornaments({"rails": {"class": "literal-voice"}}, tmp_path)
    rails = plan.record["rails"]
    assert (rails["width"], rails["min_lines"], rails["ladder"]) == ("0.50in", 4, {"step": 2, "max": 38})
    assert rails["empty_rungs"] == list(range(2, 40, 2))


# --- packages ----------------------------------------------------------------

def _package(repo: Path, pid: str = "kc-test", **extra) -> Path:
    d = repo / pid
    d.mkdir(parents=True)
    (d / "defaults.yaml").write_text("pdf-engine: lualatex\n")
    spec = {"schema_version": "profile_package_v1", "id": pid, "extends": "keeper", "defaults": ["defaults.yaml"], **extra}
    (d / "profile.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    return d


def test_repositories_come_from_the_env_and_the_host_pointer(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    (tmp_path / "cfg" / "optical-foundry").mkdir(parents=True)
    (tmp_path / "cfg" / "optical-foundry" / "profile_repos").write_text(f"# comment\n{b}\n{a}\n")
    monkeypatch.setenv("OF_PROFILE_PATH", str(a))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert profile_repositories() == [a, b]


def test_a_package_extends_an_engine_profile(tmp_path, monkeypatch):
    d = _package(tmp_path, ornaments={"slots": {"breath": {}}})
    monkeypatch.setenv("OF_PROFILE_PATH", str(tmp_path))
    profile = resolve_profile("kc-test")
    assert profile.package_dir == d.resolve()
    assert profile.template_path.name == "keeper.tex"
    assert profile.defaults_stack[-1] == (d / "defaults.yaml").resolve()
    assert profile.ornaments == {"slots": {"breath": {}}}
    assert profile.boundary["profile_package"] == str(d.resolve())


def test_an_engine_profile_is_never_shadowed(tmp_path, monkeypatch):
    _package(tmp_path, pid="keeper")
    monkeypatch.setenv("OF_PROFILE_PATH", str(tmp_path))
    assert resolve_profile("keeper").package_dir is None


def test_package_shape_is_checked(tmp_path):
    d = _package(tmp_path)
    spec = yaml.safe_load((d / "profile.yaml").read_text())
    (d / "profile.yaml").write_text(yaml.safe_dump({**spec, "colour": "red"}))
    with pytest.raises(ProfilePackageError, match="unknown key"):
        load_package(d / "profile.yaml")
    (d / "profile.yaml").write_text(yaml.safe_dump({**spec, "id": "other"}))
    with pytest.raises(ProfilePackageError, match="must match its directory"):
        load_package(d / "profile.yaml")


# --- render ------------------------------------------------------------------

@pytest.mark.skipif(not (shutil.which("pandoc") and shutil.which("lualatex")), reason="pandoc/lualatex missing")
def test_rails_and_the_law_on_a_rendered_page(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    from renderers.document_renderer import DocumentRenderer
    from renderers.pandoc_renderer import PandocRenderer

    repo = tmp_path / "repo"
    d = repo / "kc-test"
    art = [{"path": f"rails/r{L:02d}_{k}.png", "rung": L} for L in range(4, 40, 2) for k in range(2)]
    for item in art:
        _rail(d / item["path"], item["rung"])
    _piece(d / "orn" / "breath.png", 600, 200)
    (d / "defaults.yaml").write_text("pdf-engine: lualatex\n")
    (d / "profile.yaml").write_text(yaml.safe_dump({
        "schema_version": "profile_package_v1", "id": "kc-test", "extends": "keeper", "defaults": ["defaults.yaml"],
        "ornaments": {"rails": {"class": "literal-voice", "art": art},
                      "slots": {"breath": {"art": ["orn/breath.png"]}, "hinge": {}}},
    }, sort_keys=False))
    monkeypatch.setenv("OF_PROFILE_PATH", str(repo))
    para = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor. " * 6
    src = tmp_path / "doc.md"
    src.write_text(
        f"---\ntitle: Probe\ntoc: false\nnumbersections: false\n---\n\n{para}\n\n"
        f"::: literal-voice\n{para}\n\n{para}\n:::\n\n{para}\n\n::: breath\n:::\n\n{para}\n\n"
        f"::: hinge\n:::\n\n```{{=latex}}\n\\clearpage\n```\n\n::: breath\n:::\n\nAfter the stranded breath. {para}\n",
        encoding="utf-8",
    )
    plan = DocumentRenderer().build_plan(src, "kc-test")
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert evidence["status"] == "ok", evidence.get("error")
    record = evidence["render_metadata"]["ornaments"]
    assert record["slots"]["breath"]["art"] == 1 and record["slots"]["hinge"]["art"] == 0

    doc = fitz.open(evidence["output"]["pdf_path"])
    rails, breaths = [], []
    for number, page in enumerate(doc, start=1):
        text = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
        right = max(b["bbox"][2] for b in text)
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            if y1 - y0 > 3 * (x1 - x0):
                rails.append((number, x0 > right, x1 - x0))
            elif x1 - x0 > 2 * (y1 - y0):
                breaths.append((number, y0))
    assert rails and all(outer for _, outer, _ in rails)                 # outer margin, beside the block
    assert all(width <= WIDTH * 72 + 1 for *_, width in rails)          # never wider than the slot
    assert len(breaths) == 1 and breaths[0][0] == 1                     # the stranded breath was dropped
