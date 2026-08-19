// background.js - Agent Bro Hands Background Hub & Execution Manager
try {
    importScripts("protocol.js");
} catch (e) {
    console.warn("protocol.js loaded via fallback scope or already available:", e);
}

const DEFAULT_SERVERS = [
    { id: "hermes", name: "Hermes Local", url: "ws://127.0.0.1:8000/ws/extension", enabled: true, color: "purple" },
    { id: "antigravity", name: "Antigravity Local", url: "ws://127.0.0.1:9000/ws/extension", enabled: false, color: "blue" },
    { id: "claude", name: "Claude Code", url: "ws://127.0.0.1:8500/ws/extension", enabled: false, color: "green" },
    { id: "vps", name: "Hostinger VPS", url: "wss://yourvps.com/ws/extension", enabled: false, color: "red" }
];

const MT = (typeof MessageTypes !== "undefined") ? MessageTypes : {
    EXECUTE_ACTION: "execute_action",
    COMMAND_RESPONSE: "command_response",
    STATE_CHANGE: "state_change",
    STATE_SYNC: "state_sync",
    STATE_CHANGED: "state_changed",
    PAGE_TAKEOVER: "page_takeover",
    PAGE_RESUME: "page_resume",
    PAGE_STOP: "page_stop",
    SHOW_GLOW: "show_glow",
    SHOW_TAKEOVER: "show_takeover",
    HIDE_GLOW: "hide_glow",
    GET_STATE: "get_state",
    TOGGLE_MODE: "toggle_mode",
    AUTH_STATUS_CHANGED: "auth_status_changed",
    RELOAD_CONNECTIONS: "reload_connections",
    GET_CONNECTION_STATUSES: "get_connection_statuses",
    SCAN_LOCAL_AGENTS: "scan_local_agents",
    PING: "ping"
};

const AT = (typeof ActionTypes !== "undefined") ? ActionTypes : {
    NAVIGATE: "navigate",
    EXECUTE_JS: "execute_js",
    TASK_COMPLETE: "task_complete"
};

let activeSockets = {}; // key: serverId, value: ResilientSocket
let humanInControl = false;
let agentAuthorized = false;
let pendingAuthResolve = null;

// Active tasks session tracking: sessionTitle -> { groupColor, tabId, groupId, active }
const activeSessions = new Map();

// Active evaluations tracking: tabId -> Set of reject callbacks
const activeEvaluations = new Map();

// ============================================================================
// RESILIENT WEBSOCKET CONNECTION MANAGER
// ============================================================================
class ResilientSocket {
    constructor(server, onAction, onStateSync) {
        this.server = server;
        this.onAction = onAction;
        this.onStateSync = onStateSync;
        this.ws = null;
        this.retryCount = 0;
        this.maxDelay = 30000;
        this.isDisposed = false;
        this.reconnectTimer = null;
        this.connect();
    }

    connect() {
        if (this.isDisposed) return;
        console.log(`[Hub] Connecting to ${this.server.name} at ${this.server.url}...`);
        
        try {
            this.ws = new WebSocket(this.server.url);
        } catch (err) {
            console.warn(`[Hub] WebSocket init error for ${this.server.name}:`, err);
            this.scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.log(`[Hub] Successfully connected to ${this.server.name}`);
            this.retryCount = 0;
            if (this.isOpen()) {
                this.send({
                    type: MT.STATE_CHANGE,
                    human_in_control: humanInControl,
                    notes: ""
                });
            }
        };

        this.ws.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === MT.EXECUTE_ACTION) {
                    await this.onAction(this.server, data, this);
                } else if (data.type === MT.STATE_SYNC) {
                    this.onStateSync(this.server, data);
                }
            } catch (err) {
                console.error(`[Hub] Error processing message from ${this.server.name}:`, err);
            }
        };

        this.ws.onclose = () => {
            if (!this.isDisposed) {
                this.scheduleReconnect();
            }
        };

        this.ws.onerror = () => {
            // Suppress noisy console logs on closed / offline optional servers
        };
    }

    scheduleReconnect() {
        if (this.isDisposed || this.reconnectTimer) return;
        const delay = Math.min(1000 * Math.pow(1.5, this.retryCount), this.maxDelay) + (Math.random() * 500);
        this.retryCount++;
        
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            chrome.storage.local.get(["agent_servers"], (data) => {
                const servers = data.agent_servers || [];
                const active = servers.find(s => s.id === this.server.id);
                if (active && active.enabled && !this.isDisposed) {
                    this.server = active;
                    this.connect();
                }
            });
        }, delay);
    }

    send(payload) {
        if (this.isOpen()) {
            this.ws.send(typeof payload === "string" ? payload : JSON.stringify(payload));
            return true;
        }
        return false;
    }

    ping() {
        return this.send({ type: MT.PING || "ping" });
    }

    isOpen() {
        return !!(this.ws && this.ws.readyState === WebSocket.OPEN);
    }

    close() {
        this.isDisposed = true;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            try {
                this.ws.close();
            } catch (e) {}
            this.ws = null;
        }
    }
}

