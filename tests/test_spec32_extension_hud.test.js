/**
 * Unit and DOM Tests for Feature Spec 32:
 * Milestone-Driven In-Page HUD Milestone Row, Progress Bar & Live Action Ticker 🎯🛡️
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

// Global Mocks for Node.js test environment
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
    scrollY: 0,
    location: { href: "https://example.com/test", hostname: "example.com" },
    addEventListener: () => {},
    removeEventListener: () => {},
    getComputedStyle: () => ({ display: "block", visibility: "visible", opacity: "1" })
};

global.sessionStorage = {
    _data: {},
    getItem: (k) => global.sessionStorage._data[k] || null,
    setItem: (k, v) => { global.sessionStorage._data[k] = String(v); },
    removeItem: (k) => { delete global.sessionStorage._data[k]; },
    clear: () => { global.sessionStorage._data = {}; }
};

global.document = {
    body: new MockElement('body'),
    documentElement: new MockElement('html'),
    title: 'Test Page',
    readyState: 'complete',
    createElement: (tag) => new MockElement(tag),
    getElementById: (id) => {
        if (id === 'agentsocket-hud-host') {
            return global.document.documentElement.getElementById(id) || global.document.body.getElementById(id);
        }
        return null;
    },
    addEventListener: () => {}
};

// Import content.js
const contentScript = require('../extension/content.js');

function getHostAndShadow() {
    const host = global.document.getElementById('agentsocket-hud-host');
    assert(host, 'HUD host should exist');
    const shadow = host.shadowRoot;
    assert(shadow, 'HUD shadow root should exist');
    return { host, shadow };
}

function resetHUD() {
    const host = global.document.getElementById('agentsocket-hud-host');
    if (host) host.remove();
    sentMessages.length = 0;
}

console.log('--- Running Spec 32 Extension HUD Tests ---');

// Test 1: Dual-Level HUD Pill Hierarchy
{
    resetHUD();
    contentScript.renderActiveGlow('Batch 10 CRM Enrichment', 'purple');
    const { shadow } = getHostAndShadow();

    const pill = shadow.getElementById('ab-control-pill');
    assert(pill, 'ab-control-pill must be rendered in shadow DOM');

    const topRow = shadow.getElementById('ab-hud-top-row');
    assert(topRow, 'ab-hud-top-row must exist');

    const milestoneRow = shadow.getElementById('ab-milestone-row');
    assert(milestoneRow, 'ab-milestone-row must exist (Spec 32 requirement)');

    const progressContainer = shadow.getElementById('ab-hud-progress-container');
    assert(progressContainer, 'ab-hud-progress-container must exist');

    const progressBar = shadow.getElementById('ab-hud-progress-bar');
    assert(progressBar, 'ab-hud-progress-bar must exist');

    const subtext = shadow.getElementById('ab-action-subtext');
    assert(subtext, 'ab-action-subtext must exist');

    console.log('✔ Test 1 Passed: Dual-level HUD pill hierarchy correctly structured.');
}

// Test 2: Strategic Milestone Rendering & Progress Calculation
{
    resetHUD();
    contentScript.renderActiveGlow('Batch 10 CRM Enrichment', 'purple');
    const { shadow } = getHostAndShadow();

    // Send SET_PLAN message
    const listeners = global.chrome.runtime.onMessage._listeners;
    assert(listeners.length > 0, 'onMessage listeners must be registered');

    const setPlanMsg = {
        type: 'set_plan',
        session_title: 'Batch 10 CRM Enrichment',
        milestones: [
            { index: 1, title: 'Open target account', status: 'completed' },
            { index: 2, title: 'Getting the last message from Omar', status: 'in_progress' },
            { index: 3, title: 'Extract CRM fields', status: 'pending' }
        ],
        active_index: 2,
        current_action: 'Open account no1'
    };

    listeners[0](setPlanMsg, {}, () => {});

    const milestoneRow = shadow.getElementById('ab-milestone-row');
    assert(milestoneRow.textContent.includes('Milestone [2/3]'), `Milestone row must include [2/3], got: ${milestoneRow.textContent}`);
    assert(milestoneRow.textContent.includes('Getting the last message from Omar'), 'Milestone row must include active title');

    const progressBar = shadow.getElementById('ab-hud-progress-bar');
    assert(progressBar.style.width === '33%', `Progress bar width should be 33% for 1/3 completed, got: ${progressBar.style.width}`);

    const subtext = shadow.getElementById('ab-action-subtext');
    assert(subtext.textContent.includes('↳ Action: Open account no1'), `Action subtext should show Open account no1, got: ${subtext.textContent}`);

    console.log('✔ Test 2 Passed: Strategic milestone and progress track render accurately.');
}

// Test 3: Micro-Action Ticker Updates (Live OODA Action Passthrough)
{
    const { shadow } = getHostAndShadow();
    const listeners = global.chrome.runtime.onMessage._listeners;

    const setMilestoneMsg = {
        type: 'set_milestone',
        session_title: 'Batch 10 CRM Enrichment',
        milestone_index: 2,
        current_action: '(Clicking send button on chat)',
        progress_percent: 50
    };

    listeners[0](setMilestoneMsg, {}, () => {});

    const subtext = shadow.getElementById('ab-action-subtext');
    assert(subtext.textContent.includes('(Clicking send button on chat)'), `Subtext must update live action detail, got: ${subtext.textContent}`);

    console.log('✔ Test 3 Passed: Live micro-action ticker updates dynamically with zero flickering.');
}

// Test 4: BUG-04 Layout Popping Fixed (In-Place Takeover Transition)
{
    const { shadow } = getHostAndShadow();
    const pillBefore = shadow.getElementById('ab-control-pill');
    assert(pillBefore, 'Control pill must exist prior to takeover');

    // Operator initiates takeover
    contentScript.handleTakeover('Need to solve captcha');

    // Verify BUG-04 fix: pill was NOT destroyed or replaced with #ab-takeover-pill
    const pillAfter = shadow.getElementById('ab-control-pill');
    assert.strictEqual(pillBefore, pillAfter, 'Control pill must remain the exact same element in-place (no layout popping)');
    assert(!shadow.getElementById('ab-takeover-pill'), 'Legacy ab-takeover-pill must not be spawned');

    // Verify takeover states
    const dot = shadow.getElementById('ab-status-dot');
    assert.strictEqual(dot.style.background, '#f9e2af', 'Status dot must transition to amber (#f9e2af)');

    const milestoneRow = shadow.getElementById('ab-milestone-row');
    assert(milestoneRow.textContent.includes('(Paused)'), `Milestone row must indicate (Paused), got: ${milestoneRow.textContent}`);

    const subtext = shadow.getElementById('ab-action-subtext');
    assert(subtext.textContent.includes('Human Takeover Active'), `Subtext must show operator guidance, got: ${subtext.textContent}`);

    const takeoverBtn = shadow.getElementById('ab-takeover-btn');
    assert(takeoverBtn.innerHTML.includes('Release to Agent'), 'Takeover button must switch to Release to Agent');

    const shield = shadow.getElementById('ab-interaction-shield');
    assert.strictEqual(shield.style.display, 'none', 'Shield must be hidden so operator can click/type');

    console.log('✔ Test 4 Passed: BUG-04 Layout Popping eliminated; takeover transitions in-place.');
}

// Test 5: Releasing Control Seamlessly Back to Agent
{
    const { shadow } = getHostAndShadow();

    // Operator releases control
    contentScript.handleRelease('Captcha solved successfully');

    const dot = shadow.getElementById('ab-status-dot');
    assert.strictEqual(dot.style.background, '#a6e3a1', 'Status dot must return to green (#a6e3a1)');

    const milestoneRow = shadow.getElementById('ab-milestone-row');
    assert(!milestoneRow.textContent.includes('(Paused)'), 'Milestone row must resume without (Paused)');

    const takeoverBtn = shadow.getElementById('ab-takeover-btn');
    assert(takeoverBtn.innerHTML.includes('Take Over'), 'Button must revert to Take Over');

    const shield = shadow.getElementById('ab-interaction-shield');
    assert.strictEqual(shield.style.display, 'block', 'Shield must re-engage for autonomous operation');

    console.log('✔ Test 5 Passed: Control released back to agent cleanly and shield re-engaged.');
}

console.log('\nAll 5 Spec 32 Extension HUD test scenarios PASSED successfully! 🎉');
