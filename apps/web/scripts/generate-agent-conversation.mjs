// Trusted, build-time Agent wire schemas only. No runtime compiler.
import Ajv from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
import { readFile, writeFile } from 'node:fs/promises';

const ajv = new Ajv({ strict: true, allErrors: false, ownProperties: true,
  coerceTypes: false, useDefaults: false, removeAdditional: false, code: { source: true, esm: false } });
ajv.addFormat('uuid', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
// Calendar validity is additionally checked with native Date round-trip in the decoder.
ajv.addFormat('date-time', /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/);
for (const [name, file] of [['body', 'agent-conversation-body.v2'], ['reply', 'agent-conversation.v2'],
  ['recordNoteCandidate', 'agent-record-note-candidate.v1']]) {
  ajv.addSchema(JSON.parse(await readFile(new URL(`../../../contracts/http/${file}.schema.json`, import.meta.url), 'utf8')), name);
}
const code = '// Generated from frozen Agent wire schemas by Ajv. Do not edit.\n' +
  standaloneCode(ajv, { body: 'body', reply: 'reply', recordNoteCandidate: 'recordNoteCandidate' }) + '\n';
const target = new URL('../src/runtime/agent-conversation-validators.cjs', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== code) throw new Error('Agent conversation validator drift');
} else if (process.argv.length === 2) await writeFile(target, code, 'utf8');
else throw new Error('Only generation or --check is supported');
