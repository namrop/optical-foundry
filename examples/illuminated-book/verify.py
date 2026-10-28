#!/usr/bin/env python3
"""Check the example's evidence, output identity and key page-level features."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

EXPECTED_PAGES = 11


def main() -> None:
    example = Path(__file__).resolve().parent
    root = example.parents[1]
    output = root / "generated" / "illuminated-book"
    evidence = json.loads((output / "illuminated-book.evidence.json").read_text())
    pdf = output / "illuminated-book.pdf"
    boundary = evidence["boundary"]
    assert evidence["status"] == "ok"
    assert evidence["render_metadata"]["success"] is True
    assert evidence["validation"]["status"] == "passed"
    assert evidence["warnings"] == []
    assert evidence["output"]["pdf_pages"] == EXPECTED_PAGES
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert evidence["output"]["pdf_sha256"] == digest
    assert boundary["target_legacy_profile_tree_mutated"] is False
    assert boundary["reads_legacy_profile_tree"] is False
    assert boundary["delivery_mode"] == "bound"
    assert boundary["delivery_duplex"] is True
    illumination = boundary["delivery_illumination"]
    assert illumination["placement"] == "explicit"
    assert len(illumination["assets"]) == 3
    assert Path(boundary["profile_package"]).resolve() == example / "profiles/illuminated-example"
    geometry = Path(evidence["render_metadata"]["page_geometry_defaults"]).read_text()
    assert "- 14pt" in geometry
    for path in evidence["render_metadata"]["defaults_stack"]:
        assert Path(path).resolve().is_relative_to(root)
    resources = evidence["resource_resolution"]["resolved_resources"]
    for resource in resources:
        assert Path(resource["winner"]).resolve().is_relative_to(root)
    winners = {Path(resource["winner"]).name for resource in resources}
    assert {"orchid-rail.png", "wisteria-rail.png", "lupine-rail.png"} <= winners
    kinds = {figure["kind"] for figure in evidence["figure_inventory"]}
    assert {"image_initial", "layout_image"} <= kinds
    slots = evidence["render_metadata"]["ornaments"]["slots"]
    assert set(slots) == {"whisper", "breath", "hinge", "tailpiece"}
    assert all(slot["art"] == 1 for slot in slots.values())
    preflight = evidence["output"]["bindery_preflight"]
    assert preflight["fonts"]["all_embedded"] is True
    assert preflight["safe_area_guide"]["fit_warnings"] == []
    text = (output / "illuminated-book.txt").read_text()
    for marker in ("of-image", "of-initial", "OFOuterRail", "OFOrnament"):
        assert marker not in text, f"Source directive leaked: {marker}"
    pages = [re.sub(r"\s+", " ", page).strip() for page in text.split("\f") if page.strip()]
    assert len(pages) == EXPECTED_PAGES
    assert "Contents" in pages[2]
    for heading in ("Four kinds of ornament", "Glossary"):
        assert heading in pages[2]
    assert pages[8].startswith("Four kinds of ornament")
    assert pages[10].startswith("Glossary")
    # Real footnotes are in the foot area, not merely mentioned in body prose.
    bbox = subprocess.check_output(["pdftotext", "-bbox", str(pdf), "-"], text=True)
    xml = ET.fromstring(bbox)
    page_nodes = [node for node in xml.iter() if node.tag.endswith("}page")]
    for page_index, word in ((3, "means"), (4, "Odd"), (8, "Definitions:")):
        page = page_nodes[page_index]
        height = float(page.attrib["height"])
        assert any(word in (node.text or "") and float(node.attrib["yMin"]) > height * 0.8
                   for node in page.iter() if node.tag.endswith("}word")), (page_index + 1, word)
    print(json.dumps({"status": "verified", "pages": EXPECTED_PAGES,
                      "body_font_pt": 14, "ornament_slots": sorted(slots),
                      "rail_art_count": 3, "footnotes_at_page_foot": [4, 5, 9],
                      "sha256": digest, "warnings": evidence["warnings"],
                      "prototype_ready": preflight["readiness"]["prototype_ready"],
                      "press_ready": preflight["readiness"]["vendor_independent_press_ready"],
                      "press_issues": preflight["readiness"]["blocking_press_ready_issues"]}, indent=2))


if __name__ == "__main__":
    main()
