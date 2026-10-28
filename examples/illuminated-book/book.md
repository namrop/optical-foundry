---
uid: illuminated-book
---

```{=latex}
\thispagestyle{empty}
\vspace*{1.1in}
{\centering
{\small A SHORT BOOK ABOUT BOOKMAKING\par}
\vspace{0.5in}
{\fontsize{34}{38}\selectfont The Shape\\of a Page\par}
\vspace{0.35in}
{\large An illuminated example\par}
\vspace{0.5in}
\includegraphics[width=0.7in]{assets/leaf-bud.png}\par
\vfill
{\small OPTICAL FOUNDRY\par}
}
\clearpage
```

## A small working book

This book is a demonstration, not a historical facsimile. Its text was written for this example. The leaves, buds and orchids were borrowed from the decorative art made for Codex 0. The framed initial comes from the engine's existing demonstration assets.

The three chapters consider the page, the margin and the finished object. Their purpose is also practical: an initial must join a live paragraph; an image must occupy a deliberate place; an ornament must mark a pause; and a margin rail must remain outside the prose.

The following pages are composed from Markdown and a YAML manifest. The type is EB Garamond, with TeX Gyre companion faces, supplied by TeX Live. No font files are bundled with this example.

A page is more than a container. It is an agreement between the length of a line, the space around it and the attention of a reader. The demonstration begins with that agreement and ends by asking whether the rendered object keeps it.

::: {.tailpiece}
:::

```{=latex}
\clearpage
```

# Chapter One: The page

```of-initial
path: assets/initial-t.png
width: 0.55in
lines: 4
gap: 0.07in
align: top
```
he page begins with a measure. A line should carry a thought far enough to gather momentum, but not so far that the eye loses its way on the return. That judgment belongs to the relationship between type size, leading and the width of the text, rather than to any one number in isolation.

An illuminated initial changes the opening without replacing the paragraph. The capital is an image; the words beside it remain text. The space reserved around the image must be large enough for its frame, yet small enough that the sentence still reads as one movement.

::: {.breath}
:::

A small ornament can offer a different kind of pause. It does not need the authority of a heading. It may simply allow one paragraph to close before another begins. Used sparingly, a leaf or bud can make that interval visible without pretending that every thought is a new chapter.

The best test is ordinary reading. If the reader notices the apparatus before the sentence, the apparatus may be asking for more attention than it has earned.

```{=latex}
\clearpage
```

# Chapter Two: The margin

The margin is not leftover space. It separates the text from the edge of the object, and it can carry a second, quieter channel of information. A note, a folio or a botanical rail can live there without narrowing every sentence into a negotiation with an illustration.

In this example, a purple orchid marks the chapter opening. Its placement belongs to the delivery manifest: the outer edge changes sides when the page changes parity. The source does not need to choose a permanent left or right margin.

::: {.breath}
:::

This illumination rail is decorative page furniture. It is not the automatic register-marking system that a profile may use to follow a particular voice through a passage. The two uses share a margin, but they make different claims about the text.

A useful margin keeps those claims legible. It should not make the reader wonder whether a flower is a footnote, whether a note belongs to the next paragraph, or whether a mark has been clipped by the trim. Restraint is a functional choice here, not the absence of design.

```{=latex}
\clearpage
```

## Rhythm and return

Paragraphs make a second measure within the page. An indentation can mark a new beginning without opening a large hole in the texture of the prose. A modest space between paragraphs can ease the transition. Too much of both may break a continuous argument into unrelated pieces.

The same is true of headings. A heading belongs to the words that follow it, not to the empty space at the bottom of the preceding page. Keeping that relationship intact is a layout responsibility. It should not depend on adding blank lines until a particular proof happens to look right.

::: {.breath}
:::

A book also has a rhythm across its openings. The reader sees a left page and a right page together. Their margins need not be identical, but their relationship should feel deliberate. The binding takes space from the inner edge; the outer edge gives the hand somewhere to rest.

A good page is therefore not an isolated rectangle. It has a neighbour, a place in a sequence and a physical future. Even a small digital proof can acknowledge those facts before paper and thread enter the work.

```{=latex}
\clearpage
```

## An image in the measure

The same botanical art can be placed inside the text area as a displayed image. This is a separate decision from putting it in a margin rail. Here the illustration occupies flow; the paragraphs before and after it remain in sequence.

```of-image
path: assets/leaf-bud.png
placement: block
width: 1.1in
gap: 0.8\baselineskip
auto_trim: false
```

A displayed image needs a clear envelope of space. Too little space makes it collide with the prose. Too much can make a small illustration feel like a missing plate. The visible size of the mark matters more than the size of the transparent canvas around it.

This distinction is also useful in the source. The image block declares its placement and dimensions. The manifest declares the page and its margins. The profile supplies type and ornament rules. Keeping those responsibilities separate makes a later revision easier to understand and easier to verify.

::: {.tailpiece}
:::

```{=latex}
\clearpage
```

# Chapter Three: The object

A rendered file is not ready merely because it exists. Its pages need the right dimensions. Its fonts must be embedded. Its images must be present, and its text must remain free of working paths, source directives and other construction debris.

Evidence helps make those questions repeatable. A render records its inputs, warnings, page count and output hash. These records identify what was built; they do not decide whether the typography is good. A clean report and a poor page can coexist.

::: {.breath}
:::

That is why the final pass returns to the page itself. Look at an opening. Follow a sentence around an initial. Check the outer margins on both parities. Read the bottom line before turning the page. Notice whether an ornament has become stranded where a page break already supplies the pause.

The object is complete only when the declared structure and the visible result agree. The source explains an intention; the manifest makes choices explicit; the profile supplies a visual grammar. The rendered book is where those parts have to meet.

::: {.tailpiece}
:::

```{=latex}
\clearpage
```

## Making this example

This eight-page specimen is intentionally small. It demonstrates a title page, a framed image initial, a displayed image, chapter-opening illumination rails and engine-native breath and tailpiece ornaments.

The example profile inherits the neutral document spine. Its ornament slots use the public engine's page-position law: a breath does not survive at a page top or foot, where a page break already performs its work. A tailpiece is allowed to close a section.

The manifest owns the half-letter page size, mirrored bound margins and outer folios. It also owns the chapter-opening rails. The companion render script isolates profile discovery so that only this repository's demonstration profile is available. It does not require a separate profile checkout.

The accompanying asset inventory records where each decorative file came from and how it was prepared. No personal manuscript text, photographs, keepsakes or location imagery are included. The text is original to this example; it is not a quotation or a claim of public-domain status.

::: {.tailpiece}
:::
