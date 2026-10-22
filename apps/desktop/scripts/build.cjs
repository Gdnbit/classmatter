const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { createIcon } = require('./icon.cjs');
const { collectNotices } = require('./notices.cjs');
const desktop = path.resolve(__dirname, '..');
const web = path.resolve(desktop, '../web');
const stage = path.join(desktop, '.build/app');

function run(args) {
  const result = spawnSync(process.execPath, args, { cwd: web, stdio: 'inherit', env: { ...process.env, VITE_CLASS_OS_DEMO: 'true', FIGMA_PUBLIC_URL: '' } });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
for (const contract of ['identity', 'model-configuration', 'agent-conversation', 'command-receipts']) {
  run([path.join(web, 'scripts', `generate-${contract}.mjs`), '--check']);
}
// Vite empties only this explicitly owned generated UI directory.
run([path.join(web, 'node_modules/vite/bin/vite.js'), 'build', '--outDir', path.join(stage, 'ui'), '--emptyOutDir']);
fs.mkdirSync(stage, { recursive: true });
for (const file of ['main.cjs', 'policy.cjs']) fs.copyFileSync(path.join(desktop, file), path.join(stage, file));
const { name, version, description, author, license, main } = require('../package.json');
fs.writeFileSync(path.join(stage, 'package.json'), JSON.stringify({ name: 'classmatter-desktop-demo', version, description, author, license, main }, null, 2) + '\n');
fs.writeFileSync(path.join(stage, 'ui/desktop-demo.json'), JSON.stringify({ mode: 'synthetic-demo', version }) + '\n');
for (const file of ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']) fs.copyFileSync(path.resolve(desktop, '../..', file), path.join(stage, file));
createIcon(stage);
collectNotices(web, stage);
console.log('Built isolated synthetic Demo assets. No API/database/server is started.');
