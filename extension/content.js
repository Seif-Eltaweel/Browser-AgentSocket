// content.js - AgentSocket On-Page HUD & Execution Interactivity (Shadow DOM Isolated)
console.log('[AgentSocket] Content script active (Shadow DOM Encapsulated).');

const MT = (typeof MessageTypes !== "undefined") ? MessageTypes : (window.AgentSocketProtocol ? window.AgentSocketProtocol.MessageTypes : {
    SHOW_GLOW: "show_glow",
    SHOW_TAKEOVER: "show_takeover",
    HIDE_GLOW: "hide_glow",
    PAGE_TAKEOVER: "page_takeover",
    PAGE_STOP: "page_stop",
    PAGE_RESUME: "page_resume",
    UPDATE_PROGRESS: "update_progress"
});

let currentSessionTitle = "AgentSocket Task";
let currentGroupColor = "purple";
let isShieldActive = false;
let isTakeoverActive = false;
let tooltipTimeout = null;
let currentProgress = {
    percent: 0,
    currentStep: 0,
    totalSteps: 0,
    stepTitle: ""
};

function computeProgressPercent(data) {
    if (!data) return 0;
    if (typeof data.percent === "number" && !isNaN(data.percent) && data.percent > 0) {
        return Math.min(Math.max(data.percent, 0), 100);
    }
    if (data.totalSteps > 0 && typeof data.currentStep === "number" && data.currentStep > 0) {
        return Math.min(Math.max(Math.round((data.currentStep / data.totalSteps) * 100), 0), 100);
    }
    if (typeof data.percent === "number" && !isNaN(data.percent)) {
        return Math.min(Math.max(data.percent, 0), 100);
    }
    return 0;
}

// Client-side progress persistence
function loadStoredProgress() {
    try {
        const stored = sessionStorage.getItem("agentsocket_hud_progress");
        if (stored) {
            const parsed = JSON.parse(stored);
            if (parsed && typeof parsed === "object") {
                currentProgress.percent = parsed.percent ?? currentProgress.percent;
                currentProgress.currentStep = parsed.currentStep ?? currentProgress.currentStep;
                currentProgress.totalSteps = parsed.totalSteps ?? currentProgress.totalSteps;
                currentProgress.stepTitle = parsed.stepTitle ?? currentProgress.stepTitle;
                if (currentProgress.totalSteps > 0 && (!currentProgress.percent || currentProgress.percent === 0)) {
                    currentProgress.percent = computeProgressPercent(currentProgress);
                }
            }
        }
    } catch (e) {}
}

function saveStoredProgress(progress) {
    try {
        sessionStorage.setItem("agentsocket_hud_progress", JSON.stringify(progress));
    } catch (e) {}
}

loadStoredProgress();

// ============================================================================
// KEYBOARD GUARD (INTERACTION SHIELD)
// Blocks accidental typing on the host page during autonomous execution
// Inspects composedPath() to allow typing inside Shadow DOM inputs/textareas
// ============================================================================
function keyboardGuard(e) {
    if (!isShieldActive) return;
    const host = document.getElementById("agentsocket-hud-host");
    if (host && host.shadowRoot) {
        const path = e.composedPath ? e.composedPath() : [];
        if (path.some(el => el === host || (host.shadowRoot && host.shadowRoot.contains(el)))) {
            return; // Allow typing inside Shadow DOM HUD
        }
    }
    e.stopPropagation();
    e.preventDefault();
}

window.addEventListener("keydown", keyboardGuard, true);
window.addEventListener("keyup", keyboardGuard, true);
window.addEventListener("keypress", keyboardGuard, true);

// ============================================================================
// MESSAGE LISTENER & INITIAL SESSION DISCOVERY
// ============================================================================
function checkInitialSessionState() {
    try {
        chrome.runtime.sendMessage({ type: "CHECK_TAB_SESSION" }, (response) => {
            if (chrome.runtime.lastError || !response) return;
            if (response.inActiveSession) {
                currentSessionTitle = response.session_title || currentSessionTitle;
                currentGroupColor = response.group_color || currentGroupColor;
                isTakeoverActive = !!response.human_in_control;
                if (response.progress_percent !== undefined || response.step_total !== undefined) {
                    currentProgress.currentStep = response.step_current ?? currentProgress.currentStep;
                    currentProgress.totalSteps = response.step_total ?? currentProgress.totalSteps;
                    currentProgress.stepTitle = response.step_title ?? currentProgress.stepTitle;
                    currentProgress.percent = response.progress_percent !== undefined 
                        ? response.progress_percent 
                        : computeProgressPercent(currentProgress);
                    saveStoredProgress(currentProgress);
                }
                if (isTakeoverActive) {
                    renderTakeoverUI(currentSessionTitle);
                } else {
                    renderActiveGlow(currentSessionTitle, currentGroupColor);
                }
            }
        });
    } catch (e) {
        // Suppress if runtime is unavailable
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", checkInitialSessionState);
} else {
    checkInitialSessionState();
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.type) {
        case MT.SHOW_GLOW:
        case "show_glow":
            currentSessionTitle = message.session_title || "AgentSocket Task";
            currentGroupColor = message.group_color || "purple";
            if (message.progress_percent !== undefined || message.step_total !== undefined) {
                currentProgress.currentStep = message.step_current ?? currentProgress.currentStep;
                currentProgress.totalSteps = message.step_total ?? currentProgress.totalSteps;
                currentProgress.stepTitle = message.step_title ?? currentProgress.stepTitle;
                currentProgress.percent = message.progress_percent !== undefined 
                    ? message.progress_percent 
                    : computeProgressPercent(currentProgress);
                saveStoredProgress(currentProgress);
            }
            if (!isTakeoverActive) {
                renderActiveGlow(currentSessionTitle, currentGroupColor);
            }
            sendResponse({ status: "success" });
            break;

        case MT.SHOW_TAKEOVER:
        case "show_takeover":
            currentSessionTitle = message.session_title || currentSessionTitle;
            if (message.progress_percent !== undefined || message.step_total !== undefined) {
                currentProgress.currentStep = message.step_current ?? currentProgress.currentStep;
                currentProgress.totalSteps = message.step_total ?? currentProgress.totalSteps;
                currentProgress.stepTitle = message.step_title ?? currentProgress.stepTitle;
                currentProgress.percent = message.progress_percent !== undefined 
                    ? message.progress_percent 
                    : computeProgressPercent(currentProgress);
                saveStoredProgress(currentProgress);
            }
            renderTakeoverUI(currentSessionTitle);
            sendResponse({ status: "success" });
            break;

        case MT.UPDATE_PROGRESS:
        case "update_progress":
            if (message.progress) {
                currentProgress = {
                    percent: message.progress.percent ?? currentProgress.percent,
                    currentStep: message.progress.currentStep ?? currentProgress.currentStep,
                    totalSteps: message.progress.totalSteps ?? currentProgress.totalSteps,
                    stepTitle: message.progress.stepTitle ?? currentProgress.stepTitle
                };
            } else {
                if (message.step_current !== undefined) currentProgress.currentStep = message.step_current;
                if (message.step_total !== undefined) currentProgress.totalSteps = message.step_total;
                if (message.step_title !== undefined) currentProgress.stepTitle = message.step_title;
                if (message.progress_percent !== undefined) {
                    currentProgress.percent = message.progress_percent;
                } else {
                    currentProgress.percent = computeProgressPercent(currentProgress);
                }
            }
            saveStoredProgress(currentProgress);
            updateHudProgressBar(currentProgress, isTakeoverActive ? "red" : currentGroupColor);
            sendResponse({ status: "success" });
            break;

        case MT.HIDE_GLOW:
        case "hide_glow":
            removeAllUI();
            sendResponse({ status: "success" });
            break;

        case "observe_page":
        case "OBSERVE_PAGE":
            const obsResult = observePage(message.options || {});
            sendResponse(obsResult);
            break;

        case "act_element":
        case "ACT_ELEMENT":
            executeAtomicAction(message.payload || message)
                .then(res => sendResponse(res))
                .catch(err => sendResponse({ status: "error", message: err.message }));
            return true;

        default:
            break;
    }
    return false;
});

