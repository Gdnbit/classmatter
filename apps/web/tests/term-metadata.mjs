import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';
import { randomUUID } from 'node:crypto';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/term-metadata.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code + '\n//# sourceURL=class-os-term-metadata.unit.mjs').toString('base64')}`);
const scope = { class_id: randomUUID(), term_id: randomUUID() };
const metadata = { schema_version: 'class-os.term-metadata.v1', ...scope, name: '合成学期',
  start_date: '2026-09-01', end_date: '2027-01-31', version: 1 };

test('term QG metadata is a closed immutable scoped snapshot, not class version or inferred fact', () => {
  const input = structuredClone(metadata);
  const result = api.decodeTermMetadata(input, scope);
  assert.deepEqual(result, metadata);
  assert(Object.isFrozen(result));
  input.name = '合成后改动';
  assert.equal(result.name, metadata.name);
});

test('wrong scope, tag, fields, date, name and unsafe versions never populate the editor', () => {
  const cases = [null, [], { ...metadata, class_id: randomUUID() }, { ...metadata, term_id: randomUUID() },
    { ...metadata, schema_version: 'class-os.roster.v1' }, { ...metadata, auto_switch: true },
    { ...metadata, version: true }, { ...metadata, version: 0 }, { ...metadata, version: 2147483647 },
    { ...metadata, start_date: '2026-02-30' }, { ...metadata, start_date: '0000-01-01' },
    { ...metadata, start_date: metadata.end_date }, { ...metadata, name: '坏\u200b名称' }, { ...metadata, name: ' 需核对' },
    ...Object.keys(metadata).map(key => { const value = { ...metadata }; delete value[key]; return value; })];
  for (const value of cases) assert.throws(() => api.decodeTermMetadata(value, scope), error =>
    error.message === '学期信息未通过范围或格式校验，请刷新后重试；尚未生成变更。');
});
