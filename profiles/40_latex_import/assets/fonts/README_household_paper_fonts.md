# Fonts vendored for the `household-paper` profile (2026-09-09)

Copied verbatim from TeX Live 2025 (`texmf-dist/fonts/opentype/public/<family>/`) so the
Foundry font policy can resolve them as `foundry_local` on any host, instead of depending on
luaotfload finding the texmf tree.

| Directory | Family | Role in the profile | License |
|---|---|---|---|
| `xcharter/` | XCharter (Michael Sharpe's extension of Bitstream Charter) | body text | SIL OFL 1.1 (CTAN `xcharter`) |
| `playfair/` | Playfair Display (Claus Eggers Sørensen) | headlines ≥ 16 pt | SIL OFL 1.1 |
| `chivo/` | Chivo (Omnibus-Type) | labels, kickers, agate, running heads | SIL OFL 1.1 |
| `oldstandard/` | Old Standard (Alexey Kryukov) | masthead **slot** placeholder face only; the masthead itself is unminted | SIL OFL 1.1 |

No license text ships in this TeX Live's doc tree for these families; the license identifiers
above are CTAN's. All four permit bundling and embedding.
