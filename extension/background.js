// background.js - AgentSocket Background Hub & Execution Manager
try {
    importScripts("protocol.js");
} catch (e) {
    console.warn("protocol.js loaded via fallback scope or already available:", e);
}

const DEFAULT_SERVERS = [
    { id: "agentsocket_local", name: "AgentSocket Local (e.g. Claude, Hermes, Antigravity)", url: "ws://127.0.0.1:8000/ws/extension", enabled: true, color: "purple" },
    { id: "antigravity", name: "Antigravity Local", url: "ws://127.0.0.1:9000/ws/extension", enabled: false, color: "blue" },
    { id: "claude", name: "Claude Code", url: "ws://127.0.0.1:8500/ws/extension", enabled: false, color: "green" },
    { id: "vps", name: "Custom Agent / VPS", url: "wss://yourvps.com/ws/extension", enabled: false, color: "red" }
];

const MT = MessageTypes;
const AT = ActionTypes;

let activeSockets = {}; // key: serverId, value: ResilientSocket
let humanInControl = false;
const authorizedSessions = new Set(); // In-memory session-scoped authorization
const sessionPermissions = new Map(); // sessionTitle -> { enable_subskills, enable_vision }
let pendingAuthResolve = null;

// Active tasks session tracking: sessionTitle -> { groupColor, tabId, groupId, active }
const activeSessions = new Map();

function saveActiveSessions() {
    try {
        const entries = Array.from(activeSessions.entries());
        chrome.storage.local.set({ active_sessions_data: entries });
    } catch (e) {
        console.warn("[Hub] Failed to persist activeSessions:", e);
    }
}

function loadActiveSessions() {
    chrome.storage.local.get(["active_sessions_data"], (data) => {
        if (data.active_sessions_data && Array.isArray(data.active_sessions_data)) {
            data.active_sessions_data.forEach(([k, v]) => {
                activeSessions.set(k, v);
            });
            console.log(`[Hub] Hydrated ${activeSessions.size} active sessions from storage.`);
        }
    });
}

// Spec 30: Persistent Session Authorization Storage
function saveAuthorizedSessions() {
    try {
        const authList = Array.from(authorizedSessions);
        const permList = Array.from(sessionPermissions.entries());
        chrome.storage.local.set({ 
            authorized_sessions_list: authList,
            session_permissions_list: permList 
        });
        console.log(`[Hub] Persisted ${authorizedSessions.size} authorized sessions to storage (Spec 30).`);
    } catch (e) {
        console.warn("[Hub] Failed to persist authorizedSessions:", e);
    }
}

function loadAuthorizedSessions() {
    return new Promise((resolve) => {
        chrome.storage.local.get(["authorized_sessions_list", "session_permissions_list"], (data) => {
            if (data.authorized_sessions_list && Array.isArray(data.authorized_sessions_list)) {
                data.authorized_sessions_list.forEach(item => authorizedSessions.add(item));
            }
            if (data.session_permissions_list && Array.isArray(data.session_permissions_list)) {
                data.session_permissions_list.forEach(([k, v]) => sessionPermissions.set(k, v));
            }
            console.log(`[Hub] Hydrated ${authorizedSessions.size} authorized sessions from storage (Spec 30).`);
            resolve();
        });
    });
}

// Spec 32: Strategic execution milestones and plan tracking per session
const sessionPlans = new Map(); // sessionTitle -> { milestones: [], active_index: 1, current_action: null, progress_percent: 0 }

function saveSessionPlans() {
    try {
        const entries = Array.from(sessionPlans.entries());
        chrome.storage.local.set({ session_plans_data: entries });
    } catch (e) {
        console.warn("[Hub] Failed to persist sessionPlans:", e);
    }
}

function loadSessionPlans() {
    return new Promise((resolve) => {
        chrome.storage.local.get(["session_plans_data"], (data) => {
            if (data.session_plans_data && Array.isArray(data.session_plans_data)) {
                data.session_plans_data.forEach(([k, v]) => sessionPlans.set(k, v));
                console.log(`[Hub] Hydrated ${sessionPlans.size} session plans from storage (Spec 32).`);
            }
            resolve();
        });
    });
}

