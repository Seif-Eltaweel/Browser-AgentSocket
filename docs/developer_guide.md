# 🛠️ Advanced Developer & Builder Reference: AgentSocket-Browser

This document provides a comprehensive technical reference for engineers building agent systems, orchestration runtimes, and specialized browser tools on top of **AgentSocket-Browser**.

---

## 1. REST API Specification

The FastAPI gateway listens on `http://127.0.0.1:8000` (or `AGENTSOCKET_PORT`).

### 1.1 `GET /status`
Returns real-time gateway health, browser connection state, active session, and operator takeover status.

#### Response Envelope:
```json
{
  "status": "online",
  "extension_connected": true,
  "human_in_control": false,
  "active_session": {
    "session_id": "sess_20260821_143000_101",
    "tab_group_id": 101,
    "tab_group_name": "LinkedIn Scraper",
    "tab_group_color": "purple",
    "started_at": "2026-08-21T14:30:00.000Z",
    "actions_count": 4,
    "takeover_count": 0
  }
}
```

---

### 1.2 `POST /execute`
Executes an automation action in the active browser session tab.

#### Request Body (`ActionPayloadModel`):
```json
{
  "id": "act_1724240000000",
  "action_type": "navigate",
  "target_data": "https://news.ycombinator.com",
  "requires_privacy_check": false,
  "session_title": "HackerNews Digest"
}
```

* `action_type`: `"navigate"` | `"execute_js"`
* `target_data`: URL string (for navigate) or JavaScript expression string (for execute_js).
* `requires_privacy_check`: `true` to immediately trigger human operator takeover.
* `session_title`: Optional human-readable tab group label.

#### Success Response:
```json
{
  "status": "success",
  "id": "act_1724240000000",
  "data": {
    "output": "Hacker News",
    "duration_ms": 42.5
  }
}
```

#### Sensitive Scope Abort Response:
```json
{
  "status": "human_intervention_required",
  "message": "[SECURITY ABORT] Outbound requests locked. sensitive keywords detected: password, login",
  "human_in_control": true
}
```

---

### 1.3 `POST /release_takeover`
Called by the human operator or AI agent to release the manual lockout, resume the Viewport Shield, and pass context notes.

#### Request Body:
```json
{
  "notes": "Completed 2-factor authentication via SMS code."
}
```

#### Response:
```json
{
  "status": "released",
  "message": "Human operator handed control back to agent.",
  "notes": "Completed 2-factor authentication via SMS code."
}
```

---

### 1.4 `POST /stop`
Immediately aborts any active agent task, releases CDP debuggers, and unlocks the user viewport.

---

### 1.5 `GET /history`
Queries the chronological session index (`server/logs/sessions/history_logs/index.json`).

#### Query Parameters:
* `query_hint` *(string, optional)*: Filter by tab group name or session title.
* `limit` *(int, default=10)*: Number of summaries to return.

---

### 1.6 `GET /subskills`
Lists all registered playbooks in the central registry (`server/logs/subskills_index.json`).

---

## 2. WebSocket Protocol (`/ws/extension`)

The Chrome Extension connects to `ws://127.0.0.1:8000/ws/extension`.

### 2.1 Connection Lifecycle
* **Heartbeat**: 24-second chrome alarm ping-pong prevents MV3 Service Worker dormancy.
* **Reconnection**: Exponential backoff with jitter (`min=1s`, `max=16s`).

### 2.2 Inbound Message Types (Extension -> Server)
```json
{
  "type": "RESPONSE",
  "id": "act_1724240000000",
  "status": "success",
  "data": { "output": "..." }
}
```

### 2.3 Outbound Message Types (Server -> Extension)
```json
{
  "type": "ACTION",
  "action_type": "execute_js",
  "id": "act_1724240000000",
  "target_data": "document.title",
  "session_title": "My Task"
}
```

---

## 3. Chrome DevTools Protocol (CDP) Execution Mechanics

AgentSocket evaluates JavaScript directly via Chrome DevTools Protocol (`chrome.debugger`) using the `Runtime.evaluate` domain method:

```javascript
chrome.debugger.sendCommand(
  { tabId: activeTabId },
  "Runtime.evaluate",
  {
    expression: jsCode,
    returnByValue: true,
    awaitPromise: true,
    userGesture: true
  },
  (result) => {
    // Returns value directly bypassing CSP
  }
);
```

### Benefits of CDP Evaluation:
* **CSP Bypassing**: Pages with strict `script-src` policies cannot block execution.
* **Cross-Frame Access**: Can inspect iframes with explicit target IDs.
* **Native Promises**: Automatically awaits top-level asynchronous promises.

---

## 4. Shadow DOM HUD Architecture

All on-page UI components (viewport shield, status pill, takeover modal) are encapsulated in an isolated Shadow Root:

```javascript
// content.js
const host = document.createElement('agentsocket-hud-host');
document.documentElement.appendChild(host);
const shadow = host.attachShadow({ mode: 'open' });

// Inject scoped CSS and markup
shadow.innerHTML = `
  <style>
    :host { all: initial !important; }
    .hud-pill { background: #191919; color: #fff; font-family: sans-serif; ... }
    .viewport-shield { position: fixed; inset: 0; z-index: 2147483646; }
  </style>
  <div class="viewport-shield"></div>
  <div class="hud-pill">...</div>
`;
```

This guarantees that host page styles (Tailwind, Bootstrap, style resets) never affect the AgentSocket interface.
