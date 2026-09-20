// content.js - AgentSocket On-Page HUD & Execution Interactivity (Shadow DOM Isolated)
console.log('[AgentSocket] Content script active (Shadow DOM Encapsulated).');

const MT = (typeof MessageTypes !== "undefined") ? MessageTypes : (window.AgentSocketProtocol ? window.AgentSocketProtocol.MessageTypes : {
    SHOW_GLOW: "show_glow",
    SHOW_TAKEOVER: "show_takeover",
    HIDE_GLOW: "hide_glow",
    PAGE_TAKEOVER: "page_takeover",
    PAGE_STOP: "page_stop",
    PAGE_RESUME: "page_resume",
    UPDATE_PROGRESS: "update_progress",
    SET_INTENT: "set_intent",
    SET_MILESTONE: "set_milestone"
});

let currentSessionTitle = "AgentSocket Task";
let currentGroupColor = "purple";
let isShieldActive = false;
let isTakeoverActive = false;
let tooltipTimeout = null;

// Spec 34: Live Intent, Action Ticker & ARIA Badging Lifecycle State
let currentIntent = "Initializing session...";
let currentActionSubtext = "(Waiting for agent action...)";
let currentPhaseBadge = "";
let isHudMinimized = false;
let isVisionEnabled = false; // Synchronized from background permissions
let badgeScrollListenerAttached = false;
let activeBadgeElements = []; // Cached element references for scroll repositioning
let repositionRaf = null;
let badgeFadeTimeout = null;

// Spec 32: Strategic Milestones & HUD Progress State
let currentMilestones = [];
let activeMilestoneIndex = 1;
let currentMilestoneTitle = "";

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
        const storedMilestones = sessionStorage.getItem("agentsocket_hud_milestones");
        if (storedMilestones) {
            const parsedM = JSON.parse(storedMilestones);
            if (Array.isArray(parsedM)) {
                currentMilestones = parsedM;
            }
        }
        const storedIdx = sessionStorage.getItem("agentsocket_hud_active_milestone");
        if (storedIdx) {
            activeMilestoneIndex = parseInt(storedIdx, 10) || activeMilestoneIndex;
        }
    } catch (e) {}
}