// Hydrate authorizations and plans on service worker wake
loadAuthorizedSessions();
loadSessionPlans();

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
            let wsUrl = this.server.url;
            if (this.server.token && !wsUrl.includes("token=")) {
                const sep = wsUrl.includes("?") ? "&" : "?";
                wsUrl = `${wsUrl}${sep}token=${encodeURIComponent(this.server.token)}`;
            }
            this.ws = new WebSocket(wsUrl);
        } catch (err) {
            console.warn(`[Hub] WebSocket init error for ${this.server.name}:`, err);
            this.scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.log(`[Hub] Successfully connected to ${this.server.name}`);
            this.retryCount = 0;
            authorizedSessions.clear();
            if (this.isOpen()) {
                this.send({
                    type: MT.STATE_CHANGE,
                    human_in_control: humanInControl,
                    notes: "",
                    agent_name: this.server.name,
                    group_color: this.server.color || "purple"
                });
            }
        };

        this.ws.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === MT.EXECUTE_ACTION) {
                    await this.onAction(this.server, data, this);
                } else if (data.type === MT.OBSERVE_PAGE || data.type === "observe_page") {
                    const result = await handleObservePage(data, data.session_title);
                    this.send({
                        type: MT.OBSERVE_RESPONSE,
                        command_id: data.id || data.command_id || data.request_id,
                        request_id: data.request_id || data.id || data.command_id,
                        payload: result
                    });
                } else if (data.type === MT.ACT_ELEMENT || data.type === "act_element") {
                    const result = await handleActElement(data, data.session_title);
                    this.send({
                        type: MT.ACT_RESPONSE,
                        command_id: data.id || data.command_id || data.request_id,
                        request_id: data.request_id || data.id || data.command_id,
                        payload: result
                    });
                } else if (data.type === MT.SET_INTENT || data.type === "set_intent") {
                    await forwardIntentToTabs(data);
                } else if (data.type === MT.STATE_SYNC) {
                    this.onStateSync(this.server, data);
                } else if (data.type === MT.UPDATE_PROGRESS) {
                    await forwardProgressToTabs(data);
                } else if (data.type === MT.SET_PLAN || data.type === "set_plan") {
                    await handleSetPlan(data);
                } else if (data.type === MT.SET_MILESTONE || data.type === "set_milestone") {
                    await handleSetMilestone(data);
                }
            } catch (err) {
                console.error(`[Hub] Error processing message from ${this.server.name}:`, err);
            }
        };

        this.ws.onclose = () => {
            const anyOpen = Object.values(activeSockets).some(s => s && s.isOpen && s.isOpen());
            if (!anyOpen) {
                hideAllGlows();
                for (const [title, sess] of activeSessions.entries()) {
                    sess.active = false;
                }
                saveActiveSessions();
            }
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
        return this.send({ type: MT.PING });
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
chrome.storage.local.get(["human_in_control", "agent_servers"], (data) => {
    humanInControl = !!data.human_in_control;
    loadAuthorizedSessions();
    loadActiveSessions();
    loadSessionPlans();

    if (!data.agent_servers) {
        chrome.storage.local.set({ agent_servers: DEFAULT_SERVERS }, () => {
            syncConnections();
        });
    } else {
        syncConnections();
    }
});

// Setup 24-second keepalive alarm
chrome.alarms.create("socket_keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "socket_keepalive") {
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

        const finalColor = currentServer.color || "purple";
        const finalSessionTitle = data.session_title || `${currentServer.name} Task`;

        const result = await handleSocketAction({
            ...data,
            group_color: finalColor,
            session_title: finalSessionTitle
        }, currentServer);

        socketInstance.send({
            type: MT.COMMAND_RESPONSE,
            command_id: data.id,
            payload: {
                ...result,
                agent_name: currentServer.name,
                group_color: finalColor
            }
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
        chrome.runtime.sendMessage({ type: MT.STATE_CHANGED, humanInControl: active }).catch(() => {});
    });
}

// REST call helper to hit the active server for release/stop
function hitServerEndpoint(endpoint, payload = {}) {
    chrome.storage.local.get(["agent_servers"], (data) => {
        const servers = data.agent_servers || [];
        servers.forEach(server => {
            if (server.enabled) {
                let httpUrl = server.url.replace(/^ws/, "http");
                let serverToken = server.token || "";
                try {
                    const parsedUrl = new URL(httpUrl);
                    if (!serverToken && parsedUrl.searchParams.has("token")) {
                        serverToken = parsedUrl.searchParams.get("token");
                    }
                    parsedUrl.search = "";
                    httpUrl = parsedUrl.toString().replace(/\/ws\/extension\/?$/, "");
                } catch (e) {
                    httpUrl = httpUrl.replace(/\/ws\/extension\/?$/, "");
                }

                const headers = { 'Content-Type': 'application/json' };
                if (serverToken) {
                    headers[typeof SecurityHeaders !== "undefined" ? SecurityHeaders.AUTH_TOKEN_HEADER : 'X-AgentSocket-Token'] = serverToken;
                }

                fetch(`${httpUrl}${endpoint}`, {
                    method: 'POST',
                    headers: headers,
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
    switch (message.type) {
        case MT.GET_STATE:
            sendResponse({ humanInControl: humanInControl });
            return false;

        case MT.TOGGLE_MODE: {
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

        case MT.AUTH_STATUS_CHANGED: {
            const isAuthed = !!message.authorized;
            const sessionTitle = message.session_title || "AgentSocket Task";
            const perms = message.permissions || { enable_subskills: true, enable_vision: false };
            const token = message.token || "";

            console.log(`[Auth] Authorization state changed for "${sessionTitle}":`, isAuthed, perms);
            if (isAuthed) {
                authorizedSessions.add(sessionTitle);
                sessionPermissions.set(sessionTitle, perms);
            } else {
                authorizedSessions.delete(sessionTitle);
                sessionPermissions.delete(sessionTitle);
            }
            saveAuthorizedSessions();

            // Handshake Spec 22 Section 4.2: broadcast AUTH_RESPONSE to active gateway sockets
            const activeSess = activeSessions.get(sessionTitle);
            const authResponseMsg = {
                type: MT.AUTH_RESPONSE || "auth_response",
                status: isAuthed ? "approved" : "denied",
                token: token,
                tab_group_id: activeSess ? activeSess.groupId : null,
                tab_group_name: sessionTitle,
                permissions: perms
            };
            for (const id in activeSockets) {
                if (activeSockets[id] && activeSockets[id].isOpen && activeSockets[id].isOpen()) {
                    activeSockets[id].send(authResponseMsg);
                }
            }

            if (pendingAuthResolve) {
                pendingAuthResolve(isAuthed);
                pendingAuthResolve = null;
            }
            return false;
        }

        case MT.PAGE_TAKEOVER:
            console.warn("[Takeover] User requested manual takeover from page overlay.");
            updateLocalState(true, message.notes || "User clicked Take Over on page");
            broadcastStateChange(true, message.notes || "User clicked Take Over on page");
            return false;

        case MT.PAGE_STOP:
            console.warn("[Takeover] User clicked Stop. Terminating active tasks.");
            authorizedSessions.clear();
            hitServerEndpoint("/stop");
            updateLocalState(false, "");
            broadcastStateChange(false, "");
            return false;

        case MT.PAGE_RESUME:
            console.log("[Takeover] User clicked Resume and continue with notes:", message.notes);
            hitServerEndpoint("/human_release", { notes: message.notes });
            updateLocalState(false, "");
            broadcastStateChange(false, "");
            return false;

        case MT.RELOAD_CONNECTIONS:
            console.log("[Hub] Reloading connections based on settings changes.");
            syncConnections();
            return false;

        case MT.GET_CONNECTION_STATUSES: {
            const statuses = {};
            for (const id in activeSockets) {
                statuses[id] = activeSockets[id].isOpen() ? "online" : "offline";
            }
            sendResponse({ statuses: statuses });
            return false;
        }

        case "CHECK_TAB_SESSION": {
            const isServerConnected = Object.values(activeSockets).some(s => s && s.isOpen && s.isOpen());
            if (!isServerConnected) {
                sendResponse({ inActiveSession: false });
                return false;
            }

            const tabId = sender.tab ? sender.tab.id : null;
            if (!tabId) {
                sendResponse({ inActiveSession: false });
                return false;
            }

            chrome.tabs.get(tabId, (freshTab) => {
                if (chrome.runtime.lastError || !freshTab) {
                    sendResponse({ inActiveSession: false });
                    return;
                }

                const groupId = freshTab.groupId;
                if (groupId && groupId !== chrome.tabGroups.TAB_GROUP_ID_NONE) {
                    chrome.tabGroups.get(groupId, (group) => {
                        if (chrome.runtime.lastError || !group || (group.title && group.title.startsWith("✅"))) {
                            sendResponse({ inActiveSession: false });
                            return;
                        }
                        const session = activeSessions.get(group.title);
                        if (session && session.active === true) {
                            sendResponse({
                                inActiveSession: true,
                                session_title: group.title,
                                group_color: session.groupColor || group.color || "purple",
                                human_in_control: humanInControl,
                                progress_percent: session.progress_percent,
                                step_current: session.step_current,
                                step_total: session.step_total,
                                step_title: session.step_title
                            });
                        } else {
                            sendResponse({ inActiveSession: false });
                        }
                    });
                } else {
                    for (const [title, sess] of activeSessions.entries()) {
                        if (sess.tabId === tabId && sess.active === true && !title.startsWith("✅")) {
                            sendResponse({
                                inActiveSession: true,
                                session_title: title,
                                group_color: sess.groupColor || "purple",
                                human_in_control: humanInControl,
                                progress_percent: sess.progress_percent,
                                step_current: sess.step_current,
                                step_total: sess.step_total,
                                step_title: sess.step_title
                            });
                            return;
                        }
                    }
                    sendResponse({ inActiveSession: false });
                }
            });
            return true;
        }

        case "get_auth_plan": {
            const reqTitle = message.session_title || "";
            const plan = sessionPlans.get(reqTitle) || sessionPlans.get(reqTitle.replace(/^✅\s*/, '')) || null;
            sendResponse({ status: "success", plan });
            return true;
        }

        case MT.SCAN_LOCAL_AGENTS:
            scanLocalPorts().then(count => {
                sendResponse({ discoveredCount: count });
            });
            return true;

        default:
            return false;
    }
});

async function ensureAuthorized(sessionTitle, server) {
    const title = sessionTitle || "AgentSocket Task";
    if (authorizedSessions.has(title)) {
        return true;
    }

    // Spec 30: Check persistent storage if in-memory set was cleared due to SW idle recycle
    await loadAuthorizedSessions();
    if (authorizedSessions.has(title)) {
        return true;
    }

    // Auto-authorize if server explicitly configured with auto_authorize
    if (server && server.auto_authorize) {
        authorizedSessions.add(title);
        sessionPermissions.set(title, { enable_subskills: true, enable_vision: true });
        saveAuthorizedSessions();
        return true;
    }

    // Extract ephemeral server token if available (Spec 22)
    let serverToken = "";
    if (server) {
        if (server.token) {
            serverToken = server.token;
        } else if (server.url) {
            try {
                const parsedUrl = new URL(server.url);
                serverToken = parsedUrl.searchParams.get("token") || "";
            } catch (e) {}
        }
    }

    // 1. Create native OS / Chrome desktop notification alerting the user
    const notifId = `auth_prompt_${Date.now()}`;
    chrome.notifications.create(notifId, {
        type: 'basic',
        iconUrl: chrome.runtime.getURL('icons/icon48.png'),
        title: 'AgentSocket Authorization Required 🔌',
        message: `An AI agent is requesting permission to automate "${title}". Click to grant or deny.`,
        priority: 2,
        requireInteraction: true
    });

    // 2. Open auth.html in a focused active tab and focus window (Spec 22 & Spec 32: with token, session, and plan)
    let planQuery = "";
    const existingPlan = sessionPlans.get(title) || sessionPlans.get(title.replace(/^✅\s*/, ''));
    if (existingPlan && existingPlan.milestones && existingPlan.milestones.length > 0) {
        try {
            planQuery = `&plan=${encodeURIComponent(JSON.stringify(existingPlan.milestones))}`;
        } catch (e) {}
    }
    const authUrl = chrome.runtime.getURL(`auth.html?session=${encodeURIComponent(title)}&token=${encodeURIComponent(serverToken)}${planQuery}`);
    chrome.tabs.create({ url: authUrl, active: true }, (tab) => {
        if (tab && tab.windowId) {
            chrome.windows.update(tab.windowId, { focused: true });
        }
    });

    return new Promise((resolve) => {
        pendingAuthResolve = resolve;
    });
}

// Notification click router
chrome.notifications.onClicked.addListener((notifId) => {
    if (notifId.startsWith('auth_prompt_')) {
        chrome.tabs.query({ url: chrome.runtime.getURL("auth.html*") }, (tabs) => {
            if (tabs && tabs.length > 0) {
                chrome.tabs.update(tabs[0].id, { active: true });
                chrome.windows.update(tabs[0].windowId, { focused: true });
            }
        });
    }
});

// ============================================================================
// AUTOMATION & CDP EXECUTION ENGINE
// ============================================================================
async function sendGlowToTab(tabId, sessionTitle, groupColor) {
    if (humanInControl) return;
    const sess = activeSessions.get(sessionTitle);
    const existingPlan = sessionPlans.get(sessionTitle) || sessionPlans.get((sessionTitle || "").replace(/^✅\s*/, ''));
    const msg = {
        type: MT.SHOW_GLOW,
        session_title: sessionTitle || "AgentSocket Task",
        group_color: groupColor || "purple",
        progress_percent: sess ? sess.progress_percent : (existingPlan ? existingPlan.progress_percent : undefined),
        step_current: sess ? sess.step_current : undefined,
        step_total: sess ? sess.step_total : undefined,
        step_title: sess ? sess.step_title : undefined,
        milestones: existingPlan ? existingPlan.milestones : undefined,
        active_milestone_index: existingPlan ? existingPlan.active_index : undefined,
        current_action: existingPlan ? existingPlan.current_action : undefined
    };
    try {
        await chrome.tabs.sendMessage(tabId, msg);
    } catch (e) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ["protocol.js", "content.js"]
            });
            await chrome.tabs.sendMessage(tabId, msg);
        } catch (scriptErr) {
            // Ignore restricted URLs
        }
    }
}

async function handleSocketAction(command, server) {
    const sessionTitle = command.session_title || "AgentSocket Task";
    const groupColor = command.group_color || "purple";

    const isAuthed = await ensureAuthorized(sessionTitle, server);
    if (!isAuthed) {
        return {
            status: "error",
            error: {
                code: "AUTH_REQUIRED",
                message: `Session authorization was denied by the user for "${sessionTitle}".`
            }
        };
    }

    switch (command.action_type) {
        case AT.NAVIGATE:
            return await handleNavigation(command.target_data, sessionTitle, groupColor);
        case AT.EXECUTE_JS:
            return await handleExecuteJS(command.target_data, sessionTitle, groupColor);
        case AT.TASK_COMPLETE:
            return await handleTaskComplete(sessionTitle);
        case AT.OBSERVE_PAGE:
        case "observe_page":
            return await handleObservePage(command, sessionTitle);
        case AT.ACT_ELEMENT:
        case "act_element":
            return await handleActElement(command, sessionTitle);
        case AT.BROWSER_SCREENSHOT:
        case "browser_screenshot":
            return await handleScreenshot(command, sessionTitle);
        default:
            return { status: "error", message: `Unknown action capability: ${command.action_type}` };
    }
}

async function getActiveTabForSession(sessionTitle, tabGroupId) {
    if (tabGroupId && Number(tabGroupId) > 0) {
        try {
            const tabs = await chrome.tabs.query({ groupId: Number(tabGroupId), active: true });
            if (tabs && tabs.length > 0) return tabs[0].id;
            const groupTabs = await chrome.tabs.query({ groupId: Number(tabGroupId) });
            if (groupTabs && groupTabs.length > 0) return groupTabs[0].id;
        } catch (e) {}
    }

    if (sessionTitle) {
        const titleTabId = await getTargetTabId(sessionTitle);
        if (titleTabId) return titleTabId;
    }

    const sess = activeSessions.get(sessionTitle);
    if (sess && sess.tabId) {
        try {
            const tab = await chrome.tabs.get(sess.tabId);
            if (tab && !tab.discarded) {
                return tab.id;
            }
        } catch (e) {}
    }

    if (sess && sess.groupId && sess.groupId > 0) {
        try {
            const tabs = await chrome.tabs.query({ groupId: sess.groupId, active: true });
            if (tabs && tabs.length > 0) return tabs[0].id;
            const groupTabs = await chrome.tabs.query({ groupId: sess.groupId });
            if (groupTabs && groupTabs.length > 0) return groupTabs[0].id;
        } catch (e) {}
    }

    try {
        const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (activeTabs && activeTabs.length > 0) return activeTabs[0].id;
    } catch (e) {}

    return null;
}

async function handleObservePage(command, sessionTitle) {
    const title = sessionTitle || command.session_title;
    const tabId = await getActiveTabForSession(title, command.tab_group_id || command.groupId);
    if (!tabId) {
        return { status: "error", message: "No active tab found for session observation." };
    }
    try {
        const response = await chrome.tabs.sendMessage(tabId, {
            type: MT.OBSERVE_PAGE || "observe_page",
            options: command.options || (typeof command.target_data === "object" ? command.target_data : {})
        });
        return response || { status: "success", elements: [] };
    } catch (err) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ["protocol.js", "content.js"]
            });
            const retryResponse = await chrome.tabs.sendMessage(tabId, {
                type: MT.OBSERVE_PAGE || "observe_page",
                options: command.options || (typeof command.target_data === "object" ? command.target_data : {})
            });
            return retryResponse || { status: "success", elements: [] };
        } catch (retryErr) {
            return { status: "error", message: `Failed to observe page: ${err.message}` };
        }
    }
}

