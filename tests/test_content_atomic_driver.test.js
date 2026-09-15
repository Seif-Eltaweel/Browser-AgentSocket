/**
 * Unit tests for Feature Spec 20: Extension Native Atomic Driver & Adaptive Settlement Engine
 * Executed via Node.js
 */

const assert = require('assert');

// Mock events recorder helper
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

// Mock window and document
const scrollHistory = [];
global.window = {
    innerHeight: 800,
    innerWidth: 1280,
    scrollY: 0,
    location: { href: "https://example.com/test-form" },
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollBy: (opts) => { scrollHistory.push({ type: "scrollBy", ...opts }); },
    scrollTo: (opts) => { scrollHistory.push({ type: "scrollTo", ...opts }); },
    getComputedStyle: (el) => ({
        display: "block",
        visibility: "visible",
        opacity: "1",
        cursor: "pointer"
    })
};

// Mock prototype for HTMLInputElement
function MockHTMLInputElement() {
    this._value = "";
    this.tagName = "INPUT";
    this.type = "text";
    this.events = [];
    this.focused = false;
    this.scrolled = false;
}

MockHTMLInputElement.prototype = {
    get value() {
        return this._value;
    },
    set value(val) {
        this._value = val;
    },
    focus() {
        this.focused = true;
        global.document.activeElement = this;
    },
    scrollIntoView() {
        this.scrolled = true;
    },
    dispatchEvent(evt) {
        this.events.push(evt.type);
        return true;
    }
};

global.HTMLInputElement = MockHTMLInputElement;

// Mock prototype for HTMLTextAreaElement
function MockHTMLTextAreaElement() {
    this._value = "";
    this.tagName = "TEXTAREA";
    this.events = [];
    this.focused = false;
    this.scrolled = false;
}

MockHTMLTextAreaElement.prototype = {
    get value() {
        return this._value;
    },
    set value(val) {
        this._value = val;
    },
    focus() {
        this.focused = true;
        global.document.activeElement = this;
    },
    scrollIntoView() {
        this.scrolled = true;
    },
    dispatchEvent(evt) {
        this.events.push(evt.type);
        return true;
    }
};

global.HTMLTextAreaElement = MockHTMLTextAreaElement;

function createMockButton() {
    return {
        tagName: "BUTTON",
        events: [],
        focused: false,
        scrolled: false,
        focus() {
            this.focused = true;
            global.document.activeElement = this;
        },
        scrollIntoView() {
            this.scrolled = true;
        },
        dispatchEvent(evt) {
            this.events.push(evt.type);
            return true;
        }
    };
}

