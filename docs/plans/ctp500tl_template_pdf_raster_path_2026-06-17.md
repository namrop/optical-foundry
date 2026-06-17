---
uid: dab7c33e-1520-4210-9bb0-2e3dcfe4b444
kind: note
note_role: implementation_plan
validation_profile: standard
status: provisional
created: 2026-06-17T15:43:11-04:00
updated: 2026-06-17T15:43:11-04:00
beam_home: 42_optical_foundry
title: "CTP500TL Template PDF Raster Path"
summary: "Provisional implementation note for using Optical Foundry as the safe template/PDF front-end for CTP500TL daemon-side printed briefs, with printer-specific profile work deferred until a focused session."
tags:
  - optical-foundry
  - ctp500tl
  - thermal-printer
  - templates
  - pdf
  - rasterization
  - daemon
---

# CTP500TL Template PDF Raster Path

## Status

Provisional path note. Do not implement during the 2026-06-17 exploration session. Luis explicitly wants this captured for near-future work, but not picked up while he is juggling other work.

## Decision pressure

The CTP500TL printer daemon should eventually support template-backed printed artifacts, especially recurring briefs. The emerging path is to use Optical Foundry as the host-side template/PDF render surface, then rasterize the resulting PDF for the printer rather than trying to teach the printer a semantic template protocol.

This fits the CorePrint APK finding that templates are rendered host-side into bitmap/raster payloads before transport. It also preserves the daemon boundary: rendering/template failures can fail terminally, while printer discovery and transport failures should continue to hold/retry.

## Probe evidence

Exploratory smoke work on Sol showed:

- Optical Foundry runs from `42_optical_foundry` with `python3` on Sol, even though older/macOS notes refer to `python3.14`.
- Focused renderer tests passed: `tests/test_renderers.py` returned `28 passed`.
- Foundry successfully rendered Markdown to PDF for `letter`, `half_letter`, and `a5` using frontmatter `page_size` and margin controls.
- Current supported page-size tokens are intentionally narrow: `letter`, `a4`, `a5`, and `half_letter`.
- TiMini-Print already supports PDF input via `timiniprint/rendering/converters/pdf.py`, rasterizing PDF pages with `pypdfium2`, trimming margins, and resizing to the printer width.
- A half-letter Foundry PDF built an offline TiMini protocol job for `mini_printer` with `legacy_rle` / `bw1` image pipeline and expected `51 78 ... ff` packet framing.

Local exploratory artifacts from the probe:

- Probe report: `/tmp/of_printer_probe/optical_foundry_printer_probe_2026-06-17.md`
- Half-letter PDF: `/tmp/of_printer_probe/out/half_letter/printer-probe-half-letter.pdf`
- TiMini raster preview: `/tmp/of_printer_probe/half_letter_timini_page_1.png`
- TiMini debug dump: `/tmp/of_printer_probe/half_letter_timini_debug.json`

These `/tmp` paths are evidence pointers from the exploration session, not durable canonical artifacts.

## Recommended implementation shape

1. Add a printer-specific Optical Foundry profile, likely named `ctp500tl-brief` or `thermal-58mm-brief`.
2. Add a deliberate page-size token rather than arbitrary dimensions, e.g. `ctp500tl_384px` or `thermal_58mm_roll`.
3. Target the printer geometry directly:
   - CTP500TL/TiMini width: `384 px`.
   - Profile DPI observed in TiMini catalog: about `200 dpi`.
   - Physical width target: `384 / 200 ≈ 1.92 in`.
   - Use small margins and roll-like bounded height, not a scaled-down `letter`/`a5` page.
4. Add a daemon/API path that accepts structured template data, renders through Foundry to a temporary PDF, then submits the resulting file/raster job to the existing print pipeline.
5. Keep failure semantics explicit:
   - template/render/schema errors: terminal failure;
   - printer discovery/transport errors: held/retryable;
   - rasterization or unsupported file errors: terminal unless evidence shows a transient dependency/transport cause.
6. Add tests before deployment:
   - Foundry profile/page-size lowering tests;
   - daemon file-job/PDF-job tests;
   - template-render-to-file enqueue tests;
   - regression tests that held transport failures do not autofail jobs.

## Guardrails

- Optical Foundry is core infrastructure. Treat this as a focused implementation packet, not a drive-by daemon patch.
- Do not broaden Foundry's page geometry contract casually. Add a named printer geometry token with tests and evidence sidecars.
- Do not bypass Foundry validation/evidence just because the final target is a tiny thermal printer.
- Do not move recurring briefs into ad hoc shell formatting if the goal is durable template support.
- Keep `/tmp` probe outputs out of canon except as provenance pointers unless a later packet promotes a clean proof artifact.

## Operational follow-up

Vikunja task created for the near-future focused implementation pass:

- Systems task id `459` — "Implement CTP500TL template-backed printing via Optical Foundry PDF raster path"
