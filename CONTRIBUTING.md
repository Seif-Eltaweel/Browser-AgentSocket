# 🤝 Contributing to AgentSocket-Browser

Thank you for your interest in contributing to **AgentSocket-Browser**! We are committed to building a secure, high-performance, human-in-the-loop browser automation bridge for the AI agent ecosystem.

This guide outlines our development workflow, architectural invariants, code quality standards, and pull request review process.

---

## 1. Non-Negotiable Architectural Invariants

Before writing any code, familiarize yourself with these core invariants that must **never** be broken in any PR:

1. **Strict Zero-Credential Storage**: Never capture, store, log, or persist passwords, credit cards, MFA secrets, or authentication cookies to disk. Sensitive values must be discarded before event logging.
2. **Headless Extension Model**: The Chrome extension must maintain zero persistent disk state; all history, telemetry, and heavy artifacts belong on the local server (`server/logs/`).
3. **Shadow DOM Encapsulation**: All on-page UI elements (glowing status frame, floating HUD pill, handoff modals) must be rendered inside an open **Shadow Root** on `<agentsocket-hud-host>`. Host page CSS resets or styling must never alter HUD visuals.
4. **Complete Session Workspace Isolation**: Every automation run must write exclusively to its dedicated subfolder (`input/`, `output/`, `adhocs/`, `artifacts/`, `sub_skill.md`, `SESSION_DOCUMENT.md`).
5. **Two-Step Lazy MCP Introspection**: History querying via MCP must remain two-step (`socket_query_history` -> `socket_get_session_details`) to prevent LLM context window exhaustion.

---

## 2. Development Setup

Follow these steps to set up your local development environment:

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/agentsocket-browser.git
cd agentsocket-browser

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 3. Install core dependencies
pip install -r requirements.txt

# 4. Load the unpacked extension in Chrome
# Navigate to chrome://extensions, enable "Developer mode", click "Load unpacked", and select extension/
```

---

## 3. Git Workflow & Commit Guidelines

### 3.1 Branch Naming Convention
* `feat/<feature-name>`: New features or major capabilities (e.g. `feat/subskills-fuzzy-search`).
* `fix/<bug-name>`: Bug fixes and stability patches (e.g. `fix/takeover-overlay-cleanup`).
* `docs/<doc-name>`: Documentation improvements and playbook updates (e.g. `docs/mcp-setup-guide`).
* `refactor/<module-name>`: Code refactoring without behavioral change.

### 3.2 Commit Messages (Conventional Commits)
We enforce the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short summary>

[optional body explaining rationale]
[optional footer / issue reference: Fixes #123]
```

**Allowed Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`.  
**Examples:**
* `feat(subskills): add fuzzy keyword search across playbook tags`
* `fix(content): resolve keyboard event capture inside shadow root handoff modal`
* `docs(readme): add Cursor IDE MCP integration snippet`

---

## 4. Code Quality & Formatting Standards

### 4.1 Python Guidelines
* **Style:** PEP 8 compliance.
* **Typing:** Strict type annotations (`typing`, `Optional`, `Dict[str, Any]`, `List[str]`).
* **Schemas:** All JSON inputs, WebSocket payloads, and event logs must use typed **Pydantic models** in [`server/models.py`](file:///c:/Users/20106/agent_bro_hands/server/models.py).
* **Process Safety:** Never use blocking sleeps in async FastAPI routes; use non-blocking event loops and timeouts.

### 4.2 JavaScript Guidelines (Chrome Extension)
* **Manifest V3:** Adhere to Chrome Extension Manifest V3 service worker lifecycle standards.
* **Zero Dependencies:** The extension (`extension/`) must remain lightweight with zero external npm runtime dependencies.
* **Modularity:** Shared constants and envelope creators belong in [`extension/protocol.js`](file:///c:/Users/20106/agent_bro_hands/extension/protocol.js) using standard UMD format for cross-environment testing.

---

## 5. Testing & Quality Gates

Every Pull Request must pass 100% of test suites before merge:

```bash
# 1. Run complete Python test suite (44+ tests)
python -m unittest discover tests

# 2. Run JavaScript protocol validation tests
node tests/test_protocol.test.js

# 3. Verify CLI subcommands
python server/socket_launcher.py status
python server/socket_launcher.py subskills list
```

---

## 6. Pull Request Submission Checklist

When opening a Pull Request:
1. Ensure your PR branch is up to date with `main`.
2. Fill out the [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md).
3. Include links to relevant issues (`Fixes #...`).
4. Add unit tests for any new features or bug fixes.
5. Verify that all 5 Architectural Invariants are preserved.