// ============================================================================
// ARIA TREEWALKER & EPHEMERAL NUMERIC BADGING ENGINE (Spec 19)
// ============================================================================

// Ephemeral Weak/Strong registry mapping numeric element ID -> live DOM node
if (typeof window !== "undefined") {
    window.__agentsocket_elements = window.__agentsocket_elements || new Map();
}

let badgeFadeTimeout = null;

function isElementVisible(el) {
    if (!el || !el.isConnected) return false;

    // Ignore internal AgentSocket UI containers
    if (el.id === "agentsocket-hud-host" || (el.closest && el.closest("#agentsocket-hud-host"))) {
        return false;
    }

    // Geometry check
    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 0, height: 0, top: 0, bottom: 0 };
    if (rect.width < 4 || rect.height < 4) return false;

    // Viewport proximity threshold (+600px vertical buffer)
    const viewHeight = (typeof window !== "undefined" && window.innerHeight) ? window.innerHeight : 800;
    if (rect.top > viewHeight + 600 || rect.bottom < -600) return false;

    // Computed visibility and opacity check
    if (typeof window !== "undefined" && window.getComputedStyle) {
        try {
            const style = window.getComputedStyle(el);
            if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") <= 0.05) {
                return false;
            }
        } catch (e) {}
    }

    return true;
}

function isInteractiveElement(el) {
    if (!el || el.nodeType !== 1) return false;
    if (!isElementVisible(el)) return false;

    // Ignore disabled elements
    if (el.disabled || el.getAttribute("aria-disabled") === "true") return false;

    const tag = (el.tagName || "").toUpperCase();

    // Standard interactive HTML elements
    if (tag === "BUTTON" || tag === "SELECT" || tag === "TEXTAREA" || tag === "DETAILS" || tag === "SUMMARY") {
        return true;
    }
    if (tag === "A" && el.hasAttribute("href")) {
        return true;
    }
    if (tag === "INPUT" && (el.type || "").toLowerCase() !== "hidden") {
        return true;
    }

    // Semantic ARIA interactive roles
    const role = (el.getAttribute("role") || "").toLowerCase();
    const interactiveRoles = [
        "button", "link", "checkbox", "radio", "menuitem", "menuitemcheckbox",
        "menuitemradio", "tab", "combobox", "switch", "searchbox", "textbox", "option"
    ];
    if (interactiveRoles.includes(role)) {
        return true;
    }

    // Generic interactive attributes
    if (el.hasAttribute("tabindex") && parseInt(el.getAttribute("tabindex"), 10) >= 0) {
        return true;
    }
    if (el.isContentEditable || el.getAttribute("contenteditable") === "true") {
        return true;
    }

    // Pointer cursor check for leaf nodes
    if (typeof window !== "undefined" && window.getComputedStyle) {
        try {
            const style = window.getComputedStyle(el);
            if (style.cursor === "pointer" && el.children && el.children.length === 0) {
                return true;
            }
        } catch (e) {}
    }

    return false;
}

function extractElementLabel(el) {
    // 1. Explicit ARIA label
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

    // 2. ARIA labelledby reference
    const ariaLabelledBy = el.getAttribute("aria-labelledby");
    if (ariaLabelledBy && typeof document !== "undefined") {
        const labellingEl = document.getElementById(ariaLabelledBy);
        if (labellingEl && (labellingEl.innerText || labellingEl.textContent)) {
            const lbl = (labellingEl.innerText || labellingEl.textContent).trim();
            if (lbl) return lbl;
        }
    }

    // 3. Associated <label> element
    if (el.labels && el.labels.length > 0 && el.labels[0]) {
        const lbl = (el.labels[0].innerText || el.labels[0].textContent || "").trim();
        if (lbl) return lbl;
    }

    // 4. Inner text content (truncated for readability)
    const text = el.innerText || el.textContent;
    if (text && text.trim()) {
        const cleaned = text.trim().replace(/\s+/g, " ");
        if (cleaned.length > 60) return cleaned.slice(0, 57) + "...";
        return cleaned;
    }

    // 5. Placeholder / title / name fallback
    if (el.placeholder && el.placeholder.trim()) return el.placeholder.trim();
    if (el.title && el.title.trim()) return el.title.trim();
    if (el.name && el.name.trim()) return el.name.trim();

    return "";
}

function extractElementValue(el) {
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "INPUT") {
        const type = (el.type || "").toLowerCase();
        if (type === "password") {
            return "[REDACTED]";
        }
        if (type === "checkbox" || type === "radio") {
            return el.checked ? "checked" : "unchecked";
        }
        return el.value || "";
    }
    if (tag === "SELECT") {
        if (el.selectedIndex >= 0 && el.options && el.options[el.selectedIndex]) {
            return el.options[el.selectedIndex].text || el.value || "";
        }
        return el.value || "";
    }
    if (tag === "TEXTAREA") {
        return el.value || "";
    }
    return "";
}

