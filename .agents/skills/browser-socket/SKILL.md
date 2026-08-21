---
name: browser-socket
description: Interact with the AgentSocket browser automation gateway, socket server, and extension bridge.
risk: safe
source: local
license: MIT
date_added: "2026-08-19"
---

# AgentSocket (browser-socket) 🔌⚡

AgentSocket is a plug-and-play browser automation gateway and Model Context Protocol (MCP) server that links AI agents directly to local browser sessions through a high-speed FastAPI WebSocket socket strip. It features zero-friction on-demand initiation (`plug`), automated tab group isolation, CDP execution, and security-first human-agent takeover workflows.

---

## ⚡ Zero-Friction Initiation & MCP Integration

AgentSocket supports native Model Context Protocol (MCP) and an automated Smart Launcher.

### 1. MCP Configuration
Add AgentSocket to your client's MCP configuration (`claude_desktop_config.json`, `mcp_config.json`, or IDE settings):

```json
{
  "mcpServers": {
    "browser-socket": {
      "command": "python",
      "args": ["c:/Users/20106/agent_bro_hands/server/socket_mcp.py"]
    }
  }
}
```

### 2. Available MCP Tools
* `socket_execute`: Ensures gateway socket and browser extension are plugged in (auto-booting if necessary), then executes a browser action (`navigate` or `execute_js`).
* `socket_status`: Checks gateway state, extension connection status, human lockout state, and handoff notes.
* `socket_release_takeover`: Releases the human operator intervention lockout with optional handoff notes.
* `socket_stop`: Immediately cancels running tasks and resets socket state.
* `socket_query_history`: Searches master session index (`index.json`) for past sessions by keyword/month.
* `socket_get_session_details`: Lazy retrieves full chronological step timelines and latencies from `session.jsonl`.
* `socket_get_session_artifact`: Reads specific offloaded heavy payloads or error screenshots.
* `socket_get_session_document`: Retrieves or generates the comprehensive consolidated Markdown document (`SESSION_DOCUMENT.md`) for any session.
* `socket_list_subskills`: Lists registered, reusable tested subskills with usage counts and tags from `subskills_index.json`.
* `socket_get_subskill`: Retrieves subskill metadata, full playbook rules (`sub_skill.md`), and available adhoc scripts.
* `socket_borrow_subskill`: Clones a subskill's playbook and adhoc scripts into the active session workspace (`adhocs/` and `input/`), logging a `subskill_borrowed` event.
* `socket_register_subskill`: Packages a completed session as a reusable subskill in the central registry.

---

## 💻 CLI Usage (`/browser-socket`)

You can also interact with AgentSocket directly via the CLI launcher:

```bash
# Check socket status
python server/socket_launcher.py status

# Plug in: Ensure gateway & browser are booted and ready
python server/socket_launcher.py plug

# Navigate to a URL
python server/socket_launcher.py navigate "https://example.com"

# Execute JavaScript in active tab
python server/socket_launcher.py eval "document.title"

# Release human lockout after manual action
python server/socket_launcher.py release --notes "Logged in successfully"

# Stop active tasks (unplug task)
python server/socket_launcher.py stop

# Terminate gateway server background process
python server/socket_launcher.py kill

# List past sessions history
python server/socket_launcher.py history --month 2026-08

# View chronological step timeline from session.jsonl
python server/socket_launcher.py logs --path server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101

# View or regenerate consolidated session document (SESSION_DOCUMENT.md)
python server/socket_launcher.py doc --path server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101

# Export unified master timeline report to Markdown
python server/socket_launcher.py export-all --out ./ALL_SESSIONS_TIMELINE.md

# 📦 Subskills & Borrowing Engine
# List available subskills
python server/socket_launcher.py subskills list

# View detailed subskill playbook & adhoc tools
python server/socket_launcher.py subskills show linkedin-crm-enricher

# Borrow subskill into a new session with input dataset
python server/socket_launcher.py subskills borrow linkedin-crm-enricher --title "Batch 4 Enrichment" --input ./new_batch.csv

# Register a session as a reusable subskill
python server/socket_launcher.py subskills register --session server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101 --name linkedin-crm-enricher --title "LinkedIn CRM Profile Enricher" --tags "linkedin,crm,enrichment"
```

*Note: `python server/browser_socket.py <command>` can also be used as a direct shorthand alias.*

---

## 📁 Session Isolation Hierarchy & Full Documents

Every session produces a standalone, isolated directory containing everything needed to inspect, reproduce, or borrow the session's work:

```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Consolidated full report with executive summary & thread
├── session.jsonl           # Append-only chronological event log stream
├── sub_skill.md            # Reusable playbook contract with selectors & rules
├── input/                  # Input datasets & source batch CSVs
├── output/                 # Deliverables, scraped datasets, enriched CSVs
├── adhocs/                 # Diagnostic probes, scripts, and helper engines
└── artifacts/              # Screenshots & offloaded JSON payloads
```


---

## 📡 REST API Endpoints & Interaction Patterns

The local Gateway Server runs at `http://127.0.0.1:8000`.

### 1. Check Connection Status
```bash
curl http://127.0.0.1:8000/status
```

Expected Response:
```json
{
  "status": "AgentSocket Server is Live",
  "extension_connected": true,
  "human_in_control": false,
  "last_intervention_notes": null,
  "idle_seconds_remaining": 1200.0
}
```

---

### 2. Execute Action on Browser
Send a command to the browser tab using `POST /execute`:

```bash
curl -X POST http://127.0.0.1:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "id": "unique-command-id",
    "action_type": "navigate",
    "target_data": "https://example.com",
    "requires_privacy_check": false,
    "session_title": "Example Session",
    "group_color": "purple"
  }'
```

#### Fields:
* `id` (string): A unique UUID or identifier for the action.
* `action_type` (string): `navigate` | `execute_js` | `task_complete`.
* `target_data` (string): The URL to navigate to, or the JavaScript code string to run.
* `requires_privacy_check` (boolean): Set to `true` to force a human takeover check immediately.
* `session_title` (string, optional): Title of the automation tab group.
* `group_color` (string, optional): UI group color indicator (e.g. `purple`, `blue`, `green`, `red`).

---

### 3. Subskills Endpoints
* `GET /subskills`: List registered subskills (supports `?query=` and `?tags=`).
* `GET /subskills/{name}`: Get detailed playbook and tools for subskill `name`.
* `POST /subskills/borrow`: Borrow playbook and adhocs into an active session.
* `POST /subskills/register`: Register session folder as a named subskill.
* `GET /session/document`: Retrieve or regenerate `SESSION_DOCUMENT.md` for a session path.

---

## 🛡️ Takeover & Handoff Workflow

When you request an action that is sensitive (e.g. login, payment) or set `requires_privacy_check: true`, the gateway automatically shifts state to **Human Takeover Mode**.

### Step A: Catch the Abort
The server will respond with:
```json
{
  "status": "security_abort",
  "message": "Sensitive scope detected. Outbound requests locked. Human intervention required. Reason: sensitive keywords detected"
}
```
**Action**: Immediately stop calling the API. Inform the user that the action is sensitive, and you are waiting for them to complete the step manually in their browser and click "Release Control".

### Step B: Adapt to Handoff Context
When the human completes the action and clicks "Release", your next call to `/execute` (or checking `/status`) will return:
```json
{
  "status": "resumed_context",
  "message": "[HUMAN INTERVENTION OVERRIDE LOG]: <notes entered by the user>",
  "instructions": "Human operator handoff caught. Adapt steps using log data."
}
```
**Action**: Read the message payload, adapt your remaining steps based on what the user completed, and continue your task execution loop.