async function handleActElement(command, sessionTitle) {
    const title = sessionTitle || command.session_title;
    const tabId = await getActiveTabForSession(title, command.tab_group_id || command.groupId);
    if (!tabId) {
        return { status: "error", message: "No active tab found for acting on element." };
    }
    try {
        const payload = command.payload || (typeof command.target_data === "object" ? command.target_data : command);
        const response = await chrome.tabs.sendMessage(tabId, {
            type: MT.ACT_ELEMENT || "act_element",
            payload: payload
        });
        return response || { status: "success" };
    } catch (err) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ["protocol.js", "content.js"]
            });
            const payload = command.payload || (typeof command.target_data === "object" ? command.target_data : command);
            const retryResponse = await chrome.tabs.sendMessage(tabId, {
                type: MT.ACT_ELEMENT || "act_element",
                payload: payload
            });
            return retryResponse || { status: "success" };
        } catch (retryErr) {
            return { status: "error", message: `Failed to act on element: ${err.message}` };
        }
    }
}

async function forwardIntentToTabs(data) {
    try {
        let targetTabs = [];
        if (data.tab_group_id) {
            targetTabs = await chrome.tabs.query({ groupId: Number(data.tab_group_id) });
        }
        if (!targetTabs || targetTabs.length === 0) {
            const activeTabId = await getActiveTabForSession(data.session_title, data.tab_group_id);
            if (activeTabId) targetTabs = [{ id: activeTabId }];
        }
        for (const tab of targetTabs) {
            chrome.tabs.sendMessage(tab.id, {
                type: MT.SET_INTENT || "set_intent",
                intent: data.intent,
                subtext: data.subtext,
                phase: data.phase
            }).catch(() => {});
        }
    } catch (e) {
        console.warn("[Hub] Failed forwarding intent to tabs:", e);
    }
}

