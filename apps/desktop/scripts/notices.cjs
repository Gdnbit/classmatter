const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { createHash } = require('node:crypto');

// Copy exact installed notices for the entire Web production dependency closure,
// not build/test dependencies (which are not part of the distributed application).
function collectNotices(web, stage, thirdParty = path.resolve(__dirname, '../../../third_party')) {
  const entries = [];
  const visited = new Set();
  function visit(name, parent) {
    const resolver = createRequire(path.join(parent, 'package.json'));
    // Type-only packages have no JS entry; some JS entry subdirectories also
    // contain package.json files that are not the package's license metadata.
    const metadata = (resolver.resolve.paths(name) || []).map(base => path.join(base, name, 'package.json')).find(file => fs.existsSync(file));
    if (!metadata) throw new Error(`Package metadata missing: ${name}`);
    const location = fs.realpathSync(path.dirname(metadata));
    const pkg = JSON.parse(fs.readFileSync(path.join(location, 'package.json'), 'utf8'));
    const key = `${pkg.name}@${pkg.version}`;
    if (visited.has(key)) return;
    visited.add(key);
    const notices = fs.readdirSync(location).filter(file => /^(?:licen[cs]e|notice|copying)(?:[.-]|$)/i.test(file) && fs.statSync(path.join(location, file)).isFile());
    if (!pkg.license) throw new Error(`License review required: ${key}`);
    let sources = notices.map(file => ({ file, source: path.join(location, file) }));
    if (!sources.length) {
      const review = JSON.parse(fs.readFileSync(path.join(thirdParty, 'supplemental-license-review.json'), 'utf8'));
      const matches = review.upstream_release_notices.filter(item => item.name === pkg.name && item.version === pkg.version);
      if (!matches.length) throw new Error(`License review required: ${key}`);
      const root = fs.realpathSync(path.join(thirdParty, 'licenses/upstream'));
      sources = matches.map(item => {
        const source = fs.realpathSync(path.resolve(thirdParty, item.path));
        const relative = path.relative(root, source);
        if (!relative || relative.startsWith('..') || path.isAbsolute(relative)
            || !/^[0-9a-f]{64}$/.test(item.sha256)
            || createHash('sha256').update(fs.readFileSync(source)).digest('hex') !== item.sha256) {
          throw new Error(`Reviewed notice mismatch: ${key}`);
        }
        return { file: path.basename(source), source };
      });
      if (new Set(sources.map(item => item.file.toLowerCase())).size !== sources.length) throw new Error(`Notice filename conflict: ${key}`);
    }
    const directory = path.join(stage, 'third_party', key.replace(/[^A-Za-z0-9_.@-]/g, '_'));
    fs.mkdirSync(directory, { recursive: true });
    for (const item of sources) fs.copyFileSync(item.source, path.join(directory, item.file));
    entries.push({ name: pkg.name, version: pkg.version, license: pkg.license, notices: sources.map(item => path.relative(stage, path.join(directory, item.file)).split(path.sep).join('/')) });
    for (const dependency of Object.keys(pkg.dependencies || {})) visit(dependency, location);
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(web, 'package.json'), 'utf8'));
  for (const name of Object.keys(pkg.dependencies)) visit(name, web);
  fs.writeFileSync(path.join(stage, 'third_party', 'web-runtime.json'), JSON.stringify({ scope: 'Installed Web production closure; Electron runtime notices accompany executable separately', packages: entries.sort((a, b) => a.name.localeCompare(b.name)) }, null, 2) + '\n');
}
module.exports = { collectNotices };
