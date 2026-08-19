---
name: bro-hands
description: Interact with the Agent Bro Hands browser automation gateway and extension system.
risk: safe
source: local
license: MIT
date_added: "2026-07-07"
---

# Agent Bro Hands (bro-hands) 🤖🖐️

Agent Bro Hands is a browser automation gateway and Model Context Protocol (MCP) server that links AI agents to a local browser session through a FastAPI WebSocket bridge. It supports zero-friction on-demand initiation, automated navigation, JavaScript execution, and security-first human takeover workflows.

---

## ⚡ Zero-Friction Initiation & MCP Integration

Agent Bro Hands supports native Model Context Protocol (MCP) and an automated Smart Launcher.

### 1. MCP Configuration
Add Agent Bro Hands to your client's MCP configuration (`claude_desktop_config.json`, `mcp_config.json`, or IDE settings):

```json
{
  "mcpServers": {
    "bro-hands": {
      "command": "python",
      "args": ["c:/Users/20106/agent_bro_hands/server/bro_mcp.py"]
    }
  }
}
```

### 2. Available MCP Tools
* `bro_execute`: Ensures server and browser extension are alive (auto-booting if necessary), then executes a browser action (`navigate` or `execute_js`).
* `bro_status`: Checks gateway state, extension connection status, human lockout state, and handoff notes.
* `bro_release_takeover`: Releases the human operator intervention lockout with optional handoff notes.
* `bro_stop`: Immediately cancels running tasks and resets state.

---

## 💻 CLI Usage

You can also interact with Agent Bro Hands directly via the CLI launcher:

```bash
# Check status
python server/bro_launcher.py status

# Ensure gateway & browser are booted
python server/bro_launcher.py start

# Navigate to a URL
python server/bro_launcher.py navigate "https://example.com"

# Execute JavaScript in active tab
python server/bro_launcher.py eval "document.title"

# Release human lockout after manual action
python server/bro_launcher.py release --notes "Logged in successfully"

# Stop active tasks
python server/bro_launcher.py stop

# Terminate gateway server background process
python server/bro_launcher.py kill
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
  "status": "Agent Bro Hands Server is Live",
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
* `session_title` (string, optional): Title of the automation group.
* `group_color` (string, optional): UI group color indicator (e.g. `purple`, `blue`, `green`, `red`).

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
