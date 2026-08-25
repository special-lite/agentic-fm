# Updating Step Catalogs

## Objective

Maintain 100% coverage of `agent/catalogs/step-catalog-en.json`, and any other language variation thereof, for all possible FileMaker script steps. The catalog is the **canonical HR (human-readable) reference** while `snippet_examples/` files are the **canonical XML reference**. There should be a 1:1 match for each entry within a catalog file and the files found within snippet examples.

Every entry must conform to the structural contract in [`CATALOG_SCHEMA.md`](./CATALOG_SCHEMA.md) — the normative definition of every `type`, key, and grammar rule the catalog uses. Consult it before adding or changing a parameter shape.

## Token Efficiency

**NEVER read `step-catalog-en.json` in full.** It is large (~200KB+) and reading it wastes tokens. Always use Grep to extract only the entry being worked on:

```bash
grep -A 60 '"name": "Step Name Here"' agent/catalogs/step-catalog-en.json
```

Adjust the `-A` line count if the entry is longer. Similarly, when scanning for remaining work, grep for `"auto"` or `"unfinished"` status rather than reading the whole file.

## Workflow Per Step

The user either pastes both the HR format and fmxmlsnippet XML for each step or references a temporary file name which contains both formats. For each step:

1. **Grep** the current catalog entry (see Token Efficiency above) and read the snippet_examples file (including `agent/snippet_examples/steps/CONVENTIONS.md` for snippet authoring rules)
2. **Extract** the `id` from the fmxmlsnippet
3. **Map** HR labels and enum values (which often differ from XML values)
4. **Cross-check** against snippet_examples — always explicitly present the comparison result to the user, even when there are no differences
5. **Update catalog**: set id, add hrLabels, HR enumValues, order params to **XML serialization order** (the order FileMaker writes the child elements/attributes — this is the normative param order per `CATALOG_SCHEMA.md`, used for positional HR↔XML round-tripping; `hrSignature` separately conveys HR display order), set hrSignature, status→"complete"
6. **Update snippet_examples** if needed: fix wrong comments, add missing structure/elements, add HR annotations to comments
7. **Do NOT** include XML comments in code output — they are reference only

## Key Patterns Discovered

- **`invertedHr: true`** — for `NoInteract` → "With dialog" where HR On = XML False
- **`parentElement`** — for params nested inside wrapper elements (e.g., `<FineTuneLLM>`, `<LLMRequestWithTools>`)
- **HR boolean values** — often "On"/"Off" or "Yes"/"No" while XML uses "True"/"False"
- **Flag-style booleans** — some params shown as a word when True, omitted when False (e.g., "Select", "Automatically open", "Stream", "Agentic mode")
- **Canonical XML typos** — `SetLLMAccout`, `AccoutName` (missing 'n'), `RAGPPrompt` (extra P) — these are FileMaker's actual XML
- **Dual-format Field** — `<Field table="" id="" name=""/>` for field refs OR `<Field>$variable</Field>` with `<Text/>` for variables. Both support `repetition` attribute. This is system-wide.
- **Typed Field elements** — inside wrappers like `<Field type="ToolCalls">` or `<Field type="Messages">`
- **`<Text/>` empty element** — appears as sibling when Field holds a variable; not a real HR param
- **`fileReference` type** — for FileReference elements with UniversalPathList children
- **DataType codes** — 4-character classic Mac file type codes (e.g., `"TABS"`, `"XLS "`, `"DBF "`)
- **`findRequests` param type** — used for Query elements; references the shared `find-requests.md` for structure, search operators, and variable rules
- **No-parameter steps** — self-closing steps with no params get `hrSignature: ""` (empty string, not null)
- **Behavioral variants on omission** — some steps change purpose when an optional element is omitted (e.g., Go to Field without a Field element exits the current field and implicitly commits the record). The `required` flag in auto-generated entries may be wrong — always verify against user-provided examples.
- **`flagElement` type** — empty XML elements where presence = on, absence = off (e.g., `<Overwrite/>`, `<ContinueOnError/>`, `<ShowSummary/>`). Different from flag-style booleans which use `state="True"/"False"`.
- **Snippet independence** — snippet_examples must be fully self-contained. Never reference catalog enum files (`animation-enums.md`, `window-enums.md`, etc.) from snippet comments. Those files are only for catalog discussion/modification. Snippet comments must inline all enumerations and attribute values directly.
- **`<Text>` dual role** — In most steps, `<Text/>` (empty, self-closing) is a sibling of `<Field>` signaling a variable target. In Insert Text, `<Text>content</Text>` holds the literal text being inserted (raw content, not Calculation/CDATA). Same element name, different purpose — check the step's snippet carefully.
- **Multi-line raw Text** — `<Text>` content in Insert Text uses `&#xD;` (carriage return) XML character entities for line breaks, not literal newlines.
- **UniversalPathList `type` always explicit** — "Embedded" and "Reference" are always written as explicit attribute values. Never omit the type attribute to mean Embedded. Auto-generated snippets for Insert PDF, Insert Picture, and Insert Audio/Video incorrectly said "omit type attribute to embed" — all corrected.

