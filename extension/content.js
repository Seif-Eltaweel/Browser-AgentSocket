// content.js - AgentSocket On-Page HUD & Execution Interactivity (Shadow DOM Isolated)
console.log('[AgentSocket] Content script active (Shadow DOM Encapsulated).');

const MT = (typeof MessageTypes !== "undefined") ? MessageTypes : (window.AgentSocketProtocol ? window.AgentSocketProtocol.MessageTypes : (window.BroProtocol ? window.BroProtocol.MessageTypes : {
    SHOW_GLOW: "show_glow",
    SHOW_TAKEOVER: "show_takeover",
    HIDE_GLOW: "hide_glow",
    PAGE_TAKEOVER: "page_takeover",
    PAGE_STOP: "page_stop",
    PAGE_RESUME: "page_resume"
}));

let currentSessionTitle = "AgentSocket Task";
let currentGroupColor = "purple";
let isShieldActive = false;
let isTakeoverActive = false;
let tooltipTimeout = null;

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
    if (message.type === (MT.SHOW_GLOW || "show_glow")) {
        currentSessionTitle = message.session_title || "AgentSocket Task";
        currentGroupColor = message.group_color || "purple";
        if (!isTakeoverActive) {
            renderActiveGlow(currentSessionTitle, currentGroupColor);
        }
        sendResponse({ status: "success" });
    } else if (message.type === (MT.SHOW_TAKEOVER || "show_takeover")) {
        currentSessionTitle = message.session_title || currentSessionTitle;
        renderTakeoverUI(currentSessionTitle);
        sendResponse({ status: "success" });
    } else if (message.type === (MT.HIDE_GLOW || "hide_glow")) {
        removeAllUI();
        sendResponse({ status: "success" });
    }
    return false;
});


