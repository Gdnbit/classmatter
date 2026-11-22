// Owned disposable D3 fixture only; never connects to the user's runtime.
const { _electron: electron } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const profile = process.env.CLASSMATTER_TEST_PROFILE || 'workspace-chat-d3';
if (!['workspace-chat-d3','classroom-work-d4'].includes(profile)) throw new Error('Owned fixture profile required');
const stage = path.resolve(__dirname, profile === 'classroom-work-d4' ? '../.build/runtime-d4' : '../.build/runtime-d3');
const root = process.env.CLASSMATTER_TEST_RUNTIME_ROOT, port = Number(process.env.CLASSMATTER_TEST_SERVICE_PORT);
if (!root || !path.isAbsolute(root) || !Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Owned fixture required');
const file = path.join(stage, 'runtime-source.json'), original = fs.readFileSync(file);
const source = JSON.parse(original); source.runtimeRoot = root; source.servicePort = port;
const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
let app, step = 'first startup';
const failures = [], errors = [], legacyReads = [];
// Give the fixture time to report and release only the process it launched
// before the outer Python deadline can terminate the Node runner.
const watchdog = setTimeout(() => {
  console.error('Native regression reached its deadline during: ' + step);
  app?.process().kill();
  fs.writeFileSync(file, original);
  process.exit(1);
}, profile === 'classroom-work-d4' ? 250000 : 150000);
async function expectLeavePrompt(count) {
  const observed = await app.evaluate(async ({ app }, expected) => {
    const until = Date.now() + 5000;
    while (app.__classmatterDraftCheck.prompts.length < expected && Date.now() < until)
      await new Promise(resolve => setTimeout(resolve, 25));
    return app.__classmatterDraftCheck.prompts.length;
  }, count);
  assert.equal(observed, count, 'Exactly one native confirmation per attempted leave');
}
async function launch() {
  const previousLegacyReads = legacyReads.length;
  app = await electron.launch({ executablePath: require('electron'), args: [stage, '--classmatter-development-no-password'], env });
  app.context().on('response', response => {
    if (response.status() >= 500) failures.push({status: response.status(), path: new URL(response.url()).pathname});
  });
  app.context().on('request', request => {
    if (/\/conversation-d1\/classes\/[^/]+\/terms\/[^/]+\/conversations$/.test(new URL(request.url()).pathname)) legacyReads.push(request.url());
  });
  app.on('window', page => page.on('pageerror', error => errors.push(error.name)));
  // Private workspace connection (15s) precedes the API's bounded startup (30s).
  const page = await app.firstWindow({ timeout: 60000 });
  page.setDefaultTimeout(30000);
  page.setDefaultNavigationTimeout(30000);
  await page.getByLabel('输入消息').waitFor();
  await page.getByRole('button', { name: '新对话', exact: true }).waitFor();
  assert.deepEqual(failures, [], 'Desktop startup requests must succeed');
  assert.equal(legacyReads.length, previousLegacyReads, 'Workspace startup does not read the optional legacy archive');
  assert.equal(await page.getByLabel('密码', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '退出登录', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '进入本机开发', exact: true }).count(), 0);
  assert.equal(await page.evaluate(() => window.classMatterDesktop.localOnly), true);
  return page;
}
(async () => { try {
  fs.writeFileSync(file, JSON.stringify(source));
  let page = await launch();
  console.log('PASS first native startup');
  step = 'legacy and ordinary chat';
  await page.locator('summary', { hasText: '班级旧对话' }).click();
  await page.getByRole('button', { name: '合成原对话', exact: true }).click();
  await page.getByRole('region', { name: '已保存的对话' }).getByText('合成升级前消息', { exact: true }).waitFor();
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await page.waitForURL(url => url.pathname === '/');
  await page.getByLabel('输入消息').waitFor();
  await page.getByLabel('输入消息').fill('合成桌面重启持久聊天');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const history = page.getByRole('region', { name: '已保存的对话' });
  await history.locator('article.assistant').waitFor();
  const answer = history.getByRole('article', { name: '助手回复', exact: true }).last();
  const answerText = await answer.locator('p').first().textContent();
  await answer.getByRole('button', { name: '复制回答', exact: true }).click();
  await answer.getByText('已复制回答', { exact: true }).waitFor({ timeout: 3000 });
  // Windows clipboard line endings may be CRLF; compare the original text,
  // never the rendered innerText or action labels, without printing clipboard data.
  assert.equal(await app.evaluate(async ({ clipboard }, expected) => (await clipboard.readText()).replace(/\r\n/g,'\n') === expected.replace(/\r\n/g,'\n'), answerText), true);
  const chatPath = new URL(page.url()).pathname;
  assert.match(chatPath, /^\/chats\/[a-f0-9-]{36}$/);
  console.log('PASS native chat and clipboard');
  step = 'unsent draft survives cancelled reload and close';
  // Stub only the owned fixture's native dialog response. The real window,
  // renderer unload event, service and database stay on the original path.
  await app.evaluate(({ app, dialog }) => {
    app.__classmatterDraftCheck = { leave: false, prompts: [] };
    dialog.showMessageBoxSync = (_window, options) => {
      app.__classmatterDraftCheck.prompts.push(options);
      return app.__classmatterDraftCheck.leave ? 1 : 0;
    };
  });
  const draft = '合成未发送草稿';
  await page.getByLabel('输入消息').fill(draft);
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await page.waitForURL(url => url.pathname === '/');
  assert.equal(await page.getByLabel('输入消息').inputValue(), '');
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.reload());
  await expectLeavePrompt(1);
  await page.getByRole('button', { name: '合成桌面重启持久聊天', exact: true }).click();
  assert.equal(await page.getByLabel('输入消息').inputValue(), draft, 'Hidden conversation draft survives cancelled reload');
  await app.evaluate(({ app }) => app.quit());
  await expectLeavePrompt(2);
  assert.equal((await page.request.get(new URL('/health/ready', page.url()).href)).status(), 200,
    'Cancelling application quit must keep its service alive');
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
  await expectLeavePrompt(3);
  assert.equal(await page.getByLabel('输入消息').inputValue(), draft);
  await app.evaluate(({ app }) => { app.__classmatterDraftCheck.leave = true; });
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.reload());
  await expectLeavePrompt(4);
  await page.getByLabel('输入消息').waitFor();
  assert.equal(await page.getByLabel('输入消息').inputValue(), '');
  await history.getByText('合成桌面重启持久聊天', { exact: true }).waitFor();
  const prompts = await app.evaluate(({ app }) => app.__classmatterDraftCheck.prompts);
  assert.ok(prompts.every(item => item.defaultId === 0 && item.cancelId === 0
    && item.buttons[0] === '继续编辑' && item.buttons[1] === '放弃并离开'));
  // Reloading/closing without a local draft must not add a routine prompt.
  await page.reload(); await page.getByLabel('输入消息').waitFor();
  assert.equal(await app.evaluate(({ app }) => app.__classmatterDraftCheck.prompts.length), 4);
  console.log('PASS native draft lifecycle');
  step = 'close first native window';
  await app.close(); app = null;
  step = 'second native startup';
  page = await launch();
  step = 'restore persisted chat after restart';
  await page.getByRole('button', { name: '合成桌面重启持久聊天', exact: true }).click();
  await page.getByRole('region', { name: '已保存的对话' }).getByText('合成桌面重启持久聊天', { exact: true }).waitFor();
  await page.getByRole('region', { name: '已保存的对话' }).locator('article.assistant').waitFor();
  assert.equal(new URL(page.url()).pathname, chatPath);
  await page.reload();
  await page.getByLabel('输入消息').waitFor();
  assert.equal(await page.getByRole('button', { name: '进入本机开发', exact: true }).count(), 0);
  if (profile === 'classroom-work-d4') {
    step = 'grades and seating after restart';
    await page.getByLabel('更多功能', {exact:true}).click();
    await page.getByRole('button',{name:'成绩',exact:true}).click();
    await page.getByRole('region',{name:'成绩表格',exact:true}).getByRole('row').filter({hasText:'合成原学生'}).filter({hasText:'88.50'}).waitFor();
    await page.getByLabel('更多功能', {exact:true}).click();
    await page.getByRole('button',{name:'座位',exact:true}).click();
    await page.getByRole('button',{name:'1排2座 合成原学生',exact:true}).waitFor();
    console.log('PASS owned D4 Electron: grades/seating share the preserved world after full native/API restart');
  }
  console.log('PASS owned D3 Electron: passwordless original shell; persisted ordinary chat survives full API/application restart');
  assert.deepEqual(failures, [], 'Original desktop requests must not hide server failures');
  assert.deepEqual(errors, []);
} catch (error) {
  console.error('Native regression failed during: ' + step, error);
  throw error;
} finally {
  if (app) await app.close();
  fs.writeFileSync(file, original);
  clearTimeout(watchdog);
} })().catch(() => { process.exitCode = 1; });
