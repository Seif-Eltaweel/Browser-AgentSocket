# AgentSocket-Browser 🔌⚡

**Autonomous Multi-Agent Browser Automation Gateway, FastMCP Server & Chrome MV3 Extension Bridge.**

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Chrome MV3](https://img.shields.io/badge/Chrome-Manifest%20V3-orange.svg)](extension/manifest.json)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP%20Ready-purple.svg)](server/socket_mcp.py)
[![Docker Support](https://img.shields.io/badge/Docker-Ready%20%28Xvfb%29-blue.svg)](Dockerfile)
[![Test Suite](https://img.shields.io/badge/tests-44%2F44%20passing-brightgreen.svg)](tests/)

AgentSocket-Browser is a secure, human-in-the-loop browser automation bridge that connects autonomous AI agents (such as **Claude Code**, **Antigravity**, **Cursor**, **Windsurf**, or custom Python agents) directly to your active browser session. Operating through native **Model Context Protocol (MCP)** and WebSocket streams, it pairs zero-friction on-demand startup (`plug`) with strict safety guardrails, **Shadow DOM-isolated HUD**, viewport interaction shielding, tab group session isolation, and seamless human-agent takeover workflows.

---

## 🧭 Documentation & Quick Links

| Document | Purpose |
|:---|:---|
| 📖 [**Installation Guide (`INSTALL.md`)**](INSTALL.md) | Cross-platform installation, Chrome extension setup, and MCP client config. |
| 🛠️ [**Developer & Builder Guide (`DEVELOPER.md`)**](DEVELOPER.md) | Building custom automation runners, REST/WebSocket APIs, and MCP extension. |
| 🤝 [**Contributing Guide (`CONTRIBUTING.md`)**](CONTRIBUTING.md) | 5 Architectural Invariants, Git conventions, code quality, and PR standards. |
| 🛡️ [**Security Policy (`SECURITY.md`)**](SECURITY.md) | Zero-credential storage invariants, sensitive keyword filters, and reporting. |
| 📖 [**Subskills Playbook Guide (`docs/subskills_playbook_guide.md`)**](docs/subskills_playbook_guide.md) | Authoring high-accuracy `sub_skill.md` playbooks, selector contracts & schemas. |
| 🌐 [**Extended Multi-OS & Docker Guide (`docs/installation.md`)**](docs/installation.md) | Deep guide covering Brave, Edge, Docker headless runtimes & enterprise VPNs. |
| 📚 [**Master Codebase Spec (`docs/codebase_master_specification.md`)**](docs/codebase_master_specification.md) | Complete engineering reference covering Specifications 00 through 14. |

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────┐
│             AI Agent (Claude Code / Antigravity / IDE) │
└────────────────────────────────────────────────────────┘
          │ (MCP stdio or CLI launcher /browser-socket)
          ▼
┌────────────────────────────────────────────────────────┐
│  AgentSocket Launcher & FastMCP Server (socket_mcp.py) │
│  - Port 8000 health check & auto-plugging gateway      │
│  - Auto-launches Chrome with --load-extension if down  │
│  - 20-minute Keepalive / Auto-Idle Watchdog            │
└────────────────────────────────────────────────────────┘
          │ (HTTP / WebSocket)
          ▼
┌───────────────────────────┐      WebSocket (Resilient)      ┌───────────────────────────┐
│ FastAPI Gateway (Port 8000)│ ◄────────────────────────────► │ Chrome Extension (MV3)    │
│ (socket_server.py)        │ (Backoff + Jitter + Heartbeat) │ (background.js / alarms)  │
└───────────────────────────┘                                └───────────────────────────┘
                                                                           │ (CDP / Shadow Root)
                                                                           ▼
                                                               ┌───────────────────────────┐
                                                               │ Active Tab in Group       │
                                                               │ [<agentsocket-hud-host>]  │
                                                               │ [Shadow DOM HUD + Shield] │
                                                               └───────────────────────────┘
```

The system is organized into three coordinated layers:
1. **MCP Server & Smart Launcher (`server/socket_mcp.py` & `server/socket_launcher.py`)**: Zero-friction bootstrapper exposing 11 FastMCP tools and auto-plugging services on demand.
2. **FastAPI Gateway Server (`server/socket_server.py` & `server/session_manager.py`)**: Orchestrates agent requests with strict Pydantic schemas, sensitive keyword safety triggers, non-blocking lock states, hierarchical session logging, and auto-idle lifecycle management.
3. **Chrome Extension (`extension/`)**: A Manifest V3 extension linking to the gateway over resilient WebSockets to execute CDP scripts, manage colored tab groups, project the Shadow DOM Notion Dark Mode HUD, and control the viewport interaction shield.

---

## 🌟 Core Features & Capabilities

### 1. ⚡ Zero-Friction FastMCP Server & Smart Launcher (`plug`)
* **11 Native MCP Tools**: Out-of-the-box tools for execution, health queries, human handoffs, history indexing, and subskill borrowing.
* **On-Demand Auto-Boot (`plug`)**: Automatically spins up the FastAPI gateway and launches Google Chrome with the unpacked extension if either is offline.
* **20-Minute Auto-Idle Watchdog**: Server cleanly terminates after 20 minutes of inactivity to prevent background CPU/RAM waste.
* **Stale PID Auto-Cleanup**: Automatically cleans stale `.socket_server.pid` files upon fresh boot.

### 2. 🗂️ Dynamic Tab Grouping & Session Reuse
* **Visual Group Isolation**: Each agent session is assigned its own colored Chrome Tab Group (e.g. *Purple*, *Blue*, *Green*).
* **Anti-Proliferation Tab Reuse**: Automatically reuses active tabs within the assigned task group instead of cluttering your window with dozens of runaway tabs.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Tabs: [ 🟣 LinkedIn Session: Active Tab | ✕ ]  [ Plain User Tab ]     │
├────────────────────────────────────────────────────────────────────────┤
│  Browser Viewport                                                      │
│                                                                        │
│                       [ 🔌 Session is active ]                         │
│                       [ ✋ Take Over ] [ ⏹ Stop ]                       │
└────────────────────────────────────────────────────────────────────────┘
```

### 3. 🛡️ Viewport Interaction Shield & Accidental Input Lockout
* **Input Interception**: When an agent is actively executing, an invisible overlay shield intercepts webpage clicks, typing, and drag-and-drop to prevent the human from accidentally disturbing active form-filling or CDP operations.
* **Feedback Tooltip**: Clicking anywhere on the shielded page displays a helpful HUD cue (*"Agent is operating. Click 'Take Over' below to interact"*).

### 4. 🎨 Shadow DOM Encapsulation & Notion Dark Mode HUD
* **100% CSS Isolation**: All on-page UI elements (floating pill, interaction shield, glowing frame, and handoff modal) are rendered inside an open **Shadow Root** on `<agentsocket-hud-host>`. Host page styles (Tailwind, Bootstrap, resets) can never break the HUD.
* **Notion Dark Mode Aesthetic**: Curated dark theme palette (`#191919`, `#202020`, `#2e2e2e`), compact pill dimensions, and crisp status badges.
* **Keyboard Guard with `composedPath()`**: Blocks host page keystrokes during agent execution while preserving fluid typing inside the handoff modal.

### 5. ✋ 1-Click Human Takeover & Pinned Handoff Modal
* **Instant Pause**: Drops the interaction shield immediately, allowing you to solve 2FA, Captchas, or complex forms.
* **Context-Enriched Handoff**: When clicking *Release to Agent*, a modal captures your handoff notes (e.g., *"Logged in via Authenticator app"*) and injects them directly into the agent's next execution cycle.

```
                  ┌──────────────────────────────┐
                  │   Agent Operating (Active)   │
                  │   - Viewport Shield ON       │
                  │   - Bottom HUD: [Take Over]  │
                  └──────────────┬───────────────┘
                                 │
                     User clicks │ "Take Over" or
                     Privacy     │ Keyword Auto-Abort
                                 ▼
                  ┌──────────────────────────────┐
                  │  Operator in Control (Lock)  │
                  │  - Viewport Shield OFF       │
                  │  - Bottom HUD: [Release]     │
                  └──────────────┬───────────────┘
                                 │
                     User clicks │ "Release to Agent"
                     & enters    │ Handoff Notes
                                 ▼
                  ┌──────────────────────────────┐
                  │    Agent Resumes Context     │
                  │    - Injected notes loaded   │
                  │    - Viewport Shield ON      │
                  └──────────────────────────────┘
```

### 6. 📦 100% Session Isolation & Reusable Subskills Playbooks
Every session writes to its own isolated directory with inputs, deliverables, diagnostic scripts, artifacts, and playbooks:

```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Auto-generated executive report of run
├── session.jsonl           # Complete line-delimited event telemetry
├── sub_skill.md            # Reusable playbook rules, selectors & anti-bot SLA
├── input/                  # Input targets, CSVs, parameter lists
├── output/                 # Deliverables, structured JSON, scraped CSVs
├── adhocs/                 # Ad-hoc Python scripts and one-off scrapers
└── artifacts/              # Screenshots and large offloaded payloads (>10KB)
```

---

## ⚡ Quickstart

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Seif-Eltaweel/agentsocket-browser.git
cd agentsocket-browser

# Setup virtual environment
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1 | macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Load Chrome Extension
1. Open Chrome and go to `chrome://extensions`.
2. Toggle **Developer mode** to **ON** (top right).
3. Click **Load unpacked** (top left) and select the `extension/` folder in this repo.

### 3. Verify with Smoke Test
```bash
# 1. Boot gateway and verify connection
python server/socket_launcher.py plug

# 2. Test navigation
python server/socket_launcher.py navigate "https://example.com"

# 3. Test CDP JavaScript evaluation
python server/socket_launcher.py eval "document.title"
```

---

## ⚙️ MCP Agent Configuration

Add AgentSocket-Browser to your AI agent's configuration:

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "agentsocket": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/agentsocket-browser/server/socket_mcp.py"]
    }
  }
}
```

### Claude Code CLI
```bash
claude mcp add agentsocket python /absolute/path/to/agentsocket-browser/server/socket_mcp.py
```

### Google Antigravity / Gemini CLI (`mcp_config.json`)
```json
{
  "mcpServers": {
    "agentsocket": {
      "command": "python",
      "args": ["/absolute/path/to/agentsocket-browser/server/socket_mcp.py"]
    }
  }
}
```

### Cursor / Windsurf IDE
Add a new MCP server in **Settings -> MCP**:
* **Name:** `agentsocket`
* **Type:** `command`
* **Command:** `python /absolute/path/to/agentsocket-browser/server/socket_mcp.py`

---

## 🛠️ Complete MCP Tools Reference

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `socket_execute` | `action_type`, `target_data`, `session_title`, `requires_privacy_check` | Auto-boots gateway/browser and executes navigation or JS evaluation via CDP. |
| `socket_status` | *none* | Queries gateway health, extension WebSocket link, human lockout state, and idle timeout. |
| `socket_release_takeover` | `notes` | Releases human operator lockout and passes handoff context notes back to the agent. |
| `socket_stop` | *none* | Immediately halts active browser tasks and resets execution state. |
| `socket_query_history` | `query_hint`, `month`, `limit` | Searches the master session index (`index.json`) for past session cards by keywords. |
| `socket_get_session_details` | `session_path` | Reconstructs the full chronological step timeline from `session.jsonl`. |
| `socket_get_session_artifact` | `session_path`, `artifact_name` | Reads offloaded heavy JSON payloads or screenshot files from `artifacts/`. |
| `socket_get_session_document` | `session_path` | Generates or retrieves the consolidated `SESSION_DOCUMENT.md` report. |
| `socket_list_subskills` | `query_hint`, `tags` | Lists registered subskills with tags, borrow counts, and latest session references. |
| `socket_get_subskill` | `name` | Retrieves detailed subskill contract (`sub_skill.md`) and adhoc tool references. |
| `socket_borrow_subskill` | `name`, `session_title`, `input_file_path` | Clones subskill playbook and tools into a new session folder with input files. |
| `socket_register_subskill` | `session_path`, `name`, `display_title`, `description`, `tags` | Registers a completed session folder as a reusable subskill playbook. |

---

## 💻 CLI Command Reference

```bash
# Gateway status & auto-boot
python server/socket_launcher.py status
python server/socket_launcher.py plug

# Browser Actions
python server/socket_launcher.py navigate "https://news.ycombinator.com" --title "HackerNews"
python server/socket_launcher.py eval "document.title" --title "HackerNews"

# Human In The Loop Controls
python server/socket_launcher.py release --notes "Logged in via 2FA"
python server/socket_launcher.py stop
python server/socket_launcher.py kill

# Session History & Document Reports
python server/socket_launcher.py history --month 2026-08
python server/socket_launcher.py logs --path server/logs/2026-08-21/My_Session_Folder
python server/socket_launcher.py doc --path server/logs/2026-08-21/My_Session_Folder
python server/socket_launcher.py export-all --out ./ALL_SESSIONS_TIMELINE.md

# 📦 Subskills Management
python server/socket_launcher.py subskills list
python server/socket_launcher.py subskills show linkedin-crm-enricher
python server/socket_launcher.py subskills register --session server/logs/2026-08-21/My_Session --name my-scraper --title "My Scraper" --tags "data,scraping"
python server/socket_launcher.py subskills borrow linkedin-crm-enricher --title "Batch 2" --input ./targets.csv
```

---

## 🐳 Optional Docker Deployment

For headless cloud VMs (AWS EC2, GCP, DigitalOcean) and CI/CD pipelines:

```bash
# Start container with Xvfb virtual display on port 8000
docker compose up -d

# View live logs
docker compose logs -f
```

---

## 🧪 Test Suite

Run the full automated test suite before opening a Pull Request:

```bash
# 1. Run Python Unit & Integration Tests (44+ tests)
python -m unittest discover tests -v

# 2. Run JavaScript Protocol Tests
node tests/test_protocol.test.js
```

---

## 🛡️ Security & Privacy Guardrails

1. **Zero Credential Persistence**: AgentSocket **never** writes passwords, payment data, or session cookies to disk.
2. **Sensitive Keyword Protection**: Keywords like `password`, `bank`, `payment`, `stripe`, and `cvv` trigger an immediate `[SECURITY ABORT]`, dropping the Viewport Shield and handing control to the human operator.
3. **Loopback-Only Binding**: Default gateway binds exclusively to `127.0.0.1:8000`.

---

## 📄 License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

Copyright © 2026 Seif Eltaweel and AgentSocket-Browser Contributors.
