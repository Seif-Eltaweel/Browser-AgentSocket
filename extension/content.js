// content.js - Agent Bro Hands On-Page HUD & Execution Interactivity
console.log('[Agent Bro Hands] Content script active.');

let currentSessionTitle = "Agent Bro Task";
let currentGroupColor = "purple";
let isShieldActive = false;
let tooltipTimeout = null;

// ============================================================================
// KEYBOARD GUARD (INTERACTION SHIELD)
// Blocks accidental typing on the host page during autonomous execution
// ============================================================================
function keyboardGuard(e) {
    if (!isShieldActive) return;
    const hudContainer = document.getElementById("agent-bro-hands-hud-container");
    if (hudContainer && hudContainer.contains(e.target)) {
        return; // Allow typing inside HUD input elements / textareas
    }
    e.stopPropagation();
    e.preventDefault();
}

window.addEventListener("keydown", keyboardGuard, true);
window.addEventListener("keyup", keyboardGuard, true);
window.addEventListener("keypress", keyboardGuard, true);

// ============================================================================
// MESSAGE LISTENER
// ============================================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "show_glow") {
        currentSessionTitle = message.session_title || "Agent Bro Task";
        currentGroupColor = message.group_color || "purple";
        renderActiveGlow(currentSessionTitle, currentGroupColor);
        sendResponse({ status: "success" });
    } else if (message.type === "hide_glow") {
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
            borderHex: "#BB86FC",
            glowColor: "rgba(187, 134, 252, 0.6)",
            accentGrad: "linear-gradient(135deg, #7b1fa2, #9c27b0)",
            tagBg: "rgba(187, 134, 252, 0.15)"
        },
        blue: {
            borderHex: "#4285F4",
            glowColor: "rgba(66, 133, 244, 0.6)",
            accentGrad: "linear-gradient(135deg, #1976d2, #4285f4)",
            tagBg: "rgba(66, 133, 244, 0.15)"
        },
        green: {
            borderHex: "#34A853",
            glowColor: "rgba(52, 168, 83, 0.6)",
            accentGrad: "linear-gradient(135deg, #2e7d32, #34a853)",
            tagBg: "rgba(52, 168, 83, 0.15)"
        },
        orange: {
            borderHex: "#FF8F00",
            glowColor: "rgba(255, 143, 0, 0.6)",
            accentGrad: "linear-gradient(135deg, #ef6c00, #ff8f00)",
            tagBg: "rgba(255, 143, 0, 0.15)"
        },
        red: {
            borderHex: "#EA4335",
            glowColor: "rgba(234, 67, 53, 0.6)",
            accentGrad: "linear-gradient(135deg, #c62828, #ea4335)",
            tagBg: "rgba(234, 67, 53, 0.15)"
        }
    };
    return palette[colorName] || palette.purple;
}

// ============================================================================
// UI CONTAINER & TEARDOWN
// ============================================================================
function getOrCreateRootContainer() {
    let root = document.getElementById("agent-bro-hands-hud-container");
    if (!root) {
        root = document.createElement("div");
        root.id = "agent-bro-hands-hud-container";
        root.style.cssText = `
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            pointer-events: none !important;
            z-index: 2147483647 !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
            font-size: 13px !important;
            line-height: 1.4 !important;
            box-sizing: border-box !important;
        `;
        const host = document.body || document.documentElement;
        host.appendChild(root);
        injectGlobalStyles();
    }
    return root;
}

function removeAllUI() {
    isShieldActive = false;
    clearTimeout(tooltipTimeout);
    const root = document.getElementById("agent-bro-hands-hud-container");
    if (root && root.parentNode) {
        root.parentNode.removeChild(root);
    }
}