// ============================================================================
// INITIALIZATION & LIFECYCLE KEEP-ALIVE ALARMS
// ============================================================================
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

// Setup 24-second keepalive alarm
chrome.alarms.create("bro_keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "bro_keepalive") {
        for (const id in activeSockets) {
            activeSockets[id].ping();
        }
        syncConnections();
    }
});

// Manage connections to enabled agent servers
function syncConnections() {
    chrome.storage.local.get(["agent_servers"], (data) => {
        const servers = data.agent_servers || DEFAULT_SERVERS;
        
        // Connect new or existing enabled servers
        servers.forEach(server => {
            if (server.enabled) {
                const existing = activeSockets[server.id];
                if (!existing || existing.isDisposed) {
                    activeSockets[server.id] = new ResilientSocket(
                        server,
                        handleIncomingAction,
                        handleIncomingStateSync
                    );
                } else if (existing && !existing.isOpen() && !existing.reconnectTimer) {
                    existing.connect();
                }
            } else {
                const existing = activeSockets[server.id];
                if (existing) {
                    existing.close();
                    delete activeSockets[server.id];
                    console.log(`[Hub] Disconnected from disabled agent: ${server.name}`);
                }
            }
        });

        // Clean up servers removed entirely from configuration
        for (const id in activeSockets) {
            if (!servers.some(s => s.id === id)) {
                activeSockets[id].close();
                delete activeSockets[id];
            }
        }
    });
}

// Action dispatcher
async function handleIncomingAction(server, data, socketInstance) {
    chrome.storage.local.get(["agent_servers"], async (store) => {
        const servers = store.agent_servers || DEFAULT_SERVERS;
        const currentServer = servers.find(s => s.id === server.id) || server;
        
        const finalColor = currentServer.color || data.group_color || "purple";
        const finalSessionTitle = data.session_title || `${currentServer.name} Task`;

        const result = await handleHermesAction({
            ...data,
            group_color: finalColor,
            session_title: finalSessionTitle
        });
        
        socketInstance.send({
            type: MT.COMMAND_RESPONSE,
            command_id: data.id,
            payload: result
        });
    });
}

