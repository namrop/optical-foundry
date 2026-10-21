"""Contracts for manifest-declared, work-owned render resource roots."""
from __future__ import annotations

from engine import source_preparation
from engine.profile_resolver import resolve_profile
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import cli
import service
from engine.manifest_compiler import (
    CAMStackCompiler,
    CodexBundleCompiler,
    CompositeBundleCompiler,
    MarkdownDocumentCompiler,
)
from engine.layout_images import LayoutImageRenderError, preprocess_layout_image_blocks
from engine.projection_plan import ProjectionPlan
from engine.resource_roots import (
    effective_resource_roots,
    resolve_manifest_resource_roots,
    resource_resolution_evidence,
    resource_root_paths,
    typed_resource_references,
)
from renderers.document_renderer import DocumentRenderer
from renderers.pandoc_renderer import PandocRenderer
import renderers.pandoc_renderer as pandoc_renderer_module


def _document_manifest(source: Path, resource_roots=None) -> dict:
    manifest = {
        "kind": "markdown_document",
        "schema_version": "document_manifest_v1",
        "document_id": "resource-root-document",
        "profile": "generic-report",
        "source": {"path": str(source)},
        "render": {"include_toc": False, "numbersections": False},
    }
    if resource_roots is not None:
        manifest["resource_roots"] = resource_roots
    return manifest


def _bundle_manifest(kind: str, source: Path, resource_roots: list[str]) -> dict:
    return {
        "kind": kind,
        "schema_version": "bundle_manifest_v1",
        "bundle_id": f"{kind}-resource-root",
        "bundle_name": "Resource Root Bundle",
        "profile": "generic-report",
        "resource_roots": resource_roots,
        "presentation": {"title": "Resource Root Bundle"},
        "sources": [
            {
                "uid": "source-one",
                "path": str(source),
                "role": "primary_anchor",
                "title": "Source One",
                "order": 1,
                "include_frontmatter": "none",
                "suppress_frontmatter": True,
            }
        ],
        "render": {"include_toc": False, "numbersections": False},
    }


def _profile(resource_paths: list[Path]):
    return SimpleNamespace(
        canonical_profile_id="generic-report",
        profile_id="generic-report",
        profile_family="report",
        template_path=Path("generic.tex"),
        asset_roots=[],
        render_environment=SimpleNamespace(resource_paths=resource_paths),
    )


