import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { build } from 'vite';
const output = await build({ configFile: false, logLevel: 'silent', build: { write: false, lib: { entry: 'src/runtime/classroom-work.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(chunk.code).toString('base64')}`);
const session = { csrf_token: 'synthetic-csrf', subject: { workspace_id: randomUUID() } }, scope = { class_id: randomUUID(), term_id: randomUUID() };
const exam = randomUUID(), student = randomUUID(), layout = randomUUID(), original = globalThis.fetch;
const response = value => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });
const client = api.classroomClient(session, scope);
test('classroom discovery never falls back after outage or access denial', async () => {
  try {
    globalThis.fetch = async () => new Response('', { status: 404 });
    assert.equal(await api.classroomAvailable(session), false);
    for (const status of [401, 403, 409, 500]) {
      globalThis.fetch = async () => new Response('', { status });
      await assert.rejects(api.classroomAvailable(session));
    }
  } finally { globalThis.fetch = original; }
});
test('scores keep zero distinct from absence and reject ambiguous or wrong-target responses', async () => {
  const value = { schema_version: 'classmatter.exam-results.v1', exam_id: exam, title: '合成月考', subject: '数学', maximum_score: '100.00', version: 2,
    results: [{ student_id: student, version: 1, status: 'scored', score: '0.00', reason: '', created_at: '2026-11-09T00:00:00Z' }], scored_count: 1, average: '0.00' };
  try {
    globalThis.fetch = async () => response(value);
    assert.equal((await client.results(exam)).results[0].score, '0.00');
    for (const broken of [{ ...value, exam_id: randomUUID() }, { ...value, results: [...value.results, ...value.results] },
      { ...value, results: [{ ...value.results[0], status: 'absent' }] }, { ...value, average: 'NaN' },
      { ...value, results: [{ ...value.results[0], score: '101' }] }, { ...value, scored_count: 0 }]) {
      globalThis.fetch = async () => response(broken);
      await assert.rejects(client.results(exam));
    }
  } finally { globalThis.fetch = original; }
});
test('seating rejects duplicate identities, duplicate cells and partial grids', async () => {
  const value = { schema_version: 'classmatter.seating.v1', layout: { layout_id: layout, rows: 1, columns: 2, version: 1,
    seats: [{ row_index: 1, column_index: 1, student_id: student }, { row_index: 1, column_index: 2, student_id: null }] } };
  try {
    globalThis.fetch = async () => response(value);
    assert.equal((await client.seating()).layout.seats.length, 2);
    for (const seats of [[value.layout.seats[0]], [value.layout.seats[0], value.layout.seats[0]],
      [value.layout.seats[0], { ...value.layout.seats[1], student_id: student }]]) {
      globalThis.fetch = async () => response({ ...value, layout: { ...value.layout, seats } });
      await assert.rejects(client.seating());
    }
  } finally { globalThis.fetch = original; }
});
test('classroom preview rejects a shifted scope before sending and binds canonical fields', async () => {
  const command = { command: 'seat.assign', ...scope, layout_id: layout, student_id: student, expected_version: 1, row: 1, column: 2 };
  let calls = 0;
  try {
    globalThis.fetch = async () => { calls++; return response({ schema_version: 'classmatter.classroom-preview.v1', proposal_id: randomUUID(), payload_hash: 'a'.repeat(64),
      risk: 'W2', expires_at: '2026-11-09T00:00:00Z', payload: { ...command, column: 1 } }); };
    await assert.rejects(client.preview({ ...command, class_id: randomUUID() })); assert.equal(calls, 0);
    await assert.rejects(client.preview(command)); assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
