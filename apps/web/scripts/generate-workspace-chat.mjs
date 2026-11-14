import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true, coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
ajv.addFormat('date-time', /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/);
ajv.addFormat('date', /^\d{4}-\d{2}-\d{2}$/);
const names = { capabilities: 'capabilities', listing: 'list', history: 'history', send: 'send', turn: 'turn', version: 'version', clear: 'clear', thread: 'thread', previewBody: 'preview-body', preview: 'preview' };
for (const [name, suffix] of Object.entries(names)) ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/workspace-chat-${suffix}.v1.schema.json`, import.meta.url), 'utf8')), name);
for (const suffix of ['input', 'output']) { const name = `capture${suffix}`; names[name] = name; ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/composer-${suffix}.v1.schema.json`, import.meta.url), 'utf8')), name); }
ajv.addSchema(JSON.parse(await readFile(new URL('../../../contracts/http/personal-summary-check.v1.schema.json', import.meta.url), 'utf8')), 'summaryWake');
names.summaryWake = 'summaryWake';
const code = '// Generated from fixed workspace chat schemas by Ajv. Do not edit.\n' + standaloneCode(ajv, Object.fromEntries(Object.keys(names).map(name => [name, name]))) + '\n';
const target = new URL('../src/runtime/workspace-chat-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Workspace chat validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
