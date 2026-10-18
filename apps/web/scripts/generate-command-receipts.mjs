// Trusted, build-time BCG response schemas; no runtime schema compiler.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
ajv.addFormat('date', /^\d{4}-\d{2}-\d{2}$/);
for (const [name, file] of [['receipt', 'roster-receipt.v1'], ['state', 'command-status.v1'], ['term', 'term-metadata.v1']]) {
  ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/${file}.schema.json`, import.meta.url), 'utf8')), name);
}
const code = '// Generated from frozen BCG response schemas by Ajv. Do not edit.\n' +
  standaloneCode(ajv, { receipt: 'receipt', state: 'state', term: 'term' }) + '\n';
const target = new URL('../src/runtime/command-receipts-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Command receipt validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
