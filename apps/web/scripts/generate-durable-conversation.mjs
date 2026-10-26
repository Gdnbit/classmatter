// Trusted build-time D1 schemas, not a runtime compiler or custom schema engine.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const names = {
  capabilities: 'runtime-capabilities-d1.v1', listing: 'conversation-d1-list.v1',
  history: 'conversation-d1-history.v2', run: 'conversation-d1-run.v1',
  preview: 'conversation-d1-preview.v1', control: 'conversation-d1-control-status.v1',
  activity: 'activity-d1.v1', audit: 'business-audit-d1.v1',
  state: 'command-status.v1', receipt: 'roster-receipt.v1',
  exitSummary: 'conversation-d1-exit-summary.v1', exitPreview: 'conversation-d1-exit-preview.v1',
};
const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
ajv.addFormat('date-time', /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/);
for (const [name, file] of Object.entries(names)) {
  ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/${file}.schema.json`, import.meta.url), 'utf8')), name);
}
const code = '// Generated from reviewed D1 wire schemas by Ajv. Do not edit.\n' +
  standaloneCode(ajv, Object.fromEntries(Object.keys(names).map(name => [name, name]))) + '\n';
const target = new URL('../src/runtime/durable-conversation-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Durable conversation validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
