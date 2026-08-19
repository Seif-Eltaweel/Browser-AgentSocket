# Agent Bro Hands 🤖🖐️

**Multi-agent browser automation operator client, native MCP server, and human-in-the-loop state control hub.**

Agent Bro Hands is a secure, human-in-the-loop web automation bridge that connects autonomous AI agents (such as Antigravity, Claude Code, Cursor, or Hermes) to your actual browser session. Operating through native Model Context Protocol (MCP) and WebSocket gateways, it pairs zero-friction on-demand initiation with strict safety guardrails, viewport interaction shielding, tab group session isolation, and seamless human-agent takeover workflows.

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────┐
│             AI Agent (Antigravity / Claude / Cursor)   │
└────────────────────────────────────────────────────────┘
          │ (MCP stdio or CLI launcher)
          ▼
┌────────────────────────────────────────────────────────┐
│  Bro-Hands Launcher & MCP Server (bro_mcp.py)          │
│  - Checks port 8000 & extension connection             │
│  - Spawns FastAPI Subprocess if not running            │
│  - Spawns Chrome with --load-extension if disconnected │
│  - Maintains 20-min Keepalive / Auto-Idle Watchdog     │
└────────────────────────────────────────────────────────┘
          │ (HTTP / WebSocket)
          ▼
┌───────────────────────────┐      WebSocket      ┌───────────────────────────┐
│ FastAPI Gateway (Port 8000)│ ◄────────────────► │ Chrome Extension (MV3)    │
│ (bro_server.py)           │                     │ (Background / Content)    │
└───────────────────────────┘                     └───────────────────────────┘
                                                            │ (CDP / DOM)
                                                            ▼
                                                  ┌───────────────────────────┐
                                                  │ Active Tab in Group       │
                                                  │ [Shield + Floating HUD]   │
                                                  └───────────────────────────┘
```

The system comprises three coordinated subsystems:
1. **MCP Server & Smart Launcher (`server/bro_mcp.py` & `server/bro_launcher.py`)**: Zero-friction bootstrapper exposing standard MCP tools and automatically launching backend services on demand.
2. **FastAPI Gateway Server (`server/bro_server.py`)**: Orchestrates agent requests, enforces sensitive keyword privacy triggers, manages non-blocking lock states, and handles auto-idle lifecycle management.
3. **Chrome Extension (`/extension`)**: A Manifest V3 extension linking to the gateway over WebSockets to execute CDP scripts, manage colored tab groups, project the floating HUD, and control the viewport interaction shield.

---

## 🌟 Core Features & Capabilities

### 1. ⚡ Zero-Friction MCP Server & Smart Launcher
* **Native MCP Tools**: Directly provides `bro_execute`, `bro_status`, `bro_release_takeover`, and `bro_stop` to any MCP client.
* **On-Demand Auto-Boot**: Automatically spins up the FastAPI gateway and launches Google Chrome with the unpacked extension if either is offline.
* **Auto-Idle Watchdog**: Background server cleanly terminates after **20 minutes of inactivity** to prevent runaway CPU or RAM consumption.

### 2. 🗂️ Dynamic Tab Grouping & Session Reuse
* **Visual Isolation**: Each agent session is assigned its own colored Chrome Tab Group (e.g. *Purple*, *Blue*, *Green*).
* **Anti-Proliferation Tab Reuse**: Rather than opening dozens of runaway tabs, the engine automatically reuses active tabs within the assigned task group.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Tabs: [ 🟣 LinkedIn Session: Active Tab | ✕ ]  [ Plain User Tab ]     │
├────────────────────────────────────────────────────────────────────────┤
│  Browser Viewport                                                      │
│                                                                        │
│                       [ 🤖 Session is active ]                         │
│                       [ ✋ Take Over ] [ ⏹ Stop ]                       │
└────────────────────────────────────────────────────────────────────────┘
```

### 3. 🛡️ Viewport Interaction Shield & Accidental Input Lockout
* **Input Interception**: When an agent is actively running, an invisible overlay shield locks webpage clicks, typing, and drag-and-drop to prevent the human from accidentally disturbing active form-filling or CDP executions.
* **Feedback Tooltip**: Clicking anywhere on the shielded page shows a helpful HUD cue (*"Agent is operating. Click 'Take Over' below to interact"*).

### 4. ✋ Human Takeover & Pinned Handoff Modal
* **1-Click Takeover**: Instantly drops the interaction shield and pauses the agent, giving you full control of the browser tab.
* **Pinned Takeover HUD**: The bottom bar updates to **`🔒 Operator Takeover Active`** with **`▶ Release to Agent`** and stays pinned until you are ready.
* **Context-Enriched Handoff**: When clicking *Release to Agent*, a modal captures your notes (e.g., *"Completed 2FA login"*) and injects them directly into the agent's next execution cycle.

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