function injectGlobalStyles() {
    if (document.getElementById("agent-bro-hud-styles")) return;
    const style = document.createElement("style");
    style.id = "agent-bro-hud-styles";
    style.textContent = `
        @keyframes agentBroGlowPulse {
            0% { 
                box-shadow: inset 0 0 20px 4px var(--ab-glow-color, rgba(66, 133, 244, 0.4)), 0 0 12px 2px var(--ab-glow-color, rgba(66, 133, 244, 0.4)); 
            }
            100% { 
                box-shadow: inset 0 0 40px 10px var(--ab-glow-color, rgba(66, 133, 244, 0.75)), 0 0 24px 6px var(--ab-glow-color, rgba(66, 133, 244, 0.6)); 
            }
        }
        @keyframes agentBroDotPing {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.4); opacity: 0.6; }
            100% { transform: scale(1); opacity: 1; }
        }
        @keyframes agentBroFadeInUp {
            from { opacity: 0; transform: translate(-50%, 16px); }
            to { opacity: 1; transform: translate(-50%, 0); }
        }
        @keyframes agentBroModalFadeIn {
            from { opacity: 0; transform: translate(-50%, -46%); }
            to { opacity: 1; transform: translate(-50%, -50%); }
        }
        .ab-btn {
            font-family: inherit !important;
            font-size: 12px !important;
            font-weight: 600 !important;
            padding: 6px 14px !important;
            border-radius: 20px !important;
            cursor: pointer !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 6px !important;
            pointer-events: auto !important;
            user-select: none !important;
            outline: none !important;
            border: none !important;
        }
        .ab-btn:hover {
            transform: translateY(-1px) !important;
            filter: brightness(1.1) !important;
        }
        .ab-btn:active {
            transform: translateY(0px) !important;
            filter: brightness(0.95) !important;
        }
    `;
    document.head.appendChild(style);
}

