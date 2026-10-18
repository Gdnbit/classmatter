// Build-time only. Never compiles a schema supplied by a user/model/server.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false,
  code: { source: true, esm: false } });
// Canonical UUID wire output only, bounded regex, no generic remote formats.
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
const names = { challenge: 'identity-challenge', session: 'identity-session',
  kit: 'identity-kit-session', signedOut: 'identity-signed-out', logoutReceipt: 'identity-logout-receipt',
  operationReceipt: 'identity-operation-receipt' };
for (const [name, file] of Object.entries(names)) {
  const schema = JSON.parse(await readFile(new URL(`../../../contracts/http/${file}.v1.schema.json`, import.meta.url), 'utf8'));
  ajv.addSchema(schema, name);
}
const code = '// Generated from frozen identity v1 schemas by Ajv. Do not edit.\n' +
  standaloneCode(ajv, Object.fromEntries(Object.keys(names).map(name => [name, name]))) + '\n';
const target = new URL('../src/runtime/identity-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Identity validator drift; regenerate from canonical schemas');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