// State sync dispatcher
function handleIncomingStateSync(server, data) {
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

function broadcastStateChange(humanInControl, notes) {
    for (const id in activeSockets) {
        activeSockets[id].send({
            type: MT.STATE_CHANGE,
            human_in_control: humanInControl,
            notes: notes || ""
        });
    }
}

function updateLocalState(active, notes) {
    humanInControl = active;
    chrome.storage.local.set({ human_in_control: active, intervention_notes: notes }, () => {
        chrome.runtime.sendMessage({ type: MT.STATE_CHANGED || "state_changed", humanInControl: active }).catch(() => {});
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

// ============================================================================
// RUNTIME MESSAGE DISPATCHER
// ============================================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === (MT.GET_STATE || "get_state")) {
        sendResponse({ humanInControl: humanInControl });
        return false;
    } 
    
    else if (message.type === (MT.TOGGLE_MODE || "toggle_mode")) {
        const targetMode = !humanInControl;
        const notes = message.human_intervention_notes || "";
        
        if (targetMode) {
            updateLocalState(true, notes);
            broadcastStateChange(true, notes);
            sendResponse({ humanInControl: true });
        } else {
            hitServerEndpoint("/human_release", { notes: notes });
            updateLocalState(false, "");
            broadcastStateChange(false, "");
            sendResponse({ humanInControl: false });
        }
        return false;
    }

    else if (message.type === (MT.AUTH_STATUS_CHANGED || "auth_status_changed")) {
        agentAuthorized = !!message.authorized;
        console.log("[Auth] Authorization state changed:", agentAuthorized);
        if (agentAuthorized && pendingAuthResolve) {
            pendingAuthResolve(true);
            pendingAuthResolve = null;
        }
        return false;
    }

    else if (message.type === (MT.PAGE_TAKEOVER || "page_takeover")) {
        console.warn("[Takeover] User requested manual takeover from page overlay.");
        updateLocalState(true, message.notes || "User clicked Take Over on page");
        broadcastStateChange(true, message.notes || "User clicked Take Over on page");
        return false;
    }

    else if (message.type === (MT.PAGE_STOP || "page_stop")) {
        console.warn("[Takeover] User clicked Stop. Terminating active tasks.");
        hitServerEndpoint("/stop");
        updateLocalState(false, "");
        broadcastStateChange(false, "");
        return false;
    }

    else if (message.type === (MT.PAGE_RESUME || "page_resume")) {
        console.log("[Takeover] User clicked Resume and continue with notes:", message.notes);
        hitServerEndpoint("/human_release", { notes: message.notes });
        updateLocalState(false, "");
        broadcastStateChange(false, "");
        return false;
    }

    else if (message.type === (MT.RELOAD_CONNECTIONS || "reload_connections")) {
        console.log("[Hub] Reloading connections based on settings changes.");
        syncConnections();
        return false;
    }

    else if (message.type === (MT.GET_CONNECTION_STATUSES || "get_connection_statuses")) {
        const statuses = {};
        for (const id in activeSockets) {
            statuses[id] = activeSockets[id].isOpen() ? "online" : "offline";
        }
        sendResponse({ statuses: statuses });
        return false;
    }

    else if (message.type === (MT.SCAN_LOCAL_AGENTS || "scan_local_agents")) {
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

// ============================================================================
// AUTOMATION & CDP EXECUTION ENGINE
// ============================================================================
async function handleHermesAction(command) {
    // 1. Ensure user has granted one-time authorization
    await ensureAuthorized();

    const sessionTitle = command.session_title || "Agent Bro Task";
    const groupColor = command.group_color || "purple";

    switch (command.action_type) {
        case (AT.NAVIGATE || "navigate"):
            return await handleNavigation(command.target_data, sessionTitle, groupColor);
        case (AT.EXECUTE_JS || "execute_js"):
            return await handleExecuteJS(command.target_data, sessionTitle, groupColor);
        case (AT.TASK_COMPLETE || "task_complete"):
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

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.groupId && tab.groupId !== chrome.tabGroups.TAB_GROUP_ID_NONE) {
        chrome.tabGroups.get(tab.groupId, (group) => {
            if (chrome.runtime.lastError || !group) return;
            const session = activeSessions.get(group.title);
            if (session && session.active && !humanInControl) {
                chrome.tabs.sendMessage(tabId, {
                    type: MT.SHOW_GLOW || "show_glow",
                    session_title: group.title,
                    group_color: session.groupColor || "purple"
                }).catch(() => {});
            }
        });
    }
});

// Locate or create dynamic tab group and navigate
async function handleNavigation(url, sessionTitle, groupColor) {
    activeSessions.set(sessionTitle, { groupColor, active: true });
    try {
        const groups = await chrome.tabGroups.query({ title: sessionTitle });

        if (groups && groups.length > 0) {
            const group = groups[0];
            const tabs = await chrome.tabs.query({ groupId: group.id });

            if (tabs && tabs.length > 0) {
                const targetTab = tabs.find(t => t.active) || tabs[0];
                try {
                    const updatedTab = await chrome.tabs.update(targetTab.id, { url: url, active: true });
                    activeSessions.set(sessionTitle, { groupColor, tabId: updatedTab.id, groupId: group.id, active: true });
                    return {
                        status: "success",
                        tabId: updatedTab.id,
                        groupId: group.id,
                        reused: true
                    };
                } catch (updateErr) {
                    console.warn(`[Hub] Failed to update tab ${targetTab.id}, falling back to new tab:`, updateErr);
                }
            }

            // Group exists but has no open tabs or update failed
            const res = await createAndGroupTab(url, sessionTitle, groupColor, group.id);
            if (res && res.tabId) {
                activeSessions.set(sessionTitle, { groupColor, tabId: res.tabId, groupId: res.groupId, active: true });
            }
            return res;
        }

        // No group exists yet
        const res = await createAndGroupTab(url, sessionTitle, groupColor, null);
        if (res && res.tabId) {
            activeSessions.set(sessionTitle, { groupColor, tabId: res.tabId, groupId: res.groupId, active: true });
        }
        return res;
    } catch (e) {
        console.error("[Hub] Error in handleNavigation:", e);
        return { status: "error", message: e.message || String(e) };
    }
}

function createAndGroupTab(url, sessionTitle, groupColor, existingGroupId) {
    return new Promise((resolve) => {
        chrome.tabs.create({ url: url, active: true }, (newTab) => {
            if (chrome.runtime.lastError || !newTab) {
                const err = chrome.runtime.lastError ? chrome.runtime.lastError.message : "Failed to create tab";
                resolve({ status: "error", message: err });
                return;
            }

            if (existingGroupId !== null && existingGroupId !== undefined) {
                chrome.tabs.group({ groupId: existingGroupId, tabIds: newTab.id }, () => {
                    if (chrome.runtime.lastError) {
                        createFreshHermesGroup(newTab.id, sessionTitle, groupColor, resolve);
                    } else {
                        resolve({ status: "success", tabId: newTab.id, groupId: existingGroupId, reused: false });
                    }
                });
            } else {
                createFreshHermesGroup(newTab.id, sessionTitle, groupColor, resolve);
            }
        });
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
            resolve({ status: "success", tabId: tabId, groupId: groupId, reused: false });
        });
    });
}

// Find target tab ID in secure task group
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

chrome.tabs.onRemoved.addListener((tabId) => {
    if (activeEvaluations.has(tabId)) {
        const rejects = activeEvaluations.get(tabId);
        activeEvaluations.delete(tabId);
        rejects.forEach(reject => reject(new Error("Tab was closed during execution.")));
    }
});

chrome.debugger.onDetach.addListener((source, reason) => {
    console.warn(`[CDP] Debugger detached from tab ${source.tabId}:`, reason);
});

function attachDebugger(target) {
    return new Promise((resolve, reject) => {
        chrome.debugger.attach(target, "1.3", () => {
            if (chrome.runtime.lastError) {
                const errMsg = chrome.runtime.lastError.message || "";
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
}

function detachDebugger(target) {
    return new Promise((resolve) => {
        chrome.debugger.detach(target, () => {
            resolve();
        });
    });
}

function sendCDPCommand(target, method, commandParams) {
    return new Promise((resolve, reject) => {
        chrome.debugger.sendCommand(target, method, commandParams, (response) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else {
                resolve(response);
            }
        });
    });
}

async function handleExecuteJS(code, sessionTitle, groupColor) {
    const tabId = await getTargetTabId(sessionTitle);
    if (!tabId) {
        return { 
            status: "error", 
            message: `Security Block: No tab found in the secure '${sessionTitle}' group. Navigate first to initialize a tab in the group.` 
        };
    }

    if (!humanInControl) {
        try {
            await chrome.tabs.sendMessage(tabId, { 
                type: MT.SHOW_GLOW || "show_glow", 
                session_title: sessionTitle, 
                group_color: groupColor 
            });
        } catch (e) {}
    }

    console.log(`Executing dynamic script via CDP in tab ${tabId} (inside secure group '${sessionTitle}')`);
    const target = { tabId: tabId };
    let attached = false;

    let tabCloseReject;
    const tabClosePromise = new Promise((_, reject) => {
        tabCloseReject = reject;
        if (!activeEvaluations.has(tabId)) {
            activeEvaluations.set(tabId, new Set());
        }
        activeEvaluations.get(tabId).add(reject);
    });

    const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error("[CDP Timeout]: Script evaluation exceeded 25s timeout limit.")), 25000);
    });

    try {
        const evalPromise = (async () => {
            await attachDebugger(target);
            attached = true;

            const res = await sendCDPCommand(target, "Runtime.evaluate", {
                expression: code,
                returnByValue: true,
                awaitPromise: true
            });

            if (res && res.exceptionDetails) {
                const desc = res.exceptionDetails.exception?.description 
                          || res.exceptionDetails.text 
                          || "JavaScript runtime error";
                throw new Error(`[CDP JS Error]: ${desc}`);
            }

            return res && res.result ? res.result.value : null;
        })();

        const result = await Promise.race([evalPromise, tabClosePromise, timeoutPromise]);
        return { status: "success", output: result };
    } catch (err) {
        console.error("Script execution failed:", err);
        return { status: "error", message: err.message };
    } finally {
        if (activeEvaluations.has(tabId)) {
            const set = activeEvaluations.get(tabId);
            set.delete(tabCloseReject);
            if (set.size === 0) activeEvaluations.delete(tabId);
        }
        if (attached) {
            await detachDebugger(target);
        }
    }
}

// Helper to remove page glows on all tabs across the system
async function hideAllGlows() {
    try {
        const tabs = await chrome.tabs.query({});
        for (const tab of tabs) {
            try {
                chrome.tabs.sendMessage(tab.id, { type: MT.HIDE_GLOW || "hide_glow" });
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
                    try { tempSocket.close(); } catch(e){}
                    resolve(false);
                }, 800);

                tempSocket.onopen = () => {
                    clearTimeout(timer);
                    try { tempSocket.close(); } catch(e){}
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
