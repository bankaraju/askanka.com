# Waivers Register

Per Section 15.4 of `docs/superpowers/specs/backtesting-specs.txt`, any deviation from Sections 1-14 of the standards requires a written waiver logged here BEFORE the deviation takes effect.

## Filename convention
`YYYY-MM-DD-<strategy-or-component>.md`

## Required fields
- **Hypothesis / strategy ID** (from `docs/superpowers/hypothesis-registry.jsonl`)
- **Section being waived** (e.g., "Section 6.2 survivorship coverage_ratio < 10%")
- **Reason for waiver** (data-unavailable, awaiting-build, research-only, etc.)
- **Expiry date** (hard stop, no open-ended waivers)
- **Signing principal** (Bharat Ankaraju)
- **Date signed** (must be BEFORE the deviation)

## Rules
- Waivers are **not retroactive**. A test that already ran without a waiver cannot be covered after-the-fact.
- **Section 0 principles cannot be waived.** Ever.
- Expired waivers must be renewed with explicit re-signature, not rolled silently.
- Every waiver is git-committed with the principal's co-author tag.
