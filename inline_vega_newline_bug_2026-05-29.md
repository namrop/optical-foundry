---
uid: 31ce9bdd-e60a-4ce4-b9e2-49fed73d3606
kind: note
note_role: mechanism_record
title: "Vega fence replacement newline bug — engine/vega.py:124"
validation_profile: minimal
status: active
created: 2026-05-29T11:30:00-04:00
updated: 2026-05-29T11:30:00-04:00
beam_home: 42_optical_foundry
tags:
  - optical-foundry
  - vega
  - bug
  - pandoc
summary: "Vega preprocessor replacement strips trailing newline, collapsing subsequent headings into the image block for Pandoc."
---

# Vega fence replacement newline bug

## Location
`engine/vega.py`, line 124 — the `replace()` closure inside
`preprocess_vega_blocks()`.

## Cause
The Vega fence regex at line 213:

```python
r"^```vega[^\n]*\n(?P<body>.*?)^```\\s*$"
```

The `\s*$` in multiline mode **consumes the trailing newline** that follows
the closing `` ``` `` fence. The replacement string on line 124:

```python
return f"![Vega chart {index}]({figure_path}){{#fig:vega-{index}}}"
```

**had no trailing newline**, so the newline consumed by the regex was never
restored. Net result: the intermediate markdown fed to Pandoc collapsed the
image reference and the following heading onto adjacent lines with no blank
line separator:

```
![Vega chart 1](...pdf){#fig:vega-1}
### Key Takeaways ...
```

Pandoc then interprets the `###` as continuation of the image block rather
than a heading.

## Impact
Any `\`vega fenced block immediately followed by a heading (`##` or `###`)
will have that heading silently degraded to plain body text in the rendered
PDF. Discovered while rendering keeper-profile documents with embedded Vega
charts followed by "Key Takeaways" subsections.

## Applied fix
Changed line 124 to restore the trailing newline:

```python
return f"![Vega chart {index}]({figure_path}){{#fig:vega-{index}}}" + "\n"
```

This ensures the image reference ends with `\n`, which — combined with the
`\n` already preserved after the regex match — produces a blank-line
separation before the next heading.

## Regression check
Added `test_preprocess_vega_blocks_preserves_heading_after_fence` in
`tests/test_vega_preprocessor.py` to assert that a heading immediately after a
Vega fence remains on its own line in the rewritten Markdown. The existing Vega
preprocessor tests continue to pass after the fix. No other Vega charts in the
Atrium use immediate-post-fence headings, so no other documents are affected.

## Future prevention
Consider adding a `\n\n` (double newline) to the replacement instead of a
single `\n`, for extra robustness against Pandoc's block-parsing edge cases.
Also consider a unit test that asserts the replacement output ends with `\n`.