async function handleScreenshot(command, sessionTitle) {
    const perms = sessionPermissions.get(sessionTitle) || { enable_vision: false };
    if (!perms.enable_vision) {
        return {
            status: "denied",
            message: "Vision disabled by user"
        };
    }

    try {
        const dataUrl = await new Promise((resolve, reject) => {
            chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else {
                    resolve(dataUrl);
                }
            });
        });
        return {
            status: "success",
            data: dataUrl
        };
    } catch (err) {
        return { status: "error", message: `Screenshot capture failed: ${err.message}` };
    }
}

async function handleTaskComplete(sessionTitle) {
    const cleanTitle = sessionTitle.replace(/^✅\s*/, '');
    authorizedSessions.delete(sessionTitle);
    authorizedSessions.delete(cleanTitle);

    const sess = activeSessions.get(sessionTitle) || activeSessions.get(cleanTitle);
    if (sess) {
        sess.active = false;
    }
    activeSessions.delete(sessionTitle);
    activeSessions.delete(cleanTitle);
    saveActiveSessions();

    try {
        let groups = await chrome.tabGroups.query({ title: sessionTitle });
        if (!groups || groups.length === 0) {
            groups = await chrome.tabGroups.query({ title: cleanTitle });
        }
        if (groups && groups.length > 0) {
            const groupId = groups[0].id;
            await new Promise((resolve) => {
                chrome.tabGroups.update(groupId, {
                    title: `✅ ${cleanTitle}`,
                    color: "grey"
                }, resolve);
            });
            hideAllGlows();
            await forwardProgressToTabs({
                session_title: `✅ ${cleanTitle}`,
                progress_percent: 100,
                step_current: 100,
                step_total: 100,
                step_title: "Task Complete"
            });
            return { status: "success", message: "Task marked complete and tab group renamed." };
        }
        hideAllGlows();
        return { status: "success", message: "Task marked complete and glows cleared." };
    } catch (e) {
        return { status: "error", message: e.message };
    }
}

