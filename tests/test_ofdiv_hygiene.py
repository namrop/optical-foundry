"""Final-PDF hygiene for load-bearing OFDIV furnish markers."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter  # type: ignore[import-not-found]
from pypdf.generic import (  # type: ignore[import-not-found]
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.furnish import DividerMarkerSanitizationError, sanitize_divider_markers
from engine.manifest_compiler import CompositeBundleCompiler
from renderers.pandoc_renderer import (
    PandocRenderer,
    RenderArtifactPublicationError,
)


def _write_content_stream_pdf(path: Path, stream_data: bytes) -> None:
    """Write one Helvetica-backed page with the supplied raw content stream."""

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(stream_data)
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_hidden_marker_pdf(path: Path, *, tagged_marker: bool) -> None:
    """Write one page with unrelated mode-3 text and one OFDIV marker token."""

    marker_begin = b"/OFDIV BMC\n/Span BMC\n" if tagged_marker else b""
    marker_end = b"EMC\nEMC\n" if tagged_marker else b""
    _write_content_stream_pdf(
        path,
        b"BT /F1 1 Tf 3 Tr 10 180 Td (UNRELATED-BEFORE) Tj ET\n"
        + marker_begin
        + b"BT /F1 1 Tf 3 Tr 10 160 Td ([[OFDIV:part-i]]) Tj ET\n"
        + marker_end
        + b"BT /F1 1 Tf 3 Tr 10 140 Td (UNRELATED-AFTER) Tj ET\n",
    )


def _operation_signatures(path: Path) -> list[tuple[bytes, tuple[str, ...]]]:
    reader = PdfReader(path)
    content = ContentStream(reader.pages[0].get_contents(), reader)
    return [(operator, tuple(str(operand) for operand in operands)) for operands, operator in content.operations]


def test_sanitizer_removes_only_tagged_marker_text_show(tmp_path):
    pdf_path = tmp_path / "tagged-marker.pdf"
    _write_hidden_marker_pdf(pdf_path, tagged_marker=True)
    before_operations = _operation_signatures(pdf_path)

    result = sanitize_divider_markers(pdf_path, {"part-i": 1})

    assert result.removed_text_operations == 1
    assert result.pages_sanitized == [1]
    after_operations = _operation_signatures(pdf_path)
    assert after_operations == [
        operation
        for operation in before_operations
        if not (operation[0] == b"Tj" and operation[1] == ("[[OFDIV:part-i]]",))
    ]
    page = PdfReader(pdf_path).pages[0]
    assert float(page.mediabox.width) == 200
    assert float(page.mediabox.height) == 200
    text = page.extract_text()
    assert "UNRELATED-BEFORE" in text
    assert "UNRELATED-AFTER" in text
    assert "[[OFDIV:" not in text


def test_sanitizer_fails_when_expected_page_has_no_tagged_marker(tmp_path):
    pdf_path = tmp_path / "untagged-marker.pdf"
    _write_hidden_marker_pdf(pdf_path, tagged_marker=False)
    original_pdf = pdf_path.read_bytes()

    with pytest.raises(DividerMarkerSanitizationError, match="tagged hidden marker"):
        sanitize_divider_markers(pdf_path, {"part-i": 1})

    assert pdf_path.read_bytes() == original_pdf
    assert "[[OFDIV:part-i]]" in PdfReader(pdf_path).pages[0].extract_text()


def test_sanitizer_restores_visible_text_state_across_q_q(tmp_path):
    pdf_path = tmp_path / "q-q-visible-marker.pdf"
    _write_content_stream_pdf(
        pdf_path,
        b"BT /F1 12 Tf 0 Tr ET\n"
        b"q\n"
        b"BT /F1 1 Tf 3 Tr ET\n"
        b"Q\n"
        b"/OFDIV BMC\n"
        b"BT 10 160 Td ([[OFDIV:part-i]]) Tj ET\n"
        b"EMC\n",
    )
    original_pdf = pdf_path.read_bytes()

    with pytest.raises(DividerMarkerSanitizationError, match="tagged hidden marker"):
        sanitize_divider_markers(pdf_path, {"part-i": 1})

    assert pdf_path.read_bytes() == original_pdf
    assert "[[OFDIV:part-i]]" in PdfReader(pdf_path).pages[0].extract_text()


def test_sanitizer_rejects_marker_sharing_text_object_with_retained_show(tmp_path):
    pdf_path = tmp_path / "shared-text-object.pdf"
    _write_content_stream_pdf(
        pdf_path,
        b"/OFDIV BMC 3 Tr\n"
        b"BT /F1 1 Tf 10 160 Td ([[OFDIV:part-i]]) Tj\n"
        b"0 Tr /F1 12 Tf 0 -20 Td (RETAINED-VISIBLE-TEXT) Tj ET\n"
        b"EMC\n",
    )
    original_pdf = pdf_path.read_bytes()

    with pytest.raises(DividerMarkerSanitizationError, match="shares its BT/ET object"):
        sanitize_divider_markers(pdf_path, {"part-i": 1})

    assert pdf_path.read_bytes() == original_pdf
    text = PdfReader(pdf_path).pages[0].extract_text()
    assert "[[OFDIV:part-i]]" in text
    assert "RETAINED-VISIBLE-TEXT" in text


def test_sanitizer_preserves_original_when_postwrite_verification_fails(tmp_path, monkeypatch):
    pdf_path = tmp_path / "surviving-marker.pdf"
    _write_hidden_marker_pdf(pdf_path, tagged_marker=True)
    original_pdf = pdf_path.read_bytes()
    monkeypatch.setattr(
        "engine.furnish.extract_divider_page_map",
        lambda _pdf_path: {"part-i": 1},
    )

    with pytest.raises(DividerMarkerSanitizationError, match="survived"):
        sanitize_divider_markers(pdf_path, {"part-i": 1})

    assert pdf_path.read_bytes() == original_pdf
    assert not pdf_path.with_name(f".{pdf_path.name}.ofdiv-sanitize.tmp").exists()


def test_publish_render_artifacts_rolls_back_pair_when_extra_promotion_fails(
    tmp_path, monkeypatch
):
    staged_pdf = tmp_path / ".staged.pdf"
    staged_text = tmp_path / ".staged.txt"
    staged_map = tmp_path / ".staged-map.json"
    final_pdf = tmp_path / "book.pdf"
    final_text = tmp_path / "book.txt"
    final_map = tmp_path / "book.divider_pages.json"
    for path, payload in (
        (staged_pdf, b"new pdf"),
        (staged_text, b"new text"),
        (staged_map, b"new map"),
        (final_pdf, b"old pdf"),
        (final_text, b"old text"),
        (final_map, b"old map"),
    ):
        path.write_bytes(payload)

    import renderers.pandoc_renderer as renderer_module

    real_replace = renderer_module.os.replace

    def fail_extra_promotion(source, destination):
        if Path(source) == staged_map:
            raise OSError("injected page-map promotion failure")
        real_replace(source, destination)

    monkeypatch.setattr(renderer_module.os, "replace", fail_extra_promotion)

    with pytest.raises(RenderArtifactPublicationError, match="could not publish"):
        PandocRenderer._publish_render_artifacts(
            staged_pdf,
            staged_text,
            final_pdf,
            final_text,
            extra_artifacts=((staged_map, final_map),),
        )

    assert final_pdf.read_bytes() == b"old pdf"
    assert final_text.read_bytes() == b"old text"
    assert final_map.read_bytes() == b"old map"
    assert not list(tmp_path.glob(".*.rollback-*"))


def _compile_divider_plan(tmp_path: Path, bundle_id: str):
    source = tmp_path / f"{bundle_id}-body.md"
    source.write_text(
        "---\nuid: ofdiv-body\ntitle: Body\n---\n\n# Body\n\nFinal body text.\n",
        encoding="utf-8",
    )
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": bundle_id,
        "profile": "codex0",
        "sources": [
            {
                "uid": "ofdiv-body",
                "path": str(source),
                "role": "primary_anchor",
                "order": 1,
            }
        ],
        "section_dividers": [
            {
                "uid": "probe-divider",
                "before_source_order": 1,
                "title": "Probe Divider",
                "force_right_page": False,
                "blank_after": False,
                "stock": "cardstock",
            }
        ],
        "render": {"include_toc": False, "numbersections": False},
    }
    return CompositeBundleCompiler().compile(manifest)


def test_render_extracts_divider_page_map_then_removes_ofdiv_from_final_pdf(tmp_path):
    if not shutil.which("pandoc") or not shutil.which("lualatex") or not shutil.which("pdftotext"):
        pytest.skip("pandoc/lualatex/pdftotext not available")

    plan = _compile_divider_plan(tmp_path, "ofdiv-hygiene-probe")
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))

    assert evidence["status"] == "ok"
    pdf_path = Path(evidence["output"]["pdf_path"])
    extracted = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "[[OFDIV:" not in extracted
    text_sidecar = pdf_path.with_suffix(".txt")
    assert text_sidecar.exists()
    assert "[[OFDIV:" not in text_sidecar.read_text(errors="replace")

    hygiene = evidence["integrity"]["divider_markers"]
    assert hygiene["extracted_before_sanitization"] == 1
    assert hygiene["removed_text_operations"] == 1
    assert hygiene["final_pdf_marker_count"] == 0

    page_map_path = Path(hygiene["page_map_path"])
    assert page_map_path.exists()
    payload = json.loads(page_map_path.read_text())
    assert payload["schema_version"] == "divider_page_map_v1"
    assert set(payload["divider_page_map"]) == {"probe-divider"}
    landing_page = payload["divider_page_map"]["probe-divider"]
    assert landing_page >= 1
    assert hygiene["pages_sanitized"] == [landing_page]


def test_render_missing_uid_preserves_prior_final_pdf_and_text(tmp_path, monkeypatch):
    if not shutil.which("pandoc") or not shutil.which("lualatex") or not shutil.which("pdftotext"):
        pytest.skip("pandoc/lualatex/pdftotext not available")

    plan = _compile_divider_plan(tmp_path, "ofdiv-atomic-failure")
    output_dir = tmp_path / "out-atomic-failure"
    output_dir.mkdir()
    final_pdf = output_dir / f"{plan.render_id}{plan.output_extension}"
    final_text = output_dir / f"{plan.render_id}.txt"
    final_page_map = output_dir / f"{plan.render_id}.divider_pages.json"
    prior_pdf = b"PRIOR FINAL PDF SENTINEL\n"
    prior_text = "PRIOR FINAL TEXT SENTINEL\n"
    prior_page_map = '{"sentinel": "prior divider map"}\n'
    final_pdf.write_bytes(prior_pdf)
    final_text.write_text(prior_text)
    final_page_map.write_text(prior_page_map)

    monkeypatch.setattr(
        "renderers.pandoc_renderer.extract_divider_page_map",
        lambda _compile_pdf: {},
    )

    evidence = PandocRenderer().render(plan, output_dir=str(output_dir))

    assert evidence["status"] == "error"
    assert "missed divider uid(s): probe-divider" in evidence["error"]
    assert final_pdf.read_bytes() == prior_pdf
    assert final_text.read_text() == prior_text
    assert final_page_map.read_text() == prior_page_map
    compile_pdfs = list(
        output_dir.glob(
            f".{plan.render_id}.compile-stage-*{plan.output_extension}"
        )
    )
    assert len(compile_pdfs) == 1
    assert compile_pdfs[0].read_bytes().startswith(b"%PDF-")


def test_late_validation_failure_preserves_prior_final_artifacts(tmp_path, monkeypatch):
    if not shutil.which("pandoc") or not shutil.which("lualatex") or not shutil.which("pdftotext"):
        pytest.skip("pandoc/lualatex/pdftotext not available")

    plan = _compile_divider_plan(tmp_path, "ofdiv-validation-failure")
    output_dir = tmp_path / "out-validation-failure"
    output_dir.mkdir()
    final_pdf = output_dir / f"{plan.render_id}{plan.output_extension}"
    final_text = output_dir / f"{plan.render_id}.txt"
    final_page_map = output_dir / f"{plan.render_id}.divider_pages.json"
    prior_artifacts = {
        final_pdf: b"PRIOR VALIDATED PDF\n",
        final_text: b"PRIOR VALIDATED TEXT\n",
        final_page_map: b'{"sentinel": "prior validated map"}\n',
    }
    for path, payload in prior_artifacts.items():
        path.write_bytes(payload)

    monkeypatch.setattr(
        PandocRenderer,
        "_raw_latex_leakage",
        staticmethod(lambda _text_extract: True),
    )

    evidence = PandocRenderer().render(plan, output_dir=str(output_dir))

    assert evidence["status"] == "error"
    assert evidence["validation"]["status"] == "failed"
    assert evidence["validation"]["checks"]["raw_latex_leakage"] is True
    assert evidence["output"]["publication_status"] == "withheld"
    for path, payload in prior_artifacts.items():
        assert path.read_bytes() == payload
