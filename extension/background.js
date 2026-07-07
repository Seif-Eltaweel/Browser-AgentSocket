// background.js
const DEFAULT_SERVERS = [
    { id: "hermes", name: "Hermes Local", url: "ws://127.0.0.1:8000/ws/extension", enabled: true, color: "purple" },
    { id: "antigravity", name: "Antigravity Local", url: "ws://127.0.0.1:9000/ws/extension", enabled: false, color: "blue" },
    { id: "claude", name: "Claude Code", url: "ws://127.0.0.1:8500/ws/extension", enabled: false, color: "green" },
    { id: "vps", name: "Hostinger VPS", url: "wss://yourvps.com/ws/extension", enabled: false, color: "red" }
];

let sockets = {}; // key: serverId, value: WebSocket
let humanInControl = false;
let agentAuthorized = false;
let pendingAuthResolve = null;

// Initialize connections on load
chrome.storage.local.get(["human_in_control", "agent_authorized", "agent_servers"], (data) => {
    humanInControl = !!data.human_in_control;
    agentAuthorized = !!data.agent_authorized;
    
    if (!data.agent_servers) {
        chrome.storage.local.set({ agent_servers: DEFAULT_SERVERS }, () => {
            syncConnections();
        });
    } else {
        syncConnections();
    }
});

// Manage connections to enabled agent servers
function syncConnections() {
    chrome.storage.local.get(["agent_servers"], (data) => {
        const servers = data.agent_servers || DEFAULT_SERVERS;
        
        servers.forEach(server => {
            if (server.enabled) {
                const ws = sockets[server.id];
                if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
                    connectToServer(server);
                }
            } else {
                const ws = sockets[server.id];
                if (ws) {
                    ws.close();
                    delete sockets[server.id];
                    console.log(`[Hub] Disconnected from disabled agent: ${server.name}`);
                }
            }
        });
    });
}

function connectToServer(server) {
    console.log(`[Hub] Attempting connection to ${server.name} at ${server.url}...`);
    
    const ws = new WebSocket(server.url);
    sockets[server.id] = ws;

    ws.onopen = () => {
        console.log(`[Hub] Successfully connected to ${server.name}`);
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "state_change",
                human_in_control: humanInControl,
                notes: ""
            }));
        }
    };

    ws.onmessage = async (event) => {
        try {
            const data = JSON.parse(event.data);
            
            // Handle command execution requests
            if (data.type === "execute_action") {
                chrome.storage.local.get(["agent_servers"], async (store) => {
                    const servers = store.agent_servers || DEFAULT_SERVERS;
                    const currentServer = servers.find(s => s.id === server.id) || server;
                    
                    // Override with user's selected color from popup setting
                    const finalColor = currentServer.color || data.group_color || "purple";
                    const finalSessionTitle = data.session_title || `${currentServer.name} Task`;

                    const result = await handleHermesAction({
                        ...data,
                        group_color: finalColor,
                        session_title: finalSessionTitle
                    });
                    
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            type: "command_response",
                            command_id: data.id,
                            payload: result
                        }));
                    }
                });
            } 
            // Handle state synchronisation updates (aborts, releases)
            else if (data.type === "state_sync") {
                console.log(`[Hub] State sync from ${server.name}:`, data);
                updateLocalState(data.human_in_control, data.notes || "");
                
                if (data.human_in_control) {
                    chrome.notifications.create({
                        type: 'basic',
                        iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                        title: `${server.name} Paused`,
                        message: `Security Abort: ${data.notes || "Sensitive scope detected."}`,
                        priority: 1
                    });
                } else {
                    chrome.notifications.create({
                        type: 'basic',
                        iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                        title: `${server.name} Resumed`,
                        message: 'Control returned to Agent.',
                        priority: 1
                    });
                    hideAllGlows();
                }
            }
        } catch (err) {
            console.error(`[Hub] Error processing message from ${server.name}:`, err);
        }
    };

    ws.onclose = () => {
        console.warn(`[Hub] Connection closed for ${server.name}`);
        delete sockets[server.id];
        
        // Reconnect attempt if still enabled in settings
        chrome.storage.local.get(["agent_servers"], (data) => {
            const currentServers = data.agent_servers || [];
            const activeServer = currentServers.find(s => s.id === server.id);
            if (activeServer && activeServer.enabled) {
                console.log(`[Hub] Reconnecting to ${server.name} in 3s...`);
                setTimeout(() => connectToServer(activeServer), 3000);
            }
        });
    };

    ws.onerror = (err) => {
        console.error(`[Hub] WebSocket error on ${server.name}:`, err);
    };
}

