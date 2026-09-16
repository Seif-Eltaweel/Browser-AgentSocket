---
name: browser-socket
description: Interact with the AgentSocket browser automation gateway, socket server, and extension bridge.
risk: safe
source: local
license: MIT
date_added: "2026-08-19"
---

# AgentSocket (browser-socket) 🔌⚡

AgentSocket is a high-speed, plug-and-play browser automation gateway and Model Context Protocol (MCP) server that links AI agents directly to local browser sessions through a WebSocket bridge. It empowers external models to drive web browsers using the **Observe-Orient-Decide-Act (OODA)** loop, ephemeral numeric ARIA badging, adaptive settlement debouncing, automated tab group isolation, and security-first human-agent takeover workflows.

---

## 🔄 Model-Driven Operational Paradigm: The OODA Execution Loop

External AI agents operating AgentSocket MUST drive browser workflows through continuous, adaptive **Observe-Orient-Decide-Act (OODA)** cycles rather than rigid, pre-scripted automation procedures.

```
       ┌────────────────────────┐
       │   1. OBSERVE           │
       │   browser_observe()    │
       │   (ARIA tree + [1]..N) │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │   2. ORIENT            │
       │   Analyze hierarchy &  │
       │   identify element ID  │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │   3. DECIDE            │
       │   Select atomic action │
       │   (click/type/scroll)  │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │   4. ACT               │
       │   Dispatch tool & wait │
       │   adaptive settlement  │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │   5. REPEAT OR CONCLUDE│
       │   Goal met?            │
       │   Yes ──► task_complete│
       │   No  ──► (Repeat OODA)│
       └────────────────────────┘
```

### The 5 OODA Phases:

1. **Observe**: Always begin by calling `browser_observe()`. Review the structured ARIA tree (`tree_text`) and identified ephemeral numeric badges (`[1]..[N]`). Never guess CSS selectors, element positions, or assume DOM structures.
2. **Orient**: Locate the target element badge (`element_id`) that fulfills the immediate micro-goal within the current accessibility hierarchy.
3. **Decide**: Select the single atomic operator required to make progress (`browser_click`, `browser_type`, `browser_scroll`, `browser_key_press`).
4. **Act**: Dispatch the tool call. The extension driver executes native browser events and relies on the adaptive settlement engine to debounce mutations and network activity before returning state.
5. **Repeat or Conclude**: Re-observe the mutated DOM. When the final goal is achieved, verify the UI state (e.g., confirmation banner visible, target data parsed) and conclude by calling `task_complete()`.

---

## 🎯 Condition-Based Termination vs Rigid Step Countdowns

> [!IMPORTANT]
> **Anti-Pattern Warning: No Arbitrary Step Countdowns**
> Never force automation into rigid, pre-committed micro-step countdowns (e.g., "Step 1 of 5", "Progress: 60%"). Real web applications reflow asynchronously, display cookie banners, present rate limits, and load dynamic frames.
> - Terminate based strictly on **verified UI conditions** (e.g. data extracted, form submission confirmed, success alert displayed) using `task_complete(result=..., status="completed")`.
> - Do not pad steps or fail tasks prematurely simply because the interaction took more or fewer micro-actions than anticipated.

### Zero-Plan Direct Mode
For standard or exploratory tasks, models can operate in **Direct Mode**: interact directly via atomic OODA tools without generating boilerplate plan files or disposable helper scripts.

### Milestone Tracking for Complex Multi-Phase Workflows
For complex multi-stage tasks (e.g., authentication check ➔ search ➔ pagination ➔ data export), use `browser_set_milestone()` to keep the HUD badge and intent ticker updated without imposing artificial step limits:

```python
# Example: Communicate strategic phases to the user and HUD
browser_set_milestone(milestone_title="Searching product catalog", phase_number=1, total_phases=3)
# ... perform atomic OODA actions ...
browser_set_milestone(milestone_title="Extracting structured table data", phase_number=2, total_phases=3)
# ... perform atomic OODA actions ...
browser_set_milestone(milestone_title="Exporting final deliverables", phase_number=3, total_phases=3)
# ... verify final deliverables ...
task_complete(result="Extracted 42 product records successfully.", status="completed")
```