// ============================================================================
// 1. ACTIVE RUNNING STATE: Viewport Glow & Floating HUD Pill & Shield
// ============================================================================
function renderActiveGlow(sessionTitle, groupColor) {
    const root = getOrCreateRootContainer();
    root.innerHTML = ""; // Clear existing child views
    isShieldActive = true;

    const theme = getThemeColors(groupColor);
    root.style.setProperty("--ab-glow-color", theme.glowColor);

    // A. Full Viewport Border Glow
    const glowFrame = document.createElement("div");
    glowFrame.id = "ab-glow-frame";
    glowFrame.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        pointer-events: none !important;
        border: 3.5px solid ${theme.borderHex} !important;
        box-shadow: inset 0 0 24px 6px ${theme.glowColor}, 0 0 16px 2px ${theme.glowColor} !important;
        animation: agentBroGlowPulse 2.2s infinite alternate ease-in-out !important;
        box-sizing: border-box !important;
        z-index: 2147483645 !important;
    `;
    root.appendChild(glowFrame);

    // B. Interaction Shield Overlay (Blocks accidental clicks, scrolls, selection on host page)
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
        background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0.02) 60%, ${theme.tagBg} 100%) !important;
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

    root.appendChild(shield);

    // C. Bottom Floating HUD Pill
    const pill = document.createElement("div");
    pill.id = "ab-control-pill";
    pill.style.cssText = `
        position: absolute !important;
        bottom: 24px !important;
        left: 50% !important;
        transform: translate(-50%, 0) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: rgba(15, 12, 27, 0.9) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 32px !important;
        padding: 8px 16px !important;
        color: #E2DDF0 !important;
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 16px ${theme.glowColor} !important;
        animation: agentBroFadeInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        box-sizing: border-box !important;
    `;

    // Dot indicator
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 8px !important;
        height: 8px !important;
        background: ${theme.borderHex} !important;
        border-radius: 50% !important;
        box-shadow: 0 0 8px ${theme.borderHex} !important;
        animation: agentBroDotPing 1.8s infinite ease-in-out !important;
        display: inline-block !important;
    `;

    // Title label
    const label = document.createElement("div");
    label.style.cssText = `
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        font-weight: 600 !important;
        color: #FFFFFF !important;
        font-size: 12.5px !important;
    `;
    label.innerHTML = `<span style="opacity: 0.85;">🤖</span> <span>${escapeHtml(sessionTitle)}</span> <span style="font-size: 11px; opacity: 0.6; font-weight: 400;">is active</span>`;

    // Action buttons container
    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex !important; align-items: center !important; gap: 8px !important; margin-left: 4px !important;`;

    // Take Over button
    const takeoverBtn = document.createElement("button");
    takeoverBtn.className = "ab-btn";
    takeoverBtn.innerHTML = "<span>✋</span> <span>Take Over</span>";
    takeoverBtn.style.cssText += `
        background: linear-gradient(135deg, #d32f2f, #ea4335) !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(234, 67, 53, 0.35) !important;
    `;
    takeoverBtn.onclick = () => {
        renderTakeoverUI(sessionTitle);
        chrome.runtime.sendMessage({
            type: "page_takeover",
            notes: `Operator initiated manual takeover on ${window.location.hostname}`
        });
    };

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>⏹</span> <span>Stop</span>";
    stopBtn.style.cssText += `
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #e0e0e0 !important;
    `;
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: "page_stop" });
        removeAllUI();
    };

    btnGroup.appendChild(takeoverBtn);
    btnGroup.appendChild(stopBtn);

    pill.appendChild(dot);
    pill.appendChild(label);
    pill.appendChild(btnGroup);

    root.appendChild(pill);
}

// ============================================================================
// INTERVENTION HINT TOOLTIP
// ============================================================================
function showInterventionTooltip(x, y) {
    const root = getOrCreateRootContainer();
    let tooltip = document.getElementById("ab-shield-tooltip");
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "ab-shield-tooltip";
        root.appendChild(tooltip);
    }

    const safeTop = Math.min(Math.max(y - 50, 20), window.innerHeight - 80);
    const safeLeft = Math.min(Math.max(x - 140, 20), window.innerWidth - 320);

    tooltip.style.cssText = `
        position: fixed !important;
        top: ${safeTop}px !important;
        left: ${safeLeft}px !important;
        z-index: 2147483647 !important;
        background: rgba(20, 16, 36, 0.95) !important;
        border: 1px solid rgba(187, 134, 252, 0.4) !important;
        color: #F1EDFA !important;
        padding: 8px 14px !important;
        border-radius: 12px !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.6), 0 0 14px rgba(187, 134, 252, 0.25) !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        pointer-events: none !important;
        animation: agentBroFadeInUp 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
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
    const root = getOrCreateRootContainer();
    root.innerHTML = "";
    isShieldActive = false; // Disable keyboard and click shielding

    // Subtle Amber/Red Border to signify human intervention lockout
    const lockFrame = document.createElement("div");
    lockFrame.style.cssText = `
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        pointer-events: none !important;
        border: 2px dashed rgba(234, 67, 53, 0.5) !important;
        box-sizing: border-box !important;
    `;
    root.appendChild(lockFrame);

    const pill = document.createElement("div");
    pill.id = "ab-takeover-pill";
    pill.style.cssText = `
        position: absolute !important;
        bottom: 24px !important;
        left: 50% !important;
        transform: translate(-50%, 0) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        background: rgba(18, 14, 28, 0.95) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(234, 67, 53, 0.35) !important;
        border-radius: 32px !important;
        padding: 8px 16px !important;
        color: #E2DDF0 !important;
        display: flex !important;
        align-items: center !important;
        gap: 14px !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 16px rgba(234, 67, 53, 0.25) !important;
        animation: agentBroFadeInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        box-sizing: border-box !important;
    `;

    // Red Lock Status Dot
    const dot = document.createElement("span");
    dot.style.cssText = `
        width: 8px !important;
        height: 8px !important;
        background: #EA4335 !important;
        border-radius: 50% !important;
        box-shadow: 0 0 8px #EA4335 !important;
        display: inline-block !important;
    `;

    const label = document.createElement("div");
    label.style.cssText = `
        font-weight: 600 !important;
        color: #FFCDD2 !important;
        font-size: 12.5px !important;
    `;
    label.innerHTML = `<span>🔒 Operator Takeover Active</span>`;

    const btnGroup = document.createElement("div");
    btnGroup.style.cssText = `display: flex !important; align-items: center !important; gap: 8px !important;`;

    // Stop button
    const stopBtn = document.createElement("button");
    stopBtn.className = "ab-btn";
    stopBtn.innerHTML = "<span>⏹</span> <span>Stop</span>";
    stopBtn.style.cssText += `
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #e0e0e0 !important;
    `;
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: "page_stop" });
        removeAllUI();
    };

    // Release / Resume button
    const resumeBtn = document.createElement("button");
    resumeBtn.className = "ab-btn";
    resumeBtn.innerHTML = "<span>▶</span> <span>Release to Agent</span>";
    resumeBtn.style.cssText += `
        background: linear-gradient(135deg, #2e7d32, #34a853) !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(52, 168, 83, 0.35) !important;
    `;
    resumeBtn.onclick = () => {
        renderNotesModal(sessionTitle);
    };

    btnGroup.appendChild(stopBtn);
    btnGroup.appendChild(resumeBtn);

    pill.appendChild(dot);
    pill.appendChild(label);
    pill.appendChild(btnGroup);

    root.appendChild(pill);
}

