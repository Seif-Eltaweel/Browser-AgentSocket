/**
 * Unit tests for Spec 19: ARIA TreeWalker & Ephemeral Numeric Badging
 * Executed via Node.js
 */

const assert = require('assert');

// Mock browser DOM environment for Node.js testing
global.window = {
    innerHeight: 800,
    innerWidth: 1280,
    scrollY: 0,
    location: { href: "https://example.com/test-page" },
    addEventListener: () => {},
    removeEventListener: () => {},
    getComputedStyle: (el) => ({
        display: el.style?.display || "block",
        visibility: el.style?.visibility || "visible",
        opacity: el.style?.opacity || "1",
        cursor: el.style?.cursor || "default"
    })
};

global.document = {
    title: "Test OODA Page",
    readyState: "complete",
    documentElement: { clientWidth: 1280, clientHeight: 800, appendChild: () => {} },
    body: { appendChild: () => {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    getElementById: () => null,
    createElement: (tag) => ({
        id: "",
        className: "",
        style: {},
        appendChild: () => {},
        remove: () => {},
        setAttribute: () => {},
        getAttribute: () => null
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

// Helper to create mock DOM elements
function createMockElement(tagName, options = {}) {
    const el = {
        nodeType: 1,
        tagName: tagName.toUpperCase(),
        type: options.type || (tagName.toUpperCase() === "INPUT" ? "text" : null),
        id: options.id || "",
        name: options.name || "",
        placeholder: options.placeholder || "",
        value: options.value !== undefined ? options.value : "",
        innerText: options.innerText || "",
        textContent: options.innerText || "",
        disabled: !!options.disabled,
        isConnected: true,
        children: options.children || [],
        attributes: options.attributes || {},
        style: options.style || {},
        labels: options.labelText ? [{ innerText: options.labelText }] : [],
        options: options.selectOptions ? options.selectOptions.map(t => ({ text: t })) : [],
        selectedIndex: options.selectedIndex !== undefined ? options.selectedIndex : 0,
        hasAttribute(attr) {
            return attr in this.attributes;
        },
        getAttribute(attr) {
            return this.attributes[attr] !== undefined ? this.attributes[attr] : null;
        },
        getBoundingClientRect() {
            return options.rect || { left: 10, top: 20, width: 100, height: 40 };
        }
    };
    return el;
}

const content = require('../extension/content.js');

console.log('[Test] Running Spec 19 ARIA TreeWalker & Badging tests...');

// 1. Test Interactive Element Filtering
const btn = createMockElement("BUTTON", { innerText: "Submit Order" });
assert.strictEqual(content.isInteractiveElement(btn), true, "Button should be interactive");

const disabledBtn = createMockElement("BUTTON", { innerText: "Disabled", disabled: true });
assert.strictEqual(content.isInteractiveElement(disabledBtn), false, "Disabled button must not be interactive");

const input = createMockElement("INPUT", { type: "text", placeholder: "Search here" });
assert.strictEqual(content.isInteractiveElement(input), true, "Text input should be interactive");

const hiddenInput = createMockElement("INPUT", { type: "hidden" });
assert.strictEqual(content.isInteractiveElement(hiddenInput), false, "Hidden input must not be interactive");

const link = createMockElement("A", { attributes: { href: "/details" }, innerText: "View Details" });
assert.strictEqual(content.isInteractiveElement(link), true, "Link with href should be interactive");

const plainDiv = createMockElement("DIV", { innerText: "Just text content" });
assert.strictEqual(content.isInteractiveElement(plainDiv), false, "Plain div must not be interactive");

const roleBtn = createMockElement("DIV", { attributes: { role: "button" }, innerText: "Custom Pill" });
assert.strictEqual(content.isInteractiveElement(roleBtn), true, "Role=button should be interactive");

console.log('✓ Element interactivity filters verified.');

// 2. Test Zero-Knowledge Secret Masking
const passwordInput = createMockElement("INPUT", { type: "password", value: "SuperSecret123" });
assert.strictEqual(content.extractElementValue(passwordInput), "[REDACTED]", "Password values must be strictly [REDACTED]");

const normalInput = createMockElement("INPUT", { type: "text", value: "Zamalek Apartment" });
assert.strictEqual(content.extractElementValue(normalInput), "Zamalek Apartment", "Normal input values should be preserved");

console.log('✓ Zero-Knowledge secret masking verified.');

// 3. Test TreeWalker & Serialized ARIA Tree
const heading = createMockElement("H1", { innerText: "Real Estate Cairo" });
const searchInput = createMockElement("INPUT", { type: "text", placeholder: "Enter neighborhood", id: "search-input" });
const filterSelect = createMockElement("SELECT", { 
    name: "property_type", 
    selectOptions: ["Apartment", "Villa"], 
    selectedIndex: 0 
});
const submitBtn = createMockElement("BUTTON", { innerText: "Search" });

const mockRoot = {
    querySelectorAll: () => [heading, searchInput, filterSelect, submitBtn]
};

const observation = content.observePage({ root: mockRoot, show_badges: false });
assert.strictEqual(observation.status, "success");
assert.strictEqual(observation.url, "https://example.com/test-page");
assert.strictEqual(observation.title, "Test OODA Page");
assert.strictEqual(observation.elements.length, 3, "Should index 3 interactive elements");

// Check IDs are sequential integers 1, 2, 3
assert.strictEqual(observation.elements[0].id, 1);
assert.strictEqual(observation.elements[1].id, 2);
assert.strictEqual(observation.elements[2].id, 3);

// Verify tree text format
assert.ok(observation.tree_text.includes("Heading 1: Real Estate Cairo"));
assert.ok(observation.tree_text.includes('[1]'));
assert.ok(observation.tree_text.includes('[2]'));
assert.ok(observation.tree_text.includes('[3]'));
assert.ok(observation.tree_text.includes('"Search"'));

console.log('✓ observePage and ARIA TreeWalker serialization verified.');
console.log('\n[PASS] Spec 19 unit tests passed cleanly! 👁️🏷️✨');
