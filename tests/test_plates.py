"""D3/D5 — floating plates: containment from the page ledger, and the render path."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from engine.plates import PlateError, check_ledger, plates_config


def _pages(*rows):
    return [{"index": i + 1, "page": i + 1, "label": str(i + 1), "start": s, "end": e, "opener": o,
             "marks": ["plate"] if plate else []}
            for i, (s, e, o, plate) in enumerate(rows)]


def test_config():
    assert plates_config({}) is None
    assert plates_config({"plates": {"floating": False}}) is None
    assert plates_config({"plates": {"floating": True}}) == {"floating": True, "gate": True}
    assert plates_config({"plates": {"gate": False}}) == {"floating": True, "gate": False}
    with pytest.raises(PlateError):
        plates_config({"plates": True})


def test_a_recto_facing_a_verso_wholly_in_its_chapter_is_contained():
    led = {"pages": _pages(("A", "A", True, False), ("A", "A", False, False), ("A", "A", False, True)),
           "plates": [{"id": 1, "asset": "p.png", "owner": "A", "page": 3, "allow_opener": False}]}
    r = check_ledger(led)
    assert r["ok"] and r["plates"][0]["side"] == "recto" and r["plates"][0]["facing_page"] == 2


def test_sharing_a_spread_with_another_chapter_fails():
    led = {"pages": _pages(("A", "A", False, False), ("A", "B", False, False), ("B", "B", False, True)),
           "plates": [{"id": 1, "asset": "p.png", "owner": "A", "page": 3, "allow_opener": False}]}
    r = check_ledger(led)
    assert not r["ok"] and "shares its spread" in r["violations"][0]["reason"]


def test_facing_the_opening_page_fails_unless_allowed():
    rows = (("A", "A", False, False), ("B", "B", True, False), ("B", "B", False, True))
    plate = {"id": 1, "asset": "p.png", "owner": "B", "page": 3, "allow_opener": False}
    assert check_ledger({"pages": _pages(*rows), "plates": [plate]})["violations"][0]["reason"] == "faces its chapter's opening page"
    assert check_ledger({"pages": _pages(*rows), "plates": [{**plate, "allow_opener": True}]})["ok"]


def test_unplaced_plates_fail():
    assert not check_ledger({"pages": [], "plates": [], "unplaced": ["late.png"]})["ok"]


@pytest.mark.skipif(shutil.which("lualatex") is None, reason="needs lualatex")
def test_render_seats_a_plate_on_a_recto_without_a_head_and_proves_it(tmp_path):
    """End to end: a floating plate in a keeper-capture-style bundle (LuaLaTeX)."""
    from PIL import Image

    from engine.manifest_compiler import CompositeBundleCompiler
    from renderers.pandoc_renderer import PandocRenderer

    art = tmp_path / "plate.png"
    Image.new("RGB", (550, 850), (40, 60, 90)).save(art)
    para = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor. " * 9
    a = tmp_path / "a.md"
    a.write_text("---\nuid: a\n---\n\n" + "\n\n".join([para] * 6)
                 + f"\n\n\\OFFloatingPlate{{{art}}}\n\n" + "\n\n".join([para] * 14) + "\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("---\nuid: b\n---\n\n" + "\n\n".join([para] * 4) + "\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "plates-probe",
        "profile": "keeper-capture",
        "presentation": {"title": "Plates"},
        "render": {"include_toc": False, "numbersections": False, "plates": {"floating": True},
                   "suppress_source_wrapper_headings": True,
                   "delivery": {"mode": "bound", "duplex": True, "page_numbers": "outer",
                                "running_headers": {"enabled": True, "source": "chapter"}}},
        "sources": [
            {"uid": "a", "path": str(a), "role": "primary_anchor", "order": 1, "chapter_opener": {"title": "Chapter A"},
             "include_frontmatter": "none", "suppress_frontmatter": True},
            {"uid": "b", "path": str(b), "role": "primary_anchor", "order": 2, "chapter_opener": {"title": "Chapter B"},
             "include_frontmatter": "none", "suppress_frontmatter": True},
        ],
    }
    from engine.profile_resolver import resolve_profile

    try:
        resolve_profile("keeper-capture")  # a LuaLaTeX profile from the profiles repository
    except Exception as exc:  # noqa: BLE001 - not every checkout points at it
        pytest.skip(f"keeper-capture profile not resolvable here: {exc}")
    compiler = CompositeBundleCompiler()
    assert compiler.validate(manifest) == []
    plan = compiler.compile(manifest)
    ev = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert ev["status"] == "ok", ev.get("error")
    report = ev["render_metadata"]["plates"]
    assert report["ok"], report
    (placed,) = report["plates"]
    assert placed["side"] == "recto" and placed["owner"] == "Chapter A"
    ledger = json.loads(Path(report["ledger"]).read_text())
    page = next(p for p in ledger["pages"] if "plate" in p["marks"])
    import fitz

    with fitz.open(ev["output"]["pdf_path"]) as doc:
        words = doc[placed["page"] - 1].get_text().split()
    assert "Chapter" not in words  # no running head on the plate page