// ============================================================================
// THEME PALETTE HELPER
// ============================================================================
function getThemeColors(colorName) {
    const palette = {
        purple: {
            borderHex: "#9A6DD7",
            subtleBorder: "rgba(154, 109, 215, 0.45)",
            tagBg: "rgba(154, 109, 215, 0.08)",
            tagText: "#9A6DD7"
        },
        blue: {
            borderHex: "#529CCA",
            subtleBorder: "rgba(82, 156, 202, 0.45)",
            tagBg: "rgba(82, 156, 202, 0.08)",
            tagText: "#529CCA"
        },
        green: {
            borderHex: "#4DAB9A",
            subtleBorder: "rgba(77, 171, 154, 0.45)",
            tagBg: "rgba(77, 171, 154, 0.08)",
            tagText: "#4DAB9A"
        },
        orange: {
            borderHex: "#FFAB40",
            subtleBorder: "rgba(255, 171, 64, 0.45)",
            tagBg: "rgba(255, 171, 64, 0.08)",
            tagText: "#FFAB40"
        },
        red: {
            borderHex: "#FF7369",
            subtleBorder: "rgba(255, 115, 105, 0.45)",
            tagBg: "rgba(255, 115, 105, 0.08)",
            tagText: "#FF7369"
        }
    };
    return palette[colorName] || palette.purple;
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
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
            font-size: 12px !important;
            line-height: 1.4 !important;
            box-sizing: border-box !important;
            -webkit-font-smoothing: antialiased !important;
        }
        * {
            box-sizing: border-box !important;
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
        }
        @keyframes agentsocketFadeInUp {
            from { opacity: 0; transform: translate(-50%, 8px); }
            to { opacity: 1; transform: translate(-50%, 0); }
        }
        @keyframes agentsocketModalFadeIn {
            from { opacity: 0; transform: scale(0.96); }
            to { opacity: 1; transform: scale(1); }
        }
        .ab-btn {
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
            font-size: 11.5px !important;
            font-weight: 500 !important;
            padding: 4px 10px !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 5px !important;
            pointer-events: auto !important;
            user-select: none !important;
            outline: none !important;
            border: 1px solid transparent !important;
            box-sizing: border-box !important;
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

function clearShadowRootViews(shadowRoot) {
    clearShadowContent(shadowRoot);
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
// 1. ACTIVE RUNNING STATE: Viewport Frame & Floating HUD Pill & Shield
// ============================================================================
function renderActiveGlow(sessionTitle, groupColor) {
    const shadow = getOrCreateShadowRoot();
    clearShadowRootViews(shadow);
    isShieldActive = true;
    isTakeoverActive = false;

    const theme = getThemeColors(groupColor);

    // A. Full Viewport Border Frame (Clean Notion-style Accent Outline)
    const glowFrame = document.createElement("div");
    glowFrame.id = "ab-glow-frame";
    glowFrame.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        pointer-events: none !important;
        border: 2px solid ${theme.borderHex} !important;
        box-shadow: inset 0 0 12px rgba(0, 0, 0, 0.25) !important;
        box-sizing: border-box !important;
        z-index: 2147483645 !important;
    `;
    shadow.appendChild(glowFrame);

    // B. Interaction Shield Overlay
    const shield = document.createElement("div");
    shield.id = "ab-interaction-shield";
    shield.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        z-index: 2147483646 !important;
        pointer-events: auto !important;
        cursor: not-allowed !important;
        background: rgba(0, 0, 0, 0.03) !important;
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

    // C. Bottom Floating HUD Pill
    const pill = document.createElement("div");
    pill.id = "ab-control-pill";
    pill.style.cssText = `
        position: absolute !important;
        bottom: 20px !important;
        left: 50% !important;
        transform: translate(-50%, 0) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: #202020 !important;
        border: 1px solid #333333 !important;
        border-radius: 6px !important;
        padding: 5px 10px !important;
        color: #e3e2de !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45) !important;
        animation: agentSocketFadeInUp 0.2s ease-out !important;
        box-sizing: border-box !important;
    `;

    // Dot indicator
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 7px !important;
        height: 7px !important;
        background: ${theme.borderHex} !important;
        border-radius: 50% !important;
        display: inline-block !important;
        flex-shrink: 0 !important;
    `;

    // Title label
    const label = document.createElement("div");
    label.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        font-weight: 500 !important;
        color: #EDEDED !important;
        font-size: 12px !important;
    `;
    label.innerHTML = `<span>🔌</span> <span>${escapeHtml(sessionTitle)}</span> <span style="font-size: 11px; color: #8F8E8B; font-weight: 400;">is active</span>`;

    // Action buttons container
    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex !important; align-items: center !important; gap: 6px !important; margin-left: 4px !important;`;

    // Take Over button
    const takeoverBtn = document.createElement("button");
    takeoverBtn.className = "ab-btn";
    takeoverBtn.innerHTML = "<span>✋</span> <span>Take Over</span>";
    takeoverBtn.style.cssText += `
        background: #eb5757 !important;
        color: #ffffff !important;
    `;
    takeoverBtn.onmouseenter = () => { takeoverBtn.style.background = "#d84343"; };
    takeoverBtn.onmouseleave = () => { takeoverBtn.style.background = "#eb5757"; };
    takeoverBtn.onclick = () => {
        renderTakeoverUI(sessionTitle);
        chrome.runtime.sendMessage({
            type: MT.PAGE_TAKEOVER || "page_takeover",
            notes: `Operator initiated manual takeover on ${window.location.hostname}`
        });
    };

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>⏹</span> <span>Stop</span>";
    stopBtn.style.cssText += `
        background: #282828 !important;
        border: 1px solid #333333 !important;
        color: #9b9b9b !important;
    `;
    stopBtn.onmouseenter = () => { stopBtn.style.background = "#303030"; stopBtn.style.color = "#e3e2de"; };
    stopBtn.onmouseleave = () => { stopBtn.style.background = "#282828"; stopBtn.style.color = "#9b9b9b"; };
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: MT.PAGE_STOP || "page_stop" });
        removeAllUI();
    };

    btnGroup.appendChild(takeoverBtn);
    btnGroup.appendChild(stopBtn);

    pill.appendChild(dot);
    pill.appendChild(label);
    pill.appendChild(btnGroup);

    shadow.appendChild(pill);
}

