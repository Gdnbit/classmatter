// Test-only fixed save destinations; the product retains the native Save dialog.
const { _electron: electron } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const stage = path.resolve(__dirname, '../.build/runtime-d4');
const root = process.env.CLASSMATTER_TEST_RUNTIME_ROOT, destination = process.env.CLASSMATTER_TEST_DOWNLOAD_ROOT;
const port = Number(process.env.CLASSMATTER_TEST_SERVICE_PORT);
if (!path.isAbsolute(root || '') || !path.isAbsolute(destination || '') || !Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Owned synthetic fixture required');
const file = path.join(stage, 'runtime-source.json'), original = fs.readFileSync(file);
const source = JSON.parse(original); source.runtimeRoot = root; source.servicePort = port;
const fixtureSource = JSON.stringify(source);
const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
let app;
(async () => { try {
  fs.writeFileSync(path.join(destination, 'runtime-source-before.json'), original, { flag: 'wx' });
  fs.writeFileSync(file, fixtureSource);
  app = await electron.launch({ executablePath: require('electron'), args: [stage, '--classmatter-development-no-password'], env });
  const page = await app.firstWindow({ timeout: 60000 });
  await page.getByLabel('输入消息').waitFor();
  console.log('phase: ready');
  await app.evaluate(({ BrowserWindow }, files) => {
    globalThis.officeDownloads = [];
    BrowserWindow.getAllWindows()[0].webContents.session.on('will-download', (_event, item) => {
      const extension = item.getFilename().endsWith('.docx') ? 'docx' : item.getFilename().endsWith('.pptx') ? 'pptx' : null;
      if (!extension) throw new Error('Unexpected fixture download');
      item.setSavePath(files[extension]);
      item.once('done', (_event, state) => globalThis.officeDownloads.push({ extension, state }));
    });
  }, { docx: path.join(destination, 'lesson.docx'), pptx: path.join(destination, 'lesson.pptx') });
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByRole('button', { name: /合成桌面教案/ }).first().click();
  const current = page.url();
  for (const [name, extension] of [['导出 Word', 'docx'], ['导出 PPT', 'pptx']]) {
    console.log('phase: download-' + extension);
    await page.getByRole('button', { name, exact: true }).click();
    const deadline = Date.now() + 30000;
    while (!(await app.evaluate(() => globalThis.officeDownloads)).some(item => item.extension === extension)) {
      if (Date.now() >= deadline) throw new Error('Native Office download did not finish');
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const done = (await app.evaluate(() => globalThis.officeDownloads)).find(item => item.extension === extension);
    assert.equal(done.state, 'completed');
    assert(fs.statSync(path.join(destination, 'lesson.' + extension)).size > 0);
    assert.equal(page.url(), current);
  }
  assert.equal((await app.evaluate(() => globalThis.officeDownloads)).length, 2);
} finally {
  if (app) {
    const process = app.process();
    let timer;
    try { await Promise.race([app.close(), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Fixture close timeout')), 10000); })]); }
    catch { if (process && process.exitCode === null) process.kill(); }
    finally { clearTimeout(timer); }
  }
  if (fs.readFileSync(file, 'utf8') !== fixtureSource) throw new Error('Concurrent runtime descriptor change; refusing overwrite');
  fs.writeFileSync(file, original);
} })().catch(error => { console.error(error); process.exitCode = 1; });
