/**
 * AgentSocket - Shared Message Protocol & Constants
 * Defines message types, action types, control modes, and standard response envelopes.
 * Compatible with MV3 Service Worker (importScripts), Content Scripts, and Node.js test runners.
 */

(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        // CommonJS / Node.js
        module.exports = factory();
    } else {
        // Browser / Web Worker / Extension Global
        const exports = factory();
        root.AgentSocketProtocol = exports;
        root.BroProtocol = exports; // Backwards compatibility alias
        // Also expose individual keys on globalThis for convenient direct access
        Object.assign(root, exports);
    }
})(typeof self !== 'undefined' ? self : typeof globalThis !== 'undefined' ? globalThis : this, function () {

    const MessageTypes = Object.freeze({
        // Gateway WebSocket <-> Extension
        EXECUTE_ACTION: "execute_action",
        COMMAND_RESPONSE: "command_response",
        OBSERVE_PAGE: "observe_page",
        OBSERVE_RESPONSE: "observe_response",
        STATE_CHANGE: "state_change",
        STATE_SYNC: "state_sync",
        PING: "ping",

        // Content Script <-> Background
        PAGE_TAKEOVER: "page_takeover",
        PAGE_RESUME: "page_resume",
        PAGE_STOP: "page_stop",
        SHOW_GLOW: "show_glow",
        SHOW_TAKEOVER: "show_takeover",
        HIDE_GLOW: "hide_glow",
        UPDATE_PROGRESS: "update_progress",
        SET_INTENT: "set_intent",
        SET_MILESTONE: "set_milestone",

        // Popup / Auth <-> Background
        GET_STATE: "get_state",
        STATE_CHANGED: "state_changed",
        TOGGLE_MODE: "toggle_mode",
        AUTH_STATUS_CHANGED: "auth_status_changed",
        RELOAD_CONNECTIONS: "reload_connections",
        GET_CONNECTION_STATUSES: "get_connection_statuses",
        SCAN_LOCAL_AGENTS: "scan_local_agents"
    });

    const ActionTypes = Object.freeze({
        NAVIGATE: "navigate",
        EXECUTE_JS: "execute_js",
        TASK_COMPLETE: "task_complete"
    });

    const ControlModes = Object.freeze({
        AGENT: "agent",
        HUMAN: "human"
    });

    const ResponseStatus = Object.freeze({
        SUCCESS: "success",
        ERROR: "error",
        HUMAN_LOCKED: "human_locked",
        SECURITY_ABORT: "security_abort",
        RESUMED_CONTEXT: "resumed_context"
    });

    const ErrorCodes = Object.freeze({
        TAB_CLOSED: "TAB_CLOSED",
        EXECUTION_TIMEOUT: "EXECUTION_TIMEOUT",
        EXTENSION_OFFLINE: "EXTENSION_OFFLINE",
        UNKNOWN_ACTION: "UNKNOWN_ACTION",
        CDP_ERROR: "CDP_ERROR",
        AUTH_REQUIRED: "AUTH_REQUIRED",
        TASK_ABORTED: "TASK_ABORTED"
    });

    /**
     * Standard response envelope creator
     */
    function createResponseEnvelope(status, data = null, error = null) {
        return {
            status: status || ResponseStatus.SUCCESS,
            data: data,
            error: error ? {
                code: error.code || ErrorCodes.CDP_ERROR,
                message: error.message || String(error)
            } : null,
            timestamp: Date.now()
        };
    }

    /**
     * Standard error envelope creator
     */
    function createErrorEnvelope(code, message) {
        return createResponseEnvelope(ResponseStatus.ERROR, null, { code, message });
    }

    return {
        MessageTypes,
        ActionTypes,
        ControlModes,
        ResponseStatus,
        ErrorCodes,
        createResponseEnvelope,
        createErrorEnvelope
    };
});
