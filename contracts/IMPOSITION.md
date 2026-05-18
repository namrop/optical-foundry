# Signature Imposition

Optical Foundry supports booklet/signature imposition for already-rendered PDFs through the CLI and for bound/booklet manifest renders through `render.delivery.imposition`. This is a generic Foundry capability; artifact-specific cover/interior splits, manuscript source trees, and art packets stay outside this contract unless reduced to fixtures:

```bash
python3.14 -m cli impose input.pdf \
  --output generated/impositions/<run-name> \
  --page-size half_letter \
  --sheet-size letter \
  --signature-size 16 \
  --duplex short-edge
```

## Manifest-owned use

For a typed manifest, use:

```yaml
render:
  delivery:
    mode: bound
    binding: saddle_stitch
    imposition:
      enabled: true
      layout: booklet_signature_2up
      sheet_size: letter
      signature_size: 8
      duplex: short_edge
```

The renderer writes the imposed PDF and `.imposition.json` sidecar next to the primary render output and records the imposition metadata in evidence.

## Current layout

- `booklet_signature_2up`
- Two portrait source pages per landscape sheet side.
- Intended first production lane: half-letter pages on letter sheets for duplex printing and folding into signatures.

For an 8-page signature, the generated sheet-side order is:

- Sheet 1 front: `[8, 1]`
- Sheet 1 back: `[2, 7]`
- Sheet 2 front: `[6, 3]`
- Sheet 2 back: `[4, 5]`

`null` in the mapping JSON means an intentional blank slot added by signature padding.

## Parameters

- `--page-size`: source PDF page size. Supported via the renderer page-size contract: `letter`, `half_letter`, `a4`, `a5` and aliases.
- `--sheet-size`: physical printer sheet size. First verified pair: `half_letter` pages on `letter` sheets.
- `--signature-size`: source pages per folded signature. Must be a positive multiple of 4.
- `--duplex`: `short-edge` or `long-edge`.
  - `short-edge` emits back sides upright. This is the normal setting for landscape booklet sheets on many duplex printers.
  - `long-edge` rotates back sides 180 degrees to compensate for long-edge duplex behavior.

## Outputs

For directory output, the CLI writes:

- `<input-stem>.imposed-<page-size>-on-<sheet-size>-sig<N>-<duplex>.pdf`
- `<same-stem>.imposition.json`

The mapping JSON records:

- source and output PDF paths
- page size / sheet size
- signature size
- duplex mode
- input page count
- padded page count
- blank count
- output sheet-side count
- per-signature, per-sheet front/back page-slot maps

## Verification expectations

For print-proofing:

1. Verify the source PDF page boxes match `--page-size` before imposition.
2. Verify every imposed output page is the target sheet size in landscape orientation.
3. Inspect the mapping JSON before printing; especially the final signature, which may contain padded blanks.
4. For a one-sheet physical test, print the first two output PDF pages duplex and fold before printing the entire run.