function traverseAriaTree(root) {
    const rootEl = root || (typeof document !== "undefined" ? (document.body || document.documentElement) : null);
    if (!rootEl) {
        return { elements: [], tree_text: "" };
    }

    if (typeof window !== "undefined") {
        window.__agentsocket_elements = new Map();
    }

    const interactiveNodes = [];
    const elementsList = [];
    let currentId = 1;

    // Use DOM TreeWalker if available
    if (typeof document !== "undefined" && document.createTreeWalker && typeof NodeFilter !== "undefined") {
        const walker = document.createTreeWalker(
            rootEl,
            NodeFilter.SHOW_ELEMENT,
            {
                acceptNode: function (node) {
                    if (node.id === "agentsocket-hud-host") {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (isInteractiveElement(node)) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    // Include structural landmark headings
                    if (/^H[1-6]$/.test(node.tagName) && isElementVisible(node)) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            },
            false
        );

        let currentNode = walker.nextNode();
        while (currentNode) {
            interactiveNodes.push(currentNode);
            currentNode = walker.nextNode();
        }
    } else if (rootEl.querySelectorAll) {
        const all = rootEl.querySelectorAll("*");
        for (let i = 0; i < all.length; i++) {
            const node = all[i];
            if (node.id === "agentsocket-hud-host") continue;
            if (isInteractiveElement(node) || (/^H[1-6]$/.test(node.tagName) && isElementVisible(node))) {
                interactiveNodes.push(node);
            }
        }
    }

    const lines = [];

    for (const node of interactiveNodes) {
        const tag = (node.tagName || "").toUpperCase();

        // Structural Headings (H1..H6)
        if (/^H[1-6]$/.test(tag) && !isInteractiveElement(node)) {
            const headingText = (node.innerText || node.textContent || "").trim();
            if (headingText) {
                lines.push(`\nHeading ${tag.slice(1)}: ${headingText}`);
            }
            continue;
        }

        const id = currentId++;
        if (typeof window !== "undefined" && window.__agentsocket_elements) {
            window.__agentsocket_elements.set(id, node);
        }

        const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 };
        const role = (node.getAttribute("role") || tag.toLowerCase()).toLowerCase();
        const label = extractElementLabel(node);
        const value = extractElementValue(node);
        const type = node.type || null;
        const placeholder = node.placeholder || null;

        const descriptor = {
            id: id,
            tag: tag,
            type: type,
            role: role,
            name: label,
            value: value,
            placeholder: placeholder,
            rect: {
                x: Math.round(rect.left || 0),
                y: Math.round(rect.top || 0),
                width: Math.round(rect.width || 0),
                height: Math.round(rect.height || 0)
            },
            is_visible: true,
            is_interactive: true
        };
        elementsList.push(descriptor);

        // Compact token-efficient line formatting
        let meta = role;
        if (type && type !== "text" && type !== role) meta += `, type="${type}"`;
        if (value) meta += `, value="${value}"`;
        if (placeholder) meta += `, placeholder="${placeholder}"`;

        const displayLabel = label ? ` "${label}"` : "";
        lines.push(`[${id}]${displayLabel} (${meta})`);
    }

    return {
        elements: elementsList,
        tree_text: lines.join("\n").trim()
    };
}

function removeBadges() {
    if (typeof document === "undefined") return;
    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;
    const container = shadow.getElementById("agentsocket-badges-container");
    if (container) {
        container.style.opacity = "0";
        setTimeout(() => {
            if (container.parentNode) container.remove();
        }, 200);
    }
}

function renderBadges(elements) {
    if (typeof document === "undefined") return;
    removeBadges();
    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;

    const container = document.createElement("div");
    container.id = "agentsocket-badges-container";
    container.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        pointer-events: none !important;
        z-index: 2147483645 !important;
        transition: opacity 0.25s ease !important;
        opacity: 1 !important;
    `;

    const viewHeight = (typeof window !== "undefined" && window.innerHeight) ? window.innerHeight : 800;

    for (const elData of elements) {
        const node = (typeof window !== "undefined" && window.__agentsocket_elements) 
            ? window.__agentsocket_elements.get(elData.id) 
            : null;
        if (!node || !node.getBoundingClientRect) continue;

        const rect = node.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        if (rect.bottom < 0 || rect.top > viewHeight) continue;

        const badge = document.createElement("div");
        badge.className = "agentsocket-badge-pill";
        badge.textContent = `[${elData.id}]`;
        badge.style.cssText = `
            position: fixed !important;
            top: ${Math.max(2, Math.round(rect.top - 4))}px !important;
            left: ${Math.max(2, Math.round(rect.left - 4))}px !important;
            background: #1e1e2e !important;
            color: #a6e3a1 !important;
            border: 1px solid rgba(166, 227, 161, 0.5) !important;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
            font-size: 10px !important;
            font-weight: 700 !important;
            line-height: 1.2 !important;
            padding: 2px 4px !important;
            border-radius: 4px !important;
            box-shadow: 0 2px 5px rgba(0,0,0,0.5) !important;
            pointer-events: none !important;
            user-select: none !important;
        `;
        container.appendChild(badge);
    }

    shadow.appendChild(container);

    if (badgeFadeTimeout) clearTimeout(badgeFadeTimeout);
    badgeFadeTimeout = setTimeout(() => {
        removeBadges();
    }, 1500);
}

function observePage(options = {}) {
    const root = options.root || (typeof document !== "undefined" ? (document.body || document.documentElement) : null);
    const { elements, tree_text } = traverseAriaTree(root);

    if (options.show_badges !== false && typeof document !== "undefined") {
        renderBadges(elements);
    }

    return {
        status: "success",
        url: typeof window !== "undefined" ? window.location.href : "",
        title: typeof document !== "undefined" ? document.title : "",
        viewport: {
            width: typeof window !== "undefined" ? window.innerWidth : 1280,
            height: typeof window !== "undefined" ? window.innerHeight : 800,
            scroll_y: typeof window !== "undefined" ? (window.scrollY || window.pageYOffset || 0) : 0
        },
        tree_text: tree_text,
        elements: elements,
        screenshot_path: null
    };
}

if (typeof window !== "undefined") {
    window.__agentsocket_observe = observePage;
    window.__agentsocket_remove_badges = removeBadges;
    window.__agentsocket_traverse_aria = traverseAriaTree;
}

// ============================================================================
// NATIVE ATOMIC OPERATOR DRIVER & ADAPTIVE SETTLEMENT ENGINE (Spec 20)
// ============================================================================

function getRegisteredElement(elementId) {
    if (typeof window === "undefined" || !window.__agentsocket_elements) {
        return null;
    }
    const numId = parseInt(elementId, 10);
    return window.__agentsocket_elements.get(numId) || null;
}

function actClick(elementId, options = {}) {
    const el = (typeof elementId === "object" && elementId !== null) ? elementId : getRegisteredElement(elementId);
    if (!el) {
        throw new Error(`Element [${elementId}] not found in element registry. Please re-run observe_page.`);
    }

    if (el.scrollIntoView) {
        try {
            el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        } catch (e) {
            try { el.scrollIntoView(); } catch (err) {}
        }
    }

    if (el.focus) {
        try { el.focus(); } catch (e) {}
    }

    const win = (typeof window !== "undefined") ? window : null;

    // Sequential native mouse/pointer event chain
    const pointerDown = (typeof PointerEvent !== "undefined")
        ? new PointerEvent('pointerdown', { bubbles: true, cancelable: true, view: win })
        : new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: win });
    el.dispatchEvent(pointerDown);

    const mouseDown = new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: win });
    el.dispatchEvent(mouseDown);

    const pointerUp = (typeof PointerEvent !== "undefined")
        ? new PointerEvent('pointerup', { bubbles: true, cancelable: true, view: win })
        : new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: win });
    el.dispatchEvent(pointerUp);

    const mouseUp = new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: win });
    el.dispatchEvent(mouseUp);

    const clickEvt = new MouseEvent('click', { bubbles: true, cancelable: true, view: win });
    el.dispatchEvent(clickEvt);

    return {
        status: "success",
        action: "click",
        element_id: typeof elementId === "number" ? elementId : null
    };
}

function actType(elementId, text, options = {}) {
    const el = (typeof elementId === "object" && elementId !== null) ? elementId : getRegisteredElement(elementId);
    if (!el) {
        throw new Error(`Element [${elementId}] not found in element registry. Please re-run observe_page.`);
    }

    if (el.scrollIntoView) {
        try { el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' }); } catch (e) {}
    }
    if (el.focus) {
        try { el.focus(); } catch (e) {}
    }

    const clearFirst = !!options.clear_first || !!options.clearFirst;
    const pressEnter = !!options.press_enter || !!options.pressEnter;
    const textToType = text !== undefined && text !== null ? String(text) : "";

    // Bypass React/Vue/Angular property descriptor overrides using prototype setter
    const tag = (el.tagName || "").toUpperCase();
    const isTextarea = tag === "TEXTAREA" || (typeof HTMLTextAreaElement !== "undefined" && el instanceof HTMLTextAreaElement);

    let proto = null;
    if (isTextarea && typeof HTMLTextAreaElement !== "undefined") {
        proto = HTMLTextAreaElement.prototype;
    } else if (typeof HTMLInputElement !== "undefined" && el instanceof HTMLInputElement) {
        proto = HTMLInputElement.prototype;
    } else if (el) {
        proto = Object.getPrototypeOf(el);
    }

    let setter = null;
    let getter = null;
    if (proto) {
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        if (desc) {
            if (desc.set) setter = desc.set;
            if (desc.get) getter = desc.get;
        }
    }

    const currentValue = getter ? getter.call(el) : (el.value || "");
    const targetValue = clearFirst ? textToType : (currentValue + textToType);

    if (setter) {
        if (clearFirst) {
            setter.call(el, "");
        }
        setter.call(el, targetValue);
    } else {
        if (clearFirst) {
            el.value = "";
        }
        el.value = targetValue;
    }

    // Dispatch standard synthetic input and change events
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));

    // Optional Enter dispatch
    if (pressEnter) {
        const win = (typeof window !== "undefined") ? window : null;
        const keyOptions = {
            key: "Enter",
            code: "Enter",
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true,
            view: win
        };
        const downEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keydown', keyOptions) : new Event('keydown', { bubbles: true });
        const pressEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keypress', keyOptions) : new Event('keypress', { bubbles: true });
        const upEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keyup', keyOptions) : new Event('keyup', { bubbles: true });

        el.dispatchEvent(downEvt);
        el.dispatchEvent(pressEvt);
        el.dispatchEvent(upEvt);
    }

    return {
        status: "success",
        action: "type",
        element_id: typeof elementId === "number" ? elementId : null,
        value: el.value
    };
}

function actScroll(direction, amount) {
    const dir = (direction || "down").toLowerCase();
    const amt = typeof amount === "number" && !isNaN(amount) ? amount : 500;
    const win = typeof window !== "undefined" ? window : null;
    const doc = typeof document !== "undefined" ? document : null;

    if (!win) {
        return { status: "success", action: "scroll", direction: dir, amount: amt };
    }

    switch (dir) {
        case "down":
            if (win.scrollBy) win.scrollBy({ top: amt, behavior: 'smooth' });
            break;
        case "up":
            if (win.scrollBy) win.scrollBy({ top: -amt, behavior: 'smooth' });
            break;
        case "top":
            if (win.scrollTo) win.scrollTo({ top: 0, behavior: 'smooth' });
            break;
        case "bottom":
            const maxScroll = (doc && doc.body) ? (doc.body.scrollHeight || doc.documentElement.scrollHeight || 999999) : 999999;
            if (win.scrollTo) win.scrollTo({ top: maxScroll, behavior: 'smooth' });
            break;
        default:
            if (win.scrollBy) win.scrollBy({ top: amt, behavior: 'smooth' });
            break;
    }

    return { status: "success", action: "scroll", direction: dir, amount: amt };
}

function actKeyPress(key) {
    const keyName = key || "Enter";
    const target = (typeof document !== "undefined" && document.activeElement) ? document.activeElement : (typeof document !== "undefined" ? document.body : null);
    const win = typeof window !== "undefined" ? window : null;

    if (!target) {
        return { status: "success", action: "key_press", key: keyName };
    }

    const keyOptions = {
        key: keyName,
        code: keyName === "Enter" ? "Enter" : (keyName === "Escape" ? "Escape" : (keyName === "Tab" ? "Tab" : keyName)),
        keyCode: keyName === "Enter" ? 13 : (keyName === "Escape" ? 27 : (keyName === "Tab" ? 9 : 0)),
        which: keyName === "Enter" ? 13 : (keyName === "Escape" ? 27 : (keyName === "Tab" ? 9 : 0)),
        bubbles: true,
        cancelable: true,
        view: win
    };

    const downEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keydown', keyOptions) : new Event('keydown', { bubbles: true });
    const pressEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keypress', keyOptions) : new Event('keypress', { bubbles: true });
    const upEvt = (typeof KeyboardEvent !== "undefined") ? new KeyboardEvent('keyup', keyOptions) : new Event('keyup', { bubbles: true });

    target.dispatchEvent(downEvt);
    target.dispatchEvent(pressEvt);
    target.dispatchEvent(upEvt);

    return { status: "success", action: "key_press", key: keyName };
}

function waitForSettlement(options = {}) {
    const quiescenceMs = options.quiescenceMs || options.quiescence_ms || 300;
    const maxWaitMs = options.maxWaitMs || options.max_wait_ms || 3000;

    return new Promise((resolve) => {
        const startTime = Date.now();
        let mutationsObserved = 0;
        let networkRequestsSettled = 0;
        let observer = null;
        let quietTimer = null;
        let maxTimer = null;
        let isResolved = false;

        function finish(reason) {
            if (isResolved) return;
            isResolved = true;

            if (observer) {
                try { observer.disconnect(); } catch (e) {}
            }
            if (quietTimer) clearTimeout(quietTimer);
            if (maxTimer) clearTimeout(maxTimer);

            const durationMs = Date.now() - startTime;
            resolve({
                duration_ms: durationMs,
                mutations_observed: mutationsObserved,
                network_requests_settled: networkRequestsSettled,
                settle_reason: reason
            });
        }

        // Hard safety timeout cap
        maxTimer = setTimeout(() => {
            finish("timeout");
        }, maxWaitMs);

        // Reset quiescence countdown on activity
        function resetQuietTimer() {
            if (quietTimer) clearTimeout(quietTimer);
            quietTimer = setTimeout(() => {
                finish("quiescence");
            }, quiescenceMs);
        }

        // Attach MutationObserver if available in DOM context
        if (typeof MutationObserver !== "undefined" && typeof document !== "undefined" && (document.body || document.documentElement)) {
            try {
                observer = new MutationObserver((mutations) => {
                    let relevantMutation = false;
                    for (const m of mutations) {
                        // Filter out internal AgentSocket HUD updates
                        if (m.target && (m.target.id === "agentsocket-hud-host" || (m.target.closest && m.target.closest("#agentsocket-hud-host")))) {
                            continue;
                        }
                        relevantMutation = true;
                        mutationsObserved++;
                    }
                    if (relevantMutation) {
                        resetQuietTimer();
                    }
                });

                const targetNode = document.body || document.documentElement;
                observer.observe(targetNode, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    characterData: true
                });
            } catch (e) {}
        }

        // Start initial quiet countdown
        resetQuietTimer();
    });
}

async function executeAtomicAction(payload = {}) {
    const action = (payload.action || "").toLowerCase();
    const elementId = payload.element_id !== undefined ? payload.element_id : payload.elementId;
    const waitSettle = payload.wait_settle !== false && payload.waitSettle !== false;
    const startTime = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();

    let actionResult = null;

    switch (action) {
        case "click":
            actionResult = actClick(elementId, payload);
            break;
        case "type":
            actionResult = actType(elementId, payload.text, payload);
            break;
        case "scroll":
            actionResult = actScroll(payload.direction, payload.amount);
            break;
        case "key_press":
        case "keypress":
            actionResult = actKeyPress(payload.key);
            break;
        default:
            throw new Error(`Unsupported atomic action: '${action}'. Supported: click, type, scroll, key_press.`);
    }

    let settlement = {
        duration_ms: 0,
        mutations_observed: 0,
        network_requests_settled: 0,
        settle_reason: "skipped"
    };

    if (waitSettle) {
        settlement = await waitForSettlement(payload.settlement_options || {});
    }

    const endTime = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    const totalDurationMs = Math.round((endTime - startTime) * 10) / 10;

    return {
        status: "success",
        action: action,
        element_id: elementId !== undefined && elementId !== null ? parseInt(elementId, 10) : null,
        duration_ms: totalDurationMs,
        mutations_observed: settlement.mutations_observed,
        network_requests_settled: settlement.network_requests_settled,
        settle_reason: settlement.settle_reason
    };
}

if (typeof window !== "undefined") {
    window.__agentsocket_act = executeAtomicAction;
    window.__agentsocket_click = actClick;
    window.__agentsocket_type = actType;
    window.__agentsocket_scroll = actScroll;
    window.__agentsocket_key_press = actKeyPress;
    window.__agentsocket_wait_settle = waitForSettlement;
}

// ============================================================================
// THEME PALETTE HELPER
// ============================================================================
// COLOR PALETTE & THEME SELECTION (Vibrant Ambient Glows)
// ============================================================================
function getThemeColors(colorName) {
    const palette = {
        blue: {
            borderHex: "#38BDF8",
            glowRgba: "rgba(56, 189, 248, 0.55)",
            auraRgba: "rgba(56, 189, 248, 0.18)",
            subtleBorder: "rgba(56, 189, 248, 0.4)",
            tagText: "#38BDF8"
        },
        purple: {
            borderHex: "#A855F7",
            glowRgba: "rgba(168, 85, 247, 0.55)",
            auraRgba: "rgba(168, 85, 247, 0.18)",
            subtleBorder: "rgba(168, 85, 247, 0.4)",
            tagText: "#C084FC"
        },
        green: {
            borderHex: "#10B981",
            glowRgba: "rgba(16, 185, 129, 0.55)",
            auraRgba: "rgba(16, 185, 129, 0.18)",
            subtleBorder: "rgba(16, 185, 129, 0.4)",
            tagText: "#34D399"
        },
        orange: {
            borderHex: "#FB923C",
            glowRgba: "rgba(251, 146, 60, 0.55)",
            auraRgba: "rgba(251, 146, 60, 0.18)",
            subtleBorder: "rgba(251, 146, 60, 0.4)",
            tagText: "#FB923C"
        },
        red: {
            borderHex: "#F87171",
            glowRgba: "rgba(248, 113, 113, 0.55)",
            auraRgba: "rgba(248, 113, 113, 0.18)",
            subtleBorder: "rgba(248, 113, 113, 0.4)",
            tagText: "#F87171"
        }
    };
    return palette[colorName] || palette.blue;
}

// ============================================================================
// SHADOW DOM ROOT CONTAINER & TEARDOWN
// ============================================================================
function getOrCreateShadowRoot() {
    let host = document.getElementById("agentsocket-hud-host");
    if (!host) {
        host = document.createElement("agentsocket-hud-host");
        host.id = "agentsocket-hud-host";
        host.style.cssText = `
            all: initial !important;
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            pointer-events: none !important;
            z-index: 2147483647 !important;
            display: block !important;
        `;
        const targetParent = document.documentElement || document.body;
        targetParent.appendChild(host);
    }
    let shadow = host.shadowRoot;
    if (!shadow) {
        shadow = host.attachShadow({ mode: "open" });
        injectShadowStyles(shadow);
    }
    return shadow;
}

function injectShadowStyles(shadowRoot) {
    if (shadowRoot.querySelector("#agentsocket-hud-styles")) return;
    const style = document.createElement("style");
    style.id = "agentsocket-hud-styles";
    style.textContent = `
        :host {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 13px;
            line-height: 1.4;
            box-sizing: border-box;
            -webkit-font-smoothing: antialiased;
        }
        * {
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        @keyframes agentSocketFadeInUp {
            from { opacity: 0; transform: translate(-50%, 12px); }
            to { opacity: 1; transform: translate(-50%, 0); }
        }
        @keyframes agentSocketPulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.25); opacity: 0.7; }
        }
        @keyframes agentAuraBreathe {
            0%, 100% { opacity: 0.95; }
            50% { opacity: 0.75; }
        }
        .ab-btn {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 12px;
            font-weight: 500;
            padding: 5px 12px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            pointer-events: auto;
            user-select: none;
            outline: none;
            border: 1px solid transparent;
            box-sizing: border-box;
        }
        .ab-btn:active {
            transform: scale(0.97);
        }
    `;
    shadowRoot.appendChild(style);
}

function clearShadowContent(shadowRoot) {
    if (!shadowRoot) return;
    const children = Array.from(shadowRoot.childNodes);
    children.forEach(child => {
        if (child.id !== "agentsocket-hud-styles") {
            shadowRoot.removeChild(child);
        }
    });
}

function removeAllUI() {
    isShieldActive = false;
    isTakeoverActive = false;
    const host = document.getElementById("agentsocket-hud-host");
    if (host && host.parentNode) {
        host.parentNode.removeChild(host);
    }
}

// ============================================================================
// 1. ACTIVE RUNNING STATE: Vibrant Glow Frame & Bottom Control Pill & Shield
// ============================================================================
function renderActiveGlow(sessionTitle, groupColor) {
    const shadow = getOrCreateShadowRoot();
    clearShadowContent(shadow);
    isShieldActive = true;
    isTakeoverActive = false;

    const theme = getThemeColors(groupColor);

    // A. Full Viewport Border Frame & Ambient Top Aura
    const glowFrame = document.createElement("div");
    glowFrame.id = "ab-glow-frame";
    glowFrame.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        pointer-events: none !important;
        border: 3.5px solid ${theme.borderHex} !important;
        box-shadow: inset 0 0 32px ${theme.glowRgba}, 0 0 20px ${theme.glowRgba} !important;
        background: radial-gradient(ellipse 110% 45% at 50% 0%, ${theme.auraRgba} 0%, rgba(255, 255, 255, 0) 75%) !important;
        box-sizing: border-box !important;
        z-index: 2147483645 !important;
        animation: agentAuraBreathe 3s infinite ease-in-out !important;
    `;
    shadow.appendChild(glowFrame);

    // B. Interaction Shield Overlay
    const shield = document.createElement("div");
    shield.id = "ab-interaction-shield";
    shield.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 2147483646 !important;
        pointer-events: auto !important;
        cursor: not-allowed !important;
        background: rgba(0, 0, 0, 0.02) !important;
    `;

    // Intercept mouse interactions and show helpful takeover tooltip
    shield.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        showInterventionTooltip(e.clientX, e.clientY);
    });
    shield.addEventListener("mousedown", (e) => { e.stopPropagation(); e.preventDefault(); });
    shield.addEventListener("mouseup", (e) => { e.stopPropagation(); e.preventDefault(); });
    shield.addEventListener("contextmenu", (e) => { e.stopPropagation(); e.preventDefault(); });
    shield.addEventListener("dblclick", (e) => { e.stopPropagation(); e.preventDefault(); });

    shadow.appendChild(shield);

    // C. Bottom Floating HUD Pill (Screenshot / Manus Style)
    const pill = document.createElement("div");
    pill.id = "ab-control-pill";
    pill.style.cssText = `
        position: fixed !important;
        bottom: 20px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        min-width: 360px !important;
        max-width: 90vw !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 7px !important;
        padding: 10px 16px 9px 16px !important;
        box-sizing: border-box !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: #18181b !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 18px !important;
        color: #f4f4f5 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05) !important;
        animation: agentSocketFadeInUp 0.25s ease-out !important;
        backdrop-filter: blur(12px) !important;
    `;

    // Row 1: Title & Controls
    const topRow = document.createElement("div");
    topRow.style.cssText = `
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        width: 100% !important;
        gap: 12px !important;
    `;

    const leftGroup = document.createElement("div");
    leftGroup.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
        overflow: hidden !important;
    `;

    const isInitialCompleted = (currentProgress.percent >= 100) || (currentProgress.totalSteps > 0 && currentProgress.currentStep >= currentProgress.totalSteps);

    // Pulsing dot indicator
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 8px;
        height: 8px;
        background: ${isInitialCompleted ? '#10B981' : theme.borderHex};
        border-radius: 50%;
        display: inline-block;
        flex-shrink: 0;
        box-shadow: ${isInitialCompleted ? '0 0 10px #10B981' : `0 0 8px ${theme.borderHex}`};
        ${isInitialCompleted ? '' : 'animation: agentSocketPulse 1.8s infinite ease-in-out;'};
    `;

    // Title label
    const label = document.createElement("div");
    label.style.cssText = `
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 500;
        color: #ffffff;
        font-size: 13px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    `;
    label.innerHTML = `<span>⚡</span> <span>${escapeHtml(sessionTitle)}</span>`;

    leftGroup.appendChild(dot);
    leftGroup.appendChild(label);

    // Action buttons container
    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex; align-items: center; gap: 8px; flex-shrink: 0;`;

    // Take Over button (Label preserved invariant as 'Take Over')
    const takeoverBtn = document.createElement("button");
    takeoverBtn.className = "ab-btn";
    takeoverBtn.innerHTML = "<span>Take Over</span>";
    takeoverBtn.style.cssText += `
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #e4e4e7 !important;
        font-size: 12px !important;
        padding: 4px 11px !important;
        border-radius: 12px !important;
    `;
    takeoverBtn.onmouseenter = () => { takeoverBtn.style.background = "rgba(255, 255, 255, 0.18)"; };
    takeoverBtn.onmouseleave = () => { takeoverBtn.style.background = "rgba(255, 255, 255, 0.1)"; };
    takeoverBtn.onclick = () => {
        renderTakeoverUI(sessionTitle);
        chrome.runtime.sendMessage({
            type: MT.PAGE_TAKEOVER,
            notes: `Operator initiated manual takeover on ${window.location.hostname}`
        });
    };

    // Stop button (Vibrant Red Pill Button)
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>Stop</span>";
    stopBtn.style.cssText += `
        background: #ef4444 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        padding: 4px 12px !important;
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(239, 68, 68, 0.4) !important;
    `;
    stopBtn.onmouseenter = () => { stopBtn.style.background = "#dc2626"; };
    stopBtn.onmouseleave = () => { stopBtn.style.background = "#ef4444"; };
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: MT.PAGE_STOP });
        removeAllUI();
    };

    btnGroup.appendChild(takeoverBtn);
    btnGroup.appendChild(stopBtn);

    topRow.appendChild(leftGroup);
    topRow.appendChild(btnGroup);

    // Row 2: Completion Progress Bar
    const progressSection = createProgressSection(currentProgress, theme);

    pill.appendChild(topRow);
    pill.appendChild(progressSection);

    shadow.appendChild(pill);
}

