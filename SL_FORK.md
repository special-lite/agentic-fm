# Special-Lite Internal Fork

This repository is **Special-Lite's internal fork** of [petrowsky/agentic-fm](https://github.com/petrowsky/agentic-fm). It is consumed as a git submodule from `special-lite/sl-inventory` and (eventually) other SL FileMaker module repos.

## Why a fork

Two reasons:

1. **SL-specific lint rules and gotchas** — the upstream project is shared with other teams. Patterns that bit us repeatedly during SL Inventory audit-fix passes (Pattern A polarity bugs, empty PSOS parameter calcs, etc.) live as fmlint rules here. See `agent/fmlint/` for the rule sources and `docs/patterns/` in sl-inventory for the prose write-ups.

2. **Bug fixes we need today** — when we hit a bug that's been bothering us for weeks (e.g., the `tx_perform_script_on_server` / `tx_new_window` translator gap in `fm_xml_to_snippet.py`) we ship the fix here immediately rather than waiting on an upstream PR review cycle.

## Do not PR changes back to `petrowsky/agentic-fm`

**This is the firm rule.** Changes made on this fork stay on this fork. Upstream improvements may be pulled in, but our changes are not sent up.

The exception: if upstream itself opens a discussion about a feature that overlaps with something we've built, we can share our implementation as a reference. But no automated/proactive PR-back.

## Pulling upstream improvements

```bash
cd path/to/sl-inventory/agentic-fm
git fetch upstream                    # `upstream` should already point at petrowsky/agentic-fm
git checkout main
git merge upstream/main               # or rebase; merge is fine
# resolve any conflicts (rare — divergence is in fmlint/ and a few translator additions)
git push origin main
```

After pushing to the fork's `main`, bump the submodule pointer in sl-inventory:

```bash
cd path/to/sl-inventory
git add agentic-fm
git commit -m "submodule: bump agentic-fm to pull upstream changes through DATE"
```

## Intentional divergences from upstream

A short ledger of what differs from `petrowsky/agentic-fm`. Update this whenever a new SL-only change lands.

| Date | Change | Reason |
|---|---|---|
| 2026-05-15 | `agent/scripts/fm_xml_to_snippet.py` — added `tx_perform_script_on_server` and `tx_new_window` translators | Catalog-driven generic translator silently dropped PSOS script reference + parameter calc, and dropped New Window's Style/Name/Bounds/Options. Both broke transactional workflows on every SaXML → fmxmlsnippet round-trip. |
| 2026-05-15 | `agent/catalogs/step-catalog-en.json` — added `CurrentLayout`, `LayoutNameByCalculation`, `LayoutNumberByCalculation` to the `LayoutDestination` enum | Verified via FM round-trip 2026-05-14 (see sl-inventory `docs/patterns/fm-fmxmlsnippet-gotchas.md` §1). Upstream catalog only listed `SelectedLayout`. |
| 2026-05-15 | `agent/fmlint/rules/sl_*` — SL-specific lint rules | Pattern A polarity bug (`Set Error Capture [OFF]` before record-mutating step) and empty PSOS parameter calc are both silent-failure classes that have bitten this codebase 3+ times. Lint catches them deterministically. |
| 2026-05-15 | `agent/docs/CODING_CONVENTIONS.md` — deprecated `Insert Text [$README]` doc-block pattern + ban `PARAMETER FORMAT` / `RESULT JSON` / `INPUT:` / `OUTPUT:` / `PARAMS:` / `RETURNS:` header comments | Header parameter/result documentation drifts the moment the script is modified — second source of truth has to be maintained in lockstep with the script's own `JSONGetElement` / HANDLE RESULT JSON. SL_Core convention is comment-step-only headers. Enforced by `fmlint` SL018. |
| 2026-05-19 | `agent/docs/CODING_CONVENTIONS.md` — added "Custom Function return contract" section | CFs follow native FM calc idioms (return value or `"?"` on failure), **not** the script `$scriptResultObject` JSON contract. Discovered during UOM v2 Phase 2b authoring: the first version of `ConvertToItemBase` returned `"ERROR: ..."` strings, which Trevor flagged as non-native. The native pattern (`Number ( "abc" ) = "?"`, etc.) is what CF callers expect. Doc captures the two CF categories (pure math vs. lookup) and the caller pattern for detecting `"?"`. |
| 2026-07-10 | `agent/fmlint/rules/sl_inventory.py` — **SL021** `sql-hardcoded-identifier` (ERROR, **mandatory — on by default, do not disable**); `agent/fmlint/engine.py` + `agent/fmlint/__main__.py` — `LintRunner.lint_calc` + `--custom-functions` CLI mode (`applies_to_calc` rule opt-in); `agent/fmlint/fmlint.config.json` — C003 `extra_known_functions` += `GetFN` / `GetTN` / `GTFN` / `ExecuteSQLe`; `agent/fmlint/tests/` — first `unittest` suite (`test_sl021_sql_name_protection.py`, 21 tests) | `ExecuteSQL` / `ExecuteSQLe` queries must build every table and field name via `GetTN()` / `GetFN()` / `GTFN()`, never as SQL string literals. A hardcoded identifier silently rots — after a Manage-Database rename, `ExecuteSQL` returns `"?"` / empty with **no error** — the same silent-failure class the other SL rules target. Applies to **scripts and custom-function definitions** (`python3 -m agent.fmlint --custom-functions` scans the exploded CF calcs; much SL_Core SQL lives in lookup CFs). Detection scans only string literals that flow into a query — inline first-args **plus SQL assembled in a `Let` variable** (the SL_Core lookup-CF pattern, e.g. `GetConfigValue`) — and flags a bareword only when an identifier-introducing keyword (`FROM`/`JOIN` → table; `SELECT`/`WHERE`/`AND`/… → field) precedes it *within the same literal*. So `GetFN`/`GetTN`-injected names, table aliases, alias-qualifier prefixes (`"SELECT V." & GetFN(…)`), and FileMaker system tables (`FileMaker_Tables`/`FileMaker_Fields`/…, which are un-renameable) never false-positive. Verified: 0 findings on the fully-protected 1209/885 scripts and on `GetConfigValue`; across the live CF library it flags exactly the genuinely-hardcoded ones (e.g. `IsItemInventoryTracked`). The C003 whitelist stops the protective CFs from themselves being flagged as unknown functions. |

