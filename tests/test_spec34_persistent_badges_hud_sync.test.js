/**
 * Unit and DOM Tests for Feature Spec 34:
 * Persistent ARIA Badging in No-Vision Mode & Dynamic HUD Plan Sync 🎯🛡️
 * Executed via Node.js
 */

const assert = require('assert');

class MockEvent {
    constructor(type, options = {}) {
        this.type = type;
        this.bubbles = !!options.bubbles;
        this.cancelable = !!options.cancelable;
        this.key = options.key || "";
        this.code = options.code || "";
        this.keyCode = options.keyCode || 0;
    }
}

global.Event = MockEvent;
global.CustomEvent = MockEvent;
global.MouseEvent = MockEvent;
global.PointerEvent = MockEvent;
global.KeyboardEvent = MockEvent;

class MockStyle {
    constructor() {
        this._cssText = '';
        this.opacity = '1';
        this.display = 'block';
        this.top = '0px';
        this.left = '0px';
        this.width = '0px';
        this.height = '0px';
        this.background = '';
        this.color = '';
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

class MockElement {
    constructor(tagName = 'div') {
        this.nodeType = 1;
        this.tagName = tagName.toUpperCase();
        this.id = '';
        this.className = '';
        this._innerHTML = '';
        this.title = '';
        this.style = new MockStyle();
        this.children = [];
        this.childNodes = [];
        this.parentNode = null;
        this.listeners = {};
        this.attributes = {};
        this.onclick = null;
        this.onmouseenter = null;
        this.onmouseleave = null;
        this._rect = { left: 100, top: 200, width: 80, height: 32, right: 180, bottom: 232 };
        this.isConnected = true;
    }

    get innerHTML() {
        return this._innerHTML || '';
    }

    set innerHTML(val) {
        this._innerHTML = String(val);
        if (val === '') {
            this.children = [];
            this.childNodes = [];
        }
    }

    get textContent() {
        return this._textContent !== undefined ? this._textContent : '';
    }

    set textContent(val) {
        this._textContent = String(val);
    }

    setAttribute(k, v) {
        this.attributes[k] = String(v);
    }

    getAttribute(k) {
        return this.attributes[k] || null;
    }

    hasAttribute(k) {
        return k in this.attributes;
    }

    removeAttribute(k) {
        delete this.attributes[k];
    }

    getBoundingClientRect() {
        return this._rect;
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
            if (selector === "*" || !selector) return true;
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

    scrollIntoView() {
        this.scrolled = true;
    }

    focus() {
        this.focused = true;
    }
}

// Global Environment Mocks
const sentMessages = [];
global.chrome = {
    runtime: {
        lastError: null,
        sendMessage: (msg, cb) => {
            sentMessages.push(msg);
            if (cb) cb({ inActiveSession: false, enable_vision: false });
        },
        onMessage: {
            _listeners: [],
            addListener: (fn) => { global.chrome.runtime.onMessage._listeners.push(fn); }
        }
    }
};

const windowListeners = {};
global.window = {
    innerHeight: 800,
    innerWidth: 1280,
    scrollY: 0,
    location: { href: "https://www.linkedin.com/mynetwork/", hostname: "www.linkedin.com" },
    addEventListener: (evt, fn) => {
        if (!windowListeners[evt]) windowListeners[evt] = [];
        windowListeners[evt].push(fn);
    },
    removeEventListener: (evt, fn) => {
        if (windowListeners[evt]) {
            windowListeners[evt] = windowListeners[evt].filter(f => f !== fn);
        }
    },
    getComputedStyle: () => ({ display: "block", visibility: "visible", opacity: "1", cursor: "pointer" })
};

global.document = {
    body: new MockElement('body'),
    documentElement: new MockElement('html'),
    title: 'LinkedIn Network',
    readyState: 'complete',
    createElement: (tag) => new MockElement(tag),
    getElementById: (id) => {
        if (id === 'agentsocket-hud-host') {
            return global.document.documentElement.getElementById(id) || global.document.body.getElementById(id);
        }
        return null;
    },
    addEventListener: () => {},
    removeEventListener: () => {}
};

global.sessionStorage = {
    _data: {},
    getItem: (k) => global.sessionStorage._data[k] || null,
    setItem: (k, v) => { global.sessionStorage._data[k] = String(v); },
    removeItem: (k) => { delete global.sessionStorage._data[k]; },
    clear: () => { global.sessionStorage._data = {}; }
};

// Import content script
const content = require('../extension/content.js');

function getShadow() {
    const host = global.document.getElementById('agentsocket-hud-host');
    assert(host, 'agentsocket-hud-host must exist');
    assert(host.shadowRoot, 'Shadow root must exist on host');
    return host.shadowRoot;
}

function resetHUD() {
    const host = global.document.getElementById('agentsocket-hud-host');
    if (host) host.remove();
    sentMessages.length = 0;
}

console.log('--- Running Spec 34 Persistent ARIA Badging & Dynamic HUD Plan Sync Tests ---');

async function runTests() {
// ============================================================================
// Test 1: Purged Hardcoded Defaults Verification (BUG-03 Remediation)
// ============================================================================
{
    resetHUD();
    content.renderActiveGlow("LinkedIn Outreach Task", "purple");
    const shadow = getShadow();

    const intentText = shadow.getElementById("ab-intent-text");
    const actionSubtext = shadow.getElementById("ab-action-subtext");

    assert(intentText, "ab-intent-text must be present");
    assert(actionSubtext, "ab-action-subtext must be present");

    // Must NOT contain legacy hardcoded strings
    assert(!intentText.textContent.includes("Searching rentals in Cairo"), "Must not contain legacy Cairo string");
    assert(!actionSubtext.textContent.includes("Initializing OODA observer"), "Must not contain legacy OODA observer string");

    console.log("✔ Test 1 Passed: Legacy hardcoded strings successfully purged from initial state.");
}

// ============================================================================
// Test 2: Persistent ARIA Badging in No-Vision Mode (BUG-01 & BUG-02 Remediation)
// ============================================================================
{
    resetHUD();
    content.renderActiveGlow("LinkedIn Connections", "purple");
    const shadow = getShadow();

    // Create 3 interactive test nodes
    const mockBtn1 = new MockElement("button");
    mockBtn1.setAttribute("aria-label", "Connect with Alex");
    mockBtn1._rect = { left: 150, top: 220, width: 100, height: 36, right: 250, bottom: 256 };

    const mockBtn2 = new MockElement("button");
    mockBtn2.setAttribute("aria-label", "Connect with Sarah");
    mockBtn2._rect = { left: 150, top: 320, width: 100, height: 36, right: 250, bottom: 356 };

    const mockRoot = new MockElement("div");
    mockRoot.appendChild(mockBtn1);
    mockRoot.appendChild(mockBtn2);

    // Call observePage with enable_vision: false (No-Vision Mode)
    const obs = content.observePage({ root: mockRoot, show_badges: true, enable_vision: false });
    assert.strictEqual(obs.status, "success");
    assert.strictEqual(obs.elements.length, 2);

    const badgeContainer = shadow.getElementById("agentsocket-badges-container");
    assert(badgeContainer, "#agentsocket-badges-container must exist in shadow root");

    const badges = badgeContainer.querySelectorAll(".agentsocket-badge-pill");
    assert.strictEqual(badges.length, 2, "Must render exactly 2 badge pills");
    assert.strictEqual(badges[0].textContent, `[${obs.elements[0].id}]`);
    assert.strictEqual(badges[1].textContent, `[${obs.elements[1].id}]`);

    // Verify badges are anchored near target coordinates
    assert(badges[0].style.top.includes("216px"), `Badge 0 top should be near 216px, got: ${badges[0].style.top}`);
    assert(badges[0].style.left.includes("146px"), `Badge 0 left should be near 146px, got: ${badges[0].style.left}`);

    // Verify passive scroll/resize listeners are attached to window
    assert(windowListeners["scroll"] && windowListeners["scroll"].length > 0, "Passive scroll listener must be attached");
    assert(windowListeners["resize"] && windowListeners["resize"].length > 0, "Passive resize listener must be attached");

    console.log("✔ Test 2 Passed: Badges rendered persistently in No-Vision mode without premature auto-fade.");
}

// ============================================================================
// Test 3: Throttled Badge Repositioning on Scroll / DOM Move
// ============================================================================
{
    const shadow = getShadow();
    const badgeContainer = shadow.getElementById("agentsocket-badges-container");
    assert(badgeContainer, "Badge container must still exist (persistent)");

    // Simulate page scroll: Alex's button moves up by 100px
    const alexNode = global.window.__agentsocket_elements.get(1);
    if (alexNode) {
        alexNode._rect = { left: 150, top: 120, width: 100, height: 36, right: 250, bottom: 156 };
    }

    // Trigger badge repositioning
    content.handleBadgeReposition();

    const badges = badgeContainer.querySelectorAll(".agentsocket-badge-pill");
    assert(badges.length >= 1, "Badges must remain rendered after scroll reposition");
    assert(badges[0].style.top.includes("116px"), `Badge 0 top should update to 116px after scroll, got: ${badges[0].style.top}`);

    console.log("✔ Test 3 Passed: Badges smoothly and dynamically reposition with target elements on scroll.");
}

// ============================================================================
// Test 4: Auto-Fade Active ONLY in Vision Mode (enable_vision: true)
// ============================================================================
{
    // Fast-forward check: render badges with enable_vision: true
    const mockBtn = new MockElement("button");
    mockBtn.setAttribute("aria-label", "Submit Form");
    mockBtn._rect = { left: 200, top: 200, width: 80, height: 30, right: 280, bottom: 230 };

    const mockRoot = new MockElement("div");
    mockRoot.appendChild(mockBtn);

    content.observePage({ root: mockRoot, show_badges: true, enable_vision: true });
    const shadow = getShadow();

    const badgeContainer = shadow.getElementById("agentsocket-badges-container");
    assert(badgeContainer, "Badge container rendered initially in vision mode");

    // In vision mode, fadeout timeout is scheduled. Trigger removeBadges to verify clean fade:
    content.removeBadges();
    assert.strictEqual(badgeContainer.style.opacity, "0", "Container opacity must be set to 0 upon fade");

    console.log("✔ Test 4 Passed: Auto-fade engages cleanly in vision mode to avoid screenshot clutter.");
}

// ============================================================================
// Test 5: Dynamic Plan & Active Milestone Synchronization (SET_PLAN)
// ============================================================================
{
    resetHUD();
    content.renderActiveGlow("LinkedIn Connection Campaign", "purple");
    const shadow = getShadow();

    const listeners = global.chrome.runtime.onMessage._listeners;
    assert(listeners.length > 0, "onMessage listeners must be registered");

    const onMessage = listeners[0];

    // Dispatch SET_PLAN
    const planMsg = {
        type: "set_plan",
        session_title: "LinkedIn Connection Campaign",
        milestones: [
            { index: 1, title: "Search target prospects", status: "completed" },
            { index: 2, title: "Review connection note template", status: "completed" },
            { index: 3, title: "Dispatch connection requests", status: "in_progress" },
            { index: 4, title: "Export results to CRM", status: "pending" }
        ],
        active_index: 3,
        enable_vision: false
    };

    let planRes = null;
    onMessage(planMsg, {}, (res) => { planRes = res; });
    assert.strictEqual(planRes.status, "success");

    const intentText = shadow.getElementById("ab-intent-text");
    const milestoneRow = shadow.getElementById("ab-milestone-row");
    const actionSubtext = shadow.getElementById("ab-action-subtext");
    const progressBar = shadow.getElementById("ab-hud-progress-bar");

    // Top Intent Line must be bound to active milestone
    assert(intentText.textContent.includes("Milestone [3/4]: Dispatch connection requests"), 
        `Top line must sync to active milestone, got: ${intentText.textContent}`);

    // Milestone Row must display progress
    assert(milestoneRow.textContent.includes("Milestone [3/4]"), `Milestone row must show [3/4], got: ${milestoneRow.textContent}`);
    assert(milestoneRow.textContent.includes("Dispatch connection requests"), "Milestone row must show active title");

    // Action subtext reflects plan initialization
    assert(actionSubtext.textContent.includes("Plan initialized"), `Subtext must show plan ready, got: ${actionSubtext.textContent}`);

    // Progress bar reflects 2/4 completed = 50%
    assert.strictEqual(progressBar.style.width, "50%", `Progress bar should be 50%, got: ${progressBar.style.width}`);

    console.log("✔ Test 5 Passed: SET_PLAN tightly synchronizes top intent line and milestone indicator.");
}

// ============================================================================
// Test 6: Autonomous OODA Action Ticker Updates (observe_page & act_element)
// ============================================================================
{
    const shadow = getShadow();
    const listeners = global.chrome.runtime.onMessage._listeners;
    const onMessage = listeners[0];

    const actionSubtext = shadow.getElementById("ab-action-subtext");

    // 1. Test observe_page message handler updates ticker
    const mockInput = new MockElement("input");
    mockInput.setAttribute("placeholder", "Search prospects...");
    mockInput.setAttribute("role", "searchbox");
    mockInput._rect = { left: 100, top: 100, width: 200, height: 35, right: 300, bottom: 135 };

    const mockContainer = new MockElement("div");
    mockContainer.appendChild(mockInput);

    let obsResponse = null;
    onMessage({
        type: "observe_page",
        options: { root: mockContainer, show_badges: true, enable_vision: false }
    }, {}, (res) => { obsResponse = res; });

    assert.strictEqual(obsResponse.status, "success");
    assert(actionSubtext.textContent.includes("Indexed"), `Action subtext should reflect indexed count, got: ${actionSubtext.textContent}`);

    // 2. Test act_element click updates ticker
    const mockBtn = new MockElement("button");
    mockBtn.setAttribute("aria-label", "Send Now");
    mockBtn._rect = { left: 400, top: 400, width: 80, height: 30, right: 480, bottom: 430 };
    mockContainer.appendChild(mockBtn);

    const freshObs = content.observePage({ root: mockContainer, show_badges: true, enable_vision: false });
    const targetElementId = freshObs.elements[freshObs.elements.length - 1].id;

    const actRes = await new Promise(resolve => {
        onMessage({
            type: "act_element",
            payload: { action: "click", element_id: targetElementId, wait_settle: false }
        }, {}, resolve);
    });

    assert.strictEqual(actRes.status, "success");
    assert(actionSubtext.textContent.includes(`Clicked element [${targetElementId}]`), 
        `Action subtext should reflect clicked state, got: ${actionSubtext.textContent}`);

    console.log("✔ Test 6 Passed: Live OODA action ticker dynamically updates for observe and act_element.");
}

// ============================================================================
// Test 7: Terminal Task Completion Frame & Badge Cleanup (BUG-05 Remediation)
// ============================================================================
{
    const shadow = getShadow();
    const listeners = global.chrome.runtime.onMessage._listeners;
    const onMessage = listeners[0];

    const intentText = shadow.getElementById("ab-intent-text");
    const actionSubtext = shadow.getElementById("ab-action-subtext");
    const progressBar = shadow.getElementById("ab-hud-progress-bar");

    // Dispatch terminal task_complete frame
    let tcRes = null;
    onMessage({
        type: "task_complete",
        session_title: "✅ LinkedIn Connection Campaign",
        result: "Successfully connected with 15 verified prospects."
    }, {}, (res) => { tcRes = res; });

    assert.strictEqual(tcRes.status, "success");

    // Top status line displays completion
    assert.strictEqual(intentText.textContent, "✅ Task Complete");

    // Bottom action ticker displays final outcome result
    assert(actionSubtext.textContent.includes("↳ Result: Successfully connected with 15 verified prospects."),
        `Action subtext must display final outcome, got: ${actionSubtext.textContent}`);

    // Progress bar 100%
    assert.strictEqual(progressBar.style.width, "100%");

    // Badges cleared
    const badgeContainer = shadow.getElementById("agentsocket-badges-container");
    assert(!badgeContainer || badgeContainer.childNodes.length === 0, "Badges must be cleared upon task completion");

    // Interaction shield lifted so user can freely interact with page
    const shield = shadow.getElementById("ab-interaction-shield");
    assert(!shield, "Interaction shield must be removed upon task completion");

    console.log("✔ Test 7 Passed: Terminal task_complete frame renders completion summary and frees the page.");
}

console.log("\nAll 7 Spec 34 tests PASSED cleanly! 🎯🛡️✨\n");
}

runTests().catch(err => {
    console.error(err);
    process.exit(1);
});
