// content.js
console.log('Agent Bro Hands content script loaded.');

let hermesGlowOverlay = null;
let hermesControlPill = null;
let hermesNotesModal = null;

let currentSessionTitle = "Agent Bro Task";
let currentGroupColor = "purple";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "show_glow") {
        currentSessionTitle = message.session_title || "Agent Bro Task";
        currentGroupColor = message.group_color || "purple";
        renderActiveGlow(currentSessionTitle, currentGroupColor);
        sendResponse({ status: "success" });
    } else if (message.type === "hide_glow") {
        removeGlowOverlay();
        sendResponse({ status: "success" });
    }
    return false; // synchronous response
});

// ============================================================================
// UI RENDERING ENGINE (STATES)
// ============================================================================

function removeAllUI() {
    removeGlowOverlay();
    removeControlPill();
    removeNotesModal();
}

function removeGlowOverlay() {
    if (hermesGlowOverlay && hermesGlowOverlay.parentNode) {
        hermesGlowOverlay.parentNode.removeChild(hermesGlowOverlay);
    }
    hermesGlowOverlay = null;
}

function removeControlPill() {
    if (hermesControlPill && hermesControlPill.parentNode) {
        hermesControlPill.parentNode.removeChild(hermesControlPill);
    }
    hermesControlPill = null;
}

function removeNotesModal() {
    if (hermesNotesModal && hermesNotesModal.parentNode) {
        hermesNotesModal.parentNode.removeChild(hermesNotesModal);
    }
    hermesNotesModal = null;
}