function saveStoredProgress(progress) {
    try {
        sessionStorage.setItem("agentsocket_hud_progress", JSON.stringify(progress));
        if (currentMilestones && currentMilestones.length > 0) {
            sessionStorage.setItem("agentsocket_hud_milestones", JSON.stringify(currentMilestones));
        }
        sessionStorage.setItem("agentsocket_hud_active_milestone", String(activeMilestoneIndex));
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
                if (response.milestones && Array.isArray(response.milestones)) {
                    currentMilestones = response.milestones;
                }
                if (response.active_milestone_index !== undefined) {
                    activeMilestoneIndex = response.active_milestone_index;
                }
                if (response.enable_vision !== undefined) {
                    isVisionEnabled = !!response.enable_vision;
                }
                if (response.current_action) {
                    currentActionSubtext = response.current_action;
                }
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
            if (message.enable_vision !== undefined) {
                isVisionEnabled = !!message.enable_vision;
            }
            if (message.milestones && Array.isArray(message.milestones)) {
                currentMilestones = message.milestones;
            }
            if (message.active_milestone_index !== undefined) {
                activeMilestoneIndex = message.active_milestone_index;
            }
            if (message.current_action) {
                currentActionSubtext = message.current_action;
            }
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

        case "clear_badges":
            removeBadges();
            sendResponse({ status: "success" });
            break;

        case "observe_page":
        case "OBSERVE_PAGE":
            if (message.options && message.options.enable_vision !== undefined) {
                isVisionEnabled = !!message.options.enable_vision;
            }
            currentActionSubtext = "↳ Action: Scanning ARIA tree & indexing elements...";
            updateHudTicker();

            const obsResult = observePage(message.options || {});
            const elCount = (obsResult && obsResult.elements) ? obsResult.elements.length : 0;
            currentActionSubtext = `↳ State: Indexed ${elCount} interactive elements`;
            updateHudTicker();

            sendResponse(obsResult);
            break;

        case "act_element":
        case "ACT_ELEMENT":
            executeAtomicAction(message.payload || message)
                .then(res => sendResponse(res))
                .catch(err => sendResponse({ status: "error", message: err.message }));
            return true;

        case "set_intent":
        case "SET_INTENT":
        case (MT.SET_INTENT || "set_intent"):
            setIntent(message.intent, message.subtext, message.phase);
            sendResponse({ status: "success" });
            break;

        case MT.SET_PLAN:
        case "set_plan":
        case "SET_PLAN":
            if (message.session_title) currentSessionTitle = message.session_title;
            if (message.milestones && Array.isArray(message.milestones)) {
                currentMilestones = message.milestones;
            }
            if (message.active_index !== undefined) {
                activeMilestoneIndex = message.active_index;
            } else if (message.active_milestone_index !== undefined) {
                activeMilestoneIndex = message.active_milestone_index;
            }
            if (message.progress_percent !== undefined) {
                currentProgress.percent = message.progress_percent;
            }
            if (message.enable_vision !== undefined) {
                isVisionEnabled = !!message.enable_vision;
            }
            // Spec 34: Sync top intent line to active milestone
            const activeM = currentMilestones.find(m => (m.index || m.phase_number) === activeMilestoneIndex) || currentMilestones[0];
            if (activeM) {
                const total = currentMilestones.length;
                currentIntent = `Milestone [${activeMilestoneIndex}/${total}]: ${activeM.title || activeM.name}`;
            }
            if (message.current_action) {
                currentActionSubtext = message.current_action;
            } else {
                currentActionSubtext = "Plan initialized. Ready for execution.";
            }
            saveStoredProgress(currentProgress);
            updateHudTicker();
            sendResponse({ status: "success" });
            break;

        case "set_milestone":
        case "SET_MILESTONE":
        case (MT.SET_MILESTONE || "set_milestone"):
            if (message.milestone_index !== undefined) {
                activeMilestoneIndex = message.milestone_index;
            } else if (message.phase_number !== undefined) {
                activeMilestoneIndex = message.phase_number;
            }
            if (message.milestone_title || message.title) {
                currentMilestoneTitle = message.milestone_title || message.title;
                if (currentMilestones && currentMilestones.length >= activeMilestoneIndex && activeMilestoneIndex > 0) {
                    const m = currentMilestones[activeMilestoneIndex - 1];
                    if (m && typeof m === "object") {
                        m.title = currentMilestoneTitle;
                    }
                }
            }
            const totalM = currentMilestones ? currentMilestones.length : 0;
            const activeTitle = currentMilestoneTitle || (currentMilestones && currentMilestones[activeMilestoneIndex - 1] ? (currentMilestones[activeMilestoneIndex - 1].title || currentMilestones[activeMilestoneIndex - 1].name) : "");
            if (totalM > 0 && activeTitle) {
                currentIntent = `Milestone [${activeMilestoneIndex}/${totalM}]: ${activeTitle}`;
            } else if (activeTitle) {
                currentIntent = activeTitle;
            }
            if (message.phase_number !== undefined && message.total_phases !== undefined) {
                currentPhaseBadge = `[Phase ${message.phase_number}/${message.total_phases}]`;
            } else if (message.phase_number !== undefined) {
                currentPhaseBadge = `[Phase ${message.phase_number}]`;
            }
            if (message.current_action) {
                currentActionSubtext = message.current_action;
            } else if (message.action_detail) {
                currentActionSubtext = message.action_detail;
            }
            if (message.progress_percent !== undefined) {
                currentProgress.percent = message.progress_percent;
            }
            saveStoredProgress(currentProgress);
            updateHudTicker();
            sendResponse({ status: "success" });
            break;

        case "task_complete":
        case "TASK_COMPLETE":
            currentIntent = "✅ Task Complete";
            const resSummary = message.result || message.target_data || "Task completed successfully";
            currentActionSubtext = `↳ Result: ${resSummary}`;
            currentProgress.percent = 100;
            isShieldActive = false;
            removeBadges();
            const compShadow = getOrCreateShadowRoot();
            if (compShadow) {
                const glowFrame = compShadow.getElementById ? compShadow.getElementById("ab-glow-frame") : compShadow.querySelector("#ab-glow-frame");
                if (glowFrame) glowFrame.remove();
                const shield = compShadow.getElementById ? compShadow.getElementById("ab-interaction-shield") : compShadow.querySelector("#ab-interaction-shield");
                if (shield) shield.remove();
            }
            saveStoredProgress(currentProgress);
            updateHudTicker();
            sendResponse({ status: "success" });
            break;

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
        try {
            if (node && node.dataset) {
                node.dataset.agentsocketId = String(id);
            }
        } catch (e) {}

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
    if (badgeFadeTimeout) {
        clearTimeout(badgeFadeTimeout);
        badgeFadeTimeout = null;
    }
    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;
    const container = shadow.getElementById ? shadow.getElementById("agentsocket-badges-container") : shadow.querySelector("#agentsocket-badges-container");
    if (container) {
        container.id = "agentsocket-badges-container-fading";
        container.style.opacity = "0";
        setTimeout(() => {
            if (container.parentNode) container.remove();
        }, 200);
    }
    activeBadgeElements = [];
}

function repositionBadges(container) {
    if (!container || typeof document === "undefined") return;
    container.innerHTML = "";
    const viewHeight = (typeof window !== "undefined" && window.innerHeight) ? window.innerHeight : 800;
    const viewWidth = (typeof window !== "undefined" && window.innerWidth) ? window.innerWidth : 1280;

    for (const elData of activeBadgeElements) {
        let node = (typeof window !== "undefined" && window.__agentsocket_elements) 
            ? window.__agentsocket_elements.get(elData.id) 
            : null;
        const isConnected = (typeof document !== "undefined" && typeof document.contains === "function")
            ? document.contains(node)
            : (typeof document !== "undefined" && document.documentElement && typeof document.documentElement.contains === "function"
                ? document.documentElement.contains(node)
                : true);
        if (!node || !isConnected) {
            if (typeof document !== "undefined" && typeof document.querySelector === "function") {
                try {
                    node = document.querySelector(`[data-agentsocket-id="${elData.id}"]`);
                    if (node && window.__agentsocket_elements) {
                        window.__agentsocket_elements.set(elData.id, node);
                    }
                } catch (e) {}
            }
        }
        if (!node || !node.getBoundingClientRect) continue;

        const rect = node.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        if (rect.bottom < 0 || rect.top > viewHeight || rect.right < 0 || rect.left > viewWidth) continue;

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
}

function handleBadgeReposition() {
    if (repositionRaf) return;
    if (typeof requestAnimationFrame === "function") {
        repositionRaf = requestAnimationFrame(() => {
            repositionRaf = null;
            const shadow = getOrCreateShadowRoot();
            if (!shadow) return;
            const container = shadow.getElementById ? shadow.getElementById("agentsocket-badges-container") : shadow.querySelector("#agentsocket-badges-container");
            if (container) {
                repositionBadges(container);
            }
        });
    } else {
        const shadow = getOrCreateShadowRoot();
        if (!shadow) return;
        const container = shadow.getElementById ? shadow.getElementById("agentsocket-badges-container") : shadow.querySelector("#agentsocket-badges-container");
        if (container) {
            repositionBadges(container);
        }
    }
}

function renderBadges(elements, options = {}) {
    if (typeof document === "undefined") return;
    removeBadges();
    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;

    activeBadgeElements = elements || [];

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
        transition: opacity 0.2s ease !important;
        opacity: 1 !important;
    `;

    repositionBadges(container);
    shadow.appendChild(container);

    // Attach passive scroll and resize listeners with capture: true for nested scrollable containers
    if (!badgeScrollListenerAttached && typeof window !== "undefined" && window.addEventListener) {
        window.addEventListener("scroll", handleBadgeReposition, { passive: true, capture: true });
        window.addEventListener("resize", handleBadgeReposition, { passive: true });
        badgeScrollListenerAttached = true;
    }

    // Spec 34: Badges remain PERSISTENT for human inspection until explicit dismissal (Escape / clear / complete)
    // Only auto-fade if explicitly requested via options.auto_fade === true
    if (options.auto_fade === true) {
        if (badgeFadeTimeout) clearTimeout(badgeFadeTimeout);
        badgeFadeTimeout = setTimeout(() => {
            removeBadges();
        }, 1500);
    }
}

function observePage(options = {}) {
    if (options.enable_vision !== undefined) {
        isVisionEnabled = !!options.enable_vision;
    }
    const root = options.root || (typeof document !== "undefined" ? (document.body || document.documentElement) : null);
    const { elements, tree_text } = traverseAriaTree(root);

    if (options.show_badges !== false && typeof document !== "undefined") {
        renderBadges(elements, options);
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
            currentActionSubtext = `↳ Action: Clicking element [${elementId}]...`;
            updateHudTicker();
            actionResult = actClick(elementId, payload);
            break;
        case "type":
            currentActionSubtext = `↳ Action: Typing into [${elementId}]...`;
            updateHudTicker();
            actionResult = actType(elementId, payload.text, payload);
            break;
        case "scroll":
            currentActionSubtext = `↳ Action: Scrolling ${payload.direction || "down"}...`;
            updateHudTicker();
            actionResult = actScroll(payload.direction, payload.amount);
            break;
        case "key_press":
        case "keypress":
            currentActionSubtext = `↳ Action: Pressing key "${payload.key}"...`;
            updateHudTicker();
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

    if (action === "click") {
        currentActionSubtext = `↳ State: Clicked element [${elementId}]`;
    } else if (action === "type") {
        currentActionSubtext = `↳ State: Typed into [${elementId}]`;
    } else if (action === "scroll") {
        currentActionSubtext = `↳ State: Scrolled ${payload.direction || "down"}`;
    } else if (action === "key_press" || action === "keypress") {
        currentActionSubtext = `↳ State: Pressed key "${payload.key}"`;
    }
    updateHudTicker();

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
        if (typeof host.attachShadow === "function") {
            shadow = host.attachShadow({ mode: "open" });
            injectShadowStyles(shadow);
        } else {
            shadow = host;
        }
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
        if (child.id !== "agentsocket-hud-styles" && child.id !== "agentsocket-badges-container") {
            shadowRoot.removeChild(child);
        }
    });
}

function removeAllUI() {
    isShieldActive = false;
    isTakeoverActive = false;
    removeBadges();
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

    // C. Bottom Floating HUD Pill (Spec 21: Live Intent & Action Ticker)
    const pill = document.createElement("div");
    pill.id = "ab-control-pill";
    pill.style.cssText = `
        position: fixed !important;
        bottom: 20px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        min-width: 420px !important;
        max-width: min(680px, 92vw) !important;
        display: ${isHudMinimized ? 'none' : 'flex'} !important;
        flex-direction: column !important;
        gap: 6px !important;
        padding: 10px 16px 10px 16px !important;
        box-sizing: border-box !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: #18181b !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 14px !important;
        color: #f4f4f5 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05) !important;
        animation: agentSocketFadeInUp 0.25s ease-out !important;
        backdrop-filter: blur(12px) !important;
    `;

    // Row 1: Status dot, Phase badge, Intent string & Controls
    const topRow = document.createElement("div");
    topRow.id = "ab-hud-top-row";
    topRow.style.cssText = `
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        width: 100% !important;
        gap: 12px !important;
    `;

    const leftGroup = document.createElement("div");
    leftGroup.id = "ab-hud-left-group";
    leftGroup.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
        overflow: hidden !important;
        flex: 1 !important;
    `;

    // 1. Pulsing status dot (🟢 Green / 🟡 Amber / 🔴 Red)
    const dot = document.createElement("span");
    dot.id = "ab-status-dot";
    const dotColor = isTakeoverActive ? "#f9e2af" : "#a6e3a1";
    dot.style.cssText = `
        width: 9px !important;
        height: 9px !important;
        background: ${dotColor} !important;
        border-radius: 50% !important;
        display: inline-block !important;
        flex-shrink: 0 !important;
        box-shadow: 0 0 8px ${dotColor} !important;
        ${isTakeoverActive ? '' : 'animation: agentSocketPulse 1.8s infinite ease-in-out !important;'};
    `;

    // 2. Phase badge ([Phase X/Y])
    const phaseBadge = document.createElement("span");
    phaseBadge.id = "ab-phase-badge";
    phaseBadge.style.cssText = `
        display: ${currentPhaseBadge ? 'inline-block' : 'none'} !important;
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 4px !important;
        padding: 1px 6px !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        color: #cdd6f4 !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
    `;
    phaseBadge.textContent = currentPhaseBadge;

    // 3. High-level intent string
    const intentText = document.createElement("span");
    intentText.id = "ab-intent-text";
    intentText.style.cssText = `
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #ffffff !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.3 !important;
    `;
    intentText.textContent = isTakeoverActive ? "Human Takeover Active: Operator in control" : (currentIntent || sessionTitle);

    leftGroup.appendChild(dot);
    leftGroup.appendChild(phaseBadge);
    leftGroup.appendChild(intentText);

    // Controls container (Right)
    const btnGroup = document.createElement("div");
    btnGroup.id = "ab-hud-btn-group";
    btnGroup.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        flex-shrink: 0 !important;
    `;

    // Takeover / Release button
    const takeoverBtn = document.createElement("button");
    takeoverBtn.id = "ab-takeover-btn";
    takeoverBtn.className = "ab-btn";
    if (isTakeoverActive) {
        takeoverBtn.innerHTML = "<span>Release to Agent</span>";
        takeoverBtn.style.cssText += `
            background: #0f7b6c !important;
            color: #ffffff !important;
            font-size: 12px !important;
            padding: 4px 11px !important;
            border-radius: 10px !important;
            border: 1px solid #14b8a6 !important;
        `;
        takeoverBtn.onmouseenter = () => { takeoverBtn.style.background = "#0b675a"; };
        takeoverBtn.onmouseleave = () => { takeoverBtn.style.background = "#0f7b6c"; };
        takeoverBtn.onclick = () => handleRelease();
    } else {
        takeoverBtn.innerHTML = "<span>Take Over</span>";
        takeoverBtn.style.cssText += `
            background: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            color: #e4e4e7 !important;
            font-size: 12px !important;
            padding: 4px 11px !important;
            border-radius: 10px !important;
        `;
        takeoverBtn.onmouseenter = () => { takeoverBtn.style.background = "rgba(255, 255, 255, 0.18)"; };
        takeoverBtn.onmouseleave = () => { takeoverBtn.style.background = "rgba(255, 255, 255, 0.1)"; };
        takeoverBtn.onclick = () => handleTakeover();
    }

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.id = "ab-stop-btn";
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>Stop</span>";
    stopBtn.style.cssText += `
        background: #ef4444 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        padding: 4px 10px !important;
        border-radius: 10px !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3) !important;
    `;
    stopBtn.onmouseenter = () => { stopBtn.style.background = "#dc2626"; };
    stopBtn.onmouseleave = () => { stopBtn.style.background = "#ef4444"; };
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: MT.PAGE_STOP });
        removeAllUI();
    };

    // Minimize button (✕)
    const minBtn = document.createElement("button");
    minBtn.id = "ab-minimize-btn";
    minBtn.className = "ab-btn";
    minBtn.title = "Minimize HUD to floating pill";
    minBtn.innerHTML = "<span>✕</span>";
    minBtn.style.cssText += `
        background: transparent !important;
        border: none !important;
        color: #71717a !important;
        font-size: 11px !important;
        padding: 4px 6px !important;
        border-radius: 8px !important;
        line-height: 1 !important;
    `;
    minBtn.onmouseenter = () => { minBtn.style.color = "#ffffff"; minBtn.style.background = "rgba(255, 255, 255, 0.1)"; };
    minBtn.onmouseleave = () => { minBtn.style.color = "#71717a"; minBtn.style.background = "transparent"; };
    minBtn.onclick = () => toggleMinimize();

    btnGroup.appendChild(takeoverBtn);
    btnGroup.appendChild(stopBtn);
    btnGroup.appendChild(minBtn);

    topRow.appendChild(leftGroup);
    topRow.appendChild(btnGroup);

    // Row 2: Strategic Milestone Indicator (Spec 32)
    const milestoneRow = document.createElement("div");
    milestoneRow.id = "ab-milestone-row";
    milestoneRow.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        color: #cdd6f4 !important;
        line-height: 1.4 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin-top: 2px !important;
    `;

    // Row 3: Visual Glowing Progress Track (Spec 32)
    const progressContainer = document.createElement("div");
    progressContainer.id = "ab-hud-progress-container";
    progressContainer.style.cssText = `
        width: 100% !important;
        height: 4px !important;
        background: rgba(255, 255, 255, 0.1) !important;
        border-radius: 2px !important;
        margin: 3px 0 4px 0 !important;
        overflow: hidden !important;
        display: flex !important;
    `;

    const progressBar = document.createElement("div");
    progressBar.id = "ab-hud-progress-bar";
    progressBar.style.cssText = `
        height: 100% !important;
        width: 0% !important;
        background: linear-gradient(90deg, #38bdf8, #818cf8) !important;
        border-radius: 2px !important;
        box-shadow: 0 0 8px rgba(56, 189, 248, 0.5) !important;
        transition: width 0.3s ease !important;
    `;
    progressContainer.appendChild(progressBar);

    // Row 4: Live micro-action ticker (Spec 32)
    const subtextRow = document.createElement("div");
    subtextRow.id = "ab-action-subtext";
    subtextRow.style.cssText = `
        font-size: 11.5px !important;
        color: #a1a1aa !important;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        padding-left: 2px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.3 !important;
    `;

    pill.appendChild(topRow);
    pill.appendChild(milestoneRow);
    pill.appendChild(progressContainer);
    pill.appendChild(subtextRow);
    shadow.appendChild(pill);

    // D. Floating Minimized Glow Pill (Bottom-Right)
    const minPill = document.createElement("div");
    minPill.id = "ab-minimized-pill";
    minPill.style.cssText = `
        position: fixed !important;
        bottom: 20px !important;
        right: 20px !important;
        z-index: 2147483647 !important;
        background: #18181b !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 20px !important;
        padding: 6px 12px !important;
        display: ${isHudMinimized ? 'flex' : 'none'} !important;
        align-items: center !important;
        gap: 8px !important;
        cursor: pointer !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5) !important;
        backdrop-filter: blur(10px) !important;
        user-select: none !important;
        pointer-events: auto !important;
        transition: transform 0.15s ease !important;
    `;
    minPill.onmouseenter = () => { minPill.style.transform = "scale(1.04)"; };
    minPill.onmouseleave = () => { minPill.style.transform = "scale(1)"; };
    minPill.onclick = () => toggleMinimize();

    const minDot = document.createElement("span");
    minDot.id = "ab-min-dot";
    minDot.style.cssText = `
        width: 8px !important;
        height: 8px !important;
        background: ${dotColor} !important;
        border-radius: 50% !important;
        box-shadow: 0 0 8px ${dotColor} !important;
        ${isTakeoverActive ? '' : 'animation: agentSocketPulse 1.8s infinite ease-in-out !important;'};
    `;

    const minLabel = document.createElement("span");
    minLabel.id = "ab-min-label";
    minLabel.style.cssText = `
        font-size: 11px !important;
        font-weight: 500 !important;
        color: #e4e4e7 !important;
    `;
    const snippet = currentIntent.length > 24 ? currentIntent.slice(0, 22) + "..." : currentIntent;
    minLabel.textContent = isTakeoverActive ? "Takeover Active" : snippet;

    const minExpand = document.createElement("span");
    minExpand.style.cssText = `font-size: 10px !important; color: #71717a !important;`;
    minExpand.textContent = "⤢";

    minPill.appendChild(minDot);
    minPill.appendChild(minLabel);
    minPill.appendChild(minExpand);
    shadow.appendChild(minPill);

    updateHudTicker();
}

// Live Update Ticker Function (Zero Flickering, Spec 32)
function updateHudTicker() {
    const shadow = getOrCreateShadowRoot();
    if (!shadow || (typeof shadow.getElementById !== "function" && typeof shadow.querySelector !== "function")) return;

    const dot = shadow.getElementById ? shadow.getElementById("ab-status-dot") : shadow.querySelector("#ab-status-dot");
    const phase = shadow.getElementById ? shadow.getElementById("ab-phase-badge") : shadow.querySelector("#ab-phase-badge");
    const intent = shadow.getElementById ? shadow.getElementById("ab-intent-text") : shadow.querySelector("#ab-intent-text");
    const milestoneRow = shadow.getElementById ? shadow.getElementById("ab-milestone-row") : shadow.querySelector("#ab-milestone-row");
    const progressBar = shadow.getElementById ? shadow.getElementById("ab-hud-progress-bar") : shadow.querySelector("#ab-hud-progress-bar");
    const subtext = shadow.getElementById ? shadow.getElementById("ab-action-subtext") : shadow.querySelector("#ab-action-subtext");
    const minDot = shadow.getElementById ? shadow.getElementById("ab-min-dot") : shadow.querySelector("#ab-min-dot");
    const minLabel = shadow.getElementById ? shadow.getElementById("ab-min-label") : shadow.querySelector("#ab-min-label");
    const takeoverBtn = shadow.getElementById ? shadow.getElementById("ab-takeover-btn") : shadow.querySelector("#ab-takeover-btn");

    const dotColor = isTakeoverActive ? "#f9e2af" : "#a6e3a1";

    if (dot) {
        dot.style.background = dotColor;
        dot.style.boxShadow = `0 0 8px ${dotColor}`;
        dot.style.animation = isTakeoverActive ? 'none' : 'agentSocketPulse 1.8s infinite ease-in-out';
    }
    if (minDot) {
        minDot.style.background = dotColor;
        minDot.style.boxShadow = `0 0 8px ${dotColor}`;
        minDot.style.animation = isTakeoverActive ? 'none' : 'agentSocketPulse 1.8s infinite ease-in-out';
    }

    if (takeoverBtn) {
        if (isTakeoverActive) {
            takeoverBtn.innerHTML = "<span>Release to Agent</span>";
            takeoverBtn.style.background = "#0f7b6c";
            takeoverBtn.style.color = "#ffffff";
            takeoverBtn.style.border = "1px solid #14b8a6";
            takeoverBtn.onclick = () => handleRelease();
        } else {
            takeoverBtn.innerHTML = "<span>Take Over</span>";
            takeoverBtn.style.background = "rgba(255, 255, 255, 0.1)";
            takeoverBtn.style.color = "#e4e4e7";
            takeoverBtn.style.border = "1px solid rgba(255, 255, 255, 0.2)";
            takeoverBtn.onclick = () => handleTakeover();
        }
    }

    if (phase) {
        if (currentPhaseBadge) {
            phase.style.display = "inline-block";
            phase.textContent = currentPhaseBadge;
        } else {
            phase.style.display = "none";
        }
    }

    if (intent) {
        intent.textContent = isTakeoverActive
            ? "Human Takeover Active: Operator in control"
            : (currentIntent || currentSessionTitle || "AgentSocket Task");
    }

    // Spec 32: Milestone text computation
    let milestoneText = "";
    let activeTitle = "";
    if (currentMilestones && currentMilestones.length > 0) {
        const totalM = currentMilestones.length;
        const currentIdx = Math.max(1, Math.min(activeMilestoneIndex || 1, totalM));
        const mObj = currentMilestones[currentIdx - 1];
        activeTitle = (mObj && typeof mObj === "object" ? mObj.title : mObj) || currentMilestoneTitle || `Milestone ${currentIdx}`;
        if (isTakeoverActive) {
            milestoneText = `🔒 Milestone [${currentIdx}/${totalM}]: ${activeTitle} (Paused)`;
        } else {
            milestoneText = `🎯 Milestone [${currentIdx}/${totalM}]: ${activeTitle}`;
        }
    } else if (currentMilestoneTitle) {
        activeTitle = currentMilestoneTitle;
        if (isTakeoverActive) {
            milestoneText = `🔒 Milestone: ${currentMilestoneTitle} (Paused)`;
        } else {
            milestoneText = `🎯 Milestone: ${currentMilestoneTitle}`;
        }
    } else {
        milestoneText = isTakeoverActive ? "🔒 Autonomous Execution (Paused)" : "🎯 Autonomous Execution";
    }

    if (milestoneRow) {
        milestoneRow.textContent = milestoneText;
    }

    // Spec 32: Glowing progress track calculation
    let calculatedPercent = currentProgress.percent || 0;
    if (currentMilestones && currentMilestones.length > 0) {
        let completed = 0;
        currentMilestones.forEach((m, i) => {
            if (m && typeof m === "object" && m.status === "completed") {
                completed++;
            } else if (i + 1 < (activeMilestoneIndex || 1)) {
                completed++;
            }
        });
        const derived = Math.round((completed / currentMilestones.length) * 100);
        calculatedPercent = Math.max(calculatedPercent, derived);
    }
    calculatedPercent = Math.min(Math.max(calculatedPercent, 0), 100);

    if (progressBar) {
        progressBar.style.width = `${calculatedPercent}%`;
        if (isTakeoverActive) {
            progressBar.style.background = "linear-gradient(90deg, #f59e0b, #d97706)";
            progressBar.style.boxShadow = "0 0 8px rgba(245, 158, 11, 0.5)";
        } else {
            progressBar.style.background = "linear-gradient(90deg, #38bdf8, #818cf8)";
            progressBar.style.boxShadow = "0 0 8px rgba(56, 189, 248, 0.5)";
        }
    }

    // Spec 32: Live micro-action ticker
    if (subtext) {
        if (isTakeoverActive) {
            subtext.textContent = "↳ Human Takeover Active: Operator in control (Click 'Release to Agent' when ready)";
            subtext.style.color = "#fcd34d";
        } else {
            let actionStr = currentActionSubtext || "(Observing page state...)";
            if (!actionStr.startsWith("↳ Action:") && !actionStr.startsWith("↳")) {
                subtext.textContent = `↳ Action: ${actionStr}`;
            } else {
                subtext.textContent = actionStr;
            }
            subtext.style.color = "#a1a1aa";
        }
    }

    if (minLabel) {
        if (isTakeoverActive) {
            minLabel.textContent = "Takeover Active";
        } else if (activeTitle) {
            const shortTitle = activeTitle.length > 20 ? activeTitle.slice(0, 18) + "..." : activeTitle;
            minLabel.textContent = `M[${activeMilestoneIndex || 1}]: ${shortTitle}`;
        } else {
            minLabel.textContent = currentIntent.length > 24 ? currentIntent.slice(0, 22) + "..." : currentIntent;
        }
    }
}

function toggleMinimize(forceState) {
    isHudMinimized = (typeof forceState === "boolean") ? forceState : !isHudMinimized;
    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;
    const pill = shadow.getElementById ? shadow.getElementById("ab-control-pill") : shadow.querySelector("#ab-control-pill");
    const minPill = shadow.getElementById ? shadow.getElementById("ab-minimized-pill") : shadow.querySelector("#ab-minimized-pill");
    if (pill) pill.style.display = isHudMinimized ? "none" : "flex";
    if (minPill) minPill.style.display = isHudMinimized ? "flex" : "none";
}

function setIntent(intent, subtext, phase) {
    if (intent !== undefined && intent !== null) currentIntent = String(intent);
    if (subtext !== undefined && subtext !== null) currentActionSubtext = String(subtext);
    if (phase !== undefined && phase !== null) currentPhaseBadge = String(phase);
    updateHudTicker();
}

function setMilestone(title, phaseNumber, totalPhases) {
    if (title) {
        currentIntent = String(title);
        currentMilestoneTitle = String(title);
    }
    if (phaseNumber !== undefined) {
        activeMilestoneIndex = parseInt(phaseNumber, 10) || activeMilestoneIndex;
    }
    if (phaseNumber !== undefined && totalPhases !== undefined) {
        currentPhaseBadge = `[Phase ${phaseNumber}/${totalPhases}]`;
    } else if (phaseNumber !== undefined) {
        currentPhaseBadge = `[Phase ${phaseNumber}]`;
    }
    updateHudTicker();
}

function handleTakeover(notes) {
    isTakeoverActive = true;
    isShieldActive = false; // Lift lockout shield so user can interact
    removeBadges(); // Spec 34: Clear badges on takeover

    const shadow = getOrCreateShadowRoot();
    if (shadow) {
        const shield = shadow.getElementById ? shadow.getElementById("ab-interaction-shield") : shadow.querySelector("#ab-interaction-shield");
        if (shield) {
            shield.style.pointerEvents = "none";
            shield.style.display = "none";
        }
        const takeoverBtn = shadow.getElementById ? shadow.getElementById("ab-takeover-btn") : shadow.querySelector("#ab-takeover-btn");
        if (takeoverBtn) {
            takeoverBtn.innerHTML = "<span>Release to Agent</span>";
            takeoverBtn.style.background = "#0f7b6c";
            takeoverBtn.style.color = "#ffffff";
            takeoverBtn.style.border = "1px solid #14b8a6";
            takeoverBtn.onclick = () => handleRelease();
        }
    }

    updateHudTicker();

    try {
        chrome.runtime.sendMessage({
            type: MT.PAGE_TAKEOVER || "page_takeover",
            notes: notes || `Operator initiated manual takeover on ${typeof window !== "undefined" && window.location ? window.location.hostname : "tab"}`
        });
    } catch (e) {}
}

function handleRelease(notes) {
    currentIntent = "Resuming task... Observing page";
    currentActionSubtext = "Capturing live ARIA tree snapshot...";
    isTakeoverActive = false;
    isShieldActive = true; // Re-engage shield for agent execution

    const shadow = getOrCreateShadowRoot();
    if (shadow) {
        const shield = shadow.getElementById ? shadow.getElementById("ab-interaction-shield") : shadow.querySelector("#ab-interaction-shield");
        if (shield) {
            shield.style.pointerEvents = "auto";
            shield.style.display = "block";
        }
        const takeoverBtn = shadow.getElementById ? shadow.getElementById("ab-takeover-btn") : shadow.querySelector("#ab-takeover-btn");
        if (takeoverBtn) {
            takeoverBtn.innerHTML = "<span>Take Over</span>";
            takeoverBtn.style.background = "rgba(255, 255, 255, 0.1)";
            takeoverBtn.style.color = "#e4e4e7";
            takeoverBtn.style.border = "1px solid rgba(255, 255, 255, 0.2)";
            takeoverBtn.onclick = () => handleTakeover();
        }
    }

    updateHudTicker();

    // Instant Auto-Observe on Release (Spec 21 contract)
    let freshObs = null;
    try {
        if (typeof observePage === "function") {
            freshObs = observePage({ show_badges: true });
        }
    } catch (e) {
        console.warn("[AgentSocket] Auto-observe failed on release:", e);
    }

    const releaseNotes = notes || "Control released by operator.";

    try {
        chrome.runtime.sendMessage({
            type: MT.PAGE_RESUME || "page_resume",
            notes: releaseNotes,
            observation: freshObs
        });
    } catch (e) {}

    return { status: "success", notes: releaseNotes, observation: freshObs };
}

// Backwards compatibility aliases
const renderLiveIntentHUD = renderActiveGlow;
function updateHudProgressBar(progressData, groupColor) {
    if (progressData && progressData.stepTitle) {
        currentActionSubtext = progressData.stepTitle;
    }
    updateHudTicker();
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
// 2. TAKEOVER / LOCKOUT STATE: Operator in Control (BUG-04 Layout-Popping Fixed)
// ============================================================================
function renderTakeoverUI(sessionTitle) {
    if (sessionTitle) currentSessionTitle = sessionTitle;
    isShieldActive = false;
    isTakeoverActive = true;

    const shadow = getOrCreateShadowRoot();
    if (!shadow) return;

    let pill = shadow.getElementById ? shadow.getElementById("ab-control-pill") : shadow.querySelector("#ab-control-pill");
    if (!pill) {
        renderActiveGlow(currentSessionTitle, currentGroupColor);
        isShieldActive = false;
        isTakeoverActive = true;
    }

    // Lift lockout shield so operator can interact freely
    const shield = shadow.getElementById ? shadow.getElementById("ab-interaction-shield") : shadow.querySelector("#ab-interaction-shield");
    if (shield) {
        shield.style.pointerEvents = "none";
        shield.style.display = "none";
    }

    // Transition glow frame to subtle dashed amber outline
    const glowFrame = shadow.getElementById ? shadow.getElementById("ab-glow-frame") : shadow.querySelector("#ab-glow-frame");
    if (glowFrame) {
        glowFrame.style.border = "3px dashed rgba(249, 226, 175, 0.7)";
        glowFrame.style.boxShadow = "inset 0 0 24px rgba(249, 226, 175, 0.2)";
    }

    updateHudTicker();
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
        margin: 0 0 8px 0;
        font-size: 14px;
        font-weight: 600;
        color: #ffffff;
    `;

    const desc = document.createElement("p");
    desc.innerText = "Briefly explain what you did, or leave instructions for the agent to proceed.";
    desc.style.cssText = `
        margin: 0 0 12px 0;
        font-size: 12px;
        color: #9b9b9b;
        line-height: 1.4;
    `;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "e.g., Solved CAPTCHA and logged into dashboard.";
    textarea.style.cssText = `
        width: 100%;
        height: 80px;
        background: #141414;
        border: 1px solid #333333;
        border-radius: 6px;
        padding: 8px 10px;
        color: #e3e2de;
        font-family: inherit;
        font-size: 12px;
        box-sizing: border-box;
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

if (typeof window !== "undefined") {
    window.__agentsocket_set_intent = setIntent;
    window.__agentsocket_set_milestone = setMilestone;
    window.__agentsocket_takeover = handleTakeover;
    window.__agentsocket_release = handleRelease;
    window.__agentsocket_toggle_minimize = toggleMinimize;
    window.__agentsocket_reposition_badges = handleBadgeReposition;
    window.__agentsocket_clear_badges = removeBadges;

    if (window.addEventListener) {
        window.addEventListener("keydown", (e) => {
            if (e && e.key === "Escape") {
                removeBadges();
            }
        }, { passive: true });
    }
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
        repositionBadges,
        handleBadgeReposition,
        observePage,
        actClick,
        actType,
        actScroll,
        actKeyPress,
        waitForSettlement,
        executeAtomicAction,
        setIntent,
        setMilestone,
        handleTakeover,
        handleRelease,
        toggleMinimize,
        renderActiveGlow,
        renderTakeoverUI,
        renderLiveIntentHUD,
        updateHudTicker
    };
}