// Guaranteed automatic HUD & Glow rendering on page navigation completion (Strict Guard)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status !== "complete") return;

    const isServerConnected = Object.values(activeSockets).some(s => s && s.isOpen && s.isOpen());
    if (!isServerConnected) return; // Do not inject if server is offline

    chrome.tabs.get(tabId, (freshTab) => {
        if (chrome.runtime.lastError || !freshTab) return;
        const groupId = freshTab.groupId;
        if (groupId && groupId !== chrome.tabGroups.TAB_GROUP_ID_NONE) {
            chrome.tabGroups.get(groupId, (group) => {
                if (chrome.runtime.lastError || !group) return;
                if (group.title && group.title.startsWith("✅")) return;

                // STRICT CHECK: Must be explicitly registered and active
                const session = activeSessions.get(group.title);
                if (session && session.active === true) {
                    if (humanInControl) {
                        chrome.tabs.sendMessage(tabId, {
                            type: MT.SHOW_TAKEOVER,
                            session_title: group.title
                        }).catch(() => {});
                    } else {
                        sendGlowToTab(tabId, group.title, session.groupColor || group.color || "purple");
                    }
                }
            });
        } else {
            for (const [title, sess] of activeSessions.entries()) {
                if (sess.tabId === tabId && sess.active === true && !title.startsWith("✅")) {
                    if (humanInControl) {
                        chrome.tabs.sendMessage(tabId, {
                            type: MT.SHOW_TAKEOVER,
                            session_title: title
                        }).catch(() => {});
                    } else {
                        sendGlowToTab(tabId, title, sess.groupColor || "purple");
                    }
                    break;
                }
            }
        }
    });
});

