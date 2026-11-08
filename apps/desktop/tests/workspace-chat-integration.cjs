// Owned disposable D3 fixture only; never connects to the user's runtime.
const { _electron: electron } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const stage = path.resolve(__dirname, '../.build/runtime-d3');
const root = process.env.CLASSMATTER_TEST_RUNTIME_ROOT, port = Number(process.env.CLASSMATTER_TEST_SERVICE_PORT);
if (!root || !path.isAbsolute(root) || !Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Owned fixture required');
const file = path.join(stage, 'runtime-source.json'), original = fs.readFileSync(file);
const source = JSON.parse(original); source.runtimeRoot = root; source.servicePort = port;
const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
let app;
async function launch() {
  app = await electron.launch({ executablePath: require('electron'), args: [stage, '--classmatter-development-no-password'], env });
  // Private workspace connection (15s) precedes the API's bounded startup (30s).
  const page = await app.firstWindow({ timeout: 60000 });
  await page.getByLabel('输入消息').waitFor();
  assert.equal(await page.getByLabel('密码', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '退出登录', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '进入本机开发', exact: true }).count(), 0);
  assert.equal(await page.evaluate(() => window.classMatterDesktop.localOnly), true);
  return page;
}
(async () => { try {
  fs.writeFileSync(file, JSON.stringify(source));
  let page = await launch();
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
  await app.close(); app = null;
  page = await launch();
  await page.getByRole('button', { name: '合成桌面重启持久聊天', exact: true }).click();
  await page.getByRole('region', { name: '已保存的对话' }).getByText('合成桌面重启持久聊天', { exact: true }).waitFor();
  await page.getByRole('region', { name: '已保存的对话' }).locator('article.assistant').waitFor();
  assert.equal(new URL(page.url()).pathname, chatPath);
  await page.reload();
  await page.getByLabel('输入消息').waitFor();
  assert.equal(await page.getByRole('button', { name: '进入本机开发', exact: true }).count(), 0);
  console.log('PASS owned D3 Electron: passwordless original shell; persisted ordinary chat survives full API/application restart');
} finally {
  if (app) await app.close();
  fs.writeFileSync(file, original);
} })().catch(error => { console.error(error); process.exitCode = 1; });