// ============================================================================
// PROGRESS BAR SECTION HELPER & LIVE UPDATES
// ============================================================================
function createProgressSection(progressData, theme) {
    const container = document.createElement("div");
    container.id = "ab-progress-section";
    container.style.cssText = `
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 4px !important;
        box-sizing: border-box !important;
    `;

    // Track
    const track = document.createElement("div");
    track.id = "ab-progress-track";
    track.style.cssText = `
        width: 100% !important;
        height: 4.5px !important;
        background: rgba(255, 255, 255, 0.12) !important;
        border-radius: 999px !important;
        overflow: hidden !important;
        position: relative !important;
    `;

    const percent = computeProgressPercent(progressData);
    const isCompleted = percent >= 100 || (progressData.totalSteps > 0 && progressData.currentStep >= progressData.totalSteps);

    const fill = document.createElement("div");
    fill.id = "ab-progress-fill";
    const bgGradient = isCompleted
        ? "linear-gradient(90deg, #10B981, #34D399)"
        : `linear-gradient(90deg, ${theme.borderHex}, #60a5fa)`;
    const glowColor = isCompleted ? "rgba(16, 185, 129, 0.55)" : theme.glowRgba;

    fill.style.cssText = `
        width: ${percent}% !important;
        height: 100% !important;
        background: ${bgGradient} !important;
        border-radius: 999px !important;
        transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 0 8px ${glowColor} !important;
    `;
    track.appendChild(fill);

    // Labels Row
    const labelsRow = document.createElement("div");
    labelsRow.id = "ab-progress-labels";
    labelsRow.style.cssText = `
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
        font-size: 11px !important;
        color: #a1a1aa !important;
        line-height: 1 !important;
        padding: 0 2px !important;
    `;

    const stepLabel = document.createElement("span");
    stepLabel.id = "ab-progress-step-text";
    if (isCompleted) {
        stepLabel.innerText = "✅ Task Complete (100%)";
    } else if (progressData.totalSteps > 0) {
        stepLabel.innerText = `Step ${progressData.currentStep} of ${progressData.totalSteps}${progressData.stepTitle ? ` • ${progressData.stepTitle}` : ''}`;
    } else {
        stepLabel.innerText = "Task in progress...";
    }

    const percentLabel = document.createElement("span");
    percentLabel.id = "ab-progress-percent-text";
    const tagTextColor = isCompleted ? "#34D399" : (theme.tagText || '#38bdf8');
    percentLabel.style.cssText = `font-weight: 600; color: ${tagTextColor};`;
    percentLabel.innerText = `${Math.round(percent)}%`;

    labelsRow.appendChild(stepLabel);
    labelsRow.appendChild(percentLabel);

    container.appendChild(track);
    container.appendChild(labelsRow);

    if (isCompleted && !document.title.startsWith("✅ ")) {
        document.title = "✅ " + document.title;
    }

    return container;
}

