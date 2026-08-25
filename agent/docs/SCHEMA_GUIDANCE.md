# Schema Guidance: Catalog Params → fmxmlsnippet XML

This document explains how to construct correct fmxmlsnippet XML from a step catalog entry alone. Follow it to avoid needing to read snippet_examples for standard steps.

> **Normative schema:** the authoritative definition of every catalog `type`, key, and grammar rule lives in [`agent/catalogs/CATALOG_SCHEMA.md`](../catalogs/CATALOG_SCHEMA.md). This document is the OSS hand-authoring guide layered on top of that contract; when the two disagree, the contract wins. For structured types not covered in detail below — `attrGroup`, `fieldList`, `repeatGroup`, `parametersList`, `fieldOrVariable`, and the full enum key family (`enumValues`/`xmlEnumValues`/`hrEnumValues`/`enumStyle`) — see the contract.

## Step Wrapper

Every script step is wrapped in `<Step id="N" enable="True">`. The `id` comes from the catalog entry's top-level `id` field. Child content depends on `selfClosing`:

```
"selfClosing": true   →  <Step id="N" enable="True"/>          (no children)
"selfClosing": false  →  <Step id="N" enable="True">...params...</Step>
```

---

## Param Types → XML

### `boolean`

Emits a single element with an attribute. `xmlAttr` names the attribute; value is always `"True"` or `"False"`.

```json
{ "xmlElement": "NoInteract", "type": "boolean", "xmlAttr": "state", "invertedHr": true }
```
```xml
<NoInteract state="True"/>
```

**`invertedHr: true`**: the HR label ("With dialog: On") maps to the opposite XML value (`state="False"`). Always check this flag. HR enum labels ("On"/"Off") from `enumValues`/`hrEnumValues` do not appear in XML.

---

### `enum`

Emits an element with the chosen value in an attribute (`xmlAttr`) or as element text (no `xmlAttr`).

Attribute form:
```json
{ "xmlElement": "LayoutDestination", "type": "enum", "xmlAttr": "value", "defaultValue": "SelectedLayout" }
```
```xml
<LayoutDestination value="SelectedLayout"/>
```

Text form (no `xmlAttr`):
```xml
<Format>PDF</Format>
```

Use only values from the `enumValues` array.

---

### `calculation`

Emits a `<Calculation>` element with a CDATA block.

```xml
<Calculation><![CDATA[$myVar & " suffix"]]></Calculation>
```

---

### `namedCalc`

A `<Calculation>` element wrapped inside a named parent. The wrapper name is in `wrapperElement`.

```json
{ "xmlElement": "Calculation", "type": "namedCalc", "wrapperElement": "TargetName" }
```
```xml
<TargetName>
  <Calculation><![CDATA[GetFieldName ( Table::Field )]]></Calculation>
</TargetName>
```

---

### `text`

Emits a plain text element — no CDATA, no attribute.

```xml
<UniversalPathList>filemac:/Volumes/Data/export.xlsx</UniversalPathList>
```

---

### `field`

Emits `<Field table="TO" id="N" name="FieldName"/>`. All three values come from CONTEXT.json or index files.

```xml
<Field table="Invoices" id="12" name="Status"/>
```

When the target is a variable, `<Field>` holds the variable name as text with a sibling `<Text/>`:

```xml
<Field>$myVariable</Field>
<Text/>
```

---

### `script`

Emits `<Script id="N" name="ScriptName"/>`. Values from CONTEXT.json `scripts` section or `scripts.index`.

```xml
<Script id="42" name="Process Invoice"/>
```

---

### `layout`

Emits `<Layout id="N" name="LayoutName"/>`. Values from CONTEXT.json `layouts` section or `layouts.index`.

```xml
<Layout id="7" name="Invoices Detail"/>
```

---

### `flagElement`

An empty self-closing element where **presence = on** and **absence = off**. No attributes, no content.

HR option on → include the element: `<Overwrite/>`

HR option off → omit the element entirely. Never emit `<Overwrite state="False"/>`.

---

## `wrapperElement` and `parentElement` Chains

**`wrapperElement`** wraps the param's `<Calculation>` inside a named element:

```json
{ "xmlElement": "Calculation", "type": "namedCalc", "wrapperElement": "RowList" }
```
```xml
<RowList><Calculation><![CDATA[$ids]]></Calculation></RowList>
```

