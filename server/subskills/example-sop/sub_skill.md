---
name: example-sop
display_title: "Example SOP Playbook"
description: "Standard operating procedure demonstrating pure natural language markdown guidance with zero executable scripts."
tags: ["example", "sop", "playbook", "ooda"]
version: "2.1.0"
---

# Playbook: Example SOP Playbook

## Strategic Objective
Demonstrate standard operating procedure (SOP) playbooks with clear OODA loops, verified selectors, and contingency handling without executable scripts.

## Recommended OODA Steps
1. Call `browser_observe` to inspect current page state and locate primary interactive container `[role="main"]`.
2. Inspect presence of primary action trigger (e.g. `button[type="submit"]`, `.action-btn`, or dropdown menu).
3. If primary action button is not directly visible:
   - Click the secondary or "More" dropdown button.
   - Re-observe page DOM state via `browser_observe`.
   - Locate and click the revealed action target.
4. If a modal dialog appears:
   - Focus the target text input field.
   - Enter input payload.
   - Click "Confirm" or "Submit".
5. If a CAPTCHA, Cloudflare challenge, or 2FA prompt appears:
   - Call `browser_set_milestone("Awaiting Human 2FA")`.
   - Pause OODA loop and wait for user Takeover.
