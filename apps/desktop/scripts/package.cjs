const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
async function main() {
  if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('This delivery targets Windows x64 only.');
  const result = spawnSync(process.execPath, [path.join(__dirname, 'build.cjs')], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error('Demo build failed.');
  const { packager } = await import('@electron/packager');
  const desktop = path.resolve(__dirname, '..');
  const output = await packager({
    dir: path.join(desktop, '.build/app'), out: path.join(desktop, 'out'),
    name: 'ClassMatter-Demo', executableName: 'ClassMatter-Demo',
    platform: 'win32', arch: 'x64', electronVersion: require('electron/package.json').version,
    download: { checksums: require('electron/checksums.json') },
    asar: true, overwrite: true, prune: false,
    icon: path.join(desktop, '.build/app/app.ico'),
    appCopyright: 'Copyright 2026 Gdnbit',
    win32metadata: { CompanyName: 'Gdnbit', ProductName: '班事有谱 ClassMatter Demo', FileDescription: 'ClassMatter synthetic desktop Demo' },
  });
  for (const directory of output) {
    // Electron itself includes LICENSE and LICENSES.chromium.html; retain them.
    const executable = path.join(directory, 'ClassMatter-Demo.exe');
    const sha256 = crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex');
    fs.writeFileSync(path.join(directory, 'LOCAL-DEMO.txt'), 'ClassMatter synthetic Demo. Keep this entire directory together. No Node, browser, API or database required. Unsigned local build; not a production release.\n');
    fs.writeFileSync(path.join(directory, 'executable.sha256'), `${sha256}  ClassMatter-Demo.exe\n`);
    console.log(`Standalone app: ${executable}`);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