// ============================================================================
// INTERVENTION HINT TOOLTIP
// ============================================================================
function showInterventionTooltip(x, y) {
    const shadow = getOrCreateShadowRoot();
    let tooltip = shadow.getElementById ? shadow.getElementById("ab-shield-tooltip") : shadow.querySelector("#ab-shield-tooltip");
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "ab-shield-tooltip";
        shadow.appendChild(tooltip);
    }

    const safeTop = Math.min(Math.max(y - 45, 16), window.innerHeight - 70);
    const safeLeft = Math.min(Math.max(x - 130, 16), window.innerWidth - 300);

    tooltip.style.cssText = `
        position: fixed !important;
        top: ${safeTop}px !important;
        left: ${safeLeft}px !important;
        z-index: 2147483647 !important;
        background: #202020 !important;
        border: 1px solid #333333 !important;
        color: #e3e2de !important;
        padding: 6px 12px !important;
        border-radius: 5px !important;
        font-size: 11.5px !important;
        font-weight: 400 !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4) !important;
        pointer-events: none !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
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
    clearShadowRootViews(shadow);
    isShieldActive = false; // Disable keyboard and click shielding
    isTakeoverActive = true;

    // Subtle Notion Red Dashed Border to signify operator takeover
    const lockFrame = document.createElement("div");
    lockFrame.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        pointer-events: none !important;
        border: 2px dashed rgba(235, 87, 87, 0.5) !important;
        box-sizing: border-box !important;
    `;
    shadow.appendChild(lockFrame);

    const pill = document.createElement("div");
    pill.id = "ab-takeover-pill";
    pill.style.cssText = `
        position: absolute !important;
        bottom: 20px !important;
        left: 50% !important;
        transform: translate(-50%, 0) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: #202020 !important;
        border: 1px solid #4a2729 !important;
        border-radius: 6px !important;
        padding: 5px 10px !important;
        color: #e3e2de !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45) !important;
        animation: agentSocketFadeInUp 0.2s ease-out !important;
        box-sizing: border-box !important;
    `;

    // Red Lock Status Dot
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 7px !important;
        height: 7px !important;
        background: #ff7369 !important;
        border-radius: 50% !important;
        display: inline-block !important;
        flex-shrink: 0 !important;
    `;

    const label = document.createElement("div");
    label.style.cssText = `
        font-weight: 500 !important;
        color: #ff7369 !important;
        font-size: 12px !important;
    `;
    label.innerHTML = `<span>🔒 Operator Active</span>`;

    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex !important; align-items: center !important; gap: 6px !important;`;

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>⏹</span> <span>Stop</span>";
    stopBtn.style.cssText += `
        background: #282828 !important;
        border: 1px solid #333333 !important;
        color: #9b9b9b !important;
    `;
    stopBtn.onmouseenter = () => { stopBtn.style.background = "#303030"; stopBtn.style.color = "#e3e2de"; };
    stopBtn.onmouseleave = () => { stopBtn.style.background = "#282828"; stopBtn.style.color = "#9b9b9b"; };
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: MT.PAGE_STOP || "page_stop" });
        removeAllUI();
    };

    // Release / Resume button
    const resumeBtn = document.createElement("button");
    resumeBtn.className = "ab-btn";
    resumeBtn.innerHTML = "<span>▶</span> <span>Release to Agent</span>";
    resumeBtn.style.cssText += `
        background: #0f7b6c !important;
        color: #ffffff !important;
    `;
    resumeBtn.onmouseenter = () => { resumeBtn.style.background = "#0b675a"; };
    resumeBtn.onmouseleave = () => { resumeBtn.style.background = "#0f7b6c"; };
    resumeBtn.onclick = () => {
        renderNotesModal(sessionTitle);
    };

    btnGroup.appendChild(stopBtn);
    btnGroup.appendChild(resumeBtn);

    pill.appendChild(dot);
    pill.appendChild(label);
    pill.appendChild(btnGroup);

    shadow.appendChild(pill);
}

// ============================================================================
// 3. HANDOFF NOTES MODAL
// ============================================================================
function renderNotesModal(sessionTitle) {
    const shadow = getOrCreateShadowRoot();

    // Remove any existing modal
    const existingModal = shadow.querySelector ? shadow.querySelector("#ab-notes-overlay") : null;
    if (existingModal) existingModal.remove();

    const overlay = document.createElement("div");
    overlay.id = "ab-notes-overlay";
    overlay.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        background: rgba(0, 0, 0, 0.6) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    `;

    const modal = document.createElement("div");
    modal.id = "ab-notes-card";
    modal.style.cssText = `
        width: 380px !important;
        max-width: 90vw !important;
        background: #202020 !important;
        border: 1px solid #2f2f2f !important;
        border-radius: 8px !important;
        padding: 20px !important;
        color: #e3e2de !important;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6) !important;
        animation: agentSocketModalFadeIn 0.15s ease-out !important;
        box-sizing: border-box !important;
    `;

    const title = document.createElement("h3");
    title.innerText = "Handoff Notes to Agent";
    title.style.cssText = `
        margin: 0 0 6px 0 !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    `;

    const desc = document.createElement("p");
    desc.innerText = "Describe what you completed so the agent can adapt smoothly:";
    desc.style.cssText = `
        margin: 0 0 12px 0 !important;
        font-size: 12px !important;
        color: #9b9b9b !important;
        line-height: 1.4 !important;
    `;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "e.g. Solved CAPTCHA and navigated to checkout page...";
    textarea.style.cssText = `
        width: 100% !important;
        height: 72px !important;
        box-sizing: border-box !important;
        background: #191919 !important;
        color: #e3e2de !important;
        border: 1px solid #333333 !important;
        border-radius: 5px !important;
        padding: 8px 10px !important;
        font-size: 12px !important;
        font-family: inherit !important;
        resize: none !important;
        margin-bottom: 14px !important;
        outline: none !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
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
        display: flex !important;
        justify-content: flex-end !important;
        gap: 8px !important;
    `;

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "ab-btn";
    cancelBtn.innerText = "Cancel";
    cancelBtn.style.cssText += `
        background: #282828 !important;
        border: 1px solid #333333 !important;
        color: #9b9b9b !important;
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
        background: #0f7b6c !important;
        color: #FFFFFF !important;
    `;
    sendBtn.onmouseenter = () => { sendBtn.style.background = "#0b675a"; };
    sendBtn.onmouseleave = () => { sendBtn.style.background = "#0f7b6c"; };
    sendBtn.onclick = () => {
        const text = textarea.value.trim();
        chrome.runtime.sendMessage({
            type: MT.PAGE_RESUME || "page_resume",
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