// Forward progress updates to HUD in active session tabs
async function forwardProgressToTabs(data) {
    try {
        const sessionTitle = data.session_title;
        const cleanTitle = sessionTitle ? sessionTitle.replace(/^✅\s*/, '') : null;
        const percent = data.progress_percent !== undefined
            ? data.progress_percent
            : (data.step_total > 0 ? Math.round((data.step_current / data.step_total) * 100) : 0);

        if (sessionTitle && activeSessions.has(sessionTitle)) {
            const sess = activeSessions.get(sessionTitle);
            sess.progress_percent = percent;
            sess.step_current = data.step_current;
            sess.step_total = data.step_total;
            sess.step_title = data.step_title;
            saveActiveSessions();
        } else if (cleanTitle && activeSessions.has(cleanTitle)) {
            const sess = activeSessions.get(cleanTitle);
            sess.progress_percent = percent;
            sess.step_current = data.step_current;
            sess.step_total = data.step_total;
            sess.step_title = data.step_title;
            saveActiveSessions();
        }

        let targetTabs = [];
        if (sessionTitle) {
            let groups = await chrome.tabGroups.query({ title: sessionTitle });
            if (!groups || groups.length === 0) {
                if (cleanTitle) {
                    groups = await chrome.tabGroups.query({ title: cleanTitle });
                    if (!groups || groups.length === 0) {
                        groups = await chrome.tabGroups.query({ title: `✅ ${cleanTitle}` });
                    }
                }
            }
            if (groups && groups.length > 0) {
                for (const g of groups) {
                    const tabsInGroup = await chrome.tabs.query({ groupId: g.id });
                    targetTabs.push(...tabsInGroup);
                }
            }
        }
        if (targetTabs.length === 0) {
            targetTabs = await chrome.tabs.query({ active: true, currentWindow: true });
        }
        for (const tab of targetTabs) {
            chrome.tabs.sendMessage(tab.id, {
                type: MT.UPDATE_PROGRESS,
                progress: data.progress,
                progress_percent: percent,
                step_current: data.step_current,
                step_total: data.step_total,
                step_title: data.step_title
            }).catch(() => {});
        }
    } catch (e) {
        console.warn("[Hub] Error forwarding progress:", e);
    }
}

// Spec 32: Forward strategic plan and milestones to HUD in active session tabs
async function handleSetPlan(data) {
    const sessionTitle = data.session_title;
    if (!sessionTitle) return;
    const cleanTitle = sessionTitle.replace(/^✅\s*/, '');
    const planObj = {
        session_title: sessionTitle,
        milestones: data.milestones || [],
        active_index: data.active_index || 1,
        progress_percent: data.progress_percent || 0,
        current_action: data.current_action || null
    };
    sessionPlans.set(sessionTitle, planObj);
    sessionPlans.set(cleanTitle, planObj);
    saveSessionPlans();

    await broadcastToSessionTabs(sessionTitle, {
        type: MT.SET_PLAN || "set_plan",
        session_title: sessionTitle,
        milestones: planObj.milestones,
        active_index: planObj.active_index,
        progress_percent: planObj.progress_percent,
        current_action: planObj.current_action
    });
}

async function handleSetMilestone(data) {
    const sessionTitle = data.session_title;
    if (!sessionTitle) return;
    const cleanTitle = sessionTitle.replace(/^✅\s*/, '');
    let plan = sessionPlans.get(sessionTitle) || sessionPlans.get(cleanTitle) || {
        session_title: sessionTitle,
        milestones: [],
        active_index: data.milestone_index || 1,
        progress_percent: data.progress_percent || 0,
        current_action: data.current_action || null
    };
    if (data.milestone_index !== undefined) plan.active_index = data.milestone_index;
    if (data.progress_percent !== undefined) plan.progress_percent = data.progress_percent;
    if (data.current_action !== undefined) plan.current_action = data.current_action;
    sessionPlans.set(sessionTitle, plan);
    sessionPlans.set(cleanTitle, plan);
    saveSessionPlans();

    await broadcastToSessionTabs(sessionTitle, {
        type: MT.SET_MILESTONE || "set_milestone",
        session_title: sessionTitle,
        milestone_index: data.milestone_index,
        milestone_title: data.milestone_title,
        current_action: data.current_action,
        progress_percent: data.progress_percent
    });
}

