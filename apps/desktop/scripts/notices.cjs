const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

// Copy exact installed notices for the entire Web production dependency closure,
// not build/test dependencies (which are not part of the distributed application).
function collectNotices(web, stage) {
  const entries = [];
  const visited = new Set();
  function visit(name, parent) {
    const resolver = createRequire(path.join(parent, 'package.json'));
    let location = path.dirname(resolver.resolve(name));
    while (!fs.existsSync(path.join(location, 'package.json'))) {
      const next = path.dirname(location);
      if (next === location) throw new Error(`Package metadata missing: ${name}`);
      location = next;
    }
    const pkg = JSON.parse(fs.readFileSync(path.join(location, 'package.json'), 'utf8'));
    const key = `${pkg.name}@${pkg.version}`;
    if (visited.has(key)) return;
    visited.add(key);
    const notices = fs.readdirSync(location).filter(file => /^(?:licen[cs]e|notice|copying)(?:[.-]|$)/i.test(file) && fs.statSync(path.join(location, file)).isFile());
    if (!notices.length || !pkg.license) throw new Error(`License review required: ${key}`);
    const directory = path.join(stage, 'third_party', key.replace(/[^A-Za-z0-9_.@-]/g, '_'));
    fs.mkdirSync(directory, { recursive: true });
    for (const file of notices) fs.copyFileSync(path.join(location, file), path.join(directory, file));
    entries.push({ name: pkg.name, version: pkg.version, license: pkg.license, notices: notices.map(file => path.relative(stage, path.join(directory, file)).split(path.sep).join('/')) });
    for (const dependency of Object.keys(pkg.dependencies || {})) visit(dependency, location);
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(web, 'package.json'), 'utf8'));
  for (const name of Object.keys(pkg.dependencies)) visit(name, web);
  fs.writeFileSync(path.join(stage, 'third_party', 'web-runtime.json'), JSON.stringify({ scope: 'Installed Web production closure; Electron runtime notices accompany executable separately', packages: entries.sort((a, b) => a.name.localeCompare(b.name)) }, null, 2) + '\n');
}
module.exports = { collectNotices };
