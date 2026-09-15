/**
 * Unit tests for Feature Spec 21: Extension Floating Live Intent Ticker & Takeover Lockout Shield
 * Executed via Node.js
 */

const assert = require('assert');

class MockStyle {
    constructor() {
        this._cssText = '';
    }
    get cssText() {
        return this._cssText;
    }
    set cssText(val) {
        this._cssText = val;
        if (typeof val === 'string') {
            const rules = val.split(';');
            for (const rule of rules) {
                const colonIdx = rule.indexOf(':');
                if (colonIdx !== -1) {
                    const prop = rule.slice(0, colonIdx).trim();
                    let propVal = rule.slice(colonIdx + 1).trim();
                    propVal = propVal.replace(/!important/g, '').trim();
                    const camelProp = prop.replace(/-([a-z])/g, (_, g) => g.toUpperCase());
                    this[camelProp] = propVal;
                    this[prop] = propVal;
                }
            }
        }
    }
}

// Mock DOM Element with styles, attributes, and events
class MockElement {
    constructor(tagName = 'div') {
        this.tagName = tagName.toUpperCase();
        this.id = '';
        this.className = '';
        this.textContent = '';
        this.innerHTML = '';
        this.title = '';
        this.style = new MockStyle();
        this.children = [];
        this.childNodes = [];
        this.parentNode = null;
        this.listeners = {};
        this.onclick = null;
        this.onmouseenter = null;
        this.onmouseleave = null;
    }

    appendChild(child) {
        if (!child) return child;
        child.parentNode = this;
        this.children.push(child);
        this.childNodes.push(child);
        return child;
    }

    removeChild(child) {
        const idx = this.childNodes.indexOf(child);
        if (idx !== -1) {
            this.childNodes.splice(idx, 1);
            const cIdx = this.children.indexOf(child);
            if (cIdx !== -1) this.children.splice(cIdx, 1);
            child.parentNode = null;
        }
        return child;
    }

    remove() {
        if (this.parentNode) {
            this.parentNode.removeChild(this);
        }
    }

    addEventListener(event, fn) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(fn);
    }

    removeEventListener(event, fn) {
        if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(f => f !== fn);
        }
    }

    dispatchEvent(evt) {
        const fns = this.listeners[evt.type] || [];
        fns.forEach(fn => fn(evt));
        if (evt.type === 'click' && typeof this.onclick === 'function') {
            this.onclick(evt);
        }
        return true;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const matchFn = (el) => {
            if (selector.startsWith('#') && el.id === selector.slice(1)) return true;
            if (selector.startsWith('.') && el.className && el.className.split(' ').includes(selector.slice(1))) return true;
            if (selector.toLowerCase() === el.tagName.toLowerCase()) return true;
            return false;
        };

        const traverse = (node) => {
            for (const child of node.childNodes) {
                if (matchFn(child)) matches.push(child);
                traverse(child);
            }
        };
        traverse(this);
        return matches;
    }

    getElementById(id) {
        const traverse = (node) => {
            for (const child of node.childNodes) {
                if (child.id === id) return child;
                const res = traverse(child);
                if (res) return res;
            }
            return null;
        };
        return traverse(this);
    }

    attachShadow() {
        if (!this.shadowRoot) {
            this.shadowRoot = new MockElement('shadow-root');
            this.shadowRoot.host = this;
        }
        return this.shadowRoot;
    }
}

// Global Mocks
const sentMessages = [];
global.chrome = {
    runtime: {
        lastError: null,
        sendMessage: (msg, cb) => {
            sentMessages.push(msg);
            if (cb) cb({ inActiveSession: false });
        },
        onMessage: {
            _listeners: [],
            addListener: (fn) => { global.chrome.runtime.onMessage._listeners.push(fn); }
        }
    }
};

global.window = {
    innerHeight: 800,
    innerWidth: 1280,
    addEventListener: () => {},
    removeEventListener: () => {},
    location: { hostname: "travel.example.com", href: "https://travel.example.com" }
};

global.document = {
    title: "Travel Booking",
    readyState: "complete",
    body: new MockElement("body"),
    documentElement: new MockElement("html"),
    createElement: (tag) => new MockElement(tag),
    getElementById: (id) => {
        if (id === "agentsocket-hud-host") {
            return global.document.documentElement.getElementById(id);
        }
        return null;
    },
    addEventListener: () => {},
    removeEventListener: () => {}
};