## Shared Enum Files

Created in `agent/catalogs/` to avoid duplication across steps:

- **`language-enums.md`** — 54 OverrideLanguage values (HR labels + assumed XML values). Simple names confirmed; special variants (Finnish v<>w, German ä=a, Chinese Pinyin/Stroke, Spanish Modern, Swedish v<>w, Serbian Latin, Greek Mixed) marked ⚠️ as needing authoritative XML verification. Used by Sort Records and Sort Records by Field.

- **`shared-enums.md`** — CharacterSet (with HR labels), DataType file source codes, Profile attributes, ImportOptions, ExportOptions, ExportEntries/SummaryFields. Used by Convert File, Export Records, Import Records.
- **`animation-enums.md`** — 12 Animation values (HR→XML), LayoutDestination values. Used by steps with layout transitions (Go to Layout, Go to List of Records, Go to Related Record, etc.).
- **`window-enums.md`** — NewWndStyles attributes, 4 window style types (Document, Floating, Dialog, Card) with supported attribute matrix, new window params. Used by steps that support "New window" mode.
- **`find-requests.md`** — Query XML structure (RequestRow, Criteria, Field, Text), search operators, variable notes, HR parameters. Used by Enter Find Mode, Perform Find, Constrain Found Set, Extend Found Set.

## Status Values

- `"auto"` — auto-generated, not yet reviewed
- `"complete"` — fully reviewed with HR data from user
- `"unfinished"` — partially reviewed, missing some data (e.g., Execute SQL needs ODBC setup)

To find remaining work, scan the catalog for any `"status"` that is not `"complete"`.

## Notes Field

Top-level `notes` object on a catalog entry captures behavioral intelligence migrated from `snippet_examples/` XML comments. Use it as the **first stop** when generating scripts — it avoids a separate file read for the most common gotchas.

### Schema

```json
"notes": {
  "behavioral": ["..."],     // general behavioral details, usage patterns, side effects
  "constraints": ["..."],    // hard rules — FileMaker will not accept or silently breaks these
  "gotchas": ["..."],        // subtle behaviors that cause bugs in real scripts
  "performance": ["..."],    // performance guidance
  "platform": {              // platform-specific notes (only include keys with actual content)
    "pro": "...",
    "server": "...",
    "webdirect": "...",
    "go": "...",
    "cloud": "...",
    "dataapi": "...",
    "cwp": "..."
  }
}
```

Only include sub-keys that have actual content. Do not add empty arrays or empty objects.

### Migration workflow

1. Read the snippet_examples file for the step (path is in the catalog entry's `snippetFile` field).
2. Extract all XML comments from the snippet file (lines starting with `<!--`).
3. Classify each comment into a `notes` sub-key:
   - Platform-qualified notes (`Server:`, `Go:`, `WebDirect:`, etc.) → `platform` sub-key
   - Hard restrictions ("not supported", "returns error", "cannot") → `constraints` or `platform`
   - Subtle or surprising behaviors → `gotchas`
   - General behavioral detail → `behavioral`
4. Add the `notes` object after `helpUrl` in the catalog entry.
5. Validate JSON: `python3 -m json.tool agent/catalogs/step-catalog-en.json > /dev/null`

### Archive rule

Once notes are migrated, the snippet file becomes the **archive** (XML reference only), not the source of behavioral truth. The catalog `notes` field is the live source for agent consumption. Do **not** modify snippet files during this migration — they remain unchanged and read-only.

## Additional Reference

Official Claris documentation for each script step may be available at `agent/docs/filemaker/script-steps/`. **Note:** this directory only exists if `agent/docs/filemaker/fetch_docs.py` has been run to download the documentation -- it is not checked into the repo. These can be consulted for parameter details, behavior notes, and platform support. **Important:** the official docs only reference terms in the human-readable format — they contain no fmxmlsnippet/XML values. They are useful for understanding HR option names and step behavior, not for XML element or attribute names.
