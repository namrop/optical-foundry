#!/usr/bin/env python3
"""Optical Foundry MCP server.

Exposes the Foundry render lane over MCP (FastMCP), so agents can render
profile-branded PDFs from Markdown without touching LaTeX, Pandoc YAML, or brand
assets. The caller contract stays narrow: Markdown plus a profile name.

MCP renders are ephemeral by contract. The server renders inside a temporary
directory, embeds the PDF bytes in the tool response, and removes its temporary
source, PDF, evidence, logs, and intermediates before the call returns. Direct
CLI and service callers retain their normal on-disk behavior.

Run locally over stdio:
    python3 -m mcp_serve
    python3 mcp_serve.py

Run over Streamable HTTP:
    python3 mcp_serve.py --transport streamable-http \
      --host 127.0.0.1 --port 8768 \
      --public-host foundry.example.org

--public-host (default: OPTICAL_FOUNDRY_MCP_PUBLIC_HOST, else localhost) is the
hostname the reverse proxy serves; the auth issuer and resource URLs derive from it.
The HTTP mode requires OPTICAL_FOUNDRY_MCP_BEARER_TOKEN (minimum 32 characters)
and exposes only inline Markdown rendering; path-reading and server-persisting
tools are removed from its advertised remote tool surface.
"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

# Make engine/renderers/cli/service importable when run as a script.
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent
from starlette.requests import Request
from starlette.responses import JSONResponse

import service
from engine.profile_checker import check_all_profiles_json
from engine.visual_proof import build_visual_proof


DEFAULT_PUBLIC_HOST = os.environ.get("OPTICAL_FOUNDRY_MCP_PUBLIC_HOST", "localhost")


def _auth_settings(public_host: str) -> AuthSettings:
    return AuthSettings(
        issuer_url=f"https://{public_host}/",
        resource_server_url=f"https://{public_host}/mcp",
        required_scopes=["render"],
    )


class EnvironmentBearerTokenVerifier:
    """Verify one bearer token supplied through the service environment."""

    env_var = "OPTICAL_FOUNDRY_MCP_BEARER_TOKEN"
    resource = f"https://{DEFAULT_PUBLIC_HOST}/mcp"

    def configured_token(self) -> str | None:
        token = os.environ.get(self.env_var)
        return token if token else None

    async def verify_token(self, token: str) -> AccessToken | None:
        expected = self.configured_token()
        if expected is None or not hmac.compare_digest(token, expected):
            return None
        return AccessToken(
            token=token,
            client_id="client-agent",
            scopes=["render"],
            resource=self.resource,
        )


_bearer_verifier = EnvironmentBearerTokenVerifier()
mcp = FastMCP(
    "optical-foundry",
    token_verifier=_bearer_verifier,
    auth=_auth_settings(DEFAULT_PUBLIC_HOST),
)


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(_request: Request | None) -> JSONResponse:
    """Return a render-free readiness response."""
    return JSONResponse(
        {
            "status": "ok",
            "service": "optical-foundry-mcp",
            "transport": "streamable-http",
        }
    )


def _distill(evidence: dict) -> dict:
    """Reduce a full evidence sidecar to fields safe after temp-tree cleanup."""
    rm = evidence.get("render_metadata", {}) or {}
    out = evidence.get("output", {}) or {}
    boundary = evidence.get("boundary", {}) or {}
    return {
        "status": evidence.get("status"),
        "success": rm.get("success"),
        "pages": out.get("pdf_pages"),
        "pdf_sha256": out.get("pdf_sha256"),
        "warnings": evidence.get("warnings") or rm.get("warnings") or [],
        "error": rm.get("error") or evidence.get("error"),
        "placeholder_assets": bool(boundary.get("placeholder_assets", False)),
        # Report-contract surface so a network caller can verify what it got.
        "profile_id": rm.get("profile"),
        "profile_version": rm.get("profile_version"),
        "resolved_classification": rm.get("resolved_classification"),
        "resolved_document_status": rm.get("resolved_document_status"),
        "frontmatter_warnings": boundary.get("frontmatter_warnings", []),
        "delivery": "embedded_resource",
        "artifact_retained_on_server": False,
    }


def _embedded_pdf_result(evidence: dict) -> CallToolResult:
    """Read a rendered PDF into the MCP result before its temp tree is removed."""
    metadata = _distill(evidence)
    pdf_value = (evidence.get("output", {}) or {}).get("pdf_path")
    pdf_path = Path(str(pdf_value)) if pdf_value else None
    if pdf_path is None or not pdf_path.is_file():
        metadata["delivery"] = "none"
        metadata["filename"] = None
        metadata["mime_type"] = None
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(metadata, indent=2))],
            structuredContent=metadata,
            isError=True,
        )

    pdf_bytes = pdf_path.read_bytes()
    # Prefer the frontmatter-derived, sanitized artifact name over the ephemeral
    # temp source stem (which is otherwise the generic "report.pdf").
    artifact_name = (evidence.get("output", {}) or {}).get("artifact_name") or pdf_path.name
    metadata.update(
        {
            "filename": artifact_name,
            "mime_type": "application/pdf",
            "bytes": len(pdf_bytes),
        }
    )
    resource = EmbeddedResource(
        type="resource",
        resource=BlobResourceContents(
            uri=f"artifact://optical-foundry/{artifact_name}",
            mimeType="application/pdf",
            blob=base64.b64encode(pdf_bytes).decode("ascii"),
        ),
    )
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(metadata, indent=2)),
            resource,
        ],
        structuredContent=metadata,
        isError=not bool(metadata.get("success")),
    )


@mcp.tool()
def list_profiles() -> str:
    """List available shared render profiles and their capabilities as JSON."""
    return check_all_profiles_json()


@mcp.tool()
def render_report(
    markdown_path: str | None = None,
    markdown_text: str | None = None,
    profile: str = "generic-report",
) -> CallToolResult:
    """Render one Markdown report and return an embedded PDF resource.

    Provide exactly one of markdown_path or markdown_text. The server selects an
    ephemeral output directory and returns no reusable server-side PDF path.
    """
    if bool(markdown_path) == bool(markdown_text):
        raise ValueError("provide exactly one of markdown_path or markdown_text")

    with tempfile.TemporaryDirectory(prefix="optical-foundry-mcp-") as temp_value:
        temp_root = Path(temp_value)
        output_dir = temp_root / "render"

        if markdown_text is not None:
            source = temp_root / "report.md"
            source.write_text(markdown_text, encoding="utf-8")
        else:
            source = Path(markdown_path)  # type: ignore[arg-type]
            if not source.is_file():
                raise ValueError(f"markdown_path does not exist: {source}")

        evidence = service.render_document(source, profile, output_dir=str(output_dir))
        return _embedded_pdf_result(evidence)


@mcp.tool()
def render_manifest(manifest_path: str) -> CallToolResult:
    """Render a typed manifest and return an ephemeral embedded PDF resource."""
    manifest = Path(manifest_path)
    if not manifest.is_file():
        raise ValueError(f"manifest_path does not exist: {manifest}")

    with tempfile.TemporaryDirectory(prefix="optical-foundry-mcp-") as temp_value:
        output_dir = Path(temp_value) / "render"
        evidence = service.render_manifest(manifest, output_dir=str(output_dir))
        return _embedded_pdf_result(evidence)


@mcp.tool()
def contact_sheet(pdf_path: str, output_dir: str | None = None, max_pages: int = 12) -> dict:
    """Rasterize a caller-owned server-side PDF into a labeled contact sheet."""
    out = Path(output_dir) if output_dir else _ROOT / "generated" / "proofs" / "mcp_contact_sheet"
    return build_visual_proof(Path(pdf_path), output_dir=out, max_pages=max_pages)


def _render_report_http(
    markdown_text: str,
    profile: str = "generic-report",
) -> CallToolResult:
    """Remote report tool: inline Markdown only, with ephemeral delivery."""
    return render_report(markdown_text=markdown_text, profile=profile)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optical Foundry MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8768, help="HTTP bind port")
    parser.add_argument("--http-path", default="/mcp", help="Streamable HTTP MCP path")
    parser.add_argument(
        "--public-host",
        default=DEFAULT_PUBLIC_HOST,
        help="Caddy-facing hostname allowed by MCP DNS-rebinding protection and named in the "
        "auth URLs (default: OPTICAL_FOUNDRY_MCP_PUBLIC_HOST, else localhost)",
    )
    return parser


def _require_http_bearer_token() -> None:
    token = _bearer_verifier.configured_token()
    if token is None or len(token) < 32:
        raise RuntimeError(
            "OPTICAL_FOUNDRY_MCP_BEARER_TOKEN must be set to at least 32 characters "
            "before starting Streamable HTTP"
        )


def _configure_streamable_http(server: FastMCP, args: argparse.Namespace) -> None:
    """Configure HTTP and replace path-reading tools with inline-only rendering."""
    host_for_url = f"[{args.host}]" if ":" in args.host and not args.host.startswith("[") else args.host
    server.settings.host = args.host
    server.settings.port = args.port
    server.settings.streamable_http_path = args.http_path
    server.settings.auth = _auth_settings(args.public_host)
    _bearer_verifier.resource = f"https://{args.public_host}/mcp"
    server.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            f"{host_for_url}:{args.port}",
            f"localhost:{args.port}",
            f"[::1]:{args.port}",
            args.public_host,
        ],
        allowed_origins=[
            f"http://{host_for_url}:{args.port}",
            f"http://localhost:{args.port}",
            f"https://{args.public_host}",
        ],
    )

    server.remove_tool("render_report")
    server.remove_tool("render_manifest")
    server.remove_tool("contact_sheet")
    server.add_tool(_render_report_http, name="render_report")


def main(argv: Sequence[str] | None = None, *, server: FastMCP = mcp) -> None:
    args = _argument_parser().parse_args(argv)
    if args.transport == "streamable-http":
        _require_http_bearer_token()
        _configure_streamable_http(server, args)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