def test_absent_manifest_resource_roots_preserves_empty_plan_field(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")

    plan = MarkdownDocumentCompiler().compile(_document_manifest(source))

    assert plan.manifest_resource_roots == []


def test_absolute_and_relative_roots_normalize_and_deduplicate_stably(tmp_path):
    manifest_dir = tmp_path / "manifests" / "nested"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "work.yaml"
    work_root = tmp_path / "book"
    work_root.mkdir()
    relative = Path("../..") / "book"

    roots = resolve_manifest_resource_roots(
        {"resource_roots": [str(relative), str(work_root), str(relative / ".")]},
        manifest_path=manifest_path,
    )

    assert roots == [work_root.resolve()]


def test_relative_root_requires_manifest_provenance(tmp_path):
    root = tmp_path / "resources"
    root.mkdir()

    with pytest.raises(ValueError, match="manifest_path"):
        resolve_manifest_resource_roots({"resource_roots": ["resources"]})


@pytest.mark.parametrize(
    "roots, message",
    [
        ("resources", "must be a list"),
        ([], "must contain at least one"),
        ([""], "non-empty path string"),
        (["https://example.com/assets"], "URL"),
    ],
)
def test_invalid_root_shapes_fail(roots, message):
    with pytest.raises(ValueError, match=message):
        resolve_manifest_resource_roots({"resource_roots": roots}, manifest_path=Path("/tmp/work.yaml"))


def test_missing_file_and_tex_unsafe_roots_fail(tmp_path):
    manifest_path = tmp_path / "work.yaml"
    file_root = tmp_path / "not-a-directory"
    file_root.write_text("no", encoding="utf-8")
    unsafe_root = tmp_path / "unsafe%root"
    unsafe_root.mkdir()

    with pytest.raises(ValueError, match="does not exist"):
        resolve_manifest_resource_roots({"resource_roots": ["missing"]}, manifest_path=manifest_path)
    with pytest.raises(ValueError, match="not a directory"):
        resolve_manifest_resource_roots({"resource_roots": [str(file_root)]}, manifest_path=manifest_path)
    with pytest.raises(ValueError, match="TeX-unsafe"):
        resolve_manifest_resource_roots({"resource_roots": [str(unsafe_root)]}, manifest_path=manifest_path)


@pytest.mark.parametrize("unsafe_character", ["&", "^", "~", os.pathsep])
def test_manifest_roots_reject_pandoc_separator_and_raw_tex_specials(
    tmp_path, unsafe_character
):
    unsafe_root = tmp_path / f"unsafe{unsafe_character}root"
    unsafe_root.mkdir()

    with pytest.raises(ValueError, match="TeX-unsafe"):
        resolve_manifest_resource_roots({"resource_roots": [str(unsafe_root)]})


def test_document_compiler_carries_relative_manifest_root(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    work_root = tmp_path / "work"
    work_root.mkdir()
    manifest_path = manifest_dir / "document.yaml"

    plan = MarkdownDocumentCompiler().compile(
        _document_manifest(source, ["../work"]),
        manifest_path=manifest_path,
    )

    assert plan.manifest_resource_roots == [work_root.resolve()]
    assert plan.source_resource_roots == [source.parent.resolve()]


@pytest.mark.parametrize(
    ("compiler_cls", "kind"),
    [
        (CompositeBundleCompiler, "composite_bundle"),
        (CAMStackCompiler, "cam_stack"),
        (CodexBundleCompiler, "codex_bundle"),
    ],
)
def test_bundle_family_compilers_carry_roots_without_subtype_branches(
    tmp_path, compiler_cls, kind
):
    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    work_root = tmp_path / "work"
    work_root.mkdir()
    manifest_path = tmp_path / "manifests" / f"{kind}.yaml"
    manifest_path.parent.mkdir()

    plan = compiler_cls().compile(
        _bundle_manifest(kind, source, ["../work"]),
        manifest_path=manifest_path,
    )

    assert plan.manifest_resource_roots == [work_root.resolve()]
    assert plan.source_resource_roots == [source.parent.resolve()]


def test_effective_order_is_run_source_manifest_profile_with_stable_dedup(tmp_path):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    profile_root = tmp_path / "profile"
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    source = source_root / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="order",
        render_source=source,
        source_resource_roots=[source_root, source_root],
        manifest_resource_roots=[manifest_root, source_root],
    )

    roots = effective_resource_roots(plan, _profile([profile_root, manifest_root]), run_root)

    assert [(root.origin, root.path) for root in roots] == [
        ("run", run_root.resolve()),
        ("source", source_root.resolve()),
        ("manifest", manifest_root.resolve()),
        ("profile", profile_root.resolve()),
    ]
    assert [root.order for root in roots] == list(range(4))


def test_effective_roots_error_when_a_source_root_is_missing(tmp_path):
    missing_source_root = tmp_path / "missing-source"
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="missing-source-root",
        render_source=missing_source_root / "source.md",
        source_resource_roots=[missing_source_root],
    )

    with pytest.raises(ValueError, match="source resource root does not exist or is not a directory"):
        effective_resource_roots(plan, _profile([]), tmp_path / "run")


def test_effective_roots_error_when_a_declared_manifest_root_is_missing(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    missing_manifest_root = tmp_path / "missing-work"
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="missing-manifest-root",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[missing_manifest_root],
    )

    with pytest.raises(ValueError, match="manifest resource root does not exist or is not a directory"):
        effective_resource_roots(plan, _profile([]), tmp_path / "run")


def test_resource_resolution_selects_manifest_winner_and_records_profile_collision(tmp_path):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    profile_root = tmp_path / "profile"
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    reference = "assets/book/plate.png"
    for root, payload in ((manifest_root, b"work"), (profile_root, b"profile")):
        target = root / reference
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
    source = source_root / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="collision",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
        boundary_assertions={
            "section_dividers": [
                {"uid": "divider", "background_image": reference, "print_image": reference}
            ]
        },
    )
    roots = effective_resource_roots(plan, _profile([profile_root]), run_root)

    evidence = resource_resolution_evidence(plan, roots)

    assert len(evidence["resolved_resources"]) == 1
    resolved = evidence["resolved_resources"][0]
    assert resolved["reference"] == reference
    assert resolved["winner"] == str((manifest_root / reference).resolve())
    assert resolved["winner_origin"] == "manifest"
    assert resolved["shadowed"] == [str((profile_root / reference).resolve())]
    assert evidence["warnings"] == [
        f"resource collision for {reference}: manifest winner shadows 1 lower-precedence match"
    ]


