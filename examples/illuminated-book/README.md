# The Shape of a Page

An eleven-page, half-letter specimen written for this repository, set in 14pt EB Garamond. It demonstrates a title page, table of contents, `of-initial`, `of-image`, three outer illumination designs, the four public engine-native ornament slots, three real footnotes and a glossary. The original prose and page breaks are preserved; the contents, ornament specimen and glossary add three pages to the first proof.

## Render

From the repository root, with the dependencies in the root README installed:

```bash
python examples/illuminated-book/render.py
python examples/illuminated-book/verify.py
```

The helper runs `python -m cli manifest` using `book.yaml`. It unsets `OF_PROFILE_PATH` and supplies temporary `HOME`, `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` values. The temporary profile pointer contains only this example's `profiles/` directory. No external profile repository is needed or consulted. The helper does not install tools or fetch images.

The resulting `generated/illuminated-book/illuminated-book.pdf` has eleven pages at 5.5 × 8.5 inches. The adjacent `.evidence.json` records success, warnings, SHA-256, page count, resolved resources and boundary assertions. `verify.py` checks these against the local PDF, confirms the contents/glossary and checks that footnote text lands at the page foot. Review the actual pages too.

## Files and ownership

- `book.md` — original example text, explicit page breaks, image blocks, four named ornament divs, Pandoc footnotes, a contents page and glossary. No external text source URL: this is newly written demonstration prose, not a public-domain excerpt. The authored `\tableofcontents*` follows the opening explanation; the template's automatic TOC is disabled to keep the title page first.
- `book.yaml` — source selection, page geometry, bound margins, outer folios and explicit illumination geometry. Three source marks select orchid, wisteria and lupine art at the chapter openings; the engine owns the left/right outer placement. Chapters One and Three land on even pages, Chapter Two on an odd page.
- `profiles/illuminated-example/profile.yaml` — a small package extending `document-spine`, with whisper, breath, hinge and tailpiece slots consumed by the engine's `of_ornaments.lua` filter.
- `profiles/illuminated-example/defaults.yaml` — 14pt EB Garamond/TeX Gyre font selection and paragraph defaults. Font files come from TeX Live, not this folder.
- `profiles/illuminated-example/preamble.tex` — keeps contents and footnote hyperlinks live without visible border boxes.
- `profiles/illuminated-example/assets/` — seven decorative images borrowed from Codex 0 and a copy of the engine's existing framed T initial.
- `assets.json` — source-relative provenance, transformations, byte sizes and source/output hashes for every image. It asserts no new license.
- `render.py` / `verify.py` — isolated rendering and evidence checks.

The leaf-and-bud, hinge and vine-tailpiece images were cropped to their alpha bounds with 12 pixels of transparent padding. The remaining files are byte-for-byte copies. Every selected image was visually reviewed: no people, keepsakes, location imagery, handwriting or personal manuscript text is included. The gold whisper is decorative linework, not written words.

## The four ornament slots

The TOC-listed *Four kinds of ornament* page shows one live specimen of each slot. The definitions and boundary rules come from [`contracts/ORNAMENT_SLOTS_CONTRACT.md`](../../contracts/ORNAMENT_SLOTS_CONTRACT.md), `engine/ornaments.py` and `engine/latex/of_ornaments.tex`:

- **Whisper**, **breath**, **hinge** are between-passage pauses in increasing height and surrounding gap. The engine drops them at page tops and feet.
- **Tailpiece** closes a section after its final block. It is legal at the page foot; only the first structural ornament there is kept.

Each slot has distinct Codex 0 art. They use the public engine, not the private Codex 0 composition filter.

## Limits and a current workaround

- The visible botanical art is **explicit decorative illumination**, not semantic register rails following a voice through a passage. The public chapter-opener injector uses its first asset rather than rotating a list; explicit source marks choose three assets without changing engine code. `render.delivery` still owns the rail geometry, reserve space and parity.
- The generic ornament filter currently errors on a slots-only profile because JSON null is treated as a rail object. This package declares an unused, empty `example-register` rail to avoid that path. No source div uses it, so it draws nothing. No engine patch is included.
- Imposition is off. The output is a reading-order prototype proof: RGB images, no bleed, no claim of vendor-independent press readiness. Inspect the advisory preflight before physical production.
- The full repository test suite still contains tests requiring non-bundled profiles/fonts and private fixtures. Run it and report the actual baseline rather than treating the example's success as a suite-wide result.
