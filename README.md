# Agent Bro Hands 🤖🖐️

**Multi-agent browser automation operator client and state control hub.**

Agent Bro Hands is a secure, human-in-the-loop web automation bridge that links autonomous AI agents (such as Hermes, Antigravity, or Claude Code) to your actual browser session via WebSockets. It features built-in security guardrails, automatic privacy scans, and seamless human-agent state takeover controls.

---

## 🏗️ System Architecture

The project consists of two core components:
1. **FastAPI Gateway Server (`/server`)**: Orchestrates commands from AI agents, monitors execution state, runs keyword-based privacy/security checks, and manages human takeover lockouts.
2. **Chrome Extension (`/extension`)**: A Manifest V3 extension acting as the automation operator in the browser. It connects to the server via WebSockets, executes JS/navigation commands on active tabs, and coordinates user-controlled release triggers.

```
┌───────────┐                ┌──────────────────┐               ┌──────────────────┐
│ AI Agent  │ ───/execute──> │ FastAPI Server   │ ──WebSocket─> │ Chrome Extension │
│ (Hermes)  │ <─command_res─ │ (bro_server.py)  │ <──ping/state │ (background.js)  │
└───────────┘                └──────────────────┘               └──────────────────┘
                                      │
                              [Privacy Check] ──> True ──> [HUMAN TAKE-OVER LOCKOUT]
```

---

## 🌟 Key Features

* **WebSocket Tunneling**: Seamless communication between server and extension using persistent WebSocket frames.
* **Smart Security Lockout**: Automatically triggers a human intervention lockout when sensitive keyword patterns (like `password`, `creditcard`, `payment`, `login`, `bank`) are detected in actions or targets.
* **Human-in-the-loop Release**: An intervention gateway allowing human operators to take manual control, perform sensitive actions, and release control back to the agent with added context logs.
* **Multi-Server Configuration**: Configure multiple local or remote agent servers (e.g. Hermes, Antigravity, Claude Code) with distinct connection parameters and group labeling.

---

## 🚀 Getting Started

### 1. Run the FastAPI Server
Navigate to the `server/` directory, install dependencies (`fastapi`, `uvicorn`, `pydantic`), and run the server:

```bash
cd server
pip install fastapi uvicorn pydantic
uvicorn bro_server:app --host 127.0.0.1 --port 8000 --reload
```

*The server will be available at `http://127.0.0.1:8000`.*

### 2. Load the Chrome Extension
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** in the top-left corner.
4. Select the `extension/` directory of this project.
5. Open the extension popup to view connection status and configure your agent servers.

---

## 🔌 API Reference

### GET `/`
Returns the status of the server gateway, showing if the browser extension is currently connected and whether a human is in control.

### GET `/status`
Returns full system state details including extension connection, human control state, and the latest intervention notes.

### POST `/execute`
Sends an automation action to the Chrome extension.
* **Payload Structure**:
  ```json
  {
    "id": "action-uuid-1234",
    "action_type": "navigate", // "navigate" | "execute_js" | "task_complete"
    "target_data": "https://github.com",
    "requires_privacy_check": false,
    "session_title": "Hermes Search",
    "group_color": "purple"
  }
  ```
* **Response States**:
  * `success`: Execution completed and returned output.
  * `security_abort`: Action triggered a security rule, locking control for manual human takeover.
  * `resumed_context`: Agent was blocked but human released the lock with instructions/log context.

### POST `/human_release`
Releases human lockout and lets the AI agent resume execution.
* **Payload Structure**:
  ```json
  {
    "notes": "Completed sign-in manually. You can now proceed to scraping."
  }
  ```

### POST `/stop`
Immediately aborts any active tasks and pending extension callbacks, resetting the control state.

---

## 📄 License
This project is licensed under the MIT License.