---

## 🔒 Strict Vision Privacy Boundaries & Credential Protection

AgentSocket enforces strict ethical and privacy boundaries to safeguard user secrets, authentication tokens, and private data.

> [!CAUTION]
> **Strictly Forbidden Screenshot Contexts (NEVER CAPTURE)**:
> - **Password or authentication input fields**: Login forms, master password prompts, OAuth consent screens.
> - **Credit card, payment, CVV, or banking pages**: Checkout gateways, bank statements, routing numbers, cryptocurrency wallets.
> - **Private personal profile settings or photo galleries**: Account settings, medical portal records, private messages/inboxes.
> - **Identity verification, KYC, or passport upload forms**: Government IDs, SSN/tax IDs, driver's licenses.

> [!TIP]
> **Permitted Screenshot Contexts**:
> - Public product, rental, or e-commerce listings.
> - Verifying general page layout when ARIA tree is ambiguous and user vision consent is granted.
> - Confirming a public search results table or analytics dashboard.

### Privacy Guard Operational Rules:
1. **Vision Permission Gate**: `browser_screenshot()` and `take_screenshot=True` in `browser_observe()` strictly require that the user granted vision permissions (`enable_vision: True`) during the extension consent handshake. If permission is denied, screenshots are blocked.
2. **Zero Credential Handling**: AI agents must NEVER type, extract, or log raw passwords, credit cards, or two-factor security codes.
3. **Yield to Human Takeover**: When an authentication wall, CAPTCHA, or payment gateway appears:
   - Call `browser_set_milestone("Awaiting Human Authentication")`.
   - Yield execution to the user. The human operator completes the sensitive action securely in the browser and releases control with notes.

---

## ⚡ MCP Configuration & Available Tools

AgentSocket exposes its operator surface via standard Model Context Protocol (MCP).

### MCP Configuration
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

### 1. Atomic Operator Tools (Primary OODA Driver)
* `browser_observe`: Captures ARIA tree, assigns ephemeral numeric badges `[1]..[N]`, and returns structured DOM snapshot.
  * *Parameters*: `tab_group_id?: int`, `take_screenshot?: bool`
* `browser_click`: Native focus and click on target element badge with adaptive settlement.
  * *Parameters*: `element_id: int`, `tab_group_id?: int`, `wait_settle?: bool`
* `browser_type`: Sets element value via prototype setter, dispatches change events, and settles.
  * *Parameters*: `element_id: int`, `text: str`, `tab_group_id?: int`, `clear_first?: bool`, `press_enter?: bool`
* `browser_scroll`: Scrolls viewport smoothly in target direction.
  * *Parameters*: `direction: "down" | "up" | "top" | "bottom"`, `amount?: int`, `tab_group_id?: int`
* `browser_key_press`: Sends native keyboard events (`"Enter"`, `"Escape"`, `"Tab"`, etc.).
  * *Parameters*: `key: str`, `tab_group_id?: int`
* `browser_screenshot`: Captures high-res viewport screenshot (subject to user vision consent).
  * *Parameters*: `tab_group_id?: int`, `filename?: str`
* `task_complete`: Signals task completion, finalizes `SESSION_DOCUMENT.md`, and resets HUD state.
  * *Parameters*: `result?: str`, `status?: "completed" | "failed"`, `tab_group_id?: int`
* `browser_set_milestone`: Updates HUD phase badge and intent ticker for complex workflows.
  * *Parameters*: `milestone_title: str`, `phase_number?: int`, `total_phases?: int`, `tab_group_id?: int`

