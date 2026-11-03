const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { prerequisites } = require('../runtime-check.cjs');

function fixture(t, profile = 'r1') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'classmatter-prerequisites-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true })); // Only this test's fresh owned directory.
  const d1=profile==='conversation-d1';
  const stageName=d1?'apps/desktop/.build/runtime-d1':'apps/desktop/.build/runtime';
  const runtimeName=d1?'.local-runtime/synthetic-conversation-d1':'.local-runtime/synthetic-v1';
  const stage = path.join(root, stageName);
  const runtime = path.join(root, runtimeName);
  const put = (name, value = '') => {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, value);
  };
  const source = d1?{ schema_version: 2, repositoryRoot: root, runtimeRoot: runtime, profile, servicePort:8001 }
    :{ schema_version: 1, repositoryRoot: root, runtimeRoot: runtime };
  const config = { profile: d1?'classmatter-owned-synthetic-conversation-d1':'class-os-owned-synthetic-v1',
    database: d1?'class_os_synthetic_conversation_local':'class_os_synthetic_local', port: 15432, pg_bin: path.join(root, 'pg') };
  function ready() {
    for (const file of ['backend/.venv/Scripts/python.exe', 'backend/desktop.py', 'apps/desktop/node_modules/electron/index.js',
      stageName+'/main.cjs', stageName+'/ui/index.html', 'pg/postgres.exe', 'pg/pg_ctl.exe',
      ...['runtime-service.cjs','runtime-policy.cjs','model-network.cjs','preload.cjs'].map(name=>stageName+'/'+name)]) put(file);
    put(stageName+'/runtime-source.json', JSON.stringify(source));
    put(stageName+'/ui/desktop-runtime.json', JSON.stringify({ mode: d1?'synthetic-conversation-d1':'synthetic-runtime' }));
    put(runtimeName+'/runtime.json', JSON.stringify(config));
    for (const role of ['root', 'migrator', 'identity', 'runtime']) put(runtimeName+`/${role}.dpapi`, 'synthetic-not-a-credential');
  }
  return { root, stage, runtime, put, source, config, ready };
}
test('empty checkout reports fixed missing steps without modifying or leaking paths', t => {
  const f = fixture(t), before = fs.readdirSync(f.root);
  const result = prerequisites(f.root, 'win32');
  assert.equal(result.prerequisites_present, false);
  assert.deepEqual(result.next_steps, ['backend', 'electron', 'build', 'source', 'database_configuration', 'protected_credentials']);
  assert.deepEqual(fs.readdirSync(f.root), before);
  assert(!JSON.stringify(result).includes(f.root));
});

