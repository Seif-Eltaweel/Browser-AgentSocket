// auth.js - AgentSocket Dynamic Session Authorization Controller
document.addEventListener("DOMContentLoaded", () => {
    const grantBtn = document.getElementById("grantBtn");
    const denyBtn = document.getElementById("denyBtn");
    const sessionNameElem = document.getElementById("sessionName");
    const sessionDescElem = document.getElementById("sessionTitleDesc");

    // Extract session name and token from query params if passed
    const urlParams = new URLSearchParams(window.location.search);
    const sessionTitle = urlParams.get("session") || "AgentSocket Task";
    const gatewayToken = urlParams.get("token") || "";

    const tokenDisplay = document.getElementById("tokenDisplay");
    const enableSubskills = document.getElementById("enableSubskills");
    const enableVision = document.getElementById("enableVision");

    if (sessionNameElem) {
        sessionNameElem.textContent = sessionTitle;
    }
    if (sessionDescElem) {
        sessionDescElem.textContent = `"${sessionTitle}"`;
    }
    // Spec 35: Persist gateway token in chrome.storage.local for resilient background WebSockets
    if (gatewayToken) {
        try {
            if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                chrome.storage.local.set({ gateway_token: gatewayToken });
            }
        } catch (e) {
            console.warn("Failed to persist gateway_token:", e);
        }
    }

    if (tokenDisplay) {
        if (gatewayToken) {
            tokenDisplay.textContent = gatewayToken.length > 16 
                ? `${gatewayToken.slice(0, 8)}...${gatewayToken.slice(-8)}`
                : gatewayToken;
            tokenDisplay.title = gatewayToken;
        } else {
            tokenDisplay.textContent = "Unauthenticated";
            tokenDisplay.style.color = "#f87171";
        }
    }

    // Spec 32: Render planned strategic execution milestones
    const milestonesList = document.getElementById("milestonesList");
    function renderMilestones(milestones) {
        if (!milestonesList) return;
        milestonesList.innerHTML = "";
        if (milestones && Array.isArray(milestones) && milestones.length > 0) {
            milestones.forEach((m, idx) => {
                const item = document.createElement("div");
                item.className = "milestone-item";

                const badge = document.createElement("span");
                badge.className = "milestone-badge";
                const num = m.index !== undefined ? m.index : (idx + 1);
                badge.textContent = `Milestone ${num}:`;

                const text = document.createElement("span");
                text.className = "milestone-text";
                text.textContent = typeof m === "string" ? m : (m.title || `Milestone ${num}`);

                item.appendChild(badge);
                item.appendChild(text);
                milestonesList.appendChild(item);
            });
        } else {
            milestonesList.innerHTML = `
                <div class="milestone-fallback">
                    <span class="fallback-icon">◆</span>
                    <span>Autonomous Milestone Discovery: Agent will adaptively establish milestones during execution.</span>
                </div>
            `;
        }
    }

    // Try parsing from query param first
    let initialMilestones = null;
    const planParam = urlParams.get("plan");
    if (planParam) {
        try {
            initialMilestones = JSON.parse(planParam);
        } catch (e) {
            console.warn("Failed to parse plan parameter:", e);
        }
    }

    if (initialMilestones && initialMilestones.length > 0) {
        renderMilestones(initialMilestones);
    } else {
        renderMilestones(null);
        try {
            if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
                chrome.runtime.sendMessage({
                    type: "get_auth_plan",
                    session_title: sessionTitle
                }, (res) => {
                    if (res && res.plan && res.plan.milestones && res.plan.milestones.length > 0) {
                        renderMilestones(res.plan.milestones);
                    }
                });
            }
        } catch (e) {}
    }

    const msgType = (typeof MessageTypes !== "undefined" && MessageTypes.AUTH_STATUS_CHANGED) ? MessageTypes.AUTH_STATUS_CHANGED : "auth_status_changed";

    grantBtn.addEventListener("click", () => {
        const permissions = {
            enable_subskills: enableSubskills ? enableSubskills.checked : true,
            enable_vision: enableVision ? enableVision.checked : false
        };

        if (gatewayToken) {
            try {
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
                    chrome.storage.local.set({ gateway_token: gatewayToken });
                }
            } catch (e) {
                console.warn("Failed to persist gateway_token on grant:", e);
            }
        }

        // Notify background script that authorization was granted for this session
        chrome.runtime.sendMessage({
            type: msgType,
            authorized: true,
            session_title: sessionTitle,
            token: gatewayToken,
            permissions: permissions
        }, () => {
            window.close();
        });
    });

    denyBtn.addEventListener("click", () => {
        // Notify background script that authorization was denied
        chrome.runtime.sendMessage({
            type: msgType,
            authorized: false,
            session_title: sessionTitle,
            token: gatewayToken,
            permissions: {
                enable_subskills: false,
                enable_vision: false
            }
        }, () => {
            window.close();
        });
    });
});