function updateHudProgressBar(progressData, groupColor) {
    const shadow = getOrCreateShadowRoot();
    const fill = shadow.getElementById ? shadow.getElementById("ab-progress-fill") : shadow.querySelector("#ab-progress-fill");
    const stepText = shadow.getElementById ? shadow.getElementById("ab-progress-step-text") : shadow.querySelector("#ab-progress-step-text");
    const percentText = shadow.getElementById ? shadow.getElementById("ab-progress-percent-text") : shadow.querySelector("#ab-progress-percent-text");
    const dot = shadow.querySelector ? shadow.querySelector("#ab-control-pill span") : null;

    if (!fill) return;

    const theme = getThemeColors(groupColor || currentGroupColor);
    const percent = computeProgressPercent(progressData);
    const isCompleted = percent >= 100 || (progressData.totalSteps > 0 && progressData.currentStep >= progressData.totalSteps);

    fill.style.width = `${percent}%`;

    if (isCompleted) {
        fill.style.background = "linear-gradient(90deg, #10B981, #34D399)";
        fill.style.boxShadow = "0 0 10px rgba(16, 185, 129, 0.6)";

        if (dot) {
            dot.style.background = "#10B981";
            dot.style.boxShadow = "0 0 10px #10B981";
            dot.style.animation = "none";
        }

        if (percentText) {
            percentText.innerText = "100%";
            percentText.style.color = "#34D399";
        }

        if (stepText) {
            stepText.innerText = "✅ Task Complete (100%)";
        }

        if (!document.title.startsWith("✅ ")) {
            document.title = "✅ " + document.title;
        }
    } else {
        fill.style.background = `linear-gradient(90deg, ${theme.borderHex}, #60a5fa)`;
        fill.style.boxShadow = `0 0 8px ${theme.glowRgba}`;

        if (dot) {
            dot.style.background = theme.borderHex;
            dot.style.boxShadow = `0 0 8px ${theme.borderHex}`;
            dot.style.animation = "agentSocketPulse 1.8s infinite ease-in-out";
        }

        if (percentText) {
            percentText.innerText = `${Math.round(percent)}%`;
            percentText.style.color = theme.tagText || '#38bdf8';
        }

        if (stepText) {
            if (progressData.totalSteps > 0) {
                stepText.innerText = `Step ${progressData.currentStep} of ${progressData.totalSteps}${progressData.stepTitle ? ` • ${progressData.stepTitle}` : ''}`;
            } else {
                stepText.innerText = `Task in progress (${Math.round(percent)}%)...`;
            }
        }
    }
}

