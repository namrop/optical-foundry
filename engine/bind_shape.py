"""Bind shape: pad a rendered PDF to whole folded signatures.

The rendered PDF stays the reading and measurement artifact. The ``*_bind.pdf``
written beside it is what goes to imposition and the bindery: the same pages,
followed by enough pad leaves to fill the last signature.

Two invariants are asserted rather than assumed (promoted from the Codex 0 build,
PASS E, 2026-09-28):

- An ODD rendered page count is a hard error. The final leaf has no verso, so the
  volume cannot be folded or sewn, and the pad must not quietly absorb that. Fix
  the source instead.
- The padded count must land exactly on a signature multiple.

Pad leaves may carry a blank-leaf mark. A bound-in blank with a mark reads as
deliberate at collation; a bare blank reads as a printing error. The choice of
mark is the work's (tenant data); this module only places it, centred, at a
fraction of the page width, with the image's own aspect ratio.

This is distinct from ``engine.imposition``: imposition pads with virtual blank
slots while laying out sheets, and never writes a paged artifact. The bind shape
is the paged artifact itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class BindShapeError(ValueError):
    """Raised when a PDF cannot be brought to a bindable shape."""


@dataclass(frozen=True)
class BindShapeResult:
    source: Path
    output: Path
    rendered_pages: int
    pad_pages: int
    signature_size: int

    @property
    def total_pages(self) -> int:
        return self.rendered_pages + self.pad_pages

    @property
    def signatures(self) -> int:
        return self.total_pages // self.signature_size

    def summary(self) -> str:
        return (
            f"{self.source.name}: {self.rendered_pages} + {self.pad_pages} pad = "
            f"{self.total_pages} ({self.signatures} x {self.signature_size}) -> {self.output.name}"
        )


def bind_output_path(source: Path) -> Path:
    """``volume.pdf`` -> ``volume_bind.pdf``, beside the source."""
    source = Path(source)
    return source.with_name(source.stem + "_bind.pdf")


def signature_pad(page_count: int, signature_size: int) -> int:
    """Pad leaves needed to reach a whole signature, after the parity check."""
    if signature_size <= 0 or signature_size % 4:
        raise BindShapeError("signature size must be a positive multiple of 4")
    if page_count % 2:
        raise BindShapeError(
            f"renders {page_count} pages — ODD. The final leaf has no verso and the volume "
            f"cannot be folded or sewn. Fix the source rather than letting the signature pad hide it."
        )
    return (-page_count) % signature_size


def pad_to_signature(
    source: Path,
    signature_size: int,
    *,
    output: Path | None = None,
    blank_mark: Path | None = None,
    mark_width_fraction: float = 0.2,
) -> BindShapeResult:
    """Write ``output`` (default ``<source>_bind.pdf``) padded to whole signatures.

    ``blank_mark`` is an image placed centred on every pad leaf at
    ``mark_width_fraction`` of the page width. Pad leaves take the size of the
    source's last page and print no folio.
    """
    import fitz  # PyMuPDF; imported lazily so the engine imports without it

    source = Path(source)
    out = Path(output) if output is not None else bind_output_path(source)
    if blank_mark is not None and not Path(blank_mark).is_file():
        raise BindShapeError(f"blank-leaf mark not found: {blank_mark}")
    if not 0 < mark_width_fraction <= 1:
        raise BindShapeError("mark width fraction must be in (0, 1]")

    doc = fitz.open(str(source))
    try:
        n = doc.page_count
        try:
            pad = signature_pad(n, signature_size)
        except BindShapeError as exc:
            raise BindShapeError(f"{source}: {exc}") from None
        if pad:
            rect = doc[n - 1].rect
            kbox = None
            if blank_mark is not None:
                pix = fitz.Pixmap(str(blank_mark))
                kw = rect.width * mark_width_fraction
                kh = kw * (pix.height / pix.width)
                kbox = fitz.Rect(
                    (rect.width - kw) / 2,
                    (rect.height - kh) / 2,
                    (rect.width + kw) / 2,
                    (rect.height + kh) / 2,
                )
            for _ in range(pad):
                page = doc.new_page(width=rect.width, height=rect.height)
                if kbox is not None:
                    page.insert_image(kbox, filename=str(blank_mark))
        doc.save(str(out))
    finally:
        doc.close()

    total = n + pad
    if total % signature_size:
        raise BindShapeError(f"{out} is {total} pages, not a multiple of {signature_size}.")
    return BindShapeResult(
        source=source,
        output=out,
        rendered_pages=n,
        pad_pages=pad,
        signature_size=signature_size,
    )
