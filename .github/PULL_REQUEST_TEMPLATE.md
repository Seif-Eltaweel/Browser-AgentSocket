## 📝 Description
Provide a concise summary of the changes introduced in this Pull Request and the problem being solved.

## 🔗 Related Issues
Fixes #(issue number)  
Related to #(issue number)

## 🏗️ Type of Change
- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] ✨ New feature (non-breaking change adding functionality)
- [ ] 💥 Breaking change (fix or feature causing existing functionality to break)
- [ ] 📚 Documentation update (installation, developer guide, subskill playbook)
- [ ] ⚡ Performance optimization / refactoring

---

## 🛡️ Architectural Invariant Verification

Please verify that your PR honors all 5 non-negotiable invariants:
- [ ] **1. Zero-Credential Storage**: No passwords, credit cards, or authentication cookies are logged or written to disk.
- [ ] **2. Headless Extension Model**: Chrome extension maintains zero local disk storage; all state is handled on server.
- [ ] **3. Shadow DOM Isolation**: All on-page HUD and takeover elements are encapsulated inside `#agentsocket-hud-host`.
- [ ] **4. Session Workspace Isolation**: Every session run writes exclusively to its dedicated subfolder (`input/`, `output/`, `adhocs/`, `artifacts/`, `sub_skill.md`).
- [ ] **5. Two-Step Lazy MCP Introspection**: History search remains two-step to prevent context window bloat.

---

## 🧪 Testing Checklist

- [ ] Python unit & integration tests pass:
  ```bash
  python -m unittest discover tests
  ```
- [ ] JavaScript protocol tests pass:
  ```bash
  node tests/test_protocol.test.js
  ```
- [ ] CLI launcher status verification:
  ```bash
  python server/socket_launcher.py status
  ```
- [ ] Manual browser smoke test performed (Extension connection, Tab Grouping, Shadow DOM HUD).

---

## 📸 Screenshots / Recordings (If Applicable)
Add screenshots or screen recordings showing UI/HUD changes or terminal outputs.
