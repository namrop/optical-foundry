"""Tests for engine.manifest_registry — registry registration/lookup."""
from engine.manifest_registry import ManifestRegistry
from engine.manifest_compiler import ManifestCompiler, NullCompiler


class FakeCompiler(ManifestCompiler):
    kind = "composite_bundle"
    schema_version = "bundle_manifest_v1"

    def compile(self, manifest, **kwargs):
        raise NotImplementedError

    def validate(self, manifest):
        return []


def test_register_and_get():
    reg = ManifestRegistry()
    reg.register("composite_bundle", "bundle_manifest_v1", FakeCompiler)
    assert reg.get_compiler("composite_bundle", "bundle_manifest_v1") is FakeCompiler


def test_unknown_returns_none():
    reg = ManifestRegistry()
    assert reg.get_compiler("unknown", "v9") is None


def test_double_register_raises():
    reg = ManifestRegistry()
    reg.register("composite_bundle", "bundle_manifest_v1", FakeCompiler)
    try:
        reg.register("composite_bundle", "bundle_manifest_v1", FakeCompiler)
        assert False, "should have raised"
    except KeyError:
        pass


def test_known_subtypes():
    reg = ManifestRegistry()
    reg.register("composite_bundle", "bundle_manifest_v1", FakeCompiler)
    tris = reg.known_subtypes()
    assert any(t[0] == "composite_bundle" for t in tris)


def test_supported_kinds_includes_registered_and_declared():
    reg = ManifestRegistry()
    reg.register("composite_bundle", "bundle_manifest_v1", FakeCompiler)
    kinds = reg.supported_kinds()
    assert "composite_bundle" in kinds
    for kind in ("label_run", "sticker_sheet", "forge_packet_review", "cam_stack", "codex_bundle"):
        assert kind in kinds, f"declared kind {kind} missing from supported_kinds"
