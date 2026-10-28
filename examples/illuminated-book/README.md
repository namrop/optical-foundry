# The Shape of a Page

An eight-page, half-letter specimen written for this repository. It demonstrates `of-initial`, `of-image`, bound illumination rails and public engine-native breath/tailpiece ornament slots. The title page is authored in the manuscript rather than generated from metadata.

## Render

From the repository root, with the dependencies in the root README installed:

```bash
python examples/illuminated-book/render.py
python examples/illuminated-book/verify.py
```

The helper runs `python -m cli manifest` using `book.yaml`. It unsets `OF_PROFILE_PATH` and supplies temporary `HOME`, `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` values. The temporary profile pointer contains only this example's `profiles/` directory. No external profile repository is needed or consulted. The helper does not install tools or fetch images.

The resulting `generated/illuminated-book/illuminated-book.pdf` has eight pages at 5.5 × 8.5 inches. The adjacent `.evidence.json` records success, warnings, SHA-256, page count, resolved resources and boundary assertions. `verify.py` checks these against the local PDF. Review the actual pages too.

## Files and ownership

- `book.md` — original example text and explicit page breaks, image blocks and ornament markers. No external text source URL: this is newly written demonstration prose, not a public-domain excerpt.
- `book.yaml` — source selection, page geometry, bound margins, outer folios and chapter-opening illumination rails. Chapter Two opens on an even page to demonstrate the left outer rail; Chapters One and Three demonstrate the right outer rail.
- `profiles/illuminated-example/profile.yaml` — a small package extending `document-spine`, with breath and tailpiece slots consumed by the engine's `of_ornaments.lua` filter.
- `profiles/illuminated-example/defaults.yaml` — EB Garamond/TeX Gyre font selection and paragraph defaults. Font files come from TeX Live, not this folder.
- `profiles/illuminated-example/assets/` — two decorative botanical images borrowed from Codex 0 and a copy of the engine's existing framed T initial.
- `assets.json` — source-relative provenance, transformations, byte sizes and source/output hashes for every image. It asserts no new license.
- `render.py` / `verify.py` — isolated rendering and evidence checks.

The leaf-and-bud image was cropped to its alpha bounds with 12 pixels of transparent padding. The orchid and T are byte-for-byte copies. Every selected image was visually reviewed: no people, keepsakes, location imagery, handwriting or personal manuscript text is included.

## Limits and a current workaround

- The visible orchids are **manifest-owned chapter-opening illumination**, not semantic register rails following a voice through a passage.
- The public engine supports ornament slots without the private Codex 0 filter. Its current generic filter nevertheless errors on a slots-only profile because JSON null is treated as a rail object. This package declares an unused, empty `example-register` rail to avoid that path. There are no corresponding source divs and it draws nothing. The real visible rails remain entirely under `render.delivery`. No engine patch is included.
- Imposition is off. The output is a reading-order prototype proof: RGB images, no bleed, no claim of vendor-independent press readiness. Inspect the advisory preflight before physical production.
- The full repository test suite still contains tests requiring non-bundled profiles/fonts and private fixtures. Run it and report the actual baseline rather than treating the example's success as a suite-wide result.