async function broadcastToSessionTabs(sessionTitle, msg) {
    try {
        const cleanTitle = sessionTitle ? sessionTitle.replace(/^✅\s*/, '') : null;
        let targetTabs = [];
        if (sessionTitle) {
            let groups = await chrome.tabGroups.query({ title: sessionTitle });
            if (!groups || groups.length === 0) {
                if (cleanTitle) {
                    groups = await chrome.tabGroups.query({ title: cleanTitle });
                    if (!groups || groups.length === 0) {
                        groups = await chrome.tabGroups.query({ title: `✅ ${cleanTitle}` });
                    }
                }
            }
            if (groups && groups.length > 0) {
                for (const g of groups) {
                    const tabsInGroup = await chrome.tabs.query({ groupId: g.id });
                    targetTabs.push(...tabsInGroup);
                }
            }
        }
        if (targetTabs.length === 0) {
            targetTabs = await chrome.tabs.query({ active: true, currentWindow: true });
        }
        for (const tab of targetTabs) {
            chrome.tabs.sendMessage(tab.id, msg).catch(() => {});
        }
    } catch (e) {
        console.warn("[Hub] broadcastToSessionTabs error:", e);
    }
}

// Locate or create dynamic tab group and navigate
async function handleNavigation(url, sessionTitle, groupColor) {
    const cleanSessionTitle = (sessionTitle || "AgentSocket Task").replace(/^✅\s*/, '').trim();
    const existingSess = activeSessions.get(sessionTitle) || activeSessions.get(cleanSessionTitle) || {};
    activeSessions.set(cleanSessionTitle, { ...existingSess, groupColor, active: true });
    activeSessions.set(sessionTitle, { ...existingSess, groupColor, active: true });
    saveActiveSessions();
    try {
        // 1. Query for existing tab group matching session title or clean title
        let groups = await chrome.tabGroups.query({ title: sessionTitle });
        if (!groups || groups.length === 0) {
            groups = await chrome.tabGroups.query({ title: `✅ ${cleanSessionTitle}` });
        }
        if (!groups || groups.length === 0) {
            groups = await chrome.tabGroups.query({ title: cleanSessionTitle });
        }
        if (!groups || groups.length === 0) {
            const allGroups = await chrome.tabGroups.query({});
            groups = allGroups.filter(g => {
                if (!g.title) return false;
                const cleanGroup = g.title.replace(/^✅\s*/, '').trim().toLowerCase();
                const cleanTarget = cleanSessionTitle.toLowerCase();
                return cleanGroup === cleanTarget || cleanTarget.startsWith(cleanGroup) || cleanGroup.startsWith(cleanTarget);
            });
        }

        if (groups && groups.length > 0) {
            const group = groups[0];

            // If group was previously completed, reactivate and restore title & color
            if (group.title && group.title.startsWith("✅")) {
                await new Promise((resolve) => {
                    chrome.tabGroups.update(group.id, {
                        title: cleanSessionTitle,
                        color: groupColor || "purple"
                    }, resolve);
                });
            }

            const tabs = await chrome.tabs.query({ groupId: group.id });

            if (tabs && tabs.length > 0) {
                const targetTab = tabs.find(t => t.active) || tabs[0];
                try {
                    const updatedTab = await chrome.tabs.update(targetTab.id, { url: url, active: true });
                    const prevSess = activeSessions.get(cleanSessionTitle) || activeSessions.get(sessionTitle) || {};
                    const updatedSessData = { ...prevSess, groupColor, tabId: updatedTab.id, groupId: group.id, active: true };
                    activeSessions.set(cleanSessionTitle, updatedSessData);
                    activeSessions.set(sessionTitle, updatedSessData);
                    saveActiveSessions();
                    sendGlowToTab(updatedTab.id, cleanSessionTitle, groupColor);
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

            const res = await createAndGroupTab(url, cleanSessionTitle, groupColor, group.id);
            if (res && res.tabId) {
                const prevSess = activeSessions.get(cleanSessionTitle) || activeSessions.get(sessionTitle) || {};
                const updatedSessData = { ...prevSess, groupColor, tabId: res.tabId, groupId: res.groupId, active: true };
                activeSessions.set(cleanSessionTitle, updatedSessData);
                activeSessions.set(sessionTitle, updatedSessData);
                saveActiveSessions();
                sendGlowToTab(res.tabId, cleanSessionTitle, groupColor);
            }
            return res;
        }

        const res = await createAndGroupTab(url, cleanSessionTitle, groupColor, null);
        if (res && res.tabId) {
            const prevSess = activeSessions.get(cleanSessionTitle) || activeSessions.get(sessionTitle) || {};
            const updatedSessData = { ...prevSess, groupColor, tabId: res.tabId, groupId: res.groupId, active: true };
            activeSessions.set(cleanSessionTitle, updatedSessData);
            activeSessions.set(sessionTitle, updatedSessData);
            saveActiveSessions();
            sendGlowToTab(res.tabId, cleanSessionTitle, groupColor);
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
                        createFreshSocketGroup(newTab.id, sessionTitle, groupColor, resolve);
                    } else {
                        resolve({ status: "success", tabId: newTab.id, groupId: existingGroupId, reused: false });
                    }
                });
            } else {
                createFreshSocketGroup(newTab.id, sessionTitle, groupColor, resolve);
            }
        });
    });
}