function broadcastStateChange(humanInControl, notes) {
    for (const id in sockets) {
        const ws = sockets[id];
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "state_change",
                human_in_control: humanInControl,
                notes: notes || ""
            }));
        }
    }
}

function updateLocalState(active, notes) {
    humanInControl = active;
    chrome.storage.local.set({ human_in_control: active, intervention_notes: notes }, () => {
        chrome.runtime.sendMessage({ type: "state_changed", humanInControl: active }).catch(() => {});
    });
}

// REST call helper to hit the active server for release/stop
function hitServerEndpoint(endpoint, payload = {}) {
    chrome.storage.local.get(["agent_servers"], (data) => {
        const servers = data.agent_servers || [];
        servers.forEach(server => {
            if (server.enabled) {
                let httpUrl = server.url.replace(/^ws/, "http");
                httpUrl = httpUrl.replace(/\/ws\/extension\/?$/, "");
                
                fetch(`${httpUrl}${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .catch(err => console.error(`[Hub] Failed to hit endpoint ${endpoint} on server ${server.name}:`, err));
            }
        });
    });
}

// Listener for messages from popup.js, auth.js, and content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Received message in background script:', message);
    
    if (message.type === "get_state") {
        sendResponse({ humanInControl: humanInControl });
        return false;
    } 
    
    else if (message.type === "toggle_mode") {
        const targetMode = !humanInControl;
        const notes = message.human_intervention_notes || "";
        
        if (targetMode) {
            updateLocalState(true, notes);
            broadcastStateChange(true, notes);
            hideAllGlows();
            sendResponse({ humanInControl: true });
        } else {
            hitServerEndpoint("/human_release", { notes: notes });
            updateLocalState(false, "");
            broadcastStateChange(false, "");
            sendResponse({ humanInControl: false });
        }
        return false;
    }

    else if (message.type === "auth_status_changed") {
        agentAuthorized = !!message.authorized;
        console.log("[Auth] Authorization state changed:", agentAuthorized);
        if (agentAuthorized && pendingAuthResolve) {
            pendingAuthResolve(true);
            pendingAuthResolve = null;
        }
        return false;
    }

    else if (message.type === "page_takeover") {
        console.warn("[Takeover] User requested manual takeover from page overlay.");
        updateLocalState(true, message.notes || "User clicked Take Over on page");
        broadcastStateChange(true, message.notes || "User clicked Take Over on page");
        hideAllGlows();
        return false;
    }

    else if (message.type === "page_stop") {
        console.warn("[Takeover] User clicked Stop. Terminating active tasks.");
        hitServerEndpoint("/stop");
        updateLocalState(false, "");
        broadcastStateChange(false, "");
        return false;
    }

    else if (message.type === "page_resume") {
        console.log("[Takeover] User clicked Resume and continue with notes:", message.notes);
        hitServerEndpoint("/human_release", { notes: message.notes });
        updateLocalState(false, "");
        broadcastStateChange(false, "");
        return false;
    }

    else if (message.type === "reload_connections") {
        console.log("[Hub] Reloading connections based on settings changes.");
        syncConnections();
        return false;
    }

    else if (message.type === "get_connection_statuses") {
        const statuses = {};
        for (const id in sockets) {
            const ws = sockets[id];
            if (ws) {
                statuses[id] = ws.readyState === WebSocket.OPEN ? "online" : "offline";
            }
        }
        sendResponse({ statuses: statuses });
        return false;
    }

    else if (message.type === "scan_local_agents") {
        scanLocalPorts().then(count => {
            sendResponse({ discoveredCount: count });
        });
        return true;
    }
});

async function ensureAuthorized() {
    if (agentAuthorized) return true;

    // Trigger one-time authorization modal card tab
    chrome.tabs.create({ url: chrome.runtime.getURL("auth.html") });

    return new Promise((resolve) => {
        pendingAuthResolve = resolve;
    });
}

async function handleHermesAction(command) {
    // 1. Ensure user has granted one-time authorization
    await ensureAuthorized();

    const sessionTitle = command.session_title || "Agent Bro Task";
    const groupColor = command.group_color || "purple";

    switch (command.action_type) {
        case "navigate":
            return await handleNavigation(command.target_data, sessionTitle, groupColor);
        case "execute_js":
            return await handleExecuteJS(command.target_data, sessionTitle, groupColor);
        case "task_complete":
            return await handleTaskComplete(sessionTitle);
        default:
            return { status: "error", message: `Unknown action capability: ${command.action_type}` };
    }
}

async function handleTaskComplete(sessionTitle) {
    try {
        const groups = await chrome.tabGroups.query({ title: sessionTitle });
        if (groups && groups.length > 0) {
            const groupId = groups[0].id;
            await new Promise((resolve) => {
                chrome.tabGroups.update(groupId, {
                    title: `✅ ${sessionTitle}`,
                    color: "grey"
                }, resolve);
            });
            // Clear any glows
            hideAllGlows();
            return { status: "success", message: "Task marked complete and tab group renamed." };
        }
        return { status: "error", message: `No active tab group found matching title: ${sessionTitle}` };
    } catch (e) {
        return { status: "error", message: e.message };
    }
}

// Locate or create the dynamic tab group and execute navigation within it
async function handleNavigation(url, sessionTitle, groupColor) {
    return new Promise(async (resolve) => {
        try {
            const groups = await chrome.tabGroups.query({ title: sessionTitle });
            let targetGroupId = null;
            if (groups && groups.length > 0) {
                targetGroupId = groups[0].id;
            }

            chrome.tabs.create({ url: url }, (newTab) => {
                if (chrome.runtime.lastError) {
                    resolve({ status: "error", message: chrome.runtime.lastError.message });
                    return;
                }

                if (targetGroupId !== null) {
                    chrome.tabs.group({ groupId: targetGroupId, tabIds: newTab.id }, () => {
                        if (chrome.runtime.lastError) {
                            createFreshHermesGroup(newTab.id, sessionTitle, groupColor, resolve);
                        } else {
                            resolve({ status: "success", tabId: newTab.id, groupId: targetGroupId });
                        }
                    });
                } else {
                    createFreshHermesGroup(newTab.id, sessionTitle, groupColor, resolve);
                }
            });
        } catch (e) {
            resolve({ status: "error", message: e.message });
        }
    });
}

function createFreshHermesGroup(tabId, sessionTitle, groupColor, resolve) {
    chrome.tabs.group({ tabIds: tabId }, (groupId) => {
        if (chrome.runtime.lastError) {
            resolve({ status: "error", message: chrome.runtime.lastError.message });
            return;
        }

        chrome.tabGroups.update(groupId, {
            title: sessionTitle,
            color: groupColor
        }, () => {
            if (chrome.runtime.lastError) {
                resolve({ status: "error", message: chrome.runtime.lastError.message });
                return;
            }
            resolve({ status: "success", tabId: tabId, groupId: groupId });
        });
    });
}

// Find the target tab ID which MUST be a member of the dynamic task group
async function getTargetTabId(sessionTitle) {
    try {
        const groups = await chrome.tabGroups.query({ title: sessionTitle });
        if (!groups || groups.length === 0) {
            return null;
        }
        
        const groupId = groups[0].id;
        const tabs = await chrome.tabs.query({ groupId: groupId });
        if (tabs && tabs.length > 0) {
            const activeTab = tabs.find(t => t.active);
            if (activeTab) return activeTab.id;
            return tabs[0].id;
        }
    } catch (e) {
        console.error("Error finding target tab in group:", e);
    }
    return null;
}

async function handleExecuteJS(code, sessionTitle, groupColor) {
    try {
        const tabId = await getTargetTabId(sessionTitle);
        if (!tabId) {
            return { 
                status: "error", 
                message: `Security Block: No tab found in the secure '${sessionTitle}' group. Navigate first to initialize a tab in the group.` 
            };
        }

        try {
            await chrome.tabs.sendMessage(tabId, { 
                type: "show_glow", 
                session_title: sessionTitle, 
                group_color: groupColor 
            });
        } catch (e) {}

        console.log(`Executing dynamic script via CDP in tab ${tabId} (inside secure group '${sessionTitle}')`);
        const target = { tabId: tabId };

        // Attach debugger to the tab
        await new Promise((resolve, reject) => {
            chrome.debugger.attach(target, "1.3", () => {
                if (chrome.runtime.lastError) {
                    const errMsg = chrome.runtime.lastError.message;
                    if (errMsg.includes("Already attached")) {
                        resolve();
                    } else {
                        reject(new Error(errMsg));
                    }
                } else {
                    resolve();
                }
            });
        });

        // Run Runtime.evaluate to execute dynamic JavaScript bypassing CSP
        const result = await new Promise((resolve, reject) => {
            chrome.debugger.sendCommand(target, "Runtime.evaluate", {
                expression: code,
                returnByValue: true,
                awaitPromise: true
            }, (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response && response.exceptionDetails) {
                    const exMsg = response.exceptionDetails.exception.description || "JavaScript execution error.";
                    reject(new Error(exMsg));
                } else {
                    resolve(response && response.result ? response.result.value : null);
                }
            });
        });

        // Detach debugger
        await new Promise((resolve) => {
            chrome.debugger.detach(target, () => {
                resolve();
            });
        });

        // Turn off page glow
        try {
            await chrome.tabs.sendMessage(tabId, { type: "hide_glow" });
        } catch (e) {}

        return { status: "success", output: result };
    } catch (err) {
        console.error("Script execution failed:", err);
        try {
            chrome.debugger.detach({ tabId: await getTargetTabId(sessionTitle) }, () => {});
        } catch(e) {}
        try {
            const tabId = await getTargetTabId(sessionTitle);
            if (tabId) await chrome.tabs.sendMessage(tabId, { type: "hide_glow" });
        } catch (e) {}
        return { status: "error", message: err.message };
    }
}

// Helper to remove page glows on all tabs across the system
async function hideAllGlows() {
    try {
        const tabs = await chrome.tabs.query({});
        for (const tab of tabs) {
            try {
                chrome.tabs.sendMessage(tab.id, { type: "hide_glow" });
            } catch(e) {}
        }
    } catch(err) {
        console.error("Error clearing glows:", err);
    }
}

async function scanLocalPorts() {
    const ports = [8000, 8080, 8500, 9000, 9500];
    let newAgentsDiscovered = 0;
    
    const store = await new Promise(resolve => chrome.storage.local.get(["agent_servers"], resolve));
    let servers = store.agent_servers || DEFAULT_SERVERS;

    for (const port of ports) {
        const url = `ws://127.0.0.1:${port}/ws/extension`;
        const exists = servers.some(s => s.url === url);
        if (exists) continue;

        try {
            const connected = await new Promise((resolve) => {
                const tempSocket = new WebSocket(url);
                const timer = setTimeout(() => {
                    tempSocket.close();
                    resolve(false);
                }, 800);

                tempSocket.onopen = () => {
                    clearTimeout(timer);
                    tempSocket.close();
                    resolve(true);
                };
                tempSocket.onerror = () => {
                    clearTimeout(timer);
                    resolve(false);
                };
            });

            if (connected) {
                let name = `Agent Local (Port ${port})`;
                let color = "purple";
                let id = `discovered_${port}`;
                
                if (port === 8000) { name = "Hermes Local"; color = "purple"; id = "hermes"; }
                else if (port === 8500) { name = "Claude Code"; color = "green"; id = "claude"; }
                else if (port === 9000) { name = "Antigravity Local"; color = "blue"; id = "antigravity"; }
                else if (port === 9500) { name = "Local Agent 9500"; color = "orange"; }

                servers.push({
                    id: id,
                    name: name,
                    url: url,
                    enabled: true,
                    color: color
                });
                newAgentsDiscovered++;
            }
        } catch(e) {}
    }

    if (newAgentsDiscovered > 0) {
        await new Promise(resolve => chrome.storage.local.set({ agent_servers: servers }, resolve));
        syncConnections();
    }

    return newAgentsDiscovered;
}

// ============================================================================
// HEARTBEAT KEEP-ALIVE PROTOCOL
// Prevents Chrome from discarding the Service Worker during automation idle phases
// ============================================================================
setInterval(() => {
    let activeSocketsFound = false;
    for (const id in sockets) {
        const ws = sockets[id];
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
            activeSocketsFound = true;
        }
    }
    if (activeSocketsFound) {
        console.log("Heartbeat ping sent to active agent servers.");
    }
}, 10000);
