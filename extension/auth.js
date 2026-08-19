// auth.js
document.addEventListener("DOMContentLoaded", () => {
    const grantBtn = document.getElementById("grantBtn");
    const denyBtn = document.getElementById("denyBtn");

    const msgType = (typeof MessageTypes !== "undefined" && MessageTypes.AUTH_STATUS_CHANGED) ? MessageTypes.AUTH_STATUS_CHANGED : "auth_status_changed";

    grantBtn.addEventListener("click", () => {
        chrome.storage.local.set({ agent_authorized: true }, () => {
            // Notify background script that authorization succeeded
            chrome.runtime.sendMessage({ type: msgType, authorized: true });
            
            // Close the tab
            window.close();
        });
    });

    denyBtn.addEventListener("click", () => {
        chrome.storage.local.set({ agent_authorized: false }, () => {
            // Notify background script
            chrome.runtime.sendMessage({ type: msgType, authorized: false });
            
            // Close the tab
            window.close();
        });
    });
});
