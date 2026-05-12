"""Tests for manifest compilers — composite bundle and label run."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_compiler import CompositeBundleCompiler, CAMStackCompiler, CodexBundleCompiler, LabelRunCompiler, StickerSheetCompiler, ForgePacketReviewCompiler, MarkdownDocumentCompiler
from engine.projection_plan import ProjectionPlan

GF = Path(__file__).resolve().parents[1]
SRC = GF / "fixtures" / "sources"


def test_markdown_document_validate_valid():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "test-doc-manifest", "profile": "generic-report",
        "source": {"path": str(SRC / "source-001.md")},
        "render": {"include_toc": False, "numbersections": False, "emit_visible_provenance": False},
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_markdown_document_compile_preserves_source_body_without_bundle_wrapping():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "test-doc-manifest", "profile": "generic-report",
        "source": {"path": str(SRC / "source-001.md")},
        "render": {
            "preserve_source_metadata": True,
            "metadata_merge_policy": "source_then_manifest_override",
            "include_toc": False,
            "numbersections": False,
            "emit_visible_provenance": False,
            "heading_transform": "preserve",
        },
        "metadata": {"title": "Manifest Override Title"},
        "variables": {"sample": True, "division": "Oasis"},
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert isinstance(plan, ProjectionPlan)
    assert plan.profile_id == "generic-report"
    assert plan.render_id == "test-doc-manifest"
    assert plan.toc is False
    assert plan.numbersections is False
    assert plan.title == "Manifest Override Title"
    assert plan.source_inventory[0]["uid"] == "test-doc-manifest"
    assert plan.source_inventory[0]["manifest_lane"] == "markdown_document"
    assert plan.boundary_assertions["document_manifest_lane"] is True
    assert plan.boundary_assertions["emit_visible_provenance"] is False
    assert plan.boundary_assertions["heading_transform"] == "preserve"
    assert "# Source" not in assembled
    assert "Provenance & Evidence" not in assembled
    assert "### Primary Synthetic Source" not in assembled
    assert "# Primary Synthetic Source" in assembled
    assert "sample: true" in assembled
    assert "division: Oasis" in assembled


def test_markdown_document_rejects_unsafe_variable_keys_and_paths():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "bad-vars", "profile": "generic-report",
        "source": {"path": str(SRC / "source-001.md")},
        "variables": {
            "sample": True,
            "evil": "\\input{/etc/passwd}",
            "logo_path": "/etc/passwd",
        },
    }
    plan = compiler.compile(manifest)
    accepted = plan.boundary_assertions["accepted_manifest_variables"]
    rejected = plan.boundary_assertions["rejected_manifest_variables"]
    assert "sample" in accepted
    assert "evil" in rejected
    assert "logo_path" in rejected


def test_markdown_document_accepts_chart_theme_variables_for_mermaid():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "chart-vars", "profile": "cam",
        "source": {"path": str(SRC / "source-001.md")},
        "variables": {
            "chart_primary": "#123456",
            "chart_accent": "D5972B",
            "chart_background": "#F7F4ED",
        },
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    accepted = plan.boundary_assertions["accepted_manifest_variables"]

    assert "chart_primary" in accepted
    assert "chart_accent" in accepted
    assert "chart_primary: '#123456'" in assembled or "chart_primary: \"#123456\"" in assembled
    assert "chart_accent: D5972B" in assembled


def test_markdown_document_accepts_titlepage_background_variables():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "title-bg-doc", "profile": "cam",
        "source": {"path": str(SRC / "source-001.md")},
        "variables": {
            "titlepage": True,
            "titlepage_background_image": "assets/logo_oasis_cam.png",
        },
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    accepted = plan.boundary_assertions["accepted_manifest_variables"]

    assert "titlepage" in accepted
    assert "titlepage_background_image" in accepted
    assert "titlepage: true" in assembled
    assert "titlepage_background_image: assets/logo_oasis_cam.png" in assembled
    assert "titlepage_background_image" not in plan.boundary_assertions["rejected_manifest_variables"]


def test_markdown_document_rejects_unsafe_titlepage_background_path():
    compiler = MarkdownDocumentCompiler()
    manifest = {
        "kind": "markdown_document", "schema_version": "document_manifest_v1",
        "document_id": "bad-title-bg-doc", "profile": "cam",
        "source": {"path": str(SRC / "source-001.md")},
        "variables": {
            "titlepage": True,
            "titlepage_background_image": "/etc/passwd",
        },
    }
    plan = compiler.compile(manifest)

    assert "titlepage" in plan.boundary_assertions["accepted_manifest_variables"]
    assert "titlepage_background_image" in plan.boundary_assertions["rejected_manifest_variables"]
    assert "titlepage_background_image: /etc/passwd" not in plan.render_source.read_text()


def test_composite_bundle_validate_valid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "src2", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_composite_bundle_validate_missing_uid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [{"role": "primary_anchor", "order": 1}],
    }
    errors = compiler.validate(manifest)
    assert any("missing uid" in e for e in errors)


def test_composite_bundle_validate_duplicate_uid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "dup", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "dup", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    errors = compiler.validate(manifest)
    assert any("duplicate uid" in e for e in errors)


def test_composite_bundle_validate_missing_path():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [{"uid": "src1", "path": "/nonexistent/path.md", "role": "primary_anchor", "order": 1}],
    }
    errors = compiler.validate(manifest)
    assert any("not found" in e for e in errors), errors


def test_composite_bundle_compile_produces_plan():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
            {"uid": "fixture-src-003", "path": str(SRC / "source-003.md"), "role": "appendix", "order": 3},
        ],
    }
    plan = compiler.compile(manifest)
    assert isinstance(plan, ProjectionPlan)
    assert plan.profile_id == "cam"
    assert plan.has_assembly
    assert plan.assembly is not None
    assert len(plan.assembly.source_order) == 3
    assert plan.source_inventory[0]["uid"] == "fixture-src-001"
    assert plan.render_source.exists()


def test_composite_bundle_faithful_stack_preserves_sources_without_reader_provenance():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "faithful-stack", "profile": "cam",
        "sources": [
            {
                "uid": "fixture-src-001",
                "path": str(SRC / "source-001.md"),
                "role": "primary_anchor",
                "order": 1,
                "title": "Wrapper Should Not Render",
                "include_frontmatter": "none",
                "suppress_frontmatter": True,
            },
        ],
        "render": {"assembly_strategy": "faithful_stack"},
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert "# Wrapper Should Not Render" not in assembled
    assert "# Primary Synthetic Source" in assembled
    assert "## Primary Synthetic Source" not in assembled
    assert "Provenance & Evidence" not in assembled
    assert plan.boundary_assertions["emit_visible_provenance"] is False
    assert plan.boundary_assertions["suppress_source_wrapper_headings"] is True
    assert plan.boundary_assertions["preserve_source_heading_levels"] is True


def test_composite_bundle_title_page_background_presentation_surface():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "bundle-title-bg", "profile": "cam",
        "presentation": {
            "title": "Background Bundle",
            "title_page": {
                "enabled": True,
                "background_image": "assets/logo_oasis_cam.png",
            },
        },
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert assembled.startswith("---\n")
    assert "titlepage: true" in assembled
    assert "titlepage_background_image: assets/logo_oasis_cam.png" in assembled
    assert plan.boundary_assertions["title_page_background_enabled"] is True
    assert plan.boundary_assertions["titlepage_background_image"] == "assets/logo_oasis_cam.png"


def test_composite_bundle_title_page_blank_after_presentation_surface():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "bundle-title-blank", "profile": "cam",
        "presentation": {
            "title": "Blank After Bundle",
            "title_page": {
                "enabled": True,
                "blank_after": True,
            },
        },
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert assembled.startswith("---\n")
    assert "titlepage: true" in assembled
    assert "titlepage_blank_after: true" in assembled
    assert "titlepage_blank_after" in plan.boundary_assertions["accepted_title_page_variables"]


def test_composite_bundle_rejects_unsafe_title_page_background_presentation_path():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "bad-bundle-title-bg", "profile": "cam",
        "presentation": {
            "title_page": {
                "enabled": True,
                "background_image": "../secrets/cover.png",
            },
        },
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
    }
    errors = compiler.validate(manifest)

    assert any("presentation.title_page.background_image" in e for e in errors)


def test_composite_bundle_inserts_generic_section_divider_before_source():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "section-divider-generic", "profile": "generic-report",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
        "section_dividers": [
            {
                "uid": "evidence-title-page",
                "before_source_uid": "fixture-src-002",
                "title": "Evidence & Field",
                "subtitle": "Why this section matters",
                "body": "A compact orientation page before the evidence source.",
            },
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert "Evidence \\& Field" in assembled
    assert "Why this section matters" in assembled
    assert "A compact orientation page" in assembled
    assert assembled.index("Evidence \\& Field") < assembled.index("# Supporting Synthetic Source")
    assert plan.boundary_assertions["section_dividers_enabled"] is True
    assert plan.boundary_assertions["section_divider_count"] == 1
    assert plan.assembly.generated_sections == ["section_divider:evidence-title-page"]


def test_composite_bundle_inserts_source_backed_section_divider_before_source_order():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "section-divider-source", "profile": "generic-report",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
        "section_dividers": [
            {
                "uid": "appendix-title-page",
                "before_source_order": 2,
                "source": {"path": str(SRC / "source-003.md"), "include_frontmatter": "none"},
            },
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert "# Data Appendix" in assembled
    assert "This appendix contains synthetic reference data." in assembled
    assert assembled.index("# Data Appendix") < assembled.index("# Supporting Synthetic Source")
    divider_inventory = plan.boundary_assertions["section_dividers"]
    assert divider_inventory == [
        {
            "uid": "appendix-title-page",
            "before_source_uid": "fixture-src-002",
            "before_source_order": 2,
            "kind": "source",
            "force_right_page": True,
            "blank_after": False,
            "background_image": "",
            "source_path": str(SRC / "source-003.md"),
        }
    ]


def test_composite_bundle_validates_section_divider_targets_and_source_paths():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "bad-section-divider", "profile": "generic-report",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
        "section_dividers": [
            {"uid": "missing-target", "before_source_uid": "does-not-exist", "title": "Missing"},
            {"uid": "missing-source", "before_source_order": 1, "source": {"path": "/nonexistent/divider.md"}},
        ],
    }

    errors = compiler.validate(manifest)

    assert any("section_divider[0] before_source_uid not found" in e for e in errors)
    assert any("section_divider[1] source path not found" in e for e in errors)


def test_composite_bundle_defaults_title_blank_after_and_section_divider_recto():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "divider-recto-defaults", "profile": "cam",
        "presentation": {"title": "Recto Defaults", "title_page": {"enabled": True}},
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
        "section_dividers": [
            {"uid": "evidence", "before_source_uid": "fixture-src-002", "title": "Evidence"},
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert "titlepage_blank_after: true" in assembled
    assert "\\OFEnsureRightPage" in assembled
    assert "\\OFIntentionalBlankPage" not in assembled.split("Evidence")[1].split("# Supporting Synthetic Source")[0]
    assert plan.boundary_assertions["titlepage_blank_after"] is True
    assert plan.boundary_assertions["section_dividers"][0]["force_right_page"] is True
    assert plan.boundary_assertions["section_dividers"][0]["blank_after"] is False


def test_composite_bundle_section_divider_profile_background_and_blank_after():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "divider-presentation", "profile": "cam",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
        "section_dividers": [
            {
                "uid": "profiled",
                "before_source_uid": "fixture-src-002",
                "title": "Profiled Divider",
                "profile_id": "mythic",
                "background_image": "assets/logo_oasis_cam.png",
                "force_right_page": False,
                "blank_after": True,
            },
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    divider_block = assembled.split("Profiled Divider")[0]

    assert "\\OFSectionDividerBackground{assets/logo_oasis_cam.png}" in assembled
    assert "\\OFApplySectionDividerProfile{mythic}{document_spine}" in assembled
    assert "\\clearpage" in divider_block
    assert "\\OFEnsureRightPage" not in divider_block
    assert "\\OFIntentionalBlankPage" in assembled.split("Profiled Divider")[1].split("# Supporting Synthetic Source")[0]
    inventory = plan.boundary_assertions["section_dividers"][0]
    assert inventory["requested_profile_id"] == "mythic"
    assert inventory["resolved_profile_id"] == "mythic"
    assert inventory["profile_family"] == "document_spine"
    assert inventory["background_image"] == "assets/logo_oasis_cam.png"
    assert inventory["force_right_page"] is False
    assert inventory["blank_after"] is True


def test_composite_bundle_validates_section_divider_background_and_profile_family():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "bad-divider-presentation", "profile": "cam",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
        "section_dividers": [
            {
                "uid": "unsafe-bg",
                "before_source_uid": "fixture-src-001",
                "title": "Bad BG",
                "background_image": "../secrets/bg.png",
            },
            {
                "uid": "wrong-family",
                "before_source_uid": "fixture-src-001",
                "title": "Wrong Family",
                "profile_id": "mythic-letter",
                "profile_family": "document_spine",
            },
        ],
    }

    errors = compiler.validate(manifest)

    assert any("section_divider[0] background_image" in e for e in errors)
    assert any("section_divider[1] requested profile_family=document_spine" in e for e in errors)


def test_composite_bundle_section_divider_numbering_demotes_source_headings_and_marks_appendices():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "faithful-divider-numbering", "profile": "cam",
        "render": {"numbering_strategy": "section_dividers", "assembly_strategy": "faithful_stack"},
        "sources": [
            {"uid": "preface", "path": str(SRC / "source-001.md"), "role": "frontmatter", "order": 1},
            {"uid": "body", "path": str(SRC / "source-002.md"), "role": "primary_anchor", "order": 2},
            {"uid": "appendix-a", "path": str(SRC / "source-003.md"), "role": "appendix", "order": 3},
        ],
        "section_dividers": [
            {"uid": "body-section", "before_source_uid": "body", "title": "Body Section"},
            {"uid": "appendix-section", "before_source_uid": "appendix-a", "title": "Appendix Section"},
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()

    assert "\\frontmatter" in assembled
    assert "\\mainmatter" in assembled
    assert "\\OFBeginAppendices" in assembled
    assert "\\refstepcounter{section}" in assembled
    assert "\\addcontentsline{toc}{section}{\\protect\\numberline{\\thesection}Body Section}" in assembled
    assert "\\addcontentsline{toc}{section}{\\protect\\numberline{\\thesection}Appendix Section}" in assembled
    assert "## Supporting Synthetic Source" in assembled
    assert "\n# Supporting Synthetic Source" not in assembled
    assert assembled.find("# Supporting Synthetic Source") == -1 or assembled.find("# Supporting Synthetic Source") == assembled.find("## Supporting Synthetic Source") + 1
    assert "## Data Appendix" in assembled
    assert plan.boundary_assertions["section_divider_numbering"] == "section_dividers"
    assert plan.assembly.numbering_strategy == "section_dividers"


def test_source_backed_section_divider_preserves_authored_heading_for_numbering():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "source-backed-divider-numbering", "profile": "cam",
        "render": {"numbering_strategy": "section_dividers", "assembly_strategy": "faithful_stack"},
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
        "section_dividers": [
            {
                "uid": "designed-divider",
                "before_source_uid": "fixture-src-002",
                "source": {"path": str(SRC / "source-003.md"), "include_frontmatter": "none"},
            },
        ],
    }

    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    divider_to_source = assembled.split("Data Appendix", 1)[1].split("Supporting material", 1)[0]

    assert "\\addcontentsline{toc}{section}{\\protect\\numberline{\\thesection}Data Appendix}" in assembled
    assert "{\\Huge\\bfseries \\thesection\\quad Data Appendix\\par}" in assembled
    assert "# Data Appendix" not in assembled
    assert "## Data Appendix" not in assembled
    assert "## Supporting Synthetic Source" in divider_to_source
    assert plan.boundary_assertions["section_divider_numbering"] == "section_dividers"


def test_latex_templates_use_required_intentional_blank_page_text():
    template = (Path(__file__).resolve().parents[1] / "profiles" / "40_latex_import" / "templates" / "cam.tex").read_text()
    assert "this page was intentionally left blank" in template
    assert "This page intentionally left blank" not in template


def test_cam_stack_compile_uses_bundle_semantics_with_cam_kind():
    compiler = CAMStackCompiler()
    manifest = {
        "kind": "cam_stack", "schema_version": "bundle_manifest_v1",
        "bundle_id": "cam-stack-smoke", "profile": "cam",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    plan = compiler.compile(manifest)
    assert plan.profile_id == "cam"
    assert plan.assembly.assembly_kind == "cam_stack"
    assert plan.assembly.manifest_subtype == "cam_stack"
    assert plan.boundary_assertions["manifest_subtype"] == "cam_stack"


def test_codex_bundle_compile_uses_bundle_semantics_with_codex_kind():
    compiler = CodexBundleCompiler()
    manifest = {
        "kind": "codex_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "codex-bundle-smoke", "profile": "mythic",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
    }
    plan = compiler.compile(manifest)
    assert plan.profile_id == "mythic"
    assert plan.assembly.assembly_kind == "codex_bundle"
    assert plan.assembly.manifest_subtype == "codex_bundle"
    assert plan.boundary_assertions["manifest_subtype"] == "codex_bundle"


def test_composite_bundle_compile_bad_manifest_raises():
    compiler = CompositeBundleCompiler()
    try:
        compiler.compile({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1"})
        assert False, "should have raised"
    except ValueError:
        pass


def test_label_run_validate_valid():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 2, "source": str(SRC / "label-002.md")},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_label_run_validate_duplicate_slot():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 1, "source": str(SRC / "label-002.md")},
        ],
    }
    errors = compiler.validate(manifest)
    assert any("duplicate slot" in e for e in errors)


def test_label_run_compile_produces_plan():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "profile": "labels-avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 2, "source": str(SRC / "label-002.md")},
        ],
    }
    plan = compiler.compile(manifest)
    assert isinstance(plan, ProjectionPlan)
    assert plan.has_assembly
    assert len(plan.assembly.source_order) == 2
    assert plan.render_source.exists()
    assert plan.boundary_assertions["layout_mode"] == "content_driven_placeholder"
    assert plan.boundary_assertions["grid_validated"] is False
    assert any("Physical Avery/grid placement" in w for w in plan.boundary_assertions["warnings"])


def test_sticker_sheet_validate():
    compiler = StickerSheetCompiler()
    manifest = {
        "kind": "sticker_sheet", "schema_version": "sticker_sheet_v1",
        "sheet_id": "test-stickers", "profile": "sticker-sheet",
        "layout": {"grid": [2, 2], "cell_size": [2.5, 2.5]},
        "cells": [
            {"position": [0, 0], "content": "Sticker A"},
            {"position": [0, 1], "content": "Sticker B"},
            {"position": [1, 0], "content": "Sticker C"},
            {"position": [1, 1], "content": "Sticker D"},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_sticker_sheet_compile_marks_placeholder_layout():
    compiler = StickerSheetCompiler()
    manifest = {
        "kind": "sticker_sheet", "schema_version": "sticker_sheet_v1",
        "sheet_id": "test-stickers", "profile": "sticker-sheet",
        "layout": {"grid": [2, 2], "cell_size": [2.5, 2.5]},
        "cells": [
            {"position": [0, 0], "content": "Sticker A"},
            {"position": [0, 1], "content": "Sticker B"},
            {"position": [1, 0], "content": "Sticker C"},
            {"position": [1, 1], "content": "Sticker D"},
        ],
    }
    plan = compiler.compile(manifest)
    assert plan.boundary_assertions["layout_mode"] == "content_driven_placeholder"
    assert plan.boundary_assertions["grid_validated"] is False
    assert any("Physical sticker grid placement" in w for w in plan.boundary_assertions["warnings"])


def test_bundle_toc_not_duplicated():
    """TOC handled by PandocRenderer --toc flag only; compiler must NOT emit \\tableofcontents."""
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-toc", "profile": "generic-report",
        "presentation": {"title": "TOC Test", "abstract": "Should have one TOC."},
        "render": {"include_toc": True, "toc_depth": 2, "numbersections": False},
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "src2", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    # Compiler must NOT embed \tableofcontents — pandoc --toc flag handles it
    assert "\\tableofcontents" not in assembled, (
        f"assembled Markdown must not contain \\tableofcontents; pandoc --toc handles TOC"
    )
    # Plan should signal toc=True so PandocRenderer adds --toc
    assert plan.toc is True
    assert plan.toc_depth == 2
    assert plan.numbersections is False


def test_bundle_suppress_frontmatter_true():
    """suppress_frontmatter: true removes the frontmatter code block from assembled output."""
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-suppress", "profile": "generic-report",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1,
             "suppress_frontmatter": True},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    # The source-001.md has frontmatter with uid, title, tags etc.
    # suppress_frontmatter=True should remove the yaml code block
    assert "Source Frontmatter" not in assembled, (
        f"suppress_frontmatter=True should suppress frontmatter block"
    )
    assert "```yaml" not in assembled, (
        f"No yaml code fences expected when suppress_frontmatter=True"
    )
    # But the body content should still be there
    assert "Primary Synthetic Source" in assembled


def test_bundle_suppress_frontmatter_false_default():
    """Default (suppress_frontmatter omitted) includes frontmatter as before."""
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-show-fm", "profile": "generic-report",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    assert "Source Frontmatter" in assembled, (
        f"Default should include frontmatter block"
    )
    assert "```yaml" in assembled


def test_bundle_suppress_frontmatter_explicit_false():
    """suppress_frontmatter: False explicitly includes frontmatter."""
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-explicit-fm", "profile": "generic-report",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1,
             "suppress_frontmatter": False},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    assert "Source Frontmatter" in assembled
    assert "```yaml" in assembled


def test_bundle_suppress_frontmatter_mixed():
    """Mixed: source 1 suppressed, source 2 not."""
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-mixed", "profile": "generic-report",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1,
             "suppress_frontmatter": True},
            {"uid": "src2", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2,
             "suppress_frontmatter": False},
        ],
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    assert "Source Frontmatter" in assembled  # source 2 shows it
    # source 1 frontmatter is suppressed, source 2 frontmatter appears
    assert "uid: fixture-src-002" in assembled  # source 2 fm visible
    assert "uid: fixture-src-001" not in assembled  # source 1 fm suppressed


def test_packet_review_validate():
    compiler = ForgePacketReviewCompiler()
    manifest = {
        "kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {
            "path": str(GF),
            "include": ["BEAM.md", "DESIGN.md"],
        },
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_packet_review_compile_uses_markdown_headings_for_file_names():
    compiler = ForgePacketReviewCompiler()
    manifest = {
        "kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {
            "path": str(GF),
            "include": ["BEAM.md"],
        },
        "render": {
            "include_questions": False,
            "include_dirty_state_summary": False,
        },
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    assert "# `BEAM.md`" in assembled
    assert "\\section{BEAM.md}" not in assembled


def test_packet_review_compile_summarizes_json_instead_of_fencing_full_block():
    compiler = ForgePacketReviewCompiler()
    manifest = {
        "kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {
            "path": str(GF),
            "include": ["STATE.json"],
        },
        "render": {
            "include_questions": False,
            "include_dirty_state_summary": False,
        },
    }
    plan = compiler.compile(manifest)
    assembled = plan.render_source.read_text()
    assert "# `STATE.json`" in assembled
    assert "**JSON summary**" in assembled
    assert "```json" not in assembled


def test_composite_bundle_plan_records_manifest_family_and_child_profiles():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "profile-evidence-bundle", "profile": "generic-report",
        "render": {"assembly_strategy": "combined_markdown", "numbering_strategy": "continuous"},
        "sources": [
            {"uid": "tech-child", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1, "profile_id": "tech"},
            {"uid": "letter-child", "path": str(SRC / "source-002.md"), "role": "appendix", "order": 2, "profile_id": "mythic-letter"},
        ],
    }
    plan = compiler.compile(manifest)

    assert plan.assembly.manifest_family == "bundle_longform"
    assert plan.assembly.assembly_strategy == "combined_markdown"
    assert plan.assembly.numbering_strategy == "continuous"
    assert [c["resolved_profile_id"] for c in plan.assembly.child_profiles] == ["yugen_tech", "mythic-letter"]
    assert [c["profile_family"] for c in plan.assembly.child_profiles] == ["document_spine", "stationery_art"]
    assert [c["defaults_stack"] for c in plan.assembly.child_profiles][0] == ["document_spine.yaml", "yugenbase.yaml", "technology.yaml"]
    assert plan.source_inventory[0]["requested_profile_id"] == "tech"
    assert plan.source_inventory[0]["resolved_profile_id"] == "yugen_tech"
    assert plan.source_inventory[1]["profile_family"] == "stationery_art"


def test_packet_review_plan_records_manifest_family_and_child_profiles():
    compiler = ForgePacketReviewCompiler()
    manifest = {
        "kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {
            "path": str(GF),
            "include": ["STATE.json", "PROGRESS.md"],
        },
        "render": {
            "include_questions": False,
            "include_dirty_state_summary": False,
            "assembly_strategy": "combined_markdown",
            "numbering_strategy": "continuous",
        },
    }
    plan = compiler.compile(manifest)

    assert plan.assembly.manifest_family == "packet_review"
    assert plan.assembly.assembly_strategy == "combined_markdown"
    assert [c["object_id"] for c in plan.assembly.child_profiles] == ["STATE_json", "PROGRESS_md"]
    assert all(c["requested_profile_id"] == "prometheus-packet" for c in plan.assembly.child_profiles)
    assert all(c["profile_family"] == "document_spine" for c in plan.assembly.child_profiles)
    assert plan.boundary_assertions["manifest_family"] == "packet_review"
    assert plan.boundary_assertions["profile_manifest_axes_separate"] is True
