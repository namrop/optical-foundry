---
uid: 019f24ff-4914-7647-877a-4acd0d7e681e
kind: note
note_role: spec
validation_profile: standard
status: draft
created: 2026-07-02T18:42:18-04:00
updated: 2026-07-28T01:08:40-04:00
beam_home: 42_optical_foundry/docs/guides
title: "Codex 0 Edition Variants"
summary: "Guide for Codex 0 source-visible edition variants selected by a pre-Pandoc comment-sentinel culler before figure/source preprocessors run."
tags:
  - optical-foundry
  - codex0
  - edition-variants
  - register-rails
  - pandoc
  - preprocessing
---

# Codex 0 edition variants

Codex 0 may keep edition-specific paragraph rewrites side-by-side in the manuscript source. This is a Codex 0 profile-scoped mechanism, not a general Foundry document primitive yet.

## Model (2026-07-04)

The prose between the `cx0:variant` open marker and the first `cx0:edition` marker is the **archival base**. It renders for every edition unless a tagged override replaces it. Each `cx0:edition` marker names one or more editions (comma-separated — a block may belong to several at once) and, for those editions only, swaps in at that place for the archival base.

- **Replacement:** a non-empty archival base + a tagged override → the tagged editions get the override, everyone else gets the base.
- **Addition:** an empty archival base + a tagged override → the prose is present only in its tagged editions and absent everywhere else.
- **Fallback:** any edition without a matching override inherits the archival (raw) base.

## Source syntax

Use HTML comment sentinels around normal Markdown prose:

```markdown
<!-- cx0:variant id="how-you-arrived-010" -->
The harbor bell rang twice before the ferry left the pier.

<!-- cx0:edition witness,reader -->
A bell rang somewhere over the water: not loud, not near, but enough to turn every head on the deck.

<!-- cx0:endvariant -->
```

Here the archival and johannah editions render the raw base; the witness and reader editions render the veiled override.

Supported markers:

- `<!-- cx0:variant id="..." -->` (optional `guard="..."`, see Safety behavior)
- `<!-- cx0:edition witness -->` or `<!-- cx0:edition witness,reader -->`
- `<!-- cx0:edition edition="witness" -->` / `<!-- cx0:edition editions="witness,reader" -->`
- `<!-- cx0:edition johannah,witness,reader register="pataphorical" -->` (optional `register="..."`, see Register rails)
- `<!-- cx0:endvariant -->` or the XML-style `<!-- /cx0:variant -->`

Bare edition labels may sit alongside a `register="..."` attribute (`<!-- cx0:edition johannah,witness,reader register="pataphorical" -->`); the culler strips the attribute token and reads the remaining comma-separated labels. An attribute-only marker with no labels still fails as a typo.

The `fallback="..."` attribute is deprecated and ignored (it emits a warning): the archival base is now the universal fallback.

The selected branch remains ordinary Markdown after preprocessing. Inactive branches are removed before Pandoc and before the existing `of-image`, Mermaid, Vega, D2, Graphviz, and emoji source preprocessors run.

## Edition lanes

- **archival** — everything raw; the base truth surface.
- **johannah** — pataphor where beauty is the point, raw where load-bearing.
- **witness** — more pataphorical hedging than johannah.
- **reader** — most veiled.

Because the archival base is the universal fallback, editions inherit the raw base for any region left un-overridden. This is fail-**open** for exposure: forgetting to veil a region leaks raw prose into wider editions. Use `guard` (below) on sensitive regions.

## Register rails

A `register="..."` attribute on a `cx0:edition` marker tags the selected override as belonging to a named register (currently `pataphorical`). When that branch is the one selected for the rendered edition, a **margin rail** is drawn beside it — a visual indicator that the reader is in the tagged register rather than the raw base.

```markdown
<!-- cx0:variant id="the-first-rooms-020" -->
Raw archival prose.
<!-- cx0:edition johannah,witness,reader register="pataphorical" -->
The fable-register prose that carries the pataphor.
<!-- cx0:endvariant -->
```

### Authoring

Edition guards are an access-control boundary: malformed or accidentally widened guards can expose sensitive prose. Do not modify a variant ID, `guard=`, edition label, or variant-close marker merely to add rail guidance.

The `register="pataphorical"` attribute on an edition marker remains supported for existing sources, but new rail-only boundary work should use a distinct fenced-Div layer wholly inside the already-selected branch:

```markdown
<!-- cx0:variant id="the-first-rooms-020" guard="witness,reader" -->
Raw archival prose.
<!-- cx0:edition witness -->
::: {.codex-pataphorical register="pataphorical"}
Existing veiled prose, unchanged.
:::
<!-- cx0:endvariant -->
```

