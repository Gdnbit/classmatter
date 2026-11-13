const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { collectNotices } = require('../scripts/notices.cjs');
const { createHash } = require('node:crypto');

test('type-only installed dependencies retain their exact original notice and metadata', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'classmatter-notices-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const web = path.join(root, 'web'), stage = path.join(root, 'stage');
  const dependency = path.join(web, 'node_modules', '@fixture', 'types');
  fs.mkdirSync(dependency, { recursive: true });
  fs.writeFileSync(path.join(web, 'package.json'), JSON.stringify({ dependencies: { '@fixture/types': '1.0.0' } }));
  fs.writeFileSync(path.join(dependency, 'package.json'), JSON.stringify({ name: '@fixture/types', version: '1.0.0', types: 'index.d.ts', license: 'MIT' }));
  fs.writeFileSync(path.join(dependency, 'index.d.ts'), 'export type Example = string;\n');
  const notice = 'Copyright synthetic upstream\nSynthetic MIT fixture\n';
  fs.writeFileSync(path.join(dependency, 'LICENSE'), notice);
  collectNotices(web, stage);
  const inventory = JSON.parse(fs.readFileSync(path.join(stage, 'third_party', 'web-runtime.json'), 'utf8'));
  assert.equal(inventory.packages.length, 1);
  assert.deepEqual(inventory.packages[0], { name: '@fixture/types', version: '1.0.0', license: 'MIT', notices: ['third_party/@fixture_types@1.0.0/LICENSE'] });
  assert.equal(fs.readFileSync(path.join(stage, inventory.packages[0].notices[0]), 'utf8'), notice);
  fs.unlinkSync(path.join(dependency, 'LICENSE'));
  assert.throws(() => collectNotices(web, stage), /License review required/);
  fs.unlinkSync(path.join(dependency, 'package.json'));
  assert.throws(() => collectNotices(web, stage), /Package metadata missing/);
  // A nested module-mode marker is not the root package's notice metadata.
  fs.mkdirSync(path.join(dependency, 'dist'), { recursive: true });
  fs.writeFileSync(path.join(dependency, 'package.json'), JSON.stringify({ name: '@fixture/types', version: '1.0.0', main: 'dist/index.js', license: 'MIT' }));
  fs.writeFileSync(path.join(dependency, 'dist', 'package.json'), JSON.stringify({ type: 'commonjs' }));
  fs.writeFileSync(path.join(dependency, 'dist', 'index.js'), 'throw Error("must not execute dependency");');
  fs.writeFileSync(path.join(dependency, 'LICENSE'), notice);
  collectNotices(web, stage);
  assert.equal(JSON.parse(fs.readFileSync(path.join(stage, 'third_party', 'web-runtime.json'), 'utf8')).packages[0].name, '@fixture/types');
});

test('missing package notices require exact reviewed version, contained path and original SHA', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'classmatter-reviewed-notice-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const web = path.join(root, 'web'), stage = path.join(root, 'stage'), thirdParty = path.join(root, 'third_party');
  const dependency = path.join(web, 'node_modules', 'synthetic-notice');
  fs.mkdirSync(dependency, { recursive: true });
  fs.writeFileSync(path.join(web, 'package.json'), JSON.stringify({ dependencies: { 'synthetic-notice': '1.0.0' } }));
  fs.writeFileSync(path.join(dependency, 'package.json'), JSON.stringify({ name: 'synthetic-notice', version: '1.0.0', license: 'MIT' }));
  const upstream = path.join(thirdParty, 'licenses/upstream/synthetic-notice-1.0.0/LICENSE.txt');
  fs.mkdirSync(path.dirname(upstream), { recursive: true });
  const original = 'Synthetic upstream notice\n';fs.writeFileSync(upstream, original);
  const entry = { name: 'synthetic-notice', version: '1.0.0', path: 'licenses/upstream/synthetic-notice-1.0.0/LICENSE.txt',
    sha256: createHash('sha256').update(original).digest('hex') };
  const writeReview = value => fs.writeFileSync(path.join(thirdParty, 'supplemental-license-review.json'), JSON.stringify({ upstream_release_notices: value }));
  writeReview([entry]); collectNotices(web, stage, thirdParty);
  const inventory = JSON.parse(fs.readFileSync(path.join(stage, 'third_party/web-runtime.json'), 'utf8'));
  assert.equal(fs.readFileSync(path.join(stage, inventory.packages[0].notices[0]), 'utf8'), original);
  for (const mutation of [{ version: '2.0.0' }, { sha256: '0'.repeat(64) }, { path: '../outside.txt' }]) {
    fs.writeFileSync(path.join(root, 'outside.txt'), original);writeReview([{ ...entry, ...mutation }]);
    assert.throws(() => collectNotices(web, stage, thirdParty), /License review required|Reviewed notice mismatch/);
  }
  writeReview([entry]);fs.appendFileSync(upstream, 'modified');
  assert.throws(() => collectNotices(web, stage, thirdParty), /Reviewed notice mismatch/);
  writeReview([]);assert.throws(() => collectNotices(web, stage, thirdParty), /License review required/);
});
