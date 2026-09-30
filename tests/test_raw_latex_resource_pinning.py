"""Raw-LaTeX resource pinning: the file the evidence names is the file LaTeX opens.

Regression for the Codex 0 Part I plate (canon scar
21_letters_and_creative/book/codex0_v5/structure/
scar_codex0_part01_plate_revision_never_rendered_2026-09-28.md): a relative path
written as raw LaTeX was resolved by LaTeX itself, from the profile folder pandoc
runs in, ahead of the manifest's resource roots, while the evidence named the
manifest copy as the winner.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.projection_plan import ProjectionPlan
from engine.profile_resolver import resolve_profile
from engine.resource_roots import (
    TEMPLATE_RESOURCE_KEYS,
    effective_resource_roots,
    pin_render_resources,
    typed_resource_references,
)
from renderers.pandoc_renderer import PandocRenderer


def _profile(resource_paths: list[Path]):
    return SimpleNamespace(render_environment=SimpleNamespace(resource_paths=resource_paths))


def _roots(tmp_path: Path, references: list[str], *, in_profile: bool = True):
    run_root, source_root, manifest_root, profile_root = (
        tmp_path / name for name in ("run", "source", "work", "profile")
    )
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    for reference in references:
        for root in (manifest_root, profile_root) if in_profile else (manifest_root,):
            target = root / reference
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(root.name.encode())
    source = source_root / "source.md"
    source.write_text("", encoding="utf-8")
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="pin",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
    )
    return effective_resource_roots(plan, _profile([profile_root]), run_root), manifest_root, profile_root


def test_divider_plate_is_pinned_to_the_manifest_winner_and_the_inversion_is_recorded(tmp_path):
    reference = "assets/codex0/v5/full_page_plates/part01.png"
    roots, manifest_root, profile_root = _roots(tmp_path, [reference])
    # The directory LaTeX looks in first holds a different copy: the scar's setup.
    text = f"\\OFSectionDividerBackground{{{reference}}}\n"

    pinned, record = pin_render_resources(text, roots, latex_cwd=profile_root)

    winner = (manifest_root / reference).resolve().as_posix()
    assert pinned == f"\\OFSectionDividerBackground{{{winner}}}\n"
    [entry] = record["pinned"]
    assert entry["pinned_to"] == winner
    assert entry["winner_origin"] == "manifest"
    assert entry["latex_cwd_candidate"] == str((profile_root / reference).resolve())
    assert record["unpinned"] == []
    assert any("would have opened" in warning for warning in record["warnings"])


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("\\includegraphics[width=1in]{\\detokenize{@R@}}", "\\includegraphics[width=1in]{\\detokenize{@W@}}"),
        ("\\includegraphics{@R@}", "\\includegraphics{@W@}"),
        ("\\CodexFloatingPlate[ch01]{@R@}", "\\CodexFloatingPlate[ch01]{@W@}"),
        ("\\OFOuterRail{@R@}", "\\OFOuterRail{@W@}"),
        ("\\OFImageInitialSetup{@R@}{.8in}{5}{0in}{0in}{top}", "\\OFImageInitialSetup{@W@}{.8in}{5}{0in}{0in}{top}"),
        ("\\OFDecorativeImage{width=.3\\linewidth}{@R@}{vignette}", "\\OFDecorativeImage{width=.3\\linewidth}{@W@}{vignette}"),
    ],
)
def test_every_supported_macro_form_is_pinned(tmp_path, raw, expected):
    reference = "assets/plate.png"
    roots, manifest_root, _profile_root = _roots(tmp_path, [reference])
    winner = (manifest_root / reference).resolve().as_posix()

    pinned, record = pin_render_resources(raw.replace("@R@", reference), roots)

    assert pinned == expected.replace("@W@", winner)
    assert record["pinned"][0]["occurrences"] == 1


def test_macro_definitions_and_indirect_arguments_are_left_alone(tmp_path):
    roots, _manifest_root, _profile_root = _roots(tmp_path, ["assets/plate.png"])
    text = (
        "\\providecommand{\\OFDecorativeImage}[3]{\\includegraphics[#1]{#2}}\n"
        "\\includegraphics[width=1in]{\\CodexBlankLeafOrnament}\n"
        "\\includegraphics{/already/absolute.png}\n"
        "\\includegraphics{https://example.com/remote.png}\n"
    )

    pinned, record = pin_render_resources(text, roots)

    assert pinned == text
    assert record == {"pinned": [], "unpinned": [], "warnings": []}


def test_unresolved_reference_is_left_relative_and_its_latex_fallback_is_named(tmp_path):
    reference = "assets/only-in-profile.png"
    roots, _manifest_root, _profile_root = _roots(tmp_path, [])
    # The pandoc working directory is not a root in the chain (as in production,
    # where only its assets/ and templates/ subfolders are).
    profile_root = tmp_path / "latex-cwd"
    (profile_root / reference).parent.mkdir(parents=True)
    (profile_root / reference).write_bytes(b"cwd")
    text = f"\\includegraphics{{{reference}}}"

    pinned, record = pin_render_resources(text, roots, latex_cwd=profile_root)

    assert pinned == text
    assert record["pinned"] == []
    assert record["unpinned"] == [
        {
            "reference": reference,
            "macro": "includegraphics",
            "reason": "no winner in the effective root chain",
            "latex_would_open": str((profile_root / reference).resolve()),
        }
    ]
    assert record["warnings"] == [
        f"raw resource {reference} has no winner in the effective root chain; "
        f"LaTeX will open {(profile_root / reference).resolve()}"
    ]


def test_template_path_variables_in_frontmatter_are_pinned_and_other_keys_are_not(tmp_path):
    references = ["assets/apparatus/knot.png", "assets/apparatus/chip.png", "assets/other.png"]
    roots, manifest_root, _profile_root = _roots(tmp_path, references)
    text = (
        "---\n"
        "title: Book\n"
        "variables:\n"
        f"  codex_blank_leaf_ornament: {references[0]}\n"
        f"  codex_folio_chip_asset: \"{references[1]}\"\n"
        f"  unrelated_key: {references[2]}\n"
        "---\n"
        "body\n"
    )

    pinned, record = pin_render_resources(text, roots, template_keys=TEMPLATE_RESOURCE_KEYS)

    knot = (manifest_root / references[0]).resolve().as_posix()
    chip = (manifest_root / references[1]).resolve().as_posix()
    assert f"  codex_blank_leaf_ornament: {knot}\n" in pinned
    assert f"  codex_folio_chip_asset: \"{chip}\"\n" in pinned
    assert f"  unrelated_key: {references[2]}\n" in pinned
    assert {entry["macro"] for entry in record["pinned"]} == {
        "template:codex_blank_leaf_ornament",
        "template:codex_folio_chip_asset",
    }


def test_repeated_reference_is_counted_once_with_occurrences(tmp_path):
    reference = "assets/leaf.png"
    roots, _manifest_root, _profile_root = _roots(tmp_path, [reference])
    text = f"\\OFSectionDividerBackground{{{reference}}}\n\\includegraphics{{\\detokenize{{{reference}}}}}\n"

    _pinned, record = pin_render_resources(text, roots)

    assert len(record["pinned"]) == 1
    assert record["pinned"][0]["occurrences"] == 2


def test_decorative_image_path_is_in_winner_evidence(tmp_path):
    source = tmp_path / "s.md"
    source.write_text("\\OFDecorativeImage{width=1in}{assets/v.png}{none}\n", encoding="utf-8")
    plan = ProjectionPlan(profile_id="generic-report", render_id="d", render_source=source)
    assert typed_resource_references(plan) == ["assets/v.png"]


def _png(path: Path, rgb: tuple[int, int, int]) -> None:
    fitz = pytest.importorskip("fitz")
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pixmap.set_rect(pixmap.irect, rgb)
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(path))


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_real_render_embeds_the_manifest_copy_when_the_profile_folder_holds_another(tmp_path):
    """End to end: a same-named image in the pandoc working directory must lose."""
    fitz = pytest.importorskip("fitz")
    profile = resolve_profile("generic-report")
    latex_cwd = Path(profile.render_environment.cwd)
    shadow_dir = latex_cwd / f".pytest-pin-shadow-{uuid.uuid4().hex[:12]}"
    reference = f"{shadow_dir.name}/plate.png"
    manifest_root = tmp_path / "work"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _png(manifest_root / reference, (0, 128, 255))  # the intended copy
    try:
        _png(latex_cwd / reference, (255, 0, 0))  # the shadow LaTeX used to open
        source = source_root / "doc.md"
        source.write_text(
            "---\ntitle: Pin\ntoc: false\nnumbersections: false\n---\n\n"
            "```{=latex}\n"
            f"\\includegraphics[width=1in]{{{reference}}}\n"
            "```\n",
            encoding="utf-8",
        )
        plan = ProjectionPlan(
            profile_id="generic-report",
            render_id="pin-real",
            render_source=source,
            source_resource_roots=[source_root],
            manifest_resource_roots=[manifest_root],
            toc=False,
            numbersections=False,
            source_inventory=[{"uid": "doc", "path": str(source), "role": "primary_anchor"}],
        )
        out_dir = tmp_path / "out"
        PandocRenderer().render(plan, output_dir=out_dir)
        evidence = json.loads((out_dir / "pin-real.evidence.json").read_text())
    finally:
        shutil.rmtree(shadow_dir, ignore_errors=True)

    assert evidence["status"] == "ok", evidence.get("error")
    pins = evidence["resource_resolution"]["raw_latex_pins"]
    [entry] = pins["pinned"]
    assert entry["pinned_to"] == (manifest_root / reference).resolve().as_posix()
    assert entry["latex_cwd_candidate"] == str((latex_cwd / reference).resolve())

    document = fitz.open(out_dir / "pin-real.pdf")
    colours = set()
    for page in document:
        for image in page.get_images(full=True):
            pixmap = fitz.Pixmap(document, image[0])
            colours.add(tuple(pixmap.pixel(0, 0)[:3]))
    assert (0, 128, 255) in colours
    assert (255, 0, 0) not in colours
