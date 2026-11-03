// Fixed reviewed document schemas, never a runtime/custom schema compiler.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const names = {
  create: 'document-create.v1', revise: 'document-revise.v1', stateCommand: 'document-state.v1',
  preview: 'document-preview.v1', receipt: 'document-receipt.v1', approval: 'document-approval.v1',
  rejection: 'document-rejection.v1', document: 'document.v1', revision: 'document-revision.v1',
  listing: 'document-list.v1', history: 'document-history.v1', state: 'command-status.v1',
};
const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
ajv.addFormat('date-time', /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/);
for (const [name, file] of Object.entries(names)) {
  ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/${file}.schema.json`, import.meta.url), 'utf8')), name);
}
const code = '// Generated from reviewed document schemas by Ajv. Do not edit.\n' +
  standaloneCode(ajv, Object.fromEntries(Object.keys(names).map(name => [name, name]))) + '\n';
const target = new URL('../src/runtime/document-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Document validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
