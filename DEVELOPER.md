# 🛠️ Developer & Builder Guide: AgentSocket-Browser

Welcome to the **AgentSocket-Browser** developer framework. This document teaches you how to build autonomous agent tools, custom automation runners, and reusable browser subskills on top of AgentSocket.

---

## 1. System Architecture & Core Concepts

AgentSocket operates as a tri-layer browser automation architecture:

```
┌────────────────────────────────────────────────────────┐
│   Agent Layer: Claude Code, Antigravity, Custom SDK    │
└───────────────────────────┬────────────────────────────┘
                            │ (MCP stdio or REST /execute)
                            ▼
┌────────────────────────────────────────────────────────┐
│   Gateway & Session Manager (FastAPI - Port 8000)      │
│   - Session logger (YYYY-MM-DD / session.jsonl)        │
│   - Sensitive keyword interception & Human lockouts    │
│   - Subskills catalog & registry engine                │
└───────────────────────────┬────────────────────────────┘
                            │ (WebSocket: ws://127.0.0.1:8000/ws/extension)
                            ▼
┌────────────────────────────────────────────────────────┐
│   Chrome Extension (Manifest V3 + CDP Engine)          │
│   - Isolated Chrome Tab Groups                         │
│   - Shadow DOM HUD Shield (#agentsocket-hud-host)      │
│   - CDP Execution (Runtime.evaluate bypassing CSP)     │
└────────────────────────────────────────────────────────┘
```

### Key Engineering Invariants
1. **Zero-Latency WebSocket Bridge**: Persistent local WebSocket connection between FastAPI gateway and Chrome Extension service worker (`background.js`).
2. **Tab Group Isolation**: Sessions run inside dedicated, color-coded Chrome Tab Groups (`tabGroups` API) to prevent tab pollution.
3. **Shadow DOM Encapsulation**: HUD components (pill, interaction shield, takeover modal) live inside `#agentsocket-hud-host` open Shadow Root. Host page CSS styles cannot alter the HUD.
4. **CDP Execution Engine**: Direct Chrome DevTools Protocol (`chrome.debugger`) execution executes scripts cleanly without Content Security Policy (CSP) blocking.

---

## 2. Building Custom Python Automation Runners

You can interact with AgentSocket directly from Python using standard HTTP requests:

```python
import requests
import time
from typing import Any, Dict

class BrowserAgentRunner:
    """Lightweight Python runner for AgentSocket-Browser automation."""

    def __init__(self, server_url: str = "http://127.0.0.1:8000", session_title: str = "Custom Task"):
        self.server_url = server_url
        self.session_title = session_title

    def check_status(self) -> Dict[str, Any]:
        """Check if gateway and browser extension are connected."""
        resp = requests.get(f"{self.server_url}/status")
        resp.raise_for_status()
        return resp.json()

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate the active session tab to target URL."""
        payload = {
            "id": f"nav_{int(time.time() * 1000)}",
            "action_type": "navigate",
            "target_data": url,
            "session_title": self.session_title
        }
        resp = requests.post(f"{self.server_url}/execute", json=payload)
        resp.raise_for_status()
        return resp.json()

    def evaluate_js(self, js_expression: str) -> Any:
        """Evaluate JavaScript inside the active page using CDP."""
        payload = {
            "id": f"eval_{int(time.time() * 1000)}",
            "action_type": "execute_js",
            "target_data": js_expression,
            "session_title": self.session_title
        }
        resp = requests.post(f"{self.server_url}/execute", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("output")

    def release_human_takeover(self, notes: str = "") -> Dict[str, Any]:
        """Release operator lockout and pass context back to agent."""
        resp = requests.post(f"{self.server_url}/release_takeover", json={"notes": notes})
        resp.raise_for_status()
        return resp.json()


# --- Usage Example ---
if __name__ == "__main__":
    runner = BrowserAgentRunner(session_title="HackerNews Scraper")
    
    # 1. Ensure system is connected
    status = runner.check_status()
    print("Gateway status:", status.get("status"))

    # 2. Navigate to Hacker News
    runner.navigate("https://news.ycombinator.com")

    # 3. Extract top story headlines
    js_query = """
    Array.from(document.querySelectorAll('.titleline > a')).slice(0, 5).map(a => ({
        title: a.innerText,
        url: a.href
    }))
    """
    stories = runner.evaluate_js(js_query)
    print("Top stories extracted:", stories)
```