### 5. 🔍 Chrome DevTools Protocol (CDP) Execution Engine
* **Direct CDP Evaluation**: JavaScript runs directly via Chrome's `Runtime.evaluate` protocol for maximum speed and fidelity.
* **Safe Attach / Detach**: The debugger automatically hooks during execution and cleanly detaches upon completion, with robust error descriptions for runtime exceptions.

---

## ⚠️ "Be Cautious With" — Operational & Safety Guidelines

> [!IMPORTANT]
> Because Agent Bro Hands interacts directly with your **real browser session**, please keep the following critical operational notes in mind:

1. **Live Browser Profile & Authenticated State**:
   * Automation runs in your actual browser window with your real cookies and login sessions. Submitting forms, deleting content, or sending messages takes effect in real life. Always verify agent tasks before executing destructive scripts.
2. **Sensitive Credentials & Payment Data**:
   * Never hardcode plain-text passwords or credit card numbers into automation prompts. Bro Hands includes an automatic keyword safety filter (`password`, `cvv`, `bank`, `payment`, `login`), which intentionally pauses execution and requests a human takeover when detected.
3. **Chrome CDP Debugger Banner**:
   * While the agent evaluates JavaScript, Chrome will show its native top banner:  
     `"Agent Bro Hands started debugging this browser" [ Cancel ] [ ✕ ]`.
   * > [!NOTE]
     > **Why this appears & what to do**: This is a standard Chrome security notice indicating that an extension is using Chrome DevTools Protocol. **Do not click "Cancel" or "✕"** while an action is running, as force-detaching the debugger mid-execution will cause the active agent command to abort. The extension will cleanly detach automatically once execution finishes.
4. **Tab Group Boundary**:
   * The agent only controls tabs inside its designated named Tab Group. Avoid dragging unrelated personal tabs (e.g. online banking) into the agent's active group.
5. **Auto-Idle Process Sleep**:
   * If left inactive for 20 minutes, the background gateway shuts down to conserve system resources. Running any CLI command or MCP action will automatically wake it back up.

---

## 🚀 Setup & Installation

### 1. Prerequisites
* **Python 3.10+**
* **Google Chrome** (or Chromium-based browser)
* Required Python packages:
  ```bash
  pip install fastapi uvicorn requests pydantic mcp
  ```

### 2. Loading the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top right corner).
3. Click **Load unpacked** and select the [`extension`](file:///c:/Users/20106/agent_bro_hands/extension) folder inside this repository.

---

## ⚙️ Agent & MCP Configuration

Add Agent Bro Hands to your agent client configuration file:

### Claude Desktop (`claude_desktop_config.json`) / Antigravity / Cursor
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

### Available MCP Tools Reference

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `bro_execute` | `action_type` (`navigate` \| `execute_js`), `target_data` (URL or JS string), `session_title`, `group_color`, `requires_privacy_check` | Automatically ensures the gateway/browser are booted and executes the browser action. |
| `bro_status` | *none* | Queries gateway health, extension WebSocket link, human lockout state, and idle timeout. |
| `bro_release_takeover` | `notes` (string, optional) | Releases the human operator intervention lockout and passes handoff notes back to the agent. |
| `bro_stop` | *none* | Immediately halts active browser tasks and resets execution state. |

---

## 💻 CLI Usage (`bro_launcher.py`)

You can test and drive Agent Bro Hands directly from your terminal:

```bash
# Check gateway and extension status
python server/bro_launcher.py status

# Ensure gateway server and Chrome are booted & connected
python server/bro_launcher.py start

# Navigate to a URL in a designated session group
python server/bro_launcher.py navigate "https://news.ycombinator.com" --title "HackerNews Automation"

# Evaluate JavaScript on the active tab in the group
python server/bro_launcher.py eval "document.title" --title "HackerNews Automation"

# Release human lockout with handoff notes
python server/bro_launcher.py release --notes "Logged in via 2FA"

# Stop active tasks
python server/bro_launcher.py stop

# Terminate the background server process
python server/bro_launcher.py kill
```

---

## 🔌 REST API Endpoints

The local FastAPI Gateway operates at `http://127.0.0.1:8000`:

* **`GET /status`**: Returns gateway status, WebSocket connection state, `human_in_control` boolean, and remaining idle seconds.
* **`POST /execute`**: Dispatches an action (`navigate`, `execute_js`, or `task_complete`) to the active tab group.
* **`POST /human_release`**: Releases human lockout with optional `{ "notes": "..." }`.
* **`POST /stop`**: Halts running tasks and cancels pending execution futures.

---

## 📄 License
This project is licensed under the MIT License.