def test_resource_resolution_does_not_follow_an_in_root_symlink_outside_its_root(tmp_path):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    outside_root = tmp_path / "outside"
    for root in (run_root, source_root, manifest_root, outside_root):
        root.mkdir()
    source = source_root / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    reference = "assets/plate.png"
    external_file = outside_root / "plate.png"
    external_file.write_bytes(b"external")
    linked_file = manifest_root / reference
    linked_file.parent.mkdir()
    linked_file.symlink_to(external_file)
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="symlink-containment",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
        boundary_assertions={"title_page": {"background_image": reference}},
    )
    roots = effective_resource_roots(plan, _profile([]), run_root)

    evidence = resource_resolution_evidence(plan, roots)

    assert evidence["resolved_resources"] == [
        {
            "reference": reference,
            "winner": None,
            "winner_origin": None,
            "shadowed": [],
        }
    ]
    assert evidence["warnings"] == [
        f"resource reference did not resolve in the effective root chain: {reference}"
    ]


def test_pandoc_and_latex_receive_the_same_effective_semantic_order(tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    profile_root = tmp_path / "profile"
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    source = source_root / "source.md"
    source.write_text(
        "```{=latex}\n\\includegraphics{assets/example.png}\n```\n",
        encoding="utf-8",
    )
    profile = _profile([profile_root])
    monkeypatch.setattr(pandoc_renderer_module, "resolve_profile", lambda _profile_id: profile)
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="semantic-order",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
    )
    roots = effective_resource_roots(plan, profile, run_root)

    prepared = source_preparation.layout_images(plan, run_root, profile)
    pandoc_options = PandocRenderer._resource_path_options(
        roots,
        manifest_resource_roots=plan.manifest_resource_roots,
        legacy_profile_paths=profile.render_environment.resource_paths,
    )

    expected_paths = [str(path) for path in resource_root_paths(roots)]
    assert pandoc_options == ["--resource-path", os.pathsep.join(expected_paths)]
    assert prepared.boundary_assertions["layout_image_graphicspath_roots"] == [
        path.rstrip("/") + "/" for path in expected_paths
    ]


def test_absent_manifest_roots_preserve_legacy_pandoc_options_and_layout_order(
    tmp_path, monkeypatch
):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "source.md"
    source.write_text(
        "```{=latex}\n\\includegraphics{assets/example.png}\n```\n",
        encoding="utf-8",
    )
    run_root = tmp_path / "run"
    profile_root_one = tmp_path / "profile-one"
    profile_root_two = tmp_path / "profile-two"
    profile_root_one.mkdir()
    profile_root_two.mkdir()
    missing_profile_root = tmp_path / "optional-missing-profile"
    profile = _profile([profile_root_one, missing_profile_root, profile_root_two])
    monkeypatch.setattr(pandoc_renderer_module, "resolve_profile", lambda _profile_id: profile)
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="absent-manifest-roots",
        render_source=source,
        source_resource_roots=[source_root],
    )
    roots = effective_resource_roots(plan, profile, run_root)

    prepared = source_preparation.layout_images(plan, run_root, profile)
    pandoc_options = PandocRenderer._resource_path_options(
        roots,
        manifest_resource_roots=plan.manifest_resource_roots,
        legacy_profile_paths=profile.render_environment.resource_paths,
    )

    assert pandoc_options == [
        "--resource-path",
        str(profile_root_one),
        "--resource-path",
        str(profile_root_two),
    ]
    assert prepared.boundary_assertions["layout_image_graphicspath_roots"][:2] == [
        source_root.as_posix().rstrip("/") + "/",
        run_root.as_posix().rstrip("/") + "/",
    ]


def test_direct_document_plan_has_source_root_but_no_manifest_root(tmp_path):
    source = tmp_path / "direct.md"
    source.write_text("# Direct\n", encoding="utf-8")

    plan = DocumentRenderer().build_plan(source, "generic-report")

    assert plan.source_resource_roots == [tmp_path.resolve()]
    assert plan.manifest_resource_roots == []


def test_raw_latex_reference_is_included_in_winner_and_collision_evidence(tmp_path):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    profile_root = tmp_path / "profile"
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    reference = "assets/book/raw-plate.png"
    for root in (manifest_root, profile_root):
        target = root / reference
        target.parent.mkdir(parents=True)
        target.write_bytes(b"plate")
    source = source_root / "source.md"
    source.write_text(
        "```{=latex}\n"
        "\\includegraphics[width=\\textwidth]{\\detokenize{" + reference + "}}\n"
        "```\n",
        encoding="utf-8",
    )
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="raw-reference",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
    )
    roots = effective_resource_roots(plan, _profile([profile_root]), run_root)

    evidence = resource_resolution_evidence(plan, roots)

    assert evidence["resolved_resources"] == [
        {
            "reference": reference,
            "winner": str((manifest_root / reference).resolve()),
            "winner_origin": "manifest",
            "shadowed": [str((profile_root / reference).resolve())],
        }
    ]


