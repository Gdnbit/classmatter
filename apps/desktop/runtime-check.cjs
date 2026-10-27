// Read-only operator prerequisites, NOT service readiness or authorization.
const fs = require('node:fs');
const path = require('node:path');

function regular(file) {
  try { return fs.lstatSync(file).isFile(); } catch { return false; }
}
function json(file) {
  try {
    if (!regular(file) || fs.statSync(file).size > 8192) return null;
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch { return null; }
}
function prerequisites(repositoryRoot, platform = process.platform, profile = 'r1') {
  if (!['r1', 'conversation-d1'].includes(profile)) throw new Error('Unknown synthetic runtime profile');
  const d1=profile==='conversation-d1';
  const root = path.resolve(repositoryRoot), desktop = path.join(root, 'apps/desktop');
  const stage = path.join(desktop, d1?'.build/runtime-d1':'.build/runtime');
  const runtime = path.join(root, d1?'.local-runtime/synthetic-conversation-d1':'.local-runtime/synthetic-v1');
  const source = json(path.join(stage, 'runtime-source.json'));
  const marker = json(path.join(stage, 'ui/desktop-runtime.json'));
  const config = json(path.join(runtime, 'runtime.json'));
  const checks = {
    windows: platform === 'win32',
    backend: regular(path.join(root, 'backend/.venv/Scripts/python.exe')) && regular(path.join(root, 'backend/desktop.py')),
    electron: regular(path.join(desktop, 'node_modules/electron/index.js')),
    build: marker?.mode === (d1?'synthetic-conversation-d1':'synthetic-runtime') && regular(path.join(stage, 'ui/index.html')) && regular(path.join(stage, 'main.cjs')),
    source: !!source && source.schema_version === (d1?2:1) && Object.keys(source).sort().join(',') === (d1?'profile,repositoryRoot,runtimeRoot,schema_version,servicePort':'repositoryRoot,runtimeRoot,schema_version')
      && (!d1 || (source.profile==='conversation-d1' && source.servicePort===8001))
      && typeof source.repositoryRoot === 'string' && path.isAbsolute(source.repositoryRoot) && path.resolve(source.repositoryRoot) === root
      && typeof source.runtimeRoot === 'string' && path.isAbsolute(source.runtimeRoot) && path.resolve(source.runtimeRoot) === runtime,
    database_configuration: !!config && Object.keys(config).sort().join(',') === 'database,pg_bin,port,profile'
      && config.profile === (d1?'classmatter-owned-synthetic-conversation-d1':'class-os-owned-synthetic-v1')
      && config.database === (d1?'class_os_synthetic_conversation_local':'class_os_synthetic_local')
      && Number.isInteger(config.port) && config.port >= 1024 && config.port <= 65535
      && typeof config.pg_bin === 'string' && path.isAbsolute(config.pg_bin)
      && regular(path.join(config.pg_bin, 'postgres.exe')) && regular(path.join(config.pg_bin, 'pg_ctl.exe')),
    protected_credentials: ['root', 'migrator', 'identity', 'runtime'].every(role => regular(path.join(runtime, role + '.dpapi'))),
  };
  return {
    schema_version: d1?'classmatter.desktop-prerequisites.v2':'classmatter.desktop-prerequisites.v1', mode: d1?'synthetic-conversation-d1':'synthetic-runtime',
    prerequisites_present: Object.values(checks).every(Boolean), checks,
    next_steps: Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name),
    service_ready: false, owner_verified: false,
  };
}
if (require.main === module) {
  const args=process.argv.slice(2);
  if(args.length && (args.length!==2 || args[0]!=='--profile' || args[1]!=='conversation-d1'))throw new Error('Unknown profile arguments');
  const result = prerequisites(path.resolve(__dirname, '../..'),process.platform,args.length?'conversation-d1':'r1');
  console.log(JSON.stringify(result));
  process.exitCode = result.prerequisites_present ? 0 : 2;
}
module.exports = { prerequisites };
