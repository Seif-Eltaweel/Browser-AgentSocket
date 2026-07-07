---
name: bro-hands
description: Interact with the Agent Bro Hands browser automation gateway and extension system.
risk: safe
source: local
license: MIT
date_added: "2026-07-07"
---

# Agent Bro Hands (bro-hands)

Agent Bro Hands is a browser automation gateway that links AI agents to a local browser session through a FastAPI WebSocket bridge. It supports automated navigation, JavaScript execution, and security-first human takeover workflows.

---

## 🛠️ When to Use

Use this skill when:
- The user asks you to interact with their browser or automate a website using their active browser session.
- You need to perform actions like navigation, form submission, clicking, or scraping on a web page via the local browser.
- You encounter security gates (login, captcha, checkout) and need to hand off control to a human and wait for them to release control back to you.

---

## 📡 API Endpoint & Interaction Patterns

The local Gateway Server runs at: `http://127.0.0.1:8000`

### 1. Check Connection Status
Before running actions, check if the gateway is running and the Chrome extension is connected:

```bash
curl http://127.0.0.1:8000/status
```

Expected Response:
```json
{
  "status": "Agent Bro Hands Server is Live",
  "extension_connected": true,
  "human_in_control": false,
  "last_intervention_notes": null
}
```

> [!IMPORTANT]
> If `extension_connected` is `false`, notify the user to start the FastAPI server and ensure their Agent Bro Hands extension is loaded and active.

---

### 2. Execute Action on Browser
Send a command to the browser tab using `POST /execute`.

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
