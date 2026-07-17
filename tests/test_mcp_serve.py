from __future__ import annotations

import asyncio
import base64
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent

import mcp_serve


PDF_BYTES = b"%PDF-1.7\n% ephemeral MCP fixture\n%%EOF\n"


def _fake_evidence(output_dir: str | Path, name: str = "report") -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / f"{name}.pdf"
    pdf.write_bytes(PDF_BYTES)
    evidence_path = out / f"{name}.evidence.json"
    evidence_path.write_text('{"status":"ok"}')
    (out / f"{name}.log").write_text("render log")
    return {
        "status": "ok",
        "render_metadata": {"success": True, "warnings": []},
        "output": {
            "pdf_path": str(pdf),
            "pdf_pages": 2,
            "pdf_sha256": "fixture-sha256",
        },
        "boundary": {"placeholder_assets": False},
        "evidence_path": str(evidence_path),
    }


def _result_parts(result: CallToolResult) -> tuple[dict, EmbeddedResource]:
    text = next(item for item in result.content if isinstance(item, TextContent))
    resource = next(item for item in result.content if isinstance(item, EmbeddedResource))
    return json.loads(text.text), resource


def test_render_report_returns_embedded_pdf_and_removes_server_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Path] = {}

    def fake_render_document(source: str | Path, profile: str, output_dir: str | None = None) -> dict:
        assert profile == "client_report"
        assert output_dir is not None
        captured["source"] = Path(source)
        captured["output_dir"] = Path(output_dir)
        assert captured["source"].exists()
        return _fake_evidence(output_dir, "client-report")

    monkeypatch.setattr(mcp_serve.service, "render_document", fake_render_document)

    result = mcp_serve.render_report(
        markdown_text="---\ntitle: Client Test\n---\n\n# Report\n",
        profile="client_report",
    )

    metadata, resource = _result_parts(result)
    assert metadata["status"] == "ok"
    assert metadata["artifact_retained_on_server"] is False
    assert metadata["delivery"] == "embedded_resource"
    assert "pdf_path" not in metadata
    assert "evidence_path" not in metadata
    assert isinstance(resource.resource, BlobResourceContents)
    assert resource.resource.mimeType == "application/pdf"
    assert base64.b64decode(resource.resource.blob) == PDF_BYTES
    assert not captured["source"].exists()
    assert not captured["output_dir"].exists()


def test_render_report_removes_temporary_files_when_rendering_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Path] = {}

    def failing_render_document(source: str | Path, profile: str, output_dir: str | None = None) -> dict:
        assert output_dir is not None
        captured["source"] = Path(source)
        captured["output_dir"] = Path(output_dir)
        captured["output_dir"].mkdir(parents=True, exist_ok=True)
        (captured["output_dir"] / "partial.pdf").write_bytes(PDF_BYTES)
        raise RuntimeError("synthetic render failure")

    monkeypatch.setattr(mcp_serve.service, "render_document", failing_render_document)

    with pytest.raises(RuntimeError, match="synthetic render failure"):
        mcp_serve.render_report(markdown_text="# Failure", profile="client_report")

    assert not captured["source"].exists()
    assert not captured["output_dir"].exists()


def test_render_manifest_returns_embedded_pdf_without_retaining_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("kind: bundle\nschema_version: v1\n")
    captured: dict[str, Path] = {}

    def fake_render_manifest(manifest_path: str | Path, output_dir: str | None = None) -> dict:
        assert Path(manifest_path) == manifest
        assert output_dir is not None
        captured["output_dir"] = Path(output_dir)
        return _fake_evidence(output_dir, "bundle")

    monkeypatch.setattr(mcp_serve.service, "render_manifest", fake_render_manifest)

    result = mcp_serve.render_manifest(str(manifest))

    metadata, resource = _result_parts(result)
    assert metadata["artifact_retained_on_server"] is False
    assert metadata["delivery"] == "embedded_resource"
    assert isinstance(resource.resource, BlobResourceContents)
    assert base64.b64decode(resource.resource.blob) == PDF_BYTES
    assert not captured["output_dir"].exists()


def test_distill_defaults_missing_placeholder_boundary_to_false() -> None:
    metadata = mcp_serve._distill(
        {"status": "ok", "render_metadata": {}, "output": {}, "boundary": {}}
    )
    assert metadata["placeholder_assets"] is False