- Both fences must sit inside one branch. They must never cross a `cx0:edition` or variant-close marker.
- The fenced Div may also wrap a source-local pataphor span outside an edition variant.
- It applies only to the text it encloses. An edition that does not select that branch receives neither its prose nor its rail guidance.
- Images, plates, layout code, hinges, and thresholds normally remain outside. A `cx0:breath` may remain inside when it is only pacing within one continuous pataphor field; do not create visual rail fragments by treating every breath as a field exit.
- The register token must be a safe identifier; a malformed value fails the render.
- When replacing a coarse `register="pataphorical"` branch wrapper with explicit spans, remove only that rendering attribute; preserve the variant ID, guard, edition labels, and close marker exactly. Preprocess every affected edition before and after, strip only rail guidance from the comparison, and require identical selected prose and identical fail-closed errors.

### Rendering

The pipeline turns the attribute into a rail in three stages:

1. **Resolver** (`codex_editions.py`): when the selected branch carries a register, the culler wraps its body in a fenced div — `::: {.codex-<register> register="<register>"} ... :::` — so the register survives into the generated Markdown as structure rather than a comment.
2. **Composition filter** (`codex0_composition.lua`): the `Div` handler for `codex-pataphorical` pulls the next asset from the rail pool and injects `\CodexRegisterRail[<width>]{<asset>}` as a leading inline in the block's first paragraph (or as a leading raw block if the first child is not a paragraph).
3. **Template** (`codex0.tex`): `\CodexRegisterRail` places the asset with `marginnote` (not `\marginpar`), so the rail is **non-floating** and pins to the passage's first line in the outer margin under `twoside`. Because `marginnote` contributes no vertical space to the main galley, placement decisions never shift the body text, and page assignments stay stable across Pandoc's multiple engine passes.

### One rail per page

`\CodexRegisterRail` uses a `zref-abspage` guard to enforce **at most one register rail per physical page**. Each invocation records its absolute page; if a later rail resolves to the same page as the last one placed, it is suppressed. The guard only suppresses when the page is *resolved* (`abspage > 0`) and equal to the last placed page, so an early pass with unresolved cross-references places every rail rather than collapsing them all — the count converges as `zref` resolves on subsequent passes.

## Selecting an edition

For direct Markdown sources, set source frontmatter:

```yaml
---
codex_edition: reader
codex_strip_editorial_callouts: true
---
```

For `markdown_document` manifests, the same values may be passed through manifest `variables:`:

```yaml
variables:
  codex_edition: reader
  codex_strip_editorial_callouts: true
```

These keys are intentionally namespaced to Codex 0.

## Safety behavior

The preprocessor still fails hard on structural problems:

- if a source contains `cx0:` edition sentinels and no `codex_edition` is selected, render fails;
- if variant markers are malformed, nested, duplicated (duplicate edition labels), or unclosed, render fails;
- if `cx0:` edition controls are present under a non-`codex0` profile, render fails rather than leaking all branches;
- generated render sources must contain no remaining `cx0:` markers.

Exposure is fail-**open** by default: an edition without a matching override inherits the raw archival base rather than failing. To restore fail-closed exposure for a sensitive region, guard it. A guarded edition must carry an explicit override and may not inherit the raw base:

```markdown
<!-- cx0:variant id="the-reckoning" guard="witness,reader" -->
Raw archival prose.
<!-- cx0:edition witness -->
Veiled witness prose.
<!-- cx0:endvariant -->
```

Here rendering the reader edition fails hard (guarded, no override), the witness edition renders its override, and the archival edition renders the raw base.

Ordinary Optical Foundry renders without `cx0:` sentinels and without Codex edition controls are unchanged.

## Editorial callouts

Editorial language belongs in callouts, not edition prose. In Codex 0, Obsidian-style blockquote callouts are treated as draft/editorial surfaces:

```markdown
> [!note] Revision lane
> This is for Lux / editorial handling, not final reader prose.
>
> Markdown remains available inside the note.
```

For draft/operator proofs, Codex 0 rewrites these source callouts before Pandoc into `.codex-editorial-note` blocks and the profile filter typesets them as visible editorial notes. For reader-facing proofs, set `codex_strip_editorial_callouts: true`; then any blockquote beginning with `> [!kind]` is stripped from the generated render source. Ordinary blockquotes are preserved.

## Image and generated-figure guidance

Keep `of-image`, `of-initial`, generated diagrams, witness plates, and rail imagery outside edition-specific branches unless a branch genuinely needs a different visual object.

The pre-Pandoc edition culler runs before current figure preprocessors, so inactive image/diagram branches will be removed safely. Still, the preferred Codex 0 pattern is edition variants for prose and shared visual objects outside the variant block.

## Evidence

Successful renders record edition behavior in the evidence sidecar under keys including:

- `codex_edition_preprocessor_enabled`
- `codex_edition`
- `codex_edition_variant_count`
- `codex_edition_selected_count`
- `codex_edition_fallback_count`
- `codex_edition_selected_variant_ids`
- `codex_edition_fallback_variant_ids`
- `codex_editorial_callouts_stripped`
- `codex_editorial_callouts_formatted`
- `codex_edition_render_mode`