---

## 3. Subskills Architecture & Playbook Lifecycle

AgentSocket organizes every browser automation run into a **self-contained session directory** that can be converted into a reusable subskill:

### 3.1 Session Directory Layout
```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Auto-generated executive session report
├── session.jsonl           # Complete line-delimited event telemetry
├── sub_skill.md            # Reusable playbook rules, selectors & anti-bot SLA
├── input/                  # Input targets, CSVs, parameter lists
├── output/                 # Deliverables, structured JSON, scraped CSVs
├── adhocs/                 # Ad-hoc Python scripts and one-off scrapers
└── artifacts/              # Screenshots and large offloaded payloads (>10KB)
```

### 3.2 Authoring a Subskill Playbook (`sub_skill.md`)
A production-ready `sub_skill.md` defines the playbook contract:

```markdown
# 🎯 Subskill Playbook: GitHub Repo Metrics Extractor

## Metadata
* **Name:** `github-repo-metrics`
* **Version:** `1.0.0`
* **Author:** Seif Eltaweel
* **Target Domain:** `github.com`
* **Tags:** `github`, `scraping`, `developer-tools`

## Objectives & SLA
Extract repository metadata (stars, forks, open issues, latest release tag, license) with zero flaky selector failures.

## Selector Hierarchy
* **Stars Counter:** `a[href$="/stargazers"] strong, #repo-stars-counter-star`
* **Forks Counter:** `a[href$="/forks"] strong, #repo-network-counter`
* **Issues Tab:** `a#issues-tab span[data-content]`
* **Latest Release:** `a[href*="/releases/tag/"] span`

## Extraction Script (CDP)
```javascript
(() => {
    const getText = (selector) => document.querySelector(selector)?.innerText?.trim() || "N/A";
    return {
        repo: window.location.pathname.replace(/^\//, ''),
        stars: getText('#repo-stars-counter-star'),
        forks: getText('#repo-network-counter'),
        license: getText('a[href*="/LICENSE"]')?.trim() || "None"
    };
})();
```

## Anti-Detection & Delays
* Inject a **1.2s to 2.5s jitter delay** between consecutive repo navigations.
* If a rate limit or login banner is detected, trigger `requires_privacy_check=True`.
```

### 3.3 Registering a Subskill via CLI
Register a finished session as a named subskill in the central catalog (`server/logs/subskills_index.json`):

```bash
python server/socket_launcher.py subskills register \
  --session server/logs/2026-08-21/GitHub_Scraper_14-30_gid101 \
  --name github-metrics-extractor \
  --title "GitHub Repository Metrics Extractor" \
  --tags "github,metrics,scraping"
```

### 3.4 Borrowing a Subskill for a New Run
Instantiate an existing subskill into a clean, isolated session workspace:

```bash
python server/socket_launcher.py subskills borrow github-metrics-extractor \
  --title "Run 2 - Scraping AI Repositories" \
  --input ./my_target_repos.csv
```

---

## 4. Extending FastMCP Tools

The Model Context Protocol (MCP) server is located in [`server/socket_mcp.py`](server/socket_mcp.py).

To add a new tool for your AI agents, use the `@server.tool()` decorator:

```python
from mcp.server import MCPServer
from server import socket_launcher

server = MCPServer("agentsocket-browser")

@server.tool()
def socket_custom_action(param1: str, param2: int = 10) -> dict:
    """
    Describe what this tool does so LLM agents know when to call it.
    """
    # Execute action through socket_launcher or session_manager
    return {"status": "success", "result": f"Handled {param1} with limit {param2}"}
```

---

## 5. Running Developer Tests

Ensure all unit and integration tests pass before submitting changes:

```bash
# Run complete Python test suite
python -m unittest discover tests

# Run JavaScript protocol tests
node tests/test_protocol.test.js

# Verify launcher subskills CLI
python server/socket_launcher.py subskills list
```
