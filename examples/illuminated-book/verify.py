#!/usr/bin/env python3
"""Check the rendered example's evidence, source closure and output identity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


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
    assert evidence["output"]["pdf_pages"] == 8
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert evidence["output"]["pdf_sha256"] == digest
    assert boundary["target_legacy_profile_tree_mutated"] is False
    assert boundary["reads_legacy_profile_tree"] is False
    assert boundary["delivery_mode"] == "bound"
    assert boundary["delivery_duplex"] is True
    assert boundary["delivery_illumination_marks"]["marks_inserted"] == 3
    assert Path(boundary["profile_package"]).resolve() == example / "profiles/illuminated-example"
    for path in evidence["render_metadata"]["defaults_stack"]:
        assert Path(path).resolve().is_relative_to(root)
    for resource in evidence["resource_resolution"]["resolved_resources"]:
        assert Path(resource["winner"]).resolve().is_relative_to(root)
    kinds = {figure["kind"] for figure in evidence["figure_inventory"]}
    assert {"image_initial", "layout_image"} <= kinds
    slots = evidence["render_metadata"]["ornaments"]["slots"]
    assert slots["breath"]["art"] == 1 and slots["tailpiece"]["art"] == 1
    preflight = evidence["output"]["bindery_preflight"]
    assert preflight["fonts"]["all_embedded"] is True
    assert preflight["safe_area_guide"]["fit_warnings"] == []
    text = (output / "illuminated-book.txt").read_text()
    for marker in ("of-image", "of-initial", "OFOuterRail", "OFOrnament"):
        assert marker not in text, f"Source directive leaked: {marker}"
    print(json.dumps({"status": "verified", "pages": 8, "sha256": digest,
                      "warnings": evidence["warnings"],
                      "prototype_ready": preflight["readiness"]["prototype_ready"],
                      "press_ready": preflight["readiness"]["vendor_independent_press_ready"],
                      "press_issues": preflight["readiness"]["blocking_press_ready_issues"]}, indent=2))


if __name__ == "__main__":
    main()