// ============================================================================
// INTERVENTION HINT TOOLTIP
// ============================================================================
function showInterventionTooltip(x, y) {
    const shadow = getOrCreateShadowRoot();
    let tooltip = shadow.querySelector ? shadow.querySelector("#ab-shield-tooltip") : null;
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "ab-shield-tooltip";
        shadow.appendChild(tooltip);
    }

    const safeTop = Math.min(Math.max(y - 45, 16), window.innerHeight - 70);
    const safeLeft = Math.min(Math.max(x - 130, 16), window.innerWidth - 300);

    tooltip.style.cssText = `
        position: fixed;
        top: ${safeTop}px;
        left: ${safeLeft}px;
        z-index: 2147483647;
        background: #202020;
        border: 1px solid #333333;
        color: #e3e2de;
        padding: 6px 12px;
        border-radius: 5px;
        font-size: 11.5px;
        font-weight: 400;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
        pointer-events: none;
        display: flex;
        align-items: center;
        gap: 6px;
    `;
    tooltip.innerHTML = `<span>🤖</span> <span>Agent is operating. Click <b>'Take Over'</b> below to interact.</span>`;

    clearTimeout(tooltipTimeout);
    tooltipTimeout = setTimeout(() => {
        if (tooltip && tooltip.parentNode) tooltip.remove();
    }, 2400);
}

