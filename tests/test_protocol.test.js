/**
 * Unit tests for extension/protocol.js
 * Executed via Node.js
 */

const assert = require('assert');
const protocol = require('../extension/protocol.js');

console.log('[Test] Running Protocol & Message Envelope tests...');

// 1. Validate MessageTypes
assert.strictEqual(protocol.MessageTypes.EXECUTE_ACTION, 'execute_action');
assert.strictEqual(protocol.MessageTypes.COMMAND_RESPONSE, 'command_response');
assert.strictEqual(protocol.MessageTypes.PAGE_TAKEOVER, 'page_takeover');
assert.strictEqual(protocol.MessageTypes.PAGE_RESUME, 'page_resume');
assert.strictEqual(protocol.MessageTypes.PAGE_STOP, 'page_stop');
assert.strictEqual(protocol.MessageTypes.SHOW_GLOW, 'show_glow');
console.log('✓ MessageTypes verified.');

// 2. Validate ActionTypes
assert.strictEqual(protocol.ActionTypes.NAVIGATE, 'navigate');
assert.strictEqual(protocol.ActionTypes.EXECUTE_JS, 'execute_js');
assert.strictEqual(protocol.ActionTypes.TASK_COMPLETE, 'task_complete');
console.log('✓ ActionTypes verified.');

// 3. Validate Response Envelope creation
const successEnvelope = protocol.createResponseEnvelope('success', { tabId: 101 });
assert.strictEqual(successEnvelope.status, 'success');
assert.deepStrictEqual(successEnvelope.data, { tabId: 101 });
assert.strictEqual(successEnvelope.error, null);
assert.ok(typeof successEnvelope.timestamp === 'number');
console.log('✓ Success Envelope creator verified.');

// 4. Validate Error Envelope creation
const errorEnvelope = protocol.createErrorEnvelope('TAB_CLOSED', 'Target tab was unexpectedly closed.');
assert.strictEqual(errorEnvelope.status, 'error');
assert.strictEqual(errorEnvelope.data, null);
assert.deepStrictEqual(errorEnvelope.error, {
    code: 'TAB_CLOSED',
    message: 'Target tab was unexpectedly closed.'
});
assert.ok(typeof errorEnvelope.timestamp === 'number');
console.log('✓ Error Envelope creator verified.');

console.log('\n[PASS] All JavaScript protocol tests passed successfully! ✨');
