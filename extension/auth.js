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

    const msgType = (typeof MessageTypes !== "undefined" && MessageTypes.AUTH_STATUS_CHANGED) ? MessageTypes.AUTH_STATUS_CHANGED : "auth_status_changed";

    grantBtn.addEventListener("click", () => {
        const permissions = {
            enable_subskills: enableSubskills ? enableSubskills.checked : true,
            enable_vision: enableVision ? enableVision.checked : false
        };

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