// ============================================================================
// 3. HANDOFF NOTES MODAL
// ============================================================================
function renderNotesModal(sessionTitle) {
    const root = getOrCreateRootContainer();

    // Remove any existing modal
    const existingModal = document.getElementById("ab-notes-overlay");
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
        backdrop-filter: blur(4px) !important;
        -webkit-backdrop-filter: blur(4px) !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    `;

    const modal = document.createElement("div");
    modal.id = "ab-notes-card";
    modal.style.cssText = `
        width: 420px !important;
        max-width: 90vw !important;
        background: rgba(20, 16, 34, 0.95) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 16px !important;
        padding: 22px !important;
        color: #E2DDF0 !important;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 24px rgba(187, 134, 252, 0.2) !important;
        animation: agentBroModalFadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
        box-sizing: border-box !important;
    `;

    const title = document.createElement("h3");
    title.innerText = "Handoff Notes to Agent";
    title.style.cssText = `
        margin: 0 0 6px 0 !important;
        font-size: 16px !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    `;

    const desc = document.createElement("p");
    desc.innerText = "Briefly describe what you completed or changed so the agent can adapt smoothly:";
    desc.style.cssText = `
        margin: 0 0 14px 0 !important;
        font-size: 12px !important;
        color: #A69EBA !important;
        line-height: 1.4 !important;
    `;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "e.g. Solved CAPTCHA and navigated to checkout page...";
    textarea.style.cssText = `
        width: 100% !important;
        height: 80px !important;
        box-sizing: border-box !important;
        background: rgba(28, 22, 48, 0.8) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 8px !important;
        padding: 10px !important;
        font-size: 12.5px !important;
        font-family: inherit !important;
        resize: none !important;
        margin-bottom: 18px !important;
        outline: none !important;
        transition: border-color 0.2s, box-shadow 0.2s !important;
    `;
    textarea.onfocus = () => {
        textarea.style.borderColor = "#BB86FC";
        textarea.style.boxShadow = "0 0 8px rgba(187, 134, 252, 0.3)";
    };
    textarea.onblur = () => {
        textarea.style.borderColor = "rgba(255, 255, 255, 0.15)";
        textarea.style.boxShadow = "none";
    };

    const actionContainer = document.createElement("div");
    actionContainer.style.cssText = `
        display: flex !important;
        justify-content: flex-end !important;
        gap: 10px !important;
    `;

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "ab-btn";
    cancelBtn.innerText = "Cancel";
    cancelBtn.style.cssText += `
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: #CCCCCC !important;
    `;
    cancelBtn.onclick = () => {
        overlay.remove();
    };

    const sendBtn = document.createElement("button");
    sendBtn.className = "ab-btn";
    sendBtn.innerHTML = "<span>🚀</span> <span>Release & Continue</span>";
    sendBtn.style.cssText += `
        background: linear-gradient(135deg, #2e7d32, #34a853) !important;
        color: #FFFFFF !important;
        box-shadow: 0 2px 10px rgba(52, 168, 83, 0.4) !important;
    `;
    sendBtn.onclick = () => {
        const text = textarea.value.trim();
        chrome.runtime.sendMessage({
            type: "page_resume",
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
    root.appendChild(overlay);

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

