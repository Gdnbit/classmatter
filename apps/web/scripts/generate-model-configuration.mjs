// Trusted build-time schema only, never a runtime user/model schema compiler.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
const schema = JSON.parse(await readFile(new URL('../../../contracts/http/model-configuration.v1.schema.json', import.meta.url), 'utf8'));
ajv.addSchema(schema, 'configuration');
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
for (const name of ['status', 'staged']) ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/model-${name}.v1.schema.json`, import.meta.url), 'utf8')), name);
const code = '// Generated from frozen model configuration v1 schema by Ajv. Do not edit.\n' +
  standaloneCode(ajv, { validate: 'configuration', status: 'status', staged: 'staged' }) + '\n';
const target = new URL('../src/runtime/model-configuration-validator.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Model configuration validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