def test_distill_surfaces_report_contract_fields() -> None:
    metadata = mcp_serve._distill(
        {
            "status": "ok",
            "render_metadata": {
                "success": True,
                "profile": "client_report",
                "profile_version": "1.1.0",
                "resolved_classification": "public",
                "resolved_document_status": "draft",
            },
            "output": {},
            "boundary": {"frontmatter_warnings": ["classification not set"]},
        }
    )
    assert metadata["profile_id"] == "client_report"
    assert metadata["profile_version"] == "1.1.0"
    assert metadata["resolved_classification"] == "public"
    assert metadata["resolved_document_status"] == "draft"
    assert metadata["frontmatter_warnings"] == ["classification not set"]


def test_embedded_pdf_result_uses_artifact_name_for_filename(tmp_path) -> None:
    evidence = _fake_evidence(tmp_path, "ephemeral-render")
    evidence["output"]["artifact_name"] = "slingshot-public-summary.pdf"
    result = mcp_serve._embedded_pdf_result(evidence)
    metadata, resource = _result_parts(result)
    assert metadata["filename"] == "slingshot-public-summary.pdf"
    assert resource.resource.uri.unicode_string().endswith("slingshot-public-summary.pdf")


def test_mcp_render_tools_do_not_accept_caller_controlled_output_directories() -> None:
    assert "output_dir" not in inspect.signature(mcp_serve.render_report).parameters
    assert "output_dir" not in inspect.signature(mcp_serve.render_manifest).parameters


class _FakeMcpServer:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            host=None,
            port=None,
            streamable_http_path=None,
            transport_security=None,
        )
        self.removed_tools: list[str] = []
        self.added_tools: list[tuple[object, str | None]] = []
        self.run_transports: list[str] = []

    def remove_tool(self, name: str) -> None:
        self.removed_tools.append(name)

    def add_tool(self, fn: object, name: str | None = None) -> None:
        self.added_tools.append((fn, name))

    def run(self, transport: str = "stdio") -> None:
        self.run_transports.append(transport)


def test_http_main_honors_requested_bind_and_exposes_inline_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPTICAL_FOUNDRY_MCP_BEARER_TOKEN", "t" * 48)
    server = _FakeMcpServer()

    mcp_serve.main(
        [
            "--transport",
            "streamable-http",
            "--host",
            "192.0.2.10",
            "--port",
            "8768",
            "--public-host",
            "foundry.example.org",
        ],
        server=server,
    )

    assert server.settings.host == "192.0.2.10"
    assert server.settings.port == 8768
    assert server.settings.streamable_http_path == "/mcp"
    assert server.run_transports == ["streamable-http"]
    assert server.removed_tools == ["render_report", "render_manifest", "contact_sheet"]
    assert len(server.added_tools) == 1
    remote_render, tool_name = server.added_tools[0]
    assert tool_name == "render_report"
    assert list(inspect.signature(remote_render).parameters) == ["markdown_text", "profile"]

    security = server.settings.transport_security
    assert security.enable_dns_rebinding_protection is True
    assert "192.0.2.10:8768" in security.allowed_hosts
    assert "foundry.example.org" in security.allowed_hosts
    assert "https://foundry.example.org" in security.allowed_origins


def test_http_main_refuses_to_start_without_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPTICAL_FOUNDRY_MCP_BEARER_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="OPTICAL_FOUNDRY_MCP_BEARER_TOKEN"):
        mcp_serve.main(["--transport", "streamable-http"], server=_FakeMcpServer())


def test_environment_bearer_verifier_uses_constant_time_token_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPTICAL_FOUNDRY_MCP_BEARER_TOKEN", "correct-" + ("x" * 40))
    verifier = mcp_serve.EnvironmentBearerTokenVerifier()

    accepted = asyncio.run(verifier.verify_token("correct-" + ("x" * 40)))
    rejected = asyncio.run(verifier.verify_token("wrong-" + ("x" * 42)))

    assert accepted is not None
    assert accepted.client_id == "client-agent"
    assert accepted.scopes == ["render"]
    assert rejected is None


def test_stdio_main_preserves_full_local_tool_surface() -> None:
    server = _FakeMcpServer()
    mcp_serve.main([], server=server)
    assert server.removed_tools == []
    assert server.added_tools == []
    assert server.run_transports == ["stdio"]


def test_healthz_reports_ready_without_rendering() -> None:
    response = asyncio.run(mcp_serve.healthz(None))
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ok",
        "service": "optical-foundry-mcp",
        "transport": "streamable-http",
    }
