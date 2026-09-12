# 📊 Progress HUD & Atomic Step Tracking Specification

**Version:** 1.0.0  
**Status:** Implemented & Standardized  
**Scope:** Real-Time Browser HUD, `input/implementation_plan.md` Protocol, WebSocket Progress Events, and Situation Awareness for Human-in-the-Loop AI Automation.

---

## 1. Executive Summary & Objective

In long-running autonomous browser automation, both the human operator and the AI agent need **instant, real-time situational awareness**:
* **Where does the task currently stand?**
* **How many steps are complete vs. remaining?**
* **What specific step is the browser currently executing?**
* **If human takeover occurs, at what exact phase did the AI pause?**

This specification defines the complete end-to-end architecture connecting the **Session Implementation Plan (`input/implementation_plan.md`)**, the **WebSocket progress protocol (`UPDATE_PROGRESS`)**, and the **On-Page Glassmorphic Floating HUD Progress Bar** rendered inside the browser's Shadow DOM.

---

## 2. System Architecture & Information Flow

```
 ┌──────────────────────────────────────────────────────────┐
 │                       AI Agent                           │
 └────────────────────────────┬─────────────────────────────┘
                              │ 1. Writes atomic checklist steps
                              ▼
 ┌──────────────────────────────────────────────────────────┐
 │        input/implementation_plan.md (On Disk)           │
 │  - [x] Step 1: [NAVIGATE] Verify Auth (Done)             │
 │  - [x] Step 2: [LOCATE] Focus Search (Done)              │
 │  - [ ] Step 3: [SCROLL] Lazy Load Feed (In Progress)     │
 │  - [ ] Step 4: [EXTRACT] Scrape Data                     │
 │  - [ ] Step 5: [FINALIZE] Save Output                    │
 └────────────────────────────┬─────────────────────────────┘
                              │ 2. Calculates Progress: 2/5 (40%)
                              │ 3. Dispatches action + progress metadata
                              ▼
 ┌──────────────────────────────────────────────────────────┐
 │          FastAPI Gateway Server (:8000)                  │
 │          POST /execute { step_current: 3, total: 5 }     │
 └────────────────────────────┬─────────────────────────────┘
                              │ 4. WebSocket: EXECUTE_ACTION / UPDATE_PROGRESS
                              ▼
 ┌──────────────────────────────────────────────────────────┐
 │          Chrome Extension (background.js)                │
 └────────────────────────────┬─────────────────────────────┘
                              │ 5. chrome.tabs.sendMessage (UPDATE_PROGRESS)
                              ▼
 ┌──────────────────────────────────────────────────────────┐
 │     Active Webpage Shadow DOM (#agentsocket-hud-host)    │
 │  ┌────────────────────────────────────────────────────┐  │
 │  │ ⚡ LinkedIn Scraper       [ Take Over ]  [ Stop ]  │  │
 │  │ ────────────────────────────────────────────────── │  │
 │  │ [██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  │  │
 │  │ Step 3 of 5 • [SCROLL_FEED]                    40% │  │
 │  └────────────────────────────────────────────────────┘  │
 └──────────────────────────────────────────────────────────┘
```

---

## 3. The `input/implementation_plan.md` Protocol

Every session folder (`server/logs/YYYY-MM-DD/<Session>/`) contains a mandatory implementation plan in `input/`.

### 3.1 Mathematical Progress Formula
$$\text{Completion Percentage} = \left( \frac{\text{Completed Steps}}{\text{Total Steps}} \right) \times 100$$

### 3.2 Standard Markdown Schema
```markdown
# 🎯 Session Implementation Plan: <Task Title>

## 1. 📌 Metadata & Objective
* **Session Title:** `<Friendly Title>`
* **Objective:** <Clear 1-sentence goal>
* **Total Atomic Steps:** 5

---

## 2. 🛠️ Execution Steps & Real-Time Progress
*Progress: [████████░░] 4/5 Steps Complete (80%)*

- [x] **Step 1: [VERIFY_AUTH]** Navigate to `https://example.com/login` and check cookie session.
- [x] **Step 2: [SUBMIT_QUERY]** Type search keyword into `input#search-box`.
- [x] **Step 3: [SCROLL_FEED]** Smooth scroll 3 steps to trigger lazy-loaded records.
- [x] **Step 4: [SCRAPE_PAYLOAD]** Extract structured items via CDP -> `output/results.json`.
- [ ] **Step 5: [FINALIZE_RUN]** Verify file integrity and dispatch `task_complete`.

---

## 3. 📦 Deliverables Contract
* **Target Output:** `output/results.json`
```

---

## 4. UI/UX Specification: The Floating HUD Completion Bar

The completion bar is rendered inside an isolated **open Shadow DOM (`#agentsocket-hud-host`)** in [`extension/content.js`](file:///c:/Users/20106/agent_bro_hands/extension/content.js), guaranteeing zero CSS conflicts with target websites.

