"""Tests for CLI registry wiring — manifest→compiler resolution."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_registry import ManifestRegistry
from engine.manifest_compiler import (
    CompositeBundleCompiler, CAMStackCompiler, CodexBundleCompiler, LabelRunCompiler,
    StickerSheetCompiler, ForgePacketReviewCompiler, MarkdownDocumentCompiler,
)


def _default_registry() -> ManifestRegistry:
    reg = ManifestRegistry()
    for cls in [CompositeBundleCompiler, CAMStackCompiler, CodexBundleCompiler, LabelRunCompiler, StickerSheetCompiler, ForgePacketReviewCompiler, MarkdownDocumentCompiler]:
        reg.register(cls.kind, cls.schema_version, cls)
    return reg


def test_registry_resolves_bundle():
    reg = _default_registry()
    raw = {"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "profile": "cam"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == CompositeBundleCompiler


def test_registry_resolves_cam_stack_bundle_alias():
    reg = _default_registry()
    raw = {"kind": "cam_stack", "schema_version": "bundle_manifest_v1", "profile": "cam"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == CAMStackCompiler


def test_registry_resolves_codex_bundle_alias():
    reg = _default_registry()
    raw = {"kind": "codex_bundle", "schema_version": "bundle_manifest_v1", "profile": "mythic"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == CodexBundleCompiler


def test_registry_resolves_label():
    reg = _default_registry()
    raw = {"kind": "label_run", "schema_version": "label_run_v1", "profile": "labels-avery-5164"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == LabelRunCompiler


def test_registry_resolves_sticker():
    reg = _default_registry()
    raw = {"kind": "sticker_sheet", "schema_version": "sticker_sheet_v1", "profile": "sticker-sheet"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == StickerSheetCompiler


def test_registry_resolves_packet_review():
    reg = _default_registry()
    raw = {"kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1", "profile": "prometheus-packet"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == ForgePacketReviewCompiler


def test_registry_resolves_markdown_document():
    reg = _default_registry()
    raw = {"kind": "markdown_document", "schema_version": "document_manifest_v1", "profile": "generic-report"}
    compiler_cls = reg.resolve_compiler(raw)
    assert compiler_cls == MarkdownDocumentCompiler


def test_registry_returns_none_for_unknown():
    reg = _default_registry()
    assert reg.resolve_compiler({}) is None
    assert reg.resolve_compiler({"kind": "bogus"}) is None


def test_all_compilers_registered():
    reg = _default_registry()
    kinds = reg.supported_kinds()
    for k in ["composite_bundle", "cam_stack", "codex_bundle", "label_run", "sticker_sheet", "forge_packet_review", "markdown_document"]:
        assert k in kinds, f"expected {k} in supported kinds"