// ============================================================================
// 2. TAKEOVER / LOCKOUT STATE: Operator in Control (Shield Removed)
// ============================================================================
function renderTakeoverUI(sessionTitle) {
    const shadow = getOrCreateShadowRoot();
    clearShadowContent(shadow);
    isShieldActive = false;
    isTakeoverActive = true;

    // Subtle dashed frame to signify operator takeover
    const lockFrame = document.createElement("div");
    lockFrame.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        pointer-events: none !important;
        border: 3px dashed rgba(235, 87, 87, 0.7) !important;
        box-sizing: border-box !important;
        z-index: 2147483645 !important;
    `;
    shadow.appendChild(lockFrame);

    const pill = document.createElement("div");
    pill.id = "ab-takeover-pill";
    pill.style.cssText = `
        position: fixed !important;
        bottom: 20px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: #202020 !important;
        border: 1px solid #4a2729 !important;
        border-radius: 18px !important;
        padding: 10px 16px 9px 16px !important;
        color: #e3e2de !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 7px !important;
        min-width: 360px !important;
        max-width: 90vw !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6) !important;
        animation: agentSocketFadeInUp 0.2s ease-out !important;
        box-sizing: border-box !important;
    `;

    // Row 1: Lock Header & Actions
    const topRow = document.createElement("div");
    topRow.style.cssText = `
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        width: 100% !important;
        gap: 12px !important;
    `;

    const leftGroup = document.createElement("div");
    leftGroup.style.cssText = `display: flex; align-items: center; gap: 8px;`;

    // Red Lock Status Dot
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 8px;
        height: 8px;
        background: #ff7369;
        border-radius: 50%;
        display: inline-block;
        flex-shrink: 0;
        box-shadow: 0 0 8px #ff7369;
    `;

    const label = document.createElement("div");
    label.style.cssText = `
        font-weight: 500;
        color: #ff7369;
        font-size: 12.5px;
    `;
    label.innerHTML = `<span>🔒 Operator Active</span>`;

    leftGroup.appendChild(dot);
    leftGroup.appendChild(label);

    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex; align-items: center; gap: 8px; flex-shrink: 0;`;

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>⏹</span> <span>Stop</span>";
    stopBtn.style.cssText += `
        background: #282828;
        border: 1px solid #333333;
        color: #9b9b9b;
        font-size: 12px !important;
        padding: 4px 10px !important;
        border-radius: 12px !important;
    `;
    stopBtn.onmouseenter = () => { stopBtn.style.background = "#303030"; stopBtn.style.color = "#e3e2de"; };
    stopBtn.onmouseleave = () => { stopBtn.style.background = "#282828"; stopBtn.style.color = "#9b9b9b"; };
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: MT.PAGE_STOP });
        removeAllUI();
    };

    // Release / Resume button
    const resumeBtn = document.createElement("button");
    resumeBtn.className = "ab-btn";
    resumeBtn.innerHTML = "<span>▶</span> <span>Release to Agent</span>";
    resumeBtn.style.cssText += `
        background: #0f7b6c;
        color: #ffffff;
        font-size: 12px !important;
        padding: 4px 12px !important;
        border-radius: 12px !important;
    `;
    resumeBtn.onmouseenter = () => { resumeBtn.style.background = "#0b675a"; };
    resumeBtn.onmouseleave = () => { resumeBtn.style.background = "#0f7b6c"; };
    resumeBtn.onclick = () => {
        renderNotesModal(sessionTitle);
    };

    btnGroup.appendChild(stopBtn);
    btnGroup.appendChild(resumeBtn);

    topRow.appendChild(leftGroup);
    topRow.appendChild(btnGroup);

    // Row 2: Progress Section with Operator Note
    const progressDataCopy = {
        ...currentProgress,
        stepTitle: currentProgress.stepTitle ? `${currentProgress.stepTitle} (Paused)` : "Paused for Operator"
    };
    const progressSection = createProgressSection(progressDataCopy, getThemeColors("red"));

    pill.appendChild(topRow);
    pill.appendChild(progressSection);

    shadow.appendChild(pill);
}

// ============================================================================
// 3. HANDOFF NOTES MODAL
// ============================================================================
function renderNotesModal(sessionTitle) {
    const shadow = getOrCreateShadowRoot();

    const existingModal = shadow.querySelector ? shadow.querySelector("#ab-notes-overlay") : null;
    if (existingModal) existingModal.remove();

    const overlay = document.createElement("div");
    overlay.id = "ab-notes-overlay";
    overlay.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.6);
        z-index: 2147483647;
        pointer-events: auto;
        display: flex;
        align-items: center;
        justify-content: center;
    `;

    const modal = document.createElement("div");
    modal.id = "ab-notes-card";
    modal.style.cssText = `
        width: 380px;
        max-width: 90vw;
        background: #202020;
        border: 1px solid #2f2f2f;
        border-radius: 8px;
        padding: 20px;
        color: #e3e2de;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
        animation: agentSocketModalFadeIn 0.15s ease-out;
        box-sizing: border-box;
    `;

    const title = document.createElement("h3");
    title.innerText = "Handoff Notes to Agent";
    title.style.cssText = `
        margin: 0 0 6px 0;
        font-size: 14px;
        font-weight: 600;
        color: #ffffff;
    `;

    const desc = document.createElement("p");
    desc.innerText = "Describe what you completed so the agent can adapt smoothly:";
    desc.style.cssText = `
        margin: 0 0 12px 0;
        font-size: 12px;
        color: #9b9b9b;
        line-height: 1.4;
    `;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "e.g. Solved CAPTCHA and navigated to checkout page...";
    textarea.style.cssText = `
        width: 100%;
        height: 72px;
        box-sizing: border-box;
        background: #191919;
        color: #e3e2de;
        border: 1px solid #333333;
        border-radius: 5px;
        padding: 8px 10px;
        font-size: 12px;
        font-family: inherit;
        resize: none;
        margin-bottom: 14px;
        outline: none;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    `;
    textarea.onfocus = () => {
        textarea.style.borderColor = "#2383e2";
        textarea.style.boxShadow = "0 0 0 2px rgba(35, 131, 226, 0.2)";
    };
    textarea.onblur = () => {
        textarea.style.borderColor = "#333333";
        textarea.style.boxShadow = "none";
    };

    const actionContainer = document.createElement("div");
    actionContainer.style.cssText = `
        display: flex;
        justify-content: flex-end;
        gap: 8px;
    `;

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "ab-btn";
    cancelBtn.innerText = "Cancel";
    cancelBtn.style.cssText += `
        background: #282828;
        border: 1px solid #333333;
        color: #9b9b9b;
    `;
    cancelBtn.onmouseenter = () => { cancelBtn.style.background = "#303030"; cancelBtn.style.color = "#e3e2de"; };
    cancelBtn.onmouseleave = () => { cancelBtn.style.background = "#282828"; cancelBtn.style.color = "#9b9b9b"; };
    cancelBtn.onclick = () => {
        overlay.remove();
    };

    const sendBtn = document.createElement("button");
    sendBtn.className = "ab-btn";
    sendBtn.innerHTML = "<span>Release & Continue</span>";
    sendBtn.style.cssText += `
        background: #0f7b6c;
        color: #FFFFFF;
    `;
    sendBtn.onmouseenter = () => { sendBtn.style.background = "#0b675a"; };
    sendBtn.onmouseleave = () => { sendBtn.style.background = "#0f7b6c"; };
    sendBtn.onclick = () => {
        const text = textarea.value.trim();
        chrome.runtime.sendMessage({
            type: MT.PAGE_RESUME,
            notes: text || "Control released by operator."
        });
        removeAllUI();
    };

    actionContainer.appendChild(cancelBtn);
    actionContainer.appendChild(sendBtn);

    modal.appendChild(title);
    modal.appendChild(desc);
    modal.appendChild(textarea);
    modal.appendChild(actionContainer);

    overlay.appendChild(modal);
    shadow.appendChild(overlay);

    setTimeout(() => textarea.focus(), 50);
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        isElementVisible,
        isInteractiveElement,
        extractElementLabel,
        extractElementValue,
        traverseAriaTree,
        renderBadges,
        removeBadges,
        observePage,
        actClick,
        actType,
        actScroll,
        actKeyPress,
        waitForSettlement,
        executeAtomicAction
    };
}