function createFreshSocketGroup(tabId, sessionTitle, groupColor, resolve) {
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

async function getTargetTabId(sessionTitle) {
    try {
        const cleanSessionTitle = (sessionTitle || "").replace(/^✅\s*/, '').trim();
        let groups = await chrome.tabGroups.query({ title: sessionTitle });
        if (!groups || groups.length === 0) {
            groups = await chrome.tabGroups.query({ title: `✅ ${cleanSessionTitle}` });
        }
        if (!groups || groups.length === 0) {
            groups = await chrome.tabGroups.query({ title: cleanSessionTitle });
        }
        if (!groups || groups.length === 0) {
            const allGroups = await chrome.tabGroups.query({});
            groups = allGroups.filter(g => {
                if (!g.title) return false;
                const cleanGroup = g.title.replace(/^✅\s*/, '').trim().toLowerCase();
                const cleanTarget = cleanSessionTitle.toLowerCase();
                return cleanGroup === cleanTarget || cleanTarget.startsWith(cleanGroup) || cleanGroup.startsWith(cleanTarget);
            });
        }
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

chrome.tabs.onRemoved.addListener(async (tabId) => {
    if (activeEvaluations.has(tabId)) {
        const rejects = activeEvaluations.get(tabId);
        activeEvaluations.delete(tabId);
        rejects.forEach(reject => reject(new Error("Tab was closed during execution.")));
    }

    // Invalidate session if its tabs were closed
    for (const [title, sess] of activeSessions.entries()) {
        if (sess.tabId === tabId) {
            try {
                const remainingTabs = sess.groupId ? await chrome.tabs.query({ groupId: sess.groupId }) : [];
                if (!remainingTabs || remainingTabs.length === 0) {
                    activeSessions.delete(title);
                    authorizedSessions.delete(title);
                    saveActiveSessions();
                    console.log(`[Hub] Session tab closed. Reset authorization for "${title}".`);
                }
            } catch (e) {
                activeSessions.delete(title);
                authorizedSessions.delete(title);
                saveActiveSessions();
            }
        }
    }
});

if (chrome.tabGroups && chrome.tabGroups.onRemoved) {
    chrome.tabGroups.onRemoved.addListener((group) => {
        for (const [title, sess] of activeSessions.entries()) {
            if (sess.groupId === group.id || title === group.title) {
                activeSessions.delete(title);
                authorizedSessions.delete(title);
                saveActiveSessions();
                console.log(`[Hub] Tab group removed. Reset authorization for "${title}".`);
            }
        }
    });
}

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

    await sendGlowToTab(tabId, sessionTitle, groupColor);

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

async function hideAllGlows() {
    try {
        const tabs = await chrome.tabs.query({});
        for (const tab of tabs) {
            try {
                chrome.tabs.sendMessage(tab.id, { type: MT.HIDE_GLOW });
            } catch(e) {}
        }
    } catch(err) {
        console.error("Error clearing glows:", err);
    }
}

async function scanLocalPorts() {
    const candidatePorts = [8000, 8001, 8002, 8003, 8080, 8500, 9000];
    let newAgentsDiscovered = 0;

    const store = await new Promise(resolve => chrome.storage.local.get(["agent_servers"], resolve));
    let servers = store.agent_servers || DEFAULT_SERVERS;

    for (const port of candidatePorts) {
        const wsUrl = `ws://127.0.0.1:${port}/ws/extension`;
        const httpUrl = `http://127.0.0.1:${port}/status`;

        // First attempt fast HTTP fetch probe
        let isHealthy = false;
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 600);
            const res = await fetch(httpUrl, { signal: controller.signal });
            clearTimeout(timeoutId);
            if (res.ok) {
                const json = await res.json();
                if (json && (json.status || json.service)) {
                    isHealthy = true;
                }
            }
        } catch (e) {
            // Fallback to WebSocket probe
        }

        if (!isHealthy) {
            try {
                isHealthy = await new Promise((resolve) => {
                    const tempSocket = new WebSocket(wsUrl);
                    const timer = setTimeout(() => {
                        try { tempSocket.close(); } catch(e){}
                        resolve(false);
                    }, 600);

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
            } catch(e) {}
        }

        if (isHealthy) {
            const existingIndex = servers.findIndex(s => s.url === wsUrl || s.url.includes(`:${port}`));
            let id = `discovered_${port}`;
            let name = `Agent Local (Port ${port})`;
            let color = "purple";

            if (port === 8000) { name = "AgentSocket Local (e.g. Claude, Hermes, Antigravity)"; color = "purple"; id = "agentsocket_local"; }
            else if (port === 8001) { name = "AgentSocket Alternate (8001)"; color = "blue"; id = "agentsocket_8001"; }
            else if (port === 8080) { name = "AgentSocket 8080"; color = "orange"; id = "agentsocket_8080"; }
            else if (port === 8500) { name = "Claude Code"; color = "green"; id = "claude"; }
            else if (port === 9000) { name = "Antigravity Local"; color = "blue"; id = "antigravity"; }

            if (existingIndex >= 0) {
                servers[existingIndex].url = wsUrl;
                servers[existingIndex].enabled = true;
            } else {
                servers.push({
                    id: id,
                    name: name,
                    url: wsUrl,
                    enabled: true,
                    color: color
                });
                newAgentsDiscovered++;
            }
        }
    }

    await new Promise(resolve => chrome.storage.local.set({ agent_servers: servers }, resolve));
    syncConnections();

    let totalOnline = 0;
    for (const id in activeSockets) {
        if (activeSockets[id] && activeSockets[id].isOpen && activeSockets[id].isOpen()) {
            totalOnline++;
        }
    }

    return {
        discoveredCount: newAgentsDiscovered,
        totalOnline: totalOnline
    };
}
