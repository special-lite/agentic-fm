# Automation & OData

The agentic-fm script collection (`filemaker/agentic-fm.xml`) contains the FM-side scripts that power the agent's feedback loops. These scripts are installed in every solution. They can be triggered in two ways:

- **Manually**: developer runs them from the Scripts menu in FM Pro
- **Via OData** (when configured): agent calls FM scripts through `AGFMScriptBridge`

## Docker networking

When FM Server runs in a Docker container and the companion server runs on the host, OData-triggered scripts execute server-side inside the container. In that case `localhost:8765` in the FM scripts will not reach the companion server — use `host.docker.internal:8765` instead.

This also applies to the agent itself when running inside a container (e.g. a Claude Code worktree). Any direct HTTP call the agent makes to the companion server will fail on `localhost:8765`. Use the fallback sequence: try `http://localhost:8765` first; if the connection is refused (curl exit code 7), retry with `http://host.docker.internal:8765` and use that host for all subsequent calls in the session.

## Plug-in capability broker (`/health.plugin`)

The companion server is also the single detection broker for the optional commercial AgenticFM plug-in. `GET /health` carries a `plugin` block so the agent makes exactly one detection call — see `agent/docs/PLUGIN_INTEGRATION.md` for the full routing model. The block reports:

- `installed` — the plug-in's macOS Application Support tree is present.
- `usable` — installed **and** the plug-in's HTTP server is reachable **and** the license is active or in trial. **This is the only field the agent routes on.**
- `server` — `{ reachable, base, token, remote }`. The address and bearer token come from the plug-in's `preferences.json` (`remoteAccessPort` default `8766`, `remoteAccessToken`); remote access must be enabled for a stable port+token.
- `license` — `{ status, licensed, daysRemaining?, … }` for the optional lapsed-license nudge.
- `solutions[]` — indexed solutions (`{ key, name, catalog, files, parsed_at }`) so the agent can match the current solution before routing understanding/context.
- `discover` — the plug-in's **self-describing endpoint suite**, brokered from its token-free `GET /api/discover`. This is the live, license-gated catalog (full suite when usable, a shrunk list + `purchaseUrl` when locked). The agent reads this to **choose** endpoints for the task rather than assuming a fixed set — the integration never hardcodes the plug-in's API surface.
- `repoPath` / `catalogBaseUrl` / `gates` — surfaced from `preferences.json` when present (workspace binding, catalog source, the plug-in's own mutation-confirmation gates).

The companion resolves `usable` by probing the plug-in's token-free `GET /api/health`, brokers `GET /api/discover`, and caches the result ~60 s. Detection only — nothing here makes any OSS feature depend on the plug-in; when the plug-in is absent or not usable the block reports it and the agent stays on the OSS path.

### Optional plug-in proxy (`/plugin/<path>`)

Direct plug-in access is the baseline (call `plugin.server.base` with `Authorization: Bearer <token>`). As a convenience for constrained environments — a container that can reach the companion but not the plug-in's port, or to keep a single base URL — the companion exposes a thin pass-through:

```
GET|POST {companion}/plugin/<path>   →   forwards to the plug-in's /<path>, bearer token injected
```

It returns `502` when the plug-in is not `usable`, so the agent's fallback to the OSS path stays self-enforcing. The proxy is inert until called.

## Agentic-fm scripts

| Script                   | What it does                                                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Get agentic-fm path**  | Validates and returns the path to the agentic-fm project folder, stored in `$$AGENTIC.FM`; called by other scripts                       |
| **Push Context**         | Prompts for a task description, calls `Context()` custom function, writes `agent/CONTEXT.json` directly via FM file steps                |
| **Explode XML**          | Calls `Save a Copy as XML`, then POSTs to `localhost:8765/explode` — companion server parses the XML into `xml_parsed/`                  |
| **Agentic-fm Debug**     | POSTs runtime state JSON to `localhost:8765/debug` — companion server writes `agent/debug/output.json`                                   |
| **AGFMScriptBridge**     | OData entry point — accepts `{ script, parameter }` JSON and runs any named script; used by the agent to trigger FM scripts autonomously |
| **AGFMGoToLayout**       | Navigates FM to a named layout; used before calling Push Context to switch solution context                                              |
| **AGFMEvaluation**       | Evaluates a FileMaker calculation expression server-side and returns the result; optionally navigates to a layout first                   |
| **Agentic-fm webviewer** | Starts or stops the agentic-fm webviewer from within FileMaker via the companion server                                                  |
| **Agentic-fm Menu**      | Handles custom menu calls and passes them through to the agentic-fm web viewer via JavaScript                                            |
| **Agentic-fm Paste**     | Opens a script tab in Script Workspace via MBS `ScriptWorkspace.OpenScript`; used by Tier 2 deployment                                   |

## OData script execution

`agent/config/automation.json` supports multiple FM solutions. Each solution is listed under the `solutions` key, where the key is the **exact FM file name** — matching the `solution` field in `agent/CONTEXT.json`. This allows the agent to work across multi-file solutions (UI file, data file, etc.) or completely separate solutions, each with their own OData credentials and paths.

**To resolve the active solution config**: read `CONTEXT.json["solution"]`, then look up `automation.json["solutions"][solution_name]`. If a match exists and it has an `odata` block, OData is available for that solution.

**IMPORTANT**: Always confirm with the developer before triggering a script via OData. State what script you are about to run and why, and wait for approval before proceeding.

### How to call a script

All FM scripts are called through `AGFMScriptBridge` — FMS 21.x cannot route OData script calls with spaces in script names, so the bridge handles dispatch:

```
POST {odata.base_url}/{url_encode(odata.database)}/Script.{odata.script_bridge}
Authorization: Basic <base64(username:password)>
Content-Type: application/json

{
  "scriptParameterValue": "{\"script\": \"<ScriptName>\", \"parameter\": \"<optional param string>\"}"
}
```

Credentials, base URL, and bridge script name are all read from `automation.json["solutions"][solution]["odata"]`. The `scriptParameterValue` is a JSON-encoded string (double-serialised — the outer JSON value is itself a JSON string).

Response shape: `{ "scriptResult": { "code": 0, "resultParameter": "<script result JSON>" } }`

### Key agent-triggered scripts

**Run Explode XML** (refresh `xml_parsed/` after FM schema or script changes):

- Script: `Explode XML`
- Parameter: `{ "repo_path": "...", "export_path": "...", "companion_url": "..." }`
- Values come from `automation.json["solutions"][solution]["explode_xml"]`
- `companion_url` here is the URL FMS uses to reach the companion server — typically `http://host.docker.internal:8765` when FMS runs in Docker

**Switch layout context and refresh CONTEXT.json**:

1. Call `AGFMGoToLayout` with parameter `{ "layout": "<layout name>" }` — navigates FM to the target layout
2. Call `Push Context` with parameter `{ "task": "<task description>", "repo_path": "...", "companion_url": "..." }` — writes a fresh `agent/CONTEXT.json` scoped to that layout

**Run any solution script**: call `AGFMScriptBridge` directly with `{ "script": "<ScriptName>", "parameter": "<optional>" }` to trigger any named script in the solution.

### automation.json solution config structure

```json
{
  "solutions": {
    "My Solution": {
      "odata": {
        "base_url": "https://<host>/fmi/odata/v4",
        "database": "My Solution",
        "username": "<odata_account>",
        "password": "<password>",
        "script_bridge": "AGFMScriptBridge"
      },
      "explode_xml": {
        "repo_path": "<absolute POSIX path to agentic-fm root on companion host>",
        "export_path": "<absolute POSIX path FMS writes the XML export to — must include filename, e.g. .../Documents/My Solution.xml>",
        "companion_url": "http://host.docker.internal:8765"
      }
    }
  }
}
```

Add one entry per FM file. The key must match `Get(FileName)` exactly — this is what appears in `CONTEXT.json["solution"]`. `automation.json` is gitignored; credentials are safe to store there.

> **Deprecation — companion address.** The top-level `companion_url` in `automation.json` is deprecated in favour of `agent/config/companion.json` (`companion.advertise_host` + `companion.port`), which is the single source of truth for the companion address. It is still honoured during the migration window; when `companion.json` is present it wins. The per-solution `explode_xml.companion_url` (the URL **FileMaker Server** dials, e.g. `http://host.docker.internal:8765` under Docker) is unaffected — it is a distinct FMS-side reach path, not the client companion address, and stays in `automation.json`.
