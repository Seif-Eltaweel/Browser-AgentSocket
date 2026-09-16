# 🔒 Specification 30: Persistent Session Authorization & Non-Redundant Consent Architecture

**Version:** 1.0.0  
**Status:** Approved Standard  
**Scope:** Chrome Extension Manifest V3 Service Worker Lifecycle, `chrome.storage.local` Hydration, Single-Prompt Session Grants, Zero-Redundancy Authorization Handshake, and Human-in-the-Loop Consent Protection.

---

## 1. Executive Summary & Problem Analysis

In previous runs (e.g. Batch 9), the human operator was repeatedly spammed with desktop notifications and browser popups opening `http://127.0.0.1:8000/auth.html`.

### 1.1 The Root Cause in Manifest V3
In Google Chrome Extensions Manifest V3 (MV3):
1. **Service Worker Ephemerality**: Background service workers (`background.js`) are not persistent background pages. Chrome automatically terminates the service worker after **30 seconds of inactivity** to save system memory.
2. **In-Memory State Loss**: `authorizedSessions` was maintained as an ephemeral in-memory `Set()`:
   ```javascript
   const authorizedSessions = new Set(); // Lost on every service worker sleep/wake cycle!
   ```
3. **Repeated Prompts**: Whenever the service worker woke up to handle an incoming WebSocket event or action, `authorizedSessions.has(sessionTitle)` returned `false`. Consequently, `ensureAuthorized()` treated every reconnection as a brand-new untrusted session, created a notification, and called `chrome.tabs.create({ url: authUrl })` again and again.

### 1.2 Core Architectural Invariant: Preserving Human Consent
* **We do NOT eliminate user authorization**: Allowing autonomous code to automate a user's browser without explicit human approval is a critical security vulnerability. Human consent is a strict system invariant.
* **We eliminate REDUNDANCY**: Once the operator reviews the session title (e.g. `"Batch 10 CRM Enrichment"`) and clicks "Authorize", that grant is persisted in `chrome.storage.local`. The user approves **EXACTLY ONCE** at session inception, and never again during that run.

---

## 2. System Architecture: Storage-Hydrated Authorization Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│               PERSISTENT SESSION AUTHORIZATION LIFECYCLE               │
└────────────────────────────────────────────────────────────────────────┘

 [Session Start: "Batch 10 CRM Enrichment"]
       │
       ▼
 1. Action Received in background.js ──► Check ensureAuthorized(sessionTitle)
                                                │
                          ┌─────────────────────┴─────────────────────┐
                          ▼ In-Memory or Storage Hit?                 ▼ Not Found
                   RETURN TRUE (INSTANT PASS)                   Trigger Consent Flow:
                          ▲                                     1. Chrome Notification
                          │                                     2. Open auth.html (ONCE)
                          │                                           │
                          │                                           ▼
                          │                                    User Clicks "Authorize"
                          │                                           │
                          │                                           ▼
                          │                                  saveAuthorizedSession()
                          │                                  Writes to chrome.storage.local:
                          │                                  {
                          │                                    title: "Batch 10 CRM Enrichment",
                          │                                    granted_at: 1726476000000,
                          │                                    permissions: {
                          │                                      enable_vision: true,
                          │                                      enable_subskills: true
                          │                                    }
                          │                                  }
                          │                                           │
                          └───────────────────────────────────────────┘
                                      │
                                      ▼
             [Service Worker Recycled by Chrome after 30s Idle]
                                      │
                                      ▼
             Service Worker Wakes Up ──► loadAuthorizedSessions()
             Hydrates in-memory Set from chrome.storage.local
             Next Action Dispatched ──► INSTANT PASS (ZERO POPUPS!)
```

---

## 3. Detailed Component Implementation

### 3.1 Persistent Storage Schema
Stored under key `authorized_sessions_data` in `chrome.storage.local`:
```json
{
  "authorized_sessions_data": [
    [
      "Batch 10 CRM Enrichment",
      {
        "granted_at": 1726476000000,
        "enable_vision": true,
        "enable_subskills": true
      }
    ]
  ]
}
```

### 3.2 Dual-Tier Check in `ensureAuthorized(sessionTitle, server)`
1. **Tier 1 (In-Memory Check)**: If `authorizedSessions.has(title)`, proceed immediately.
2. **Tier 2 (Storage Hydration Check)**: If missing in memory, check `chrome.storage.local`. If a valid unexpired grant exists, populate `authorizedSessions` and proceed immediately without opening `auth.html`.
3. **Tier 3 (User Prompt)**: If genuinely new, alert user via desktop notification and open `auth.html` once. When granted, persist to both memory and `chrome.storage.local`.

### 3.3 Session Scope & Clean Revocation
* Authorization is scoped by **session title** (e.g. `"Batch 10 CRM Enrichment"`).
* Calling `socket_launcher.py stop` or releasing the session can optionally clear or expire the grant.
* Operators can also revoke permissions anytime via the Extension Settings Popup (`popup.html`).

---

## 4. Verification & Testing Standards

Spec 30 is verified by `tests/test_spec30_session_auth.py`:
1. `test_first_access_triggers_auth`: Verifies that an unknown session initiates the consent handshake.
2. `test_authorized_session_persists_across_hydrations`: Simulates service worker restarts by clearing in-memory variables and confirming that `loadAuthorizedSessions()` restores full authorization.
3. `test_subsequent_actions_never_prompt`: Verifies that actions in an authorized session proceed with zero popups and zero delay.