for(const profile of ['r1','conversation-d1']) test(`missing ${profile} staged dependency rejects before loading Electron`,t=>{
  const f=fixture(t,profile);f.ready();
  f.put('apps/desktop/scripts/runtime-launch.cjs',fs.readFileSync(path.join(__dirname,'../scripts/runtime-launch.cjs')));
  f.put('apps/desktop/runtime-check.cjs',fs.readFileSync(path.join(__dirname,'../runtime-check.cjs')));
  f.put('apps/desktop/model-network.cjs',fs.readFileSync(path.join(__dirname,'../model-network.cjs')));
  for(const name of ['runtime-service.cjs','runtime-policy.cjs','model-network.cjs','preload.cjs']) {
    f.ready();f.put('apps/desktop/node_modules/electron/index.js','throw new Error("should-not-load-electron")');
    const missing=path.join(f.stage,name);fs.unlinkSync(missing);
    const report=prerequisites(f.root,'win32',profile);
    assert.equal(report.prerequisites_present,false,name);
    assert.equal(report.checks.build,false,name);
    assert.deepEqual(report.next_steps,['build']);
    const args=[path.join(f.root,'apps/desktop/scripts/runtime-launch.cjs'),...(profile==='r1'?[]:['--profile',profile])];
    const result=spawnSync(process.execPath,args,{encoding:'utf8',windowsHide:true,timeout:5000});
    // Launcher checks the actual host platform too; on Linux it must still
    // refuse before loading Electron, rather than bypassing the Windows gate.
    assert.equal(result.status,2,result.stderr);
    assert(!result.stderr.includes('should-not-load-electron'));
    assert(!result.stderr.includes(f.root));
    assert.equal(JSON.parse(result.stderr.split(/\r?\n/)[0]).checks.build,false);
  }
});
test('prerequisites never mean service readiness or verified Owner', t => {
  const f = fixture(t); f.ready();
  const result = prerequisites(f.root, 'win32');
  assert.equal(result.prerequisites_present, true);
  assert.deepEqual(result.next_steps, []);
  assert.equal(result.service_ready, false); assert.equal(result.owner_verified, false);
  assert.equal(prerequisites(f.root, 'linux').prerequisites_present, false);
});
test('stale checkout or integration fixture descriptor cannot become user runtime', t => {
  const f = fixture(t); f.ready();
  for (const changes of [{ repositoryRoot: path.dirname(f.root) }, { runtimeRoot: path.join(f.root, 'other-instance') },
    { repositoryRoot: '.' }, { schema_version: 2 }, { extra: 'synthetic-private' }]) {
    f.put('apps/desktop/.build/runtime/runtime-source.json', JSON.stringify({ ...f.source, ...changes }));
    assert.equal(prerequisites(f.root, 'win32').checks.source, false);
  }
});
test('invalid config/oversized build and missing protected file reject without echoing content', t => {
  const f = fixture(t); f.ready();
  for (const changes of [{ port: 80 }, { pg_bin: '.' }, { profile: 'production' }, { database: 'unknown' }, { secret: 'synthetic-private-canary' }]) {
    f.put('.local-runtime/synthetic-v1/runtime.json', JSON.stringify({ ...f.config, ...changes }));
    const result = prerequisites(f.root, 'win32');
    assert.equal(result.checks.database_configuration, false);
    assert(!JSON.stringify(result).includes('synthetic-private-canary'));
  }
  f.ready();
  f.put('apps/desktop/.build/runtime/ui/desktop-runtime.json', ' '.repeat(8193));
  assert.equal(prerequisites(f.root, 'win32').checks.build, false);
  fs.unlinkSync(path.join(f.runtime, 'identity.dpapi'));
  assert.equal(prerequisites(f.root, 'win32').checks.protected_credentials, false);
});

test('actual launcher rejects missing prerequisites and malformed/fixture source without loading Electron', t => {
  const f = fixture(t);
  f.put('apps/desktop/scripts/runtime-launch.cjs', fs.readFileSync(path.join(__dirname, '../scripts/runtime-launch.cjs')));
  f.put('apps/desktop/runtime-check.cjs', fs.readFileSync(path.join(__dirname, '../runtime-check.cjs')));
  f.put('apps/desktop/model-network.cjs', fs.readFileSync(path.join(__dirname, '../model-network.cjs')));
  function reject() {
    const result = spawnSync(process.execPath, [path.join(f.root, 'apps/desktop/scripts/runtime-launch.cjs')], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stderr.split(/\r?\n/)[0]);
    assert.equal(report.prerequisites_present, false);
    assert(!result.stderr.includes(f.root));
    assert(!result.stderr.includes('should-not-load-electron'));
    assert(!result.stderr.includes('SyntaxError'));
    assert.equal(result.stdout, '');
  }
  reject();
  f.ready();
  f.put('apps/desktop/node_modules/electron/index.js', 'throw new Error("should-not-load-electron")');
  f.put('apps/desktop/.build/runtime/runtime-source.json', '{synthetic-private-malformed');
  reject();
  f.put('apps/desktop/.build/runtime/runtime-source.json', JSON.stringify({ ...f.source, runtimeRoot: path.join(f.root, 'fixture-not-user') }));
  reject();
  assert.equal(fs.existsSync(path.join(f.root, '.local-runtime/synthetic-v1/cluster')), false);
});