### 2. Session & Gateway Management Tools
* `socket_status`: Checks gateway state, extension connection status, human lockout state, and handoff notes.
* `socket_release_takeover`: Releases human intervention lockout after manual action, returning operator notes.
* `socket_stop`: Immediately cancels running tasks and resets socket state.
* `socket_query_history`: Searches session history via fast SQLite index by keyword or month.
* `socket_get_session_details`: Lazy retrieves full chronological step timelines and latencies from `session.jsonl`.
* `socket_get_session_artifact`: Reads specific offloaded heavy payloads or error screenshots.
* `socket_get_session_document`: Retrieves or generates the consolidated markdown document (`SESSION_DOCUMENT.md`).

### 3. Subskill SOP Tools (Markdown Playbooks)
* `socket_list_subskills`: Lists registered SOP playbooks with usage counts and tags from dual SQLite/JSON catalog.
* `socket_get_subskill`: Retrieves subskill metadata and full markdown playbook rules (`sub_skill.md`).
* `socket_borrow_subskill`: Clones a subskill playbook into active session workspace (`input/sub_skill.md`).
* `socket_register_subskill`: Packages a completed session as a reusable SOP playbook in the central registry.

### 4. Legacy Script Tools (Deprecated)
* `socket_execute`: Legacy single-shot action dispatcher (`navigate` / `execute_js`). Prefer direct atomic tools.
* `socket_run_adhoc`, `socket_promote_adhoc`, `socket_list_adhocs`: Deprecated in favor of atomic OODA tools and Markdown SOPs.

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

# Execute JavaScript in active tab (diagnostic)
python server/socket_launcher.py eval "document.title"

# Release human lockout after manual action
python server/socket_launcher.py release --notes "Logged in successfully"

# Stop active tasks (unplug task)
python server/socket_launcher.py stop

# Terminate gateway server background process
python server/socket_launcher.py kill

# List past sessions history (SQLite indexed)
python server/socket_launcher.py history --month 2026-08

# View chronological step timeline from session.jsonl
python server/socket_launcher.py logs --path server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101

# View or regenerate consolidated session document (SESSION_DOCUMENT.md)
python server/socket_launcher.py doc --path server/logs/2026-08-21/LinkedIn_CRM_Enricher_08-45_gid101

# Export unified master timeline report to Markdown
python server/socket_launcher.py export-all --out ./ALL_SESSIONS_TIMELINE.md

# 📦 Subskills SOP Catalog
python server/socket_launcher.py subskills list
python server/socket_launcher.py subskills show example-sop
python server/socket_launcher.py subskills borrow example-sop --title "Batch 1 Execution"
```

---

## 📁 Session Isolation Hierarchy & Lean Storage

Every session produces an isolated, zero-waste directory:

```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Consolidated full report with YAML frontmatter & thread
├── session.jsonl           # Append-only lean chronological event stream (masked secrets)
├── sub_skill.md            # Borrowed or registered Markdown SOP playbook
├── input/                  # Input datasets and reference material
└── output/                 # Deliverables, scraped datasets, enriched CSVs
```

All session records are indexed in SQLite (`server/db.py`) for instant query access without directory thrashing.

---

## 🛡️ Takeover & Handoff Workflow

When you request an action that is sensitive (e.g. login, payment) or set `requires_privacy_check: true`, the gateway automatically shifts state to **Human Takeover Mode**.

### Step A: Catch the Security Abort
The server will respond with:
```json
{
  "status": "security_abort",
  "message": "Sensitive scope detected. Outbound requests locked. Human intervention required. Reason: sensitive keywords detected"
}
```
**Action**: Immediately stop automated calls. Inform the user that the action requires human intervention, and wait for the user to complete the step manually and click "Release Control".

### Step B: Adapt to Resumed Context
When the human completes the action and clicks "Release", the next tool call (or `/status` query) will return:
```json
{
  "status": "resumed_context",
  "message": "[HUMAN INTERVENTION OVERRIDE LOG]: <notes entered by the user>",
  "instructions": "Human operator handoff caught. Adapt steps using log data."
}
```
**Action**: Read the operator notes, adjust remaining goals based on the human's actions, and resume the OODA cycle.