@pytest.mark.parametrize(
    "raw_macro",
    [
        r"\OFOuterRail{assets/codex/outer.png}",
        r"\OFBottomRail{assets/codex/bottom.png}",
        r"\OFEdgeOrnament[edge=outer,width=.5in]{assets/codex/edge.pdf}",
        r"\OFSectionDividerBackground{assets/codex/divider.jpg}",
        r"\includegraphics[width=1in]{assets/codex/direct.png}",
    ],
)
def test_supported_raw_image_macros_trigger_graphicspath_preprocessing(tmp_path, raw_macro):
    source = tmp_path / "raw-macro.md"
    source.write_text(f"```{{=latex}}\n{raw_macro}\n```\n", encoding="utf-8")

    result = preprocess_layout_image_blocks(source, tmp_path / "render", "raw-macro")

    assert result.changed is True
    assert raw_macro in result.rewritten_source.read_text(encoding="utf-8")
    assert "\\graphicspath{" in result.rewritten_source.read_text(encoding="utf-8")


def test_supported_indirect_codex_macros_have_truthful_manifest_winner_evidence(tmp_path):
    run_root = tmp_path / "run"
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    profile_root = tmp_path / "profile"
    for root in (run_root, source_root, manifest_root, profile_root):
        root.mkdir()
    references = [
        "assets/codex/outer.png",
        "assets/codex/bottom.png",
        "assets/codex/edge.pdf",
        "assets/codex/divider.jpg",
        "assets/codex/direct.png",
    ]
    for root in (manifest_root, profile_root):
        for reference in references:
            target = root / reference
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"image")
    source = source_root / "codex-macros.md"
    source.write_text(
        "```{=latex}\n"
        "\\OFOuterRail{assets/codex/outer.png}\n"
        "\\OFBottomRail{\\detokenize{assets/codex/bottom.png}}\n"
        "\\OFEdgeOrnament[edge=outer,width=.5in]{assets/codex/edge.pdf}\n"
        "\\OFSectionDividerBackground{assets/codex/divider.jpg}\n"
        "\\includegraphics[width=1in]{assets/codex/direct.png}\n"
        "```\n",
        encoding="utf-8",
    )
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="codex-macro-evidence",
        render_source=source,
        source_resource_roots=[source_root],
        manifest_resource_roots=[manifest_root],
    )
    roots = effective_resource_roots(plan, _profile([profile_root]), run_root)

    evidence = resource_resolution_evidence(plan, roots)

    assert set(typed_resource_references(plan)) == set(references)
    assert {item["reference"] for item in evidence["resolved_resources"]} == set(references)
    for item in evidence["resolved_resources"]:
        reference = item["reference"]
        assert item["winner"] == str((manifest_root / reference).resolve())
        assert item["winner_origin"] == "manifest"
        assert item["shadowed"] == [str((profile_root / reference).resolve())]


def _manifest_template_resource_plan(tmp_path: Path) -> tuple[ProjectionPlan, Path, list[str]]:
    source_root = tmp_path / "source"
    manifest_root = tmp_path / "work"
    source_root.mkdir()
    manifest_root.mkdir()
    references = ["assets/work-titlepage.png", "assets/work-logo.png"]
    # Any real PNG serves; a synthetic fixture image (the Oasis CAM logo left the engine, SIL-32).
    fallback = Path("fixtures/sources/household_paper_placeholder_grey.png").resolve()
    for reference in references:
        target = manifest_root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fallback, target)
    source = source_root / "template-resources.md"
    source.write_text(
        "---\n"
        "title: Manifest template resources\n"
        "titlepage: true\n"
        f"titlepage_background_image: {references[0]}\n"
        f"logo_path: {references[1]}\n"
        "---\n\n"
        "# Plain body\n\n"
        "No body image controls.\n",
        encoding="utf-8",
    )
    return (
        ProjectionPlan(
            profile_id="generic-report",
            render_id="manifest-template-resources",
            render_source=source,
            source_resource_roots=[source_root],
            manifest_resource_roots=[manifest_root],
        ),
        manifest_root,
        references,
    )


