import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';
import { randomUUID } from 'node:crypto';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/command-receipts.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code).toString('base64')}`);
const id = randomUUID(), other = randomUUID();
const tag = 'class-os.roster.v1';
const receipt = (resource = id, version = 1) => ({ schema_version: tag, receipt_id: randomUUID(), resource_id: resource, version });
const proposal = command => ({ schema_version: tag, proposal_id: randomUUID(), payload_hash: 'a'.repeat(64),
  risk: 'W2', expires_at: '2026-10-15T12:00:00Z', payload: command });
const state = (p, nested = receipt(), status = 'committed') => {
  const { schema_version, ...value } = nested || {};
  return { schema_version: 'class-os.command-status.v1', proposal_id: p.proposal_id,
    payload_hash: p.payload_hash, status, receipt: nested ? value : null };
};

test('all18 registered commands bind exact receipt target and result version, not name or workspace guesses', () => {
  const cases = [
    ['class.create', 'class_id', 1], ['student.create', 'student_id', 1], ['record.create', 'record_id', 1],
    ['task.create', 'task_id', 1], ['exit_export.create', 'export_id', 1],
    ...['class.update', 'class.archive'].map(name => [name, 'class_id', 3]),
    ['term.update', 'term_id', 3],
    ...['student.update_name', 'student.update_identifier', 'student.deactivate'].map(name => [name, 'student_id', 3]),
    ...['record.correct', 'record.supersede'].map(name => [name, 'record_id', 3]),
    ...['task.update', 'task.complete', 'task.cancel'].map(name => [name, 'task_id', 3]),
    ...['model_configuration.save', 'model_configuration.clear'].map(name => [name, 'candidate_id', 3]),
  ];
  for (const [command, field, resultVersion] of cases) {
    const payload = { command, [field]: id, expected_version: resultVersion - 1, workspace_id: other, name: '合成同名' };
    const result = api.decodeCommandReceipt(receipt(id, resultVersion), payload);
    assert.equal(result.resource_id, id);
    assert.equal(result.version, resultVersion);
    assert(Object.isFrozen(result));
    assert.throws(() => api.decodeCommandReceipt(receipt(other, resultVersion), payload));
    assert.throws(() => api.decodeCommandReceipt(receipt(id, resultVersion + 1), payload));
  }
  assert.equal(api.decodeCommandReceipt(receipt(), { command: 'model_configuration.clear', candidate_id: id, expected_version: 0 }).version, 1);
});

test('malformed200 receipt cannot become saved, aliases stay isolated and no request/retry occurs', () => {
  const command = { command: 'student.update_name', student_id: id, expected_version: 1 };
  const original = receipt(id, 2);
  const result = api.decodeCommandReceipt(original, command);
  original.version = 999;
  assert.equal(result.version, 2);
  for (const change of [{ extra: 'synthetic-secret' }, { schema_version: 'wrong' }, { schema_version: undefined },
    { receipt_id: 'not-uuid' }, { resource_id: other }, { version: 0 }, { version: true }, { version: 2.1 },
    { version: '2' }, { version: Number.MAX_SAFE_INTEGER + 1 }, { version: 2147483648 }]) {
    assert.throws(() => api.decodeCommandReceipt({ ...receipt(id, 2), ...change }, command));
  }
  for (const payload of [{ command: 'student.merge', student_id: id, expected_version: 1 },
    { command: '__proto__' }, { command: 'student.update_name', student_id: other, expected_version: 1 },
    ...[true, 0, -1, 1.2, 2147483647].map(value => ({ ...command, expected_version: value }))]) {
    assert.throws(() => api.decodeCommandReceipt(receipt(id, 2), payload));
  }
});

test('read-only state requires original proposal/hash and consistent closed receipt/status', () => {
  const p = proposal({ command: 'task.create', task_id: id });
  const valid = state(p);
  assert.equal(api.decodeCommandState(valid, p).receipt.resource_id, id);
  assert(Object.isFrozen(api.decodeCommandState(valid, p).receipt));
  for (const status of ['not_committed', 'unavailable']) {
    assert.equal(api.decodeCommandState(state(p, null, status), p).receipt, null);
    assert.throws(() => api.decodeCommandState(state(p, receipt(), status), p));
  }
  for (const change of [{ extra: true }, { schema_version: undefined }, { proposal_id: other },
    { payload_hash: 'b'.repeat(64) }, { status: 'success' }, { receipt: null },
    { receipt: { ...valid.receipt, extra: 'bad' } }, { receipt: { ...valid.receipt, resource_id: other } },
    { receipt: { ...valid.receipt, version: 2 } }]) {
    assert.throws(() => api.decodeCommandState({ ...valid, ...change }, p));
  }
  const snapshot = api.decodeCommandState(valid, p);
  valid.receipt.version = 99;
  assert.equal(snapshot.receipt.version, 1);
});

test('approval reply is closed original v1 with bounded opaque token, never a success receipt', () => {
  const value = { schema_version: tag, approval: 'a'.repeat(43) };
  assert.equal(api.decodeApproval(value), value.approval);
  for (const change of [{ schema_version: 'wrong' }, { schema_version: undefined }, { approval: '' },
    { approval: 'x'.repeat(129) }, { approval: true }, { receipt_id: id }, { risk: 'W1' }]) {
    assert.throws(() => api.decodeApproval({ ...value, ...change }));
  }
});