// Global dummy observePage for auto-observe verification
global.observePage = (opts) => {
    return {
        tree: "mock-aria-tree",
        elements_count: 42,
        options_received: opts
    };
};

// Load content script
const contentScript = require('../extension/content.js');
const {
    renderLiveIntentHUD,
    setIntent,
    setMilestone,
    handleTakeover,
    handleRelease,
    toggleMinimize,
    updateHudTicker
} = contentScript;

console.log("[Test] Running Spec 21 Live Intent Ticker & Takeover Lockout Shield tests...");

// ----------------------------------------------------------------------------
// 1. Initial Render Test
// ----------------------------------------------------------------------------
renderLiveIntentHUD("Automated Booking Flow", "purple");

const host = global.document.documentElement.getElementById("agentsocket-hud-host");
assert(host, "agentsocket-hud-host must be created and appended to document");
assert(host.shadowRoot, "Host must have an attached shadowRoot");

const shadow = host.shadowRoot;
const pill = shadow.getElementById("ab-control-pill");
const minPill = shadow.getElementById("ab-minimized-pill");
const shield = shadow.getElementById("ab-interaction-shield");
const statusDot = shadow.getElementById("ab-status-dot");
const intentText = shadow.getElementById("ab-intent-text");
const actionSubtext = shadow.getElementById("ab-action-subtext");
const takeoverBtn = shadow.getElementById("ab-takeover-btn");
const minBtn = shadow.getElementById("ab-minimize-btn");

assert(pill, "#ab-control-pill must be rendered inside Shadow DOM");
assert(minPill, "#ab-minimized-pill must be rendered inside Shadow DOM");
assert(shield, "#ab-interaction-shield must be rendered inside Shadow DOM");
assert(statusDot, "#ab-status-dot must exist");
assert(intentText, "#ab-intent-text must exist");
assert(actionSubtext, "#ab-action-subtext must exist");
assert(takeoverBtn, "#ab-takeover-btn must exist");
assert(minBtn, "#ab-minimize-btn must exist");

// Check initial styling/visibility
assert.strictEqual(pill.style.display, "flex", "HUD pill must be visible by default");
assert.strictEqual(minPill.style.display, "none", "Minimized pill must be hidden by default");
assert.strictEqual(statusDot.style.background, "#a6e3a1", "Status dot should be active green");
console.log("✓ Initial HUD layout, status dot, and buttons verified.");

// ----------------------------------------------------------------------------
// 2. Set Intent & Micro-Action Subtext
// ----------------------------------------------------------------------------
setIntent("Searching roundtrip flights to Tokyo", "Selecting departure date", "[Phase 1/3]");
assert.strictEqual(intentText.textContent, "Searching roundtrip flights to Tokyo");
assert.strictEqual(actionSubtext.textContent, "↳ Action: Selecting departure date");

const phaseBadge = shadow.getElementById("ab-phase-badge");
assert(phaseBadge, "#ab-phase-badge must exist");
assert.strictEqual(phaseBadge.textContent, "[Phase 1/3]");
assert.strictEqual(phaseBadge.style.display, "inline-block");
console.log("✓ setIntent updates intent text, micro-action subtext, and phase badge.");

// ----------------------------------------------------------------------------
// 3. Set Milestone Test
// ----------------------------------------------------------------------------
setMilestone("Passenger Information", 2, 4);
assert.strictEqual(intentText.textContent, "Passenger Information");
assert.strictEqual(phaseBadge.textContent, "[Phase 2/4]");
console.log("✓ setMilestone formats phase indicator and updates title.");

// ----------------------------------------------------------------------------
// 4. Minimize / Maximize Toggle Test
// ----------------------------------------------------------------------------
toggleMinimize();
assert.strictEqual(pill.style.display, "none", "Main HUD must hide when minimized");
assert.strictEqual(minPill.style.display, "flex", "Minimized pill must show when minimized");

// Verify click on minimized pill expands it back
minPill.dispatchEvent({ type: "click" });
assert.strictEqual(pill.style.display, "flex", "Clicking minimized pill must restore HUD");
assert.strictEqual(minPill.style.display, "none", "Minimized pill must hide when restored");

// Verify force minimize
toggleMinimize(true);
assert.strictEqual(pill.style.display, "none");
toggleMinimize(false);
assert.strictEqual(pill.style.display, "flex");
console.log("✓ Floating corner minimized pill and toggle mechanics verified.");

