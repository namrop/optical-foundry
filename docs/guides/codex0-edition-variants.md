---
uid: 019f24ff-4914-7647-877a-4acd0d7e681e
kind: note
note_role: spec
validation_profile: standard
status: draft
created: 2026-07-02T18:42:18-04:00
updated: 2026-07-02T18:42:18-04:00
beam_home: 42_optical_foundry/docs/guides
title: "Codex 0 Edition Variants"
summary: "Guide for Codex 0 source-visible edition variants selected by a pre-Pandoc comment-sentinel culler before figure/source preprocessors run."
tags:
  - optical-foundry
  - codex0
  - edition-variants
  - pandoc
  - preprocessing
---

# Codex 0 edition variants

Codex 0 may keep edition-specific paragraph rewrites side-by-side in the manuscript source. This is a Codex 0 profile-scoped mechanism, not a general Foundry document primitive yet.

## Source syntax

Use HTML comment sentinels around normal Markdown prose:

```markdown
<!-- cx0:variant id="how-you-arrived-010" fallback="johannah" -->

<!-- cx0:edition johannah -->
The harbor bell rang twice before the ferry left the pier.

<!-- cx0:edition reader -->
A bell rang somewhere over the water: not loud, not near, but enough to turn every head on the deck.

<!-- cx0:endvariant -->
```

Supported markers:

- `<!-- cx0:variant id="..." fallback="..." -->`
- `<!-- cx0:edition johannah -->`
- `<!-- cx0:edition edition="johannah" -->`
- `<!-- cx0:endvariant -->`

The selected branch remains ordinary Markdown after preprocessing. Inactive branches are removed before Pandoc and before the existing `of-image`, Mermaid, Vega, D2, Graphviz, and emoji source preprocessors run.

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

The preprocessor is fail-closed:

- if a source contains `cx0:` edition sentinels and no `codex_edition` is selected, render fails;
- if the selected edition is absent and no valid fallback is present, render fails;
- if variant markers are malformed, nested, duplicated, or unclosed, render fails;
- if `cx0:` edition controls are present under a non-`codex0` profile, render fails rather than leaking all branches;
- generated render sources must contain no remaining `cx0:` markers.

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
