# M0 Migration Asset Inventory

Snapshot date: 2026-07-31

This is an inventory, not a migration approval. No legacy runtime code is copied into
M0. License status must be resolved before any source is vendored or adapted.

| Asset | Source and version | SHA-256 | License | M0 disposition | Candidate target | Capability gap |
|---|---|---|---|---|---|---|
| `convert-thesis` orchestration Skill | `/Users/fl/.codex/skills/convert-thesis/SKILL.md`; local snapshot 2026-07-31 | `e97ac2ec9c75cd474eadb59eea7e853e2e81e025d1c551937e65726e2d83482a` | Not declared; clearance required | Reference only; replace the M0 discovery marker after M1 contracts are approved | `.claude/skills/convert-thesis/SKILL.md` | Assumes direct scripts and filesystem workflow; must be rewritten around five public Tools and Agent-owned `needs_input` |
| Conversion reference contract (`anchors.md`, `library-contract.md`, `ooxml-recipes.md`, `pitfalls.md`) | `/Users/fl/.codex/skills/convert-thesis/references/`; local snapshot 2026-07-31 | Manifest `a669af104274c832cb4f27c4498b24eb616ede092bbe2e83e9bc1080f71166a5` | Not declared; clearance required | Review and selectively rewrite; do not copy in M0 | Future Tool contract tests, concrete backend notes, and universal Knowledge candidates after de-schooling | Recipes are not yet normalized to the public Tool contracts or all-or-nothing publication model; school-specific values must remain task evidence |
| DOCX analysis and audit scripts (`_docx_utils.py`, `dump_docx.py`, `check_content.py`, `check_placeholders.py`) | `/Users/fl/.codex/skills/convert-thesis/scripts/`; local snapshot 2026-07-31 | Manifest `d5b7e595369a5eb0b3e931a614da96937663c64f4d234527f8518d08e183c55f`; `_docx_utils.py` `0b0a0912b5b89e5116baa102c902ed5bbfb8bee8e9bf23e339b87497a39dfcbf`; `dump_docx.py` `01f1cc42385e9de0f01ffc3ea99921438427b6cbb84ab3e0c9b2cbfc54d624a7`; `check_content.py` `3491c1de76987298a2bb08ffe59856b6f791f2f78cffbd512edc48479416df2f`; `check_placeholders.py` `cfc04adce722ce89651fe36b56bb9606480b1af77acdce3b8c3c5688d2816b41` | Not declared; clearance required | Candidate logic only; no runtime migration in M0 | M1 OfficeCLI adapter plus `tests/contract` and `tests/integration` | No stable five-Tool schema, OfficeCLI mapping, task-root enforcement, or atomic publication contract |
| Render and page-measure scripts (`render_pages.py`, `measure_pages.py`) | `/Users/fl/.codex/skills/convert-thesis/scripts/`; local snapshot 2026-07-31 | Manifest `b661fcc6092e469e0147cb2c1b6c71e82a9fb6e03eb254f951df089c9b34f049`; `render_pages.py` `df2a9b5bcb620bb507fc5054a4189011a41f384a1fa72a60f33ae1d513b2691e`; `measure_pages.py` `e5efecfb8b47370a7d175e1a0c5521870f70200d194f5af945e227896adb43f2` | Not declared; clearance required | Hold for the fixed dual-backend PoC; LibreOfficeDev alpha is not treated as a supported backend | M1 `docx_render` OfficeCLI feedback path, Word truth path, and integration fixtures | OfficeCLI high-frequency approximation, Word baseline/recheck/final routing, supported fonts, and stable page evidence remain unproven |
| `docfit-school-extract` Skill and evidence template | `/Users/fl/.codex/skills/docfit-school-extract/`; local snapshot 2026-07-31 | Package manifest `785bcca8197aa593846f91b6517704d2b0e0e0c50c8adc6c4ac30d8e17ffbe44`; Skill `acb264c2828f4d5b8baf52b11427e1a6c667819fc56816f590c176421966786c`; template `628d2db061aa6702b47249f8887a8d22ace27cb6d0f0872ddba5e7701117e403` | Not declared; clearance required | Reference only; do not migrate its school-package output model | Future task-scoped school-material interpretation and extraction evals | Any reused output must remain in the authorized task directory; school conclusions must not be promoted to product Knowledge |

## Hash method

Full hashes are standard SHA-256 values. A package manifest hash is the SHA-256 of the
sorted list of each contained file's SHA-256 line. The source snapshot must be re-hashed
before migration because these local Skills are independently mutable.

## M0 conclusion

- The two local Skills are useful reference inputs but have no declared license.
- Direct migration: none. Adapt-and-reuse candidates: every row above, subject to
  license clearance and the named future contract. Retire: none until the fixed
  OfficeCLI/Word backend PoC supplies replacement evidence.
- No asset is safe to copy into the product runtime during M0.
- M1 Preflight must validate and lock the concrete OfficeCLI 1.0.143 and local Word
  16.111.2 integration paths, resolve license provenance, and replace abbreviated entries
  with target commit hashes for any asset approved to move. It must not introduce a
  Provider selector or generic Provider interface.