// ----------------------------------------------------------------------------
// 5. Operator Takeover Flow Test
// ----------------------------------------------------------------------------
sentMessages.length = 0; // reset
handleTakeover("User needed to solve Cloudflare Captcha");

assert.strictEqual(statusDot.style.background, "#f9e2af", "Status dot must turn amber during takeover");
assert.strictEqual(shield.style.pointerEvents, "none", "Interaction shield pointer events must be none during takeover");
assert.strictEqual(shield.style.display, "none", "Interaction shield must be hidden during takeover");
assert(takeoverBtn.innerHTML.includes("Release to Agent"), "Button text must flip to 'Release to Agent'");
assert(intentText.textContent.includes("Human Takeover Active"), "Intent text must indicate takeover active");

// Verify dispatch of PAGE_TAKEOVER
const takeoverMsg = sentMessages.find(m => m.type === "page_takeover");
assert(takeoverMsg, "PAGE_TAKEOVER runtime message must be dispatched");
assert.strictEqual(takeoverMsg.notes, "User needed to solve Cloudflare Captcha");
console.log("✓ Operator takeover lifts lockout shield, turns dot amber, and notifies background.");

// ----------------------------------------------------------------------------
// 6. Operator Release & Instant Auto-Observe Resumption Flow Test
// ----------------------------------------------------------------------------
sentMessages.length = 0; // reset
const releaseResult = handleRelease("Captcha solved by operator");

assert.strictEqual(statusDot.style.background, "#a6e3a1", "Status dot must return to active green upon release");
assert.strictEqual(shield.style.pointerEvents, "auto", "Interaction shield pointer events must be auto upon release");
assert.strictEqual(shield.style.display, "block", "Interaction shield must be visible upon release");
assert(takeoverBtn.innerHTML.includes("Take Over"), "Button text must flip back to 'Take Over'");

// Verify auto-observe execution & return value
assert.strictEqual(releaseResult.status, "success");
assert.strictEqual(releaseResult.notes, "Captcha solved by operator");
assert(releaseResult.observation, "Release result must contain fresh observation tree");
assert.strictEqual(releaseResult.observation.status, "success");
assert(releaseResult.observation.tree_text !== undefined, "Observation must contain tree_text");

// Verify dispatch of PAGE_RESUME with observation payload (Flaw 4 fix)
const resumeMsg = sentMessages.find(m => m.type === "page_resume");
assert(resumeMsg, "PAGE_RESUME runtime message must be dispatched");
assert.strictEqual(resumeMsg.notes, "Captcha solved by operator");
assert(resumeMsg.observation, "PAGE_RESUME must carry fresh ARIA observation");
assert.strictEqual(resumeMsg.observation.status, "success");
console.log("✓ Release re-engages shield, triggers instant auto-observe, and dispatches PAGE_RESUME.");

// ----------------------------------------------------------------------------
// 7. Message Listener Dispatching Tests (set_intent & set_milestone)
// ----------------------------------------------------------------------------
const listeners = global.chrome.runtime.onMessage._listeners;
assert(listeners.length > 0, "onMessage listener must be registered in content script");
const onMessage = listeners[0];

// Test SET_INTENT message
let intentResp = null;
onMessage({ type: "set_intent", intent: "Final Review", subtext: "Checking order totals", phase: "[Phase 3/3]" }, {}, (res) => { intentResp = res; });
assert.strictEqual(intentResp.status, "success");
assert.strictEqual(intentText.textContent, "Final Review");
assert.strictEqual(actionSubtext.textContent, "↳ Action: Checking order totals");
assert.strictEqual(phaseBadge.textContent, "[Phase 3/3]");

// Test SET_MILESTONE message
let milestoneResp = null;
onMessage({ type: "set_milestone", milestone_title: "Payment Completion", phase_number: 3, total_phases: 3 }, {}, (res) => { milestoneResp = res; });
assert.strictEqual(milestoneResp.status, "success");
assert.strictEqual(intentText.textContent, "Payment Completion");
assert.strictEqual(phaseBadge.textContent, "[Phase 3/3]");

console.log("✓ onMessage triggers for SET_INTENT and SET_MILESTONE verified.");

console.log("\n[PASS] Spec 21 Live Intent Ticker & Shield unit tests passed cleanly! 🎯🛡️✨\n");
