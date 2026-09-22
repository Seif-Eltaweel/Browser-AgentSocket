// popup.js - AgentSocket Extension Popup Configuration & State Controller
const DEFAULT_SERVERS = [
    { id: "agentsocket_local", name: "AgentSocket Local (e.g. Claude, Hermes, Antigravity)", url: "ws://127.0.0.1:8000/ws/extension", enabled: true, color: "purple" },
    { id: "antigravity", name: "Antigravity Local", url: "ws://127.0.0.1:9000/ws/extension", enabled: false, color: "blue" },
    { id: "claude", name: "Claude Code", url: "ws://127.0.0.1:8500/ws/extension", enabled: false, color: "green" },
    { id: "vps", name: "Custom Agent / VPS", url: "wss://yourvps.com/ws/extension", enabled: false, color: "red" }
];

document.addEventListener("DOMContentLoaded", () => {
    const actionBtn = document.getElementById("actionBtn");
    const statusTag = document.getElementById("statusTag");
    const controlText = document.getElementById("controlText");
    const contextBox = document.getElementById("contextBox");
    const interventionNotes = document.getElementById("interventionNotes");

    const agentList = document.getElementById("agentList");
    const addServerBtn = document.getElementById("addServerBtn");
    const scanAgentsBtn = document.getElementById("scanAgentsBtn");
    const noServerAlert = document.getElementById("noServerAlert");

    const addServerForm = document.getElementById("addServerForm");
    const serverNameInput = document.getElementById("serverNameInput");
    const serverUrlInput = document.getElementById("serverUrlInput");
    const saveAddBtn = document.getElementById("saveAddBtn");
    const cancelAddBtn = document.getElementById("cancelAddBtn");

    const editServerForm = document.getElementById("editServerForm");
    const editServerId = document.getElementById("editServerId");
    const editServerNameInput = document.getElementById("editServerNameInput");
    const editServerUrlInput = document.getElementById("editServerUrlInput");
    const saveEditBtn = document.getElementById("saveEditBtn");
    const cancelEditBtn = document.getElementById("cancelEditBtn");
    const deleteServerBtn = document.getElementById("deleteServerBtn");

    let isHumanMode = false;
    let serverStatuses = {};

    const MT = (typeof MessageTypes !== "undefined") ? MessageTypes : (window.AgentSocketProtocol ? window.AgentSocketProtocol.MessageTypes : {});

    // 1. Initial State Sync
    chrome.runtime.sendMessage({ type: MT.GET_STATE }, (response) => {
        if (response) {
            updateUI(response.humanInControl);
        }
    });

    // Listen for state changes pushed from background
    chrome.runtime.onMessage.addListener((message) => {
        if (message.type === MT.STATE_CHANGED) {
            updateUI(message.humanInControl);
        }
    });

    function updateUI(humanInControl) {
        isHumanMode = humanInControl;
        if (humanInControl) {
            statusTag.innerText = "Manual Active";
            statusTag.className = "status-tag status-manual";
            controlText.innerText = "Operator Active";
            controlText.style.color = "#ff7369";
            controlText.style.textShadow = "none";

            actionBtn.innerText = "Return Control to Agent";
            actionBtn.className = "btn btn-resume";
            contextBox.classList.add("active");
        } else {
            statusTag.innerText = "Auto Engine";
            statusTag.className = "status-tag status-auto";
            controlText.innerText = "Agent Active";
            controlText.style.color = "#4dab9a";
            controlText.style.textShadow = "none";

            actionBtn.innerText = "Take Over Control";
            actionBtn.className = "btn btn-takeover";
            contextBox.classList.remove("active");
            interventionNotes.value = "";
        }
    }

    // Toggle Mode Button Click handler
    actionBtn.addEventListener("click", () => {
        const notes = interventionNotes.value.trim();
        chrome.runtime.sendMessage({
            type: MT.TOGGLE_MODE,
            human_intervention_notes: notes
        }, (response) => {
            if (response) {
                updateUI(response.humanInControl);
            }
        });
    });

    // ============================================================================
    // SERVER CONFIGURATION MANAGEMENT
    // ============================================================================
    function loadAndRenderServers() {
        chrome.storage.local.get(["agent_servers"], (data) => {
            let servers = data.agent_servers;
            if (!servers) {
                servers = DEFAULT_SERVERS;
                chrome.storage.local.set({ agent_servers: servers });
            }
            renderServersList(servers);
        });
    }

    function renderServersList(servers) {
        agentList.innerHTML = "";
        servers.forEach(server => {
            const item = document.createElement("div");
            item.className = "agent-item";

            let statusClass = "disabled";
            if (server.enabled) {
                statusClass = serverStatuses[server.id] === "online" ? "online" : "offline";
            }

            const currentGroupColor = server.color || "purple";

            item.innerHTML = `
                <div class="agent-info">
                  <div class="status-dot ${statusClass}" data-id="${server.id}"></div>
                  <div class="agent-text">
                    <span class="agent-name">${escapeHtml(server.name)}</span>
                    <span class="agent-url">${escapeHtml(server.url)}</span>
                  </div>
                </div>
                <div class="agent-actions">
                  <select class="color-select" data-id="${server.id}" title="Theme Accent">
                    <option value="purple">Purple</option>
                    <option value="blue">Blue</option>
                    <option value="green">Green</option>
                    <option value="orange">Orange</option>
                    <option value="red">Red</option>
                  </select>
                  <button class="btn-edit" data-id="${server.id}" title="Configure Server">⚙️</button>
                  <label class="switch">
                    <input type="checkbox" data-id="${server.id}" ${server.enabled ? 'checked' : ''} />
                    <span class="slider"></span>
                  </label>
                </div>
            `;

            const colorSelect = item.querySelector(".color-select");
            colorSelect.value = currentGroupColor;
            colorSelect.addEventListener("change", (e) => {
                updateServerColor(server.id, e.target.value);
            });

            const toggleInput = item.querySelector("input[type='checkbox']");
            toggleInput.addEventListener("change", (e) => {
                toggleServerEnabled(server.id, e.target.checked);
            });

            const editBtn = item.querySelector(".btn-edit");
            editBtn.addEventListener("click", () => {
                showEditForm(server);
            });

            agentList.appendChild(item);
        });
    }

    function updateServerColor(id, color) {
        chrome.storage.local.get(["agent_servers"], (data) => {
            let servers = data.agent_servers || [];
            servers = servers.map(s => {
                if (s.id === id) {
                    s.color = color;
                }
                return s;
            });
            chrome.storage.local.set({ agent_servers: servers });
        });
    }

    function toggleServerEnabled(id, enabled) {
        chrome.storage.local.get(["agent_servers"], (data) => {
            let servers = data.agent_servers || [];
            servers = servers.map(s => {
                if (s.id === id) {
                    s.enabled = enabled;
                }
                return s;
            });
            chrome.storage.local.set({ agent_servers: servers }, () => {
                loadAndRenderServers();
                chrome.runtime.sendMessage({ type: MT.RELOAD_CONNECTIONS });
            });
        });
    }

    // Add Form Toggle
    addServerBtn.addEventListener("click", () => {
        editServerForm.style.display = "none";
        addServerForm.style.display = addServerForm.style.display === "none" ? "flex" : "none";
        serverNameInput.focus();
    });

    cancelAddBtn.addEventListener("click", () => {
        addServerForm.style.display = "none";
        serverNameInput.value = "";
        serverUrlInput.value = "";
    });

    saveAddBtn.addEventListener("click", () => {
        const name = serverNameInput.value.trim();
        const url = serverUrlInput.value.trim();

        if (!name || !url) return;

        chrome.storage.local.get(["agent_servers"], (data) => {
            const servers = data.agent_servers || [];
            const newServer = {
                id: "server_" + Date.now(),
                name: name,
                url: url,
                enabled: true,
                color: "purple"
            };
            servers.push(newServer);
            chrome.storage.local.set({ agent_servers: servers }, () => {
                loadAndRenderServers();
                addServerForm.style.display = "none";
                serverNameInput.value = "";
                serverUrlInput.value = "";
                chrome.runtime.sendMessage({ type: MT.RELOAD_CONNECTIONS });
            });
        });
    });

    // Edit Form Toggle
    function showEditForm(server) {
        addServerForm.style.display = "none";
        editServerForm.style.display = "flex";

        editServerId.value = server.id;
        editServerNameInput.value = server.name;
        editServerUrlInput.value = server.url;
        editServerNameInput.focus();
    }

    cancelEditBtn.addEventListener("click", () => {
        editServerForm.style.display = "none";
    });

    saveEditBtn.addEventListener("click", () => {
        const id = editServerId.value;
        const name = editServerNameInput.value.trim();
        const url = editServerUrlInput.value.trim();

        if (!name || !url) return;

        chrome.storage.local.get(["agent_servers"], (data) => {
            let servers = data.agent_servers || [];
            servers = servers.map(s => {
                if (s.id === id) {
                    s.name = name;
                    s.url = url;
                }
                return s;
            });
            chrome.storage.local.set({ agent_servers: servers }, () => {
                loadAndRenderServers();
                editServerForm.style.display = "none";
                chrome.runtime.sendMessage({ type: MT.RELOAD_CONNECTIONS });
            });
        });
    });

    deleteServerBtn.addEventListener("click", () => {
        const id = editServerId.value;
        chrome.storage.local.get(["agent_servers"], (data) => {
            let servers = data.agent_servers || [];
            servers = servers.filter(s => s.id !== id);
            chrome.storage.local.set({ agent_servers: servers }, () => {
                loadAndRenderServers();
                editServerForm.style.display = "none";
                chrome.runtime.sendMessage({ type: MT.RELOAD_CONNECTIONS });
            });
        });
    });

    // Scan Button Event
    scanAgentsBtn.addEventListener("click", () => {
        scanAgentsBtn.innerText = "Scanning ports...";
        scanAgentsBtn.disabled = true;

        chrome.runtime.sendMessage({ type: MT.SCAN_LOCAL_AGENTS }, (response) => {
            scanAgentsBtn.innerText = "🔍 Scan for Sockets";
            scanAgentsBtn.disabled = false;

            const discovered = response ? (response.discoveredCount || 0) : 0;
            const online = response ? (response.totalOnline || 0) : 0;

            loadAndRenderServers();
            pollConnectionStatuses();

            if (discovered > 0 || online > 0) {
                if (noServerAlert) noServerAlert.style.display = "none";
                chrome.notifications.create({
                    type: 'basic',
                    iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                    title: 'Sockets Discovered',
                    message: `Discovered and connected to ${discovered > 0 ? discovered : online} active agent socket(s)!`,
                    priority: 1
                });
            } else {
                if (noServerAlert) noServerAlert.style.display = "block";
                chrome.notifications.create({
                    type: 'basic',
                    iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                    title: 'Scan Finished',
                    message: 'No active AgentSocket server found on candidate ports [8000..9000].',
                    priority: 1
                });
            }
        });
    });

    // Connection Poller: pulls active state from service worker
    function pollConnectionStatuses() {
        chrome.runtime.sendMessage({ type: MT.GET_CONNECTION_STATUSES }, (response) => {
            if (response && response.statuses) {
                serverStatuses = response.statuses;
                let anyOnline = false;

                document.querySelectorAll(".status-dot").forEach(dot => {
                    const id = dot.getAttribute("data-id");
                    const isEnabled = document.querySelector(`input[data-id="${id}"]`)?.checked;

                    dot.className = "status-dot";
                    if (isEnabled) {
                        const status = serverStatuses[id] === "online" ? "online" : "offline";
                        if (status === "online") {
                            anyOnline = true;
                        }
                        dot.classList.add(status);
                    } else {
                        dot.classList.add("disabled");
                    }
                });

                if (noServerAlert) {
                    noServerAlert.style.display = anyOnline ? "none" : "block";
                }
            }
        });
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

    loadAndRenderServers();
    pollConnectionStatuses();
    setInterval(pollConnectionStatuses, 1500);
});
