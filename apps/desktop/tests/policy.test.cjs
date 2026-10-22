const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { ORIGIN, CSP, localURL, resolveResource, serveResource } = require('../policy.cjs');

test('only the exact app origin is trusted', () => {
  for (const url of ['https://example.com', 'http://127.0.0.1:8443', 'file:///etc/passwd', 'classmatter://evil/', 'classmatter://app:80/', 'classmatter://user@app/']) assert.equal(localURL(url), false, url);
  assert.equal(localURL(`${ORIGIN}/students?view=seat`), true);
});
test('existing deep links resolve to SPA, assets have explicit MIME', () => {
  for (const route of ['/', '/students', '/students/s-001?tab=timeline', '/work', '/data/documents/parents-001', '/settings/user', '/spaces/midterm']) assert.equal(resolveResource(ORIGIN + route).relative, 'index.html');
  assert.equal(resolveResource(`${ORIGIN}/assets/index-abc.js`).type, 'text/javascript; charset=utf-8');
});
test('reject APIs, mutations, traversal, maps and unknown files', () => {
  for (const route of ['/api/students', '/assets/%2e%2e%2fpackage.json', '/assets/%5csecret.js', '/assets/a.js%00', '/assets/a.js.map', '/package.json', '/missing', '/assets/%zz']) assert.equal(resolveResource(ORIGIN + route), null, route);
  for (const method of ['POST', 'PUT', 'DELETE', 'PATCH']) assert.equal(resolveResource(`${ORIGIN}/students`, method), null);
});
test('CSP denies network, frames, forms, workers and arbitrary scripts', () => {
  for (const directive of ["connect-src 'none'", "script-src 'self'", "frame-src 'none'", "form-action 'none'", "worker-src 'none'"]) assert.ok(CSP.includes(directive));
  assert.ok(!CSP.includes('unsafe-eval'));
});
test('resource serving is confined, typed, missing-safe and supports HEAD', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'classmatter-policy-'));
  try {
    await fs.writeFile(path.join(root, 'index.html'), '<h1>synthetic</h1>');
    const response = await serveResource(root, { url: `${ORIGIN}/students/s-1`, method: 'GET' });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Content-Security-Policy'), CSP);
    assert.match(await response.text(), /synthetic/);
    assert.equal(await (await serveResource(root, { url: ORIGIN + '/', method: 'HEAD' })).text(), '');
    assert.equal((await serveResource(root, { url: `${ORIGIN}/assets/missing.js`, method: 'GET' })).status, 404);
    assert.equal((await serveResource(root, { url: `${ORIGIN}/api/write`, method: 'POST' })).status, 404);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('realpath confinement rejects assets redirected outside UI by a junction', async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'classmatter-junction-'));
  try {
    const root = path.join(temporary, 'ui');
    const outside = path.join(temporary, 'outside');
    await fs.mkdir(root);
    await fs.mkdir(outside);
    await fs.writeFile(path.join(outside, 'index-a.js'), 'not a UI asset');
    await fs.symlink(outside, path.join(root, 'assets'), process.platform === 'win32' ? 'junction' : 'dir');
    const response = await serveResource(root, { url: `${ORIGIN}/assets/index-a.js`, method: 'GET' });
    assert.equal(response.status, 403);
    assert.equal(await response.text(), '');
  } finally { await fs.rm(temporary, { recursive: true, force: true }); }
});
