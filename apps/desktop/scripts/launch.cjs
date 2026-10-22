const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const stage = path.resolve(__dirname, '../.build/app');
if (!fs.existsSync(path.join(stage, 'ui/desktop-demo.json'))) {
  console.error('Run pnpm build in apps/desktop first.');
  process.exit(1);
}
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const child = spawn(require('electron'), [stage], { stdio: 'inherit', env });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code || 0; });
