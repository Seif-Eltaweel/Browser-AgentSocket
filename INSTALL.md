# 🔌 Installation Guide: AgentSocket-Browser

This guide provides step-by-step instructions to install and configure **AgentSocket-Browser** on **Windows**, **macOS**, and **Linux**.

---

## 📋 System Prerequisites

| Component | Minimum Requirement | Recommended | Notes |
|:---|:---|:---|:---|
| **Python** | `3.10+` | `3.11` or `3.12` | Verified on Python 3.10, 3.11, 3.12. |
| **Browser** | Google Chrome `115+` | Latest Stable Chrome | Also works on Chromium, Brave, Microsoft Edge. |
| **Git** | `2.30+` | Latest | For repository cloning & subskills versioning. |
| **Node.js** *(Optional)* | `18.0+` | `20.x LTS` | Optional; required only for running JS protocol tests. |

---

## 🚀 4-Step Installation Pipeline

### Step 1: Clone Repository & Set Up Virtual Environment

Open your terminal and clone the repository:

```bash
git clone https://github.com/Seif-Eltaweel/Browser-AgentSocket.git
cd Browser-AgentSocket
```

Create and activate a dedicated Python virtual environm#### 🪟 Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
# or: pip install -r requirements.txt
```

#### 🪟 Windows (Command Prompt)
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -e .
# or: pip install -r requirements.txt
```

#### 🍎 macOS / 🐧 Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
```

---

### Step 2: Load the Chrome Extension (Developer Mode)

AgentSocket requires the Manifest V3 Chrome Extension to link your active browser session to the gateway.

1. Open Google Chrome and go to:
   ```
   chrome://extensions
   ```
2. Enable **Developer mode** using the toggle in the top-right corner.
3. Click the **Load unpacked** button in the top-left corner.
4. Select the `extension/` directory inside your cloned `Browser-AgentSocket` folder.
5. You should see **AgentSocket** loaded with version `v1.1.0`.
6. *(Recommended)* Click the Chrome Extensions puzzle piece icon on your toolbar and **pin AgentSocket** for easy status viewing.

```
┌─────────────────────────────────────────────────────────────────┐
│ Extensions                   [ Developer mode: [ON] ]           │
│ ┌───────────────┐ ┌───────────────┐                             │
│ │ Load unpacked │ │ Pack extension│                             │
│ └──────┬────────┘ └───────────────┘                             │
│        ▼                                                        │
│  Select: /path/to/Browser-AgentSocket/extension                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### Step 3: Configure MCP Integration for Your AI Agent

AgentSocket exposes native FastMCP tools (`browser_observe`, `browser_click`, `browser_type`, `browser_scroll`, `browser_key_press`, `browser_screenshot`, `task_complete`, `browser_set_milestone`, `socket_status`, `socket_release_takeover`, `socket_stop`, `socket_query_history`, `socket_get_session_details`, `socket_get_session_artifact`, `socket_get_session_document`).

Configure your agent environment with the snippets below:

#### Option A: Claude Desktop (`claude_desktop_config.json`)
* **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
* **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "agentsocket": {
      "command": "agentsocket",
      "args": ["mcp"]
    }
  }
}
```
*(Or with portable module execution: `command: "python", args: ["-m", "server.socket_mcp"]`)*

#### Option B: Claude Code CLI
Run in your terminal:
```bash
claude mcp add agentsocket agentsocket mcp
# or: claude mcp add agentsocket python -m server.socket_mcp
```

#### Option C: Google Antigravity / Gemini CLI (`mcp_config.json`)
Add to your project root or global `mcp_config.json`:
```json
{
  "mcpServers": {
    "agentsocket": {
      "command": "agentsocket",
      "args": ["mcp"]
    }
  }
}
```

#### Option D: Cursor / Windsurf IDE
In Cursor **Settings -> MCP**, click **Add New MCP Server**:
* **Name:** `agentsocket`
* **Type:** `command`
* **Command:** `agentsocket mcp` (or `python -m server.socket_mcp`)

---

### Step 4: Verification & Smoke Test

Verify that the gateway, WebSocket bridge, and Chrome Extension communicate properly with a single smoke test:

```bash
# 1. Plug in gateway and verify socket health
agentsocket plug
# or: browser-socket plug (or python -m server.socket_launcher plug)

# 2. Test URL navigation in active Chrome window
agentsocket navigate "https://example.com"

# 3. Test JavaScript evaluation via CDP
agentsocket eval "document.title"
```

**Expected Output:**
```
[AgentSocket] Gateway Status: READY (HTTP 200)
[AgentSocket] Extension Bridge: CONNECTED (ws://127.0.0.1:8000/ws/extension)
[AgentSocket] Active Tab Group: "AgentSocket Task"
[AgentSocket] CDP Output: "Example Domain"
```

---

## 🛠️ Troubleshooting & FAQs

### Q1: `Extension disconnected` or `No active tab found`
1. Ensure the extension is loaded at `chrome://extensions`.
2. Click the extension popup icon in your toolbar and ensure the socket URL is set to `ws://127.0.0.1:8000/ws/extension`.
3. If Chrome was closed, run `agentsocket plug` to auto-launch Chrome with the extension attached.

### Q2: Port 8000 is already in use
* AgentSocket uses port `8000` by default. You can check the current process using port 8000:
  * **Windows:** `netstat -ano | findstr :8000`
  * **macOS / Linux:** `lsof -i :8000`
* Or specify a custom port by setting the `AGENTSOCKET_PORT` environment variable before running.

### Q3: Running in Brave or Microsoft Edge
* **Brave**: In `brave://settings/shields`, ensure local loopback WebSocket connections (`ws://127.0.0.1:8000`) are not blocked by strict shield settings.
* **Edge**: Navigate to `edge://extensions`, enable **Developer mode**, and click **Load unpacked**.

---

## 📚 Next Steps
* Read the [Developer & Builder Guide](DEVELOPER.md) to build custom runners or subskills.
* Check [Extended Multi-OS Installation Guide](docs/installation.md) for Docker, headless setups, and enterprise network configs.
