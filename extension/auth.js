// auth.js - AgentSocket Dynamic Session Authorization Controller
document.addEventListener("DOMContentLoaded", () => {
    const grantBtn = document.getElementById("grantBtn");
    const denyBtn = document.getElementById("denyBtn");
    const sessionNameElem = document.getElementById("sessionName");
    const sessionDescElem = document.getElementById("sessionTitleDesc");

    // Extract session name from query params if passed: auth.html?session=LinkedIn+CRM
    const urlParams = new URLSearchParams(window.location.search);
    const sessionTitle = urlParams.get("session") || "AgentSocket Task";

    if (sessionNameElem) {
        sessionNameElem.textContent = sessionTitle;
    }
    if (sessionDescElem) {
        sessionDescElem.textContent = `"${sessionTitle}"`;
    }

    const msgType = (typeof MessageTypes !== "undefined" && MessageTypes.AUTH_STATUS_CHANGED) ? MessageTypes.AUTH_STATUS_CHANGED : "auth_status_changed";

    grantBtn.addEventListener("click", () => {
        // Notify background script that authorization was granted for this session
        chrome.runtime.sendMessage({
            type: msgType,
            authorized: true,
            session_title: sessionTitle
        }, () => {
            window.close();
        });
    });

    denyBtn.addEventListener("click", () => {
        // Notify background script that authorization was denied
        chrome.runtime.sendMessage({
            type: msgType,
            authorized: false,
            session_title: sessionTitle
        }, () => {
            window.close();
        });
    });
});