**`parentElement`** nests the wrapper inside an additional container. When multiple params share the same `parentElement`, emit a single parent element containing all of them — do not repeat the parent.

```json
{ "xmlElement": "Overwrite", "type": "flagElement", "parentElement": "LLMBulkEmbedding" }
{ "xmlElement": "ContinueOnError", "type": "flagElement", "parentElement": "LLMBulkEmbedding" }
```
```xml
<LLMBulkEmbedding>
  <Overwrite/>
  <ContinueOnError/>
</LLMBulkEmbedding>
```

---

## `blockPair` — Matching Open/Close Steps

Steps with `blockPair` must always be emitted as complete pairs. An `If` without `End If` is invalid.

```json
"blockPair": { "role": "open", "partners": ["End If"] }
```

| Role | Meaning |
|------|---------|
| `open` | Starts a block — requires all `partners` to close it |
| `close` | Ends a block — must be preceded by the matching `open` |
| `middle` | Optional intermediary (e.g., `Else`, `Else If`) — valid only between `open` and `close` |

Steps with `blockPair: null` are standalone. Common pairs: `If`/`End If`, `Loop`/`End Loop`, `Open Transaction`/`Commit Transaction`.

---

## `notes` Field

The top-level `notes` object captures behavioral intelligence. Check it before writing steps — it avoids a snippet_examples file read for common gotchas.

```json
"notes": {
  "behavioral": ["..."],     // general behavior, usage patterns, side effects
  "constraints": ["..."],    // hard rules FileMaker enforces or silently breaks
  "gotchas": ["..."],        // subtle behaviors that cause real-world bugs
  "performance": ["..."],    // performance guidance
  "platform": {              // only keys with content; behavior differs from Pro client
    "server": "...", "webdirect": "...", "go": "..."
  }
}
```

---

## Worked Example: Set Field

```json
{ "name": "Set Field", "id": 76, "selfClosing": false,
  "params": [
    { "xmlElement": "Calculation", "type": "calculation", "required": true },
    { "xmlElement": "Field",       "type": "field",       "required": false }
  ],
  "blockPair": null }
```

HR: `Set Field [ Invoices::Status ; "Sent" ]`
Field `Status` in TO `Invoices`, id `12` (from CONTEXT.json).

```xml
<Step id="76" enable="True">
  <Calculation><![CDATA["Sent"]]></Calculation>
  <Field table="Invoices" id="12" name="Status"/>
</Step>
```

---

## Worked Example: If / End If (blockPair)

```json
{ "name": "If", "id": 68, "selfClosing": false,
  "blockPair": { "role": "open", "partners": ["End If"] } }
{ "name": "End If", "id": 70, "selfClosing": true, "blockPair": { "role": "close" } }
```

HR: `If [ $error ≠ 0 ]`

```xml
<Step id="68" enable="True">
  <Calculation><![CDATA[$error ≠ 0]]></Calculation>
</Step>
<!-- steps inside the block -->
<Step id="70" enable="True"/>
```

`End If` is `selfClosing: true` with no params — emits as a self-closing tag.

---

## Worked Example: Perform Script (script + calculation)

```json
{ "name": "Perform Script", "id": 1, "selfClosing": false,
  "params": [
    { "xmlElement": "Calculation", "type": "calculation" },
    { "xmlElement": "Script",      "type": "script" }
  ] }
```

HR: `Perform Script [ "Process Invoice" ; Parameter: $payload ]`
Script id `42` (from CONTEXT.json).

```xml
<Step id="1" enable="True">
  <Calculation><![CDATA[$payload]]></Calculation>
  <Script id="42" name="Process Invoice"/>
</Step>
```

---

## When to Fall Back to snippet_examples

Use the catalog alone when `"status": "complete"` and all param types are in this document.

Fall back to reading the snippet_examples file (path in `snippetFile`, prefixed with `agent/snippet_examples/steps/`) when:

- `"status"` is `"auto"` or `"unfinished"`
- A param has `"type": "complex"` — the legacy escape-hatch type whose structure is not modeled in the schema (prefer the structured types `attrGroup`/`fieldList`/`repeatGroup` documented in `CATALOG_SCHEMA.md`, which **can** be derived from the entry's `fields[]`; only true `complex` params need the example)
- `parentElement` chains are deeply nested or ambiguous in the entry
- Behavioral constraints in snippet XML comments are needed for correctness
