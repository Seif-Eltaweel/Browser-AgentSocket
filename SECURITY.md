# Security Policy & Privacy Invariants

The **AgentSocket-Browser** team treats security, privacy, and human safety as primary engineering constraints. Because AgentSocket connects autonomous AI agents directly to user browser sessions, strict architectural guardrails prevent credential leakage, accidental data exposure, and unauthorized actions.

---

## 1. Supported Versions

Security patches and bug fixes are actively provided for the following releases:

| Version | Supported | Notes |
|:---|:---|:---|
| `v1.1.x` | :white_check_mark: | Active production release (FastMCP, Tab Groups, Shadow DOM HUD). |
| `v1.0.x` | :white_check_mark: | Maintenance security updates. |
| `< 1.0.0` | :x: | Deprecated preview releases. |

---

## 2. Core Architectural Privacy Invariants

Every release and pull request must strictly honor these five non-negotiable security invariants:

### 1. Strict Zero-Credential Storage
* **No Passwords on Disk**: AgentSocket **never** captures, logs, or serializes passwords, credit card numbers, CVVs, MFA tokens, or session cookies to disk.
* **Redacted Logs**: Any DOM input values matching sensitive selectors (e.g. `input[type="password"]`) are discarded before being written to `session.jsonl` or `SESSION_DOCUMENT.md`.

### 2. Automatic Sensitive Scope Interception (Human Lockout)
* **Keyword Interception Engine**: If an agent requests execution of JavaScript or navigation containing sensitive keywords:
  ```
  password, passwd, passkey, bank, payment, checkout, stripe, paypal, cvv, ssn, pin, 2fa, otp
  ```
  The gateway triggers an immediate `[SECURITY ABORT]`, rejects the outbound agent execution, drops the Viewport Shield, and locks the browser into **Operator Control**.
* **Mandatory Privacy Flag**: If `requires_privacy_check=True` is provided by an agent, execution is paused until the human operator manually confirms or performs the action.

### 3. Shadow DOM Viewport Shielding
* The on-page HUD and overlay shield are encapsulated inside `#agentsocket-hud-host` open Shadow Root. Host pages cannot inject scripts or styles into the HUD, and the overlay shield prevents accidental human/agent race conditions during active operations.

### 4. Localhost Loopback Binding Only
* By default, the FastAPI gateway binds exclusively to `127.0.0.1:8000` (loopback). It is **not** exposed to the public internet or local network unless explicitly configured.

---

## 3. Reporting a Vulnerability

If you discover a security vulnerability or privacy leak in AgentSocket-Browser:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via **GitHub Private Security Advisories**:
   - Navigate to the repository's **Security** tab -> **Advisories** -> **Report a vulnerability**.
3. Or email the core maintainer directly:
   - **Email:** [github@seifeltaweel.com](mailto:github@seifeltaweel.com)
   - Include a detailed description of the issue, proof of concept (PoC), Chrome/Python versions, and remediation suggestions if available.

### What to Expect:
* **Initial Response:** Within 24-48 hours with acknowledgment.
* **Triage & Status Update:** Within 3-5 business days.
* **Fix & Release:** Coordinated disclosure after a patch is verified and released.

---

## 4. Best Practices for Agent Operators

* **Use Dedicated Browser Profiles**: When developing or evaluating untrusted agent code, use a dedicated Chrome Profile (`--user-data-dir`).
* **Review Subskills Before Borrowing**: Always inspect the JavaScript queries inside any community `sub_skill.md` playbooks before running them against sensitive internal portals.