global.document = {
    title: "Atomic Driver Test Page",
    readyState: "complete",
    activeElement: null,
    body: {
        scrollHeight: 3500,
        appendChild: () => {},
        dispatchEvent: (evt) => {}
    },
    documentElement: {
        clientWidth: 1280,
        clientHeight: 800,
        scrollHeight: 3500,
        appendChild: () => {}
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    getElementById: () => null,
    createElement: (tag) => ({
        id: "",
        style: {},
        appendChild: () => {},
        remove: () => {}
    })
};

global.sessionStorage = {
    getItem: () => null,
    setItem: () => {}
};

global.chrome = {
    runtime: {
        lastError: null,
        sendMessage: (msg, cb) => { if (cb) cb({ inActiveSession: false }); },
        onMessage: {
            addListener: () => {}
        }
    }
};

// Load content.js module
const contentScript = require('../extension/content.js');
const {
    actClick,
    actType,
    actScroll,
    actKeyPress,
    waitForSettlement,
    executeAtomicAction
} = contentScript;

console.log("[Test] Running Spec 20 Native Atomic Driver & Settlement tests...");

// Setup registry
window.__agentsocket_elements = new Map();

// ----------------------------------------------------------------------------
// 1. Test actClick
// ----------------------------------------------------------------------------
const testBtn = createMockButton();
window.__agentsocket_elements.set(1, testBtn);

const clickRes = actClick(1);
assert.strictEqual(clickRes.status, "success");
assert.strictEqual(clickRes.action, "click");
assert.strictEqual(clickRes.element_id, 1);
assert.strictEqual(testBtn.focused, true, "Button should be focused");
assert.strictEqual(testBtn.scrolled, true, "Button should be scrolled into view");
assert.deepStrictEqual(
    testBtn.events,
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'],
    "Full native click sequence should be dispatched"
);
console.log("✓ actClick event chain, focus, and scroll verified.");

// ----------------------------------------------------------------------------
// 2. Test actType with prototype descriptor override bypass
// ----------------------------------------------------------------------------
const testInput = new MockHTMLInputElement();
testInput.value = "initial_";

// Simulate React hijacking the element's 'value' property
let reactStateValue = "";
Object.defineProperty(testInput, 'value', {
    configurable: true,
    enumerable: true,
    get() {
        return reactStateValue;
    },
    set(val) {
        // In React, this setter triggers internal warnings or is ignored
        reactStateValue = val;
    }
});

window.__agentsocket_elements.set(2, testInput);

const typeRes = actType(2, "new_input", { clearFirst: false, pressEnter: true });
assert.strictEqual(typeRes.status, "success");
assert.strictEqual(typeRes.action, "type");
assert.strictEqual(testInput.focused, true);
assert.strictEqual(testInput.scrolled, true);
assert(testInput.events.includes('input'), "Input event must be dispatched");
assert(testInput.events.includes('change'), "Change event must be dispatched");
assert(testInput.events.includes('keydown'), "Enter keydown event must be dispatched");
assert(testInput.events.includes('keyup'), "Enter keyup event must be dispatched");

// Verify prototype setter was called directly (bypassing custom descriptor)
assert.strictEqual(testInput._value, "initial_new_input", "Prototype setter updated underlying _value");
console.log("✓ actType React-prototype bypass and event dispatching verified.");

// Test clearFirst
const clearRes = actType(2, "replaced", { clearFirst: true, pressEnter: false });
assert.strictEqual(testInput._value, "replaced", "clearFirst: true should clear value before appending");
console.log("✓ actType clearFirst verified.");

// ----------------------------------------------------------------------------
// 3. Test actScroll
// ----------------------------------------------------------------------------
scrollHistory.length = 0;
actScroll("down", 400);
assert.strictEqual(scrollHistory[0].type, "scrollBy");
assert.strictEqual(scrollHistory[0].top, 400);

actScroll("up", 200);
assert.strictEqual(scrollHistory[1].top, -200);

actScroll("top");
assert.strictEqual(scrollHistory[2].type, "scrollTo");
assert.strictEqual(scrollHistory[2].top, 0);

actScroll("bottom");
assert.strictEqual(scrollHistory[3].type, "scrollTo");
assert.strictEqual(scrollHistory[3].top, 3500);
console.log("✓ actScroll directions (down, up, top, bottom) verified.");

// ----------------------------------------------------------------------------
// 4. Test actKeyPress
// ----------------------------------------------------------------------------
const keyTarget = createMockButton();
global.document.activeElement = keyTarget;

const keyRes = actKeyPress("Escape");
assert.strictEqual(keyRes.status, "success");
assert.strictEqual(keyRes.action, "key_press");
assert.strictEqual(keyRes.key, "Escape");
assert.deepStrictEqual(keyTarget.events, ['keydown', 'keypress', 'keyup']);
console.log("✓ actKeyPress key dispatch verified.");

// ----------------------------------------------------------------------------
// 5. Test waitForSettlement
// ----------------------------------------------------------------------------
(async () => {
    // Quick settlement test (quiescence timeout 50ms for unit test)
    const settleStart = Date.now();
    const settleRes = await waitForSettlement({ quiescenceMs: 50, maxWaitMs: 300 });
    const settleElapsed = Date.now() - settleStart;

    assert.strictEqual(settleRes.settle_reason, "quiescence");
    assert(settleElapsed >= 45, "Settlement should wait for quiescence window");
    console.log("✓ waitForSettlement quiescence window verified.");

    // ------------------------------------------------------------------------
    // 6. Test executeAtomicAction (Unified Interface)
    // ------------------------------------------------------------------------
    const execClick = await executeAtomicAction({
        action: "click",
        element_id: 1,
        wait_settle: false
    });
    assert.strictEqual(execClick.status, "success");
    assert.strictEqual(execClick.action, "click");
    assert.strictEqual(execClick.element_id, 1);
    assert.strictEqual(execClick.settle_reason, "skipped");

    const execType = await executeAtomicAction({
        action: "type",
        element_id: 2,
        text: "_appended",
        wait_settle: true,
        settlement_options: { quiescenceMs: 40, maxWaitMs: 200 }
    });
    assert.strictEqual(execType.status, "success");
    assert.strictEqual(execType.action, "type");
    assert.strictEqual(execType.settle_reason, "quiescence");

    // ------------------------------------------------------------------------
    // 7. Test Error Handling
    // ------------------------------------------------------------------------
    let errorCaught = false;
    try {
        await executeAtomicAction({
            action: "click",
            element_id: 9999, // non-existent
            wait_settle: false
        });
    } catch (e) {
        errorCaught = true;
        assert(e.message.includes("not found in element registry"));
    }
    assert.strictEqual(errorCaught, true, "Missing element ID must throw registry error");
    console.log("✓ Missing element registry error handling verified.");

    console.log("\n[PASS] Spec 20 unit tests passed cleanly! 🕹️⚡✨\n");
})();