// 1. ACTIVE STATE: Pulsing border glow & bottom 'Take Over' pill
function renderActiveGlow(sessionTitle, groupColor) {
    removeAllUI();

    let glowColor = "rgba(187, 134, 252, 0.6)"; // Default purple
    let borderHex = "#BB86FC";
    if (groupColor === "orange") {
        glowColor = "rgba(255, 143, 0, 0.6)";
        borderHex = "#FF8F00";
    } else if (groupColor === "red") {
        glowColor = "rgba(234, 67, 53, 0.6)";
        borderHex = "#EA4335";
    } else if (groupColor === "blue") {
        glowColor = "rgba(66, 133, 244, 0.6)";
        borderHex = "#4285F4";
    } else if (groupColor === "green") {
        glowColor = "rgba(52, 168, 83, 0.6)";
        borderHex = "#34A853";
    }

    // A. Viewport Glow Frame
    hermesGlowOverlay = document.createElement("div");
    hermesGlowOverlay.id = "hermes-glow-overlay";
    hermesGlowOverlay.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        pointer-events: none !important;
        z-index: 2147483646 !important;
        box-shadow: inset 0 0 18px 6px ${glowColor} !important;
        border: 3px solid ${borderHex} !important;
        transition: all 0.3s ease !important;
        box-sizing: border-box !important;
        animation: hermesPulse 2s infinite alternate !important;
    `;

    if (!document.getElementById("hermes-style-rules")) {
        const style = document.createElement("style");
        style.id = "hermes-style-rules";
        style.textContent = `
            @keyframes hermesPulse {
                0% { box-shadow: inset 0 0 16px 4px ${glowColor}; }
                100% { box-shadow: inset 0 0 24px 8px ${glowColor}; }
            }
        `;
        document.head.appendChild(style);
    }

    // B. Control Pill
    hermesControlPill = document.createElement("div");
    hermesControlPill.id = "hermes-control-pill";
    hermesControlPill.style.cssText = getPillStyle();

    const indicator = document.createElement("span");
    indicator.style.cssText = `
        display: inline-block !important;
        width: 8px !important;
        height: 8px !important;
        background: ${borderHex} !important;
        border-radius: 50% !important;
        box-shadow: 0 0 8px ${borderHex} !important;
    `;

    const labelText = document.createElement("span");
    labelText.innerText = `${sessionTitle} is active...`;

    const takeoverBtn = document.createElement("button");
    takeoverBtn.innerText = "Take Over";
    takeoverBtn.style.cssText = getButtonStyle("#ea4335", "#c5221f");
    takeoverBtn.onmouseover = () => {
        takeoverBtn.style.transform = "scale(1.05)";
        takeoverBtn.style.boxShadow = "0 4px 12px rgba(234, 67, 53, 0.4)";
    };
    takeoverBtn.onmouseout = () => {
        takeoverBtn.style.transform = "scale(1)";
        takeoverBtn.style.boxShadow = "0 2px 8px rgba(234, 67, 53, 0.3)";
    };
    takeoverBtn.onclick = () => {
        // Switch locally to Takeover State
        renderTakeoverUI(sessionTitle);
        // Send state change back to background script
        chrome.runtime.sendMessage({ 
            type: "page_takeover", 
            notes: `User took over control on tab: ${window.location.hostname}` 
        });
    };

    hermesControlPill.appendChild(indicator);
    hermesControlPill.appendChild(labelText);
    hermesControlPill.appendChild(takeoverBtn);

    document.documentElement.appendChild(hermesGlowOverlay);
    document.documentElement.appendChild(hermesControlPill);
}

// 2. TAKEOVER STATE: No glow, bottom 'Stop' & 'Resume' pill
function renderTakeoverUI(sessionTitle) {
    removeAllUI();

    hermesControlPill = document.createElement("div");
    hermesControlPill.id = "hermes-control-pill";
    hermesControlPill.style.cssText = getPillStyle();

    const indicator = document.createElement("span");
    indicator.style.cssText = `
        display: inline-block !important;
        width: 8px !important;
        height: 8px !important;
        background: #EA4335 !important;
        border-radius: 50% !important;
        box-shadow: 0 0 8px #EA4335 !important;
    `;

    const labelText = document.createElement("span");
    labelText.innerText = "User taking over control";

    const btnContainer = document.createElement("div");
    btnContainer.style.cssText = "display: flex !important; gap: 8px !important;";

    const stopBtn = document.createElement("button");
    stopBtn.innerText = "Stop";
    stopBtn.style.cssText = getButtonStyle("#333", "#222") + "border: 1px solid rgba(255,255,255,0.1) !important;";
    stopBtn.onclick = () => {
        chrome.runtime.sendMessage({ type: "page_stop" });
        removeAllUI();
    };

    const resumeBtn = document.createElement("button");
    resumeBtn.innerText = "Resume";
    resumeBtn.style.cssText = getButtonStyle("#34a853", "#248a3d");
    resumeBtn.onclick = () => {
        renderNotesModal(sessionTitle);
    };

    btnContainer.appendChild(stopBtn);
    btnContainer.appendChild(resumeBtn);

    hermesControlPill.appendChild(indicator);
    hermesControlPill.appendChild(labelText);
    hermesControlPill.appendChild(btnContainer);

    document.documentElement.appendChild(hermesControlPill);
}

// 3. NOTES MODAL STATE: Input card to submit logs to the agent
function renderNotesModal(sessionTitle) {
    removeNotesModal();

    hermesNotesModal = document.createElement("div");
    hermesNotesModal.id = "hermes-notes-modal";
    hermesNotesModal.style.cssText = `
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        z-index: 2147483647 !important;
        width: 380px !important;
        background: rgba(15, 12, 27, 0.95) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 12px !important;
        padding: 20px !important;
        color: #E2DDF0 !important;
        font-family: system-ui, -apple-system, sans-serif !important;
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7), 0 0 20px rgba(187, 134, 252, 0.15) !important;
        backdrop-filter: blur(16px) !important;
        box-sizing: border-box !important;
    `;

    const title = document.createElement("h3");
    title.innerText = "Let Agent know what you've changed";
    title.style.cssText = `
        margin: 0 0 6px 0 !important;
        font-size: 15px !important;
        font-weight: 800 !important;
        color: #D3B9FF !important;
    `;

    const desc = document.createElement("p");
    desc.innerText = "Summarize your browser actions to help Agent work smoothly.";
    desc.style.cssText = `
        margin: 0 0 14px 0 !important;
        font-size: 11px !important;
        color: #A69EBA !important;
        line-height: 1.4 !important;
    `;

    const textarea = document.createElement("textarea");
    textarea.placeholder = "This message will be sent to the Agent...";
    textarea.style.cssText = `
        width: 100% !important;
        height: 72px !important;
        box-sizing: border-box !important;
        background: rgba(25, 18, 41, 0.6) !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 6px !important;
        padding: 8px !important;
        font-size: 12px !important;
        font-family: inherit !important;
        resize: none !important;
        margin-bottom: 16px !important;
        outline: none !important;
    `;
    textarea.onfocus = () => {
        textarea.style.borderColor = "#BB86FC";
        textarea.style.boxShadow = "0 0 6px rgba(187, 134, 252, 0.3)";
    };

    const actionContainer = document.createElement("div");
    actionContainer.style.cssText = `
        display: flex !important;
        justify-content: flex-end !important;
        gap: 8px !important;
    `;

    const cancelBtn = document.createElement("button");
    cancelBtn.innerText = "Cancel";
    cancelBtn.style.cssText = getButtonStyle("#333", "#222") + "border: 1px solid rgba(255,255,255,0.08) !important;";
    cancelBtn.onclick = () => {
        removeNotesModal();
    };

    const sendBtn = document.createElement("button");
    sendBtn.innerText = "Send and continue";
    sendBtn.style.cssText = getButtonStyle("#34a853", "#248a3d");
    sendBtn.onclick = () => {
        const text = textarea.value.trim();
        // Send resume message
        chrome.runtime.sendMessage({ 
            type: "page_resume", 
            notes: text || "Resumed by human operator." 
        });
        removeAllUI();
    };

    actionContainer.appendChild(cancelBtn);
    actionContainer.appendChild(sendBtn);

    hermesNotesModal.appendChild(title);
    hermesNotesModal.appendChild(desc);
    hermesNotesModal.appendChild(textarea);
    hermesNotesModal.appendChild(actionContainer);

    document.documentElement.appendChild(hermesNotesModal);
    textarea.focus();
}

// ============================================================================
// STYLING SPECIFICATIONS (CSS-IN-JS HELPERS)
// ============================================================================

function getPillStyle() {
    return `
        position: fixed !important;
        bottom: 24px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 2147483647 !important;
        background: rgba(15, 12, 27, 0.95) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #E2DDF0 !important;
        padding: 10px 18px !important;
        border-radius: 50px !important;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        font-size: 13px !important;
        font-weight: 700 !important;
        display: flex !important;
        align-items: center !important;
        gap: 14px !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 15px rgba(187, 134, 252, 0.2) !important;
        backdrop-filter: blur(12px) !important;
        user-select: none !important;
        box-sizing: border-box !important;
    `;
}

function getButtonStyle(colorStart, colorEnd) {
    return `
        background: linear-gradient(90deg, ${colorStart} 0%, ${colorEnd} 100%) !important;
        color: white !important;
        border: none !important;
        padding: 6px 16px !important;
        border-radius: 50px !important;
        font-size: 11px !important;
        font-weight: bold !important;
        cursor: pointer !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2) !important;
        transition: all 0.2s !important;
    `;
}

// ============================================================================
// MAIN-WORLD INJECTION (HUMAN INTERACTION EVASION HELPER LIBRARY)
// ============================================================================
(function injectMainWorldHelpers() {
    try {
        const script = document.createElement("script");
        script.id = "agent-bro-human-helpers";
        script.textContent = `
            window.agentBro = window.agentBro || {};
            
            // Jittered scrolling to target Y coordinate
            window.agentBro.scrollJitter = async function(targetY, maxScrolls = 15) {
                targetY = targetY || document.documentElement.scrollHeight || document.body.scrollHeight;
                console.log("[Agent Bro] Initializing human-like scrolling to:", targetY);
                let currentScrolls = 0;
                
                while (window.scrollY < targetY && currentScrolls < maxScrolls) {
                    const increment = Math.floor(Math.random() * (250 - 100 + 1)) + 100;
                    window.scrollBy({ top: increment, behavior: "smooth" });
                    currentScrolls++;
                    
                    const delay = Math.floor(Math.random() * (2000 - 1000 + 1)) + 1000;
                    await new Promise(resolve => setTimeout(resolve, delay));
                    
                    if ((window.innerHeight + window.scrollY) >= (document.documentElement.scrollHeight || document.body.scrollHeight)) {
                        console.log("[Agent Bro] Hit page bottom. Stopping scroll.");
                        break;
                    }
                }
                return { status: "scrolled", finalY: window.scrollY };
            };

            // Simulating a realistic hover over a target element
            window.agentBro.hoverElement = async function(selector) {
                const el = document.querySelector(selector);
                if (!el) {
                    return { status: "error", message: "Element not found for selector: " + selector };
                }
                
                console.log("[Agent Bro] Hovering element:", selector);
                const rect = el.getBoundingClientRect();
                
                const clientX = rect.left + (rect.width / 2) + (Math.random() * (rect.width * 0.2) - (rect.width * 0.1));
                const clientY = rect.top + (rect.height / 2) + (Math.random() * (rect.height * 0.2) - (rect.height * 0.1));

                const dispatchMouse = (type) => {
                    const ev = new MouseEvent(type, {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: clientX,
                        clientY: clientY
                    });
                    el.dispatchEvent(ev);
                };

                dispatchMouse("mouseenter");
                dispatchMouse("mouseover");
                dispatchMouse("mousemove");

                const delay = Math.floor(Math.random() * (700 - 300 + 1)) + 300;
                await new Promise(resolve => setTimeout(resolve, delay));

                return { status: "hovered", selector: selector };
            };
        `;
        document.documentElement.appendChild(script);
        script.remove();
    } catch(err) {
        console.error("[Agent Bro] Failed to inject main-world helpers:", err);
    }
})();