## Cross-references

- **SL FileMaker patterns and gotchas** → [`sl-inventory/docs/patterns/`](https://fmdev.special-lite.com:8080/dev/inventory/patterns/) (hosted in sl-docs)
- **SL team workflow rules** → [`sl-inventory/CLAUDE.md`](../CLAUDE.md) and [`sl-docs/dev/team-workflow.md`](https://fmdev.special-lite.com:8080/dev/team-workflow/)
- **Upstream project** → [`petrowsky/agentic-fm`](https://github.com/petrowsky/agentic-fm)

## For Claude sessions opening this folder cold

If you're an agent reading this on session start: this is a fork. The SL-specific rules in [`sl-inventory/CLAUDE.md`](../CLAUDE.md) (`No subagents for FM script generation`, etc.) apply. Read [`sl-inventory/docs/patterns/`](../docs/patterns/) before editing any FM scripts. Do not propose PRs back to petrowsky/agentic-fm.
| 2026-08-24 | `agent/docs/filemaker/fetch_docs.py` — rewritten against Claris's Markdown corpus (`help.claris.com/llms.txt`); `--guides`, `--refresh`, `--prune` added; `requests` + `beautifulsoup4` dependency dropped | Claris now publishes the whole help corpus as Markdown under the llms.txt convention, so the ~350 lines of BeautifulSoup HTML→Markdown conversion, the `_SLUG_OVERRIDES` guess table, and the `_INDEX_SLUGS` deny-list are all obsolete. The index is authoritative for what exists, front matter declares `topic_type` (so category membership no longer has to be inferred) and `date_modified` (so `--refresh` re-fetches only what changed, which the old cache-by-existence scheme could not do). Two correctness fixes fell out: the old scraper harvested *every* link on a category page and filed ~57 FileMaker Go help topics as script steps / functions (`basics.md`, `troubleshooting.md`, `shortcuts-os-x.md`, …) — discovery now reads only curated link-table rows, and `--prune` removes the strays; and the JSON functions were being discovered from the prose page `json-functions` rather than the real link table `json-functions-category`. `--guides` is new capability: whole doc-sets (`sql-reference`, `odata-guide`, `data-api-guide`, `admin-api-guide`, `security-guide`) that the pro-help-only fetcher never covered — directly relevant to SL_Core's `ExecuteSQLe`- and OData-heavy work (see SL021, and the OData auto-enter/rename limits). Caveat carried in the docs: help.claris.com always serves the current release (FM 26), so compatibility tables can describe a newer version than the deployed one. |