### 4.1 Visual Styling & Tokens

| Component | CSS Property | Value | Rationale |
|---|---|---|---|
| **Pill Container** | `background` | `#18181b` | Obsidian dark theme matches modern developer tools |
| | `backdrop-filter` | `blur(12px)` | High-end glassmorphic finish |
| | `border` | `1px solid rgba(255, 255, 255, 0.15)` | Clean contrast without blinding borders |
| | `border-radius` | `18px` | Smooth rounded pill aesthetic |
| | `box-shadow` | `0 10px 30px rgba(0,0,0,0.6)` | Floating elevated depth |
| **Progress Track** | `background` | `rgba(255, 255, 255, 0.12)` | Subtle, translucent runway |
| | `height` | `4.5px` | Sleek, non-intrusive thickness |
| | `border-radius` | `999px` | Fully pill-shaped edges |
| **Progress Fill** | `background` | `linear-gradient(90deg, ${theme.borderHex}, #60a5fa)` | Vibrant theme-colored gradient |
| | `box-shadow` | `0 0 8px ${theme.glowRgba}` | Ambient glow along the active progress line |
| | `transition` | `width 0.4s cubic-bezier(0.4, 0, 0.2, 1)` | Butter-smooth animated progression |
| **Labels Row** | `font-size` | `11px` | Crisp microcopy |
| | `color` | `#a1a1aa` (text) / `${theme.tagText}` (percent) | High readability |

---

## 5. Multi-State HUD Progression

### 5.1 Mode A: Autonomous Execution (`renderActiveGlow`)
* **Visual Frame:** Pulsing colored ambient perimeter border (`#38bdf8`, `#a855f7`, etc.).
* **Interaction Shield:** Active (blocks accidental human keystrokes/clicks).
* **HUD Pill:** Shows pulsing status dot + Session Title + `[Take Over]` + `[Stop]` buttons + active progress bar.

```
┌────────────────────────────────────────────────────────────────────────┐
│  ⚡ LinkedIn Scraper                        [ Take Over ]   [ Stop ]   │
│ ────────────────────────────────────────────────────────────────────── │
│  [██████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░]     │
│  Step 3 of 5 • [SCROLL_FEED]                                      60%   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 5.2 Mode B: Operator Takeover State (`renderTakeoverUI`)
* **Trigger:** Human clicks `Take Over` OR server detects sensitive keywords (`password`, `bank`, `2FA`).
* **Visual Frame:** Red dashed border (`border: 3px dashed rgba(235, 87, 87, 0.7)`).
* **Interaction Shield:** Removed (human operator has 100% full browser control).
* **HUD Pill:** Transitions to warm dark red theme (`#4a2729` border) with:
  * Red Lock indicator: `🔒 Operator Active`
  * Buttons: `[ Stop ]` and `[ Release to Agent ]`
  * **Progress Bar:** Clearly displays the paused state: `Step 3 of 5 • Paused for Operator (60%)`.

```
┌────────────────────────────────────────────────────────────────────────┐
│  🔒 Operator Active                           [ Stop ]  [ ▶ Release ]  │
│ ────────────────────────────────────────────────────────────────────── │
│  [██████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░]     │
│  Step 3 of 5 • Paused for Operator                                60%   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 5.3 Mode C: Final Completion (`task_complete`)
* **Trigger:** Agent finishes all steps and calls `task_complete`.
* **Visual State:** Progress bar fills to 100% emerald green (`#10b981`), tab group is renamed with `✅`, and session is finalized in `SESSION_DOCUMENT.md`.

---

## 6. Live Progress Message Protocol

### 6.1 Protocol Constant ([`extension/protocol.js`](file:///c:/Users/20106/agent_bro_hands/extension/protocol.js))
```javascript
MessageTypes.UPDATE_PROGRESS = "update_progress";
```

### 6.2 Message Payload Structure
```json
{
  "type": "update_progress",
  "progress": {
    "percent": 60.0,
    "currentStep": 3,
    "totalSteps": 5,
    "stepTitle": "[SCROLL_FEED] Lazy loading feed items"
  }
}
```

---

## 7. Automated Verification & Invariants

1. **DOM Non-Interference:** The progress bar and HUD styles are 100% encapsulated inside `#agentsocket-hud-host.shadowRoot`. No webpage CSS rules can alter or break its display.
2. **Keyboard Exemption:** Typing inside the handoff modal textarea is explicitly allowed via `e.composedPath()` inspection, while typing on the host page remains shielded.
3. **Clamped Bounds:** Progress percentages are strictly clamped `0 <= percent <= 100` to prevent layout overflow.
4. **Offline Resilience:** If progress data is omitted, the HUD displays `Task in progress...` gracefully without throwing runtime errors.