def test_manifest_only_template_resources_receive_graphicspath_and_winner_evidence(
    tmp_path, monkeypatch
):
    plan, manifest_root, references = _manifest_template_resource_plan(tmp_path)
    run_root = tmp_path / "render"
    profile = _profile([])
    monkeypatch.setattr(pandoc_renderer_module, "resolve_profile", lambda _profile_id: profile)

    prepared = source_preparation.layout_images(plan, run_root, profile)
    roots = effective_resource_roots(prepared, profile, run_root)
    evidence = resource_resolution_evidence(prepared, roots)

    assert prepared.render_source != plan.render_source
    assert plan.render_source.read_text(encoding="utf-8").endswith(
        "# Plain body\n\nNo body image controls.\n"
    )
    expected_paths = [str(path) for path in resource_root_paths(roots)]
    assert prepared.boundary_assertions["layout_image_graphicspath_roots"] == [
        path.rstrip("/") + "/" for path in expected_paths
    ]
    rewritten = prepared.render_source.read_text(encoding="utf-8")
    assert "\\graphicspath{" in rewritten
    assert f"{{{manifest_root.as_posix()}/}}" in rewritten
    assert set(typed_resource_references(prepared)) == set(references)
    assert evidence["warnings"] == []
    assert evidence["resolved_resources"] == [
        {
            "reference": reference,
            "winner": str((manifest_root / reference).resolve()),
            "winner_origin": "manifest",
            "shadowed": [],
        }
        for reference in references
    ]


def test_emitted_manifest_graphicspath_resolves_titlepage_and_logo_with_xelatex(
    tmp_path, monkeypatch
):
    xelatex = shutil.which("xelatex")
    if not xelatex:
        pytest.skip("xelatex not available")
    assert xelatex is not None
    plan, _manifest_root, references = _manifest_template_resource_plan(tmp_path)
    run_root = tmp_path / "render"
    monkeypatch.setattr(
        pandoc_renderer_module,
        "resolve_profile",
        lambda _profile_id: _profile([]),
    )
    prepared = source_preparation.layout_images(plan, run_root, resolve_profile(plan.profile_id))
    graphicspath = next(
        include
        for include in PandocRenderer._source_header_includes(prepared.render_source)
        if include.startswith("\\graphicspath{")
    )
    probe = tmp_path / "manifest-graphicspath-probe.tex"
    probe.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{graphicx}\n"
        f"{graphicspath}\n"
        "\\begin{document}\n"
        f"\\includegraphics[width=1pt]{{{references[0]}}}\n"
        f"\\includegraphics[width=1pt]{{{references[1]}}}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", probe.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert probe.with_suffix(".pdf").is_file()


def test_image_free_plain_markdown_remains_layout_preprocessor_noop_on_unsafe_path(
    tmp_path, monkeypatch
):
    source_root = tmp_path / "plain%source"
    source_root.mkdir()
    source = source_root / "plain.md"
    source.write_text("# Plain\n\nNo image resources.\n", encoding="utf-8")
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    monkeypatch.setattr(
        pandoc_renderer_module,
        "resolve_profile",
        lambda _profile_id: _profile([profile_root]),
    )
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="plain-noop",
        render_source=source,
    )

    prepared = source_preparation.layout_images(plan, tmp_path / "run", resolve_profile(plan.profile_id))

    assert prepared is plan
    assert prepared.render_source == source


def test_service_and_cli_pass_resolved_manifest_path_to_compiler(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    work_root = tmp_path / "work"
    work_root.mkdir()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "document.yaml"
    manifest_path.write_text(
        yaml.safe_dump(_document_manifest(source, ["../work"]), sort_keys=False),
        encoding="utf-8",
    )

    captured: list[list[Path]] = []

    def fake_render(self, plan, output_dir=None):
        captured.append(plan.manifest_resource_roots)
        return {"status": "ok", "render_id": plan.render_id, "output": {}}

    monkeypatch.setattr(PandocRenderer, "render", fake_render)

    assert service.render_manifest(manifest_path)["status"] == "ok"
    assert cli.cmd_manifest(argparse.Namespace(input=str(manifest_path), output=str(tmp_path / "out"))) == 0
    capsys.readouterr()

    assert captured == [[work_root.resolve()], [work_root.resolve()]]


def test_cli_reports_invalid_resource_root_without_traceback(tmp_path, capsys):
    source = tmp_path / "source.md"
    source.write_text("# Source\n", encoding="utf-8")
    manifest_path = tmp_path / "document.yaml"
    manifest_path.write_text(
        yaml.safe_dump(_document_manifest(source, ["missing-root"]), sort_keys=False),
        encoding="utf-8",
    )

    rc = cli.cmd_manifest(
        argparse.Namespace(input=str(manifest_path), output=str(tmp_path / "out"))
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "VALIDATION ERROR:" in captured.err
    assert "does not exist" in captured.err
